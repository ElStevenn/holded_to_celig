import asyncio
import json
import pytz
from datetime import datetime
from collections import defaultdict
import traceback

from services.cegid_service import CegidAPI
from services.holded_service import HoldedAPI
from config.settings import HOLDED_ACCOUNTS, increment_offset, get_offset, set_offset

tz = pytz.timezone('Europe/Madrid')

class AsyncService:

    def __init__(self):
        self.tz_mad = pytz.timezone("Europe/Madrid")
    
    async def fetch_holded_accounts(self):
        cegid_api = CegidAPI()
        tasks = []
        await cegid_api.renew_token_api_contabilidad()
        # print("Holded account: ", HOLDED_ACCOUNTS)

        for acc in reversed(HOLDED_ACCOUNTS):
            h_api = HoldedAPI(acc["api_key"])
            tasks.append(self.process_account_invoices(h_api, cegid_api, acc["subcuenta_id"], acc["offset"]))
            break
        await asyncio.gather(*tasks)


    async def process_account_invoices(self, holded_api: "HoldedAPI", cegid_api:   "CegidAPI", cuenta_cliente: str, offset: int = 0):
        invoices =  list(reversed(await holded_api.list_invoices()))[offset:] # Aplico offset
        # invoices.sort(key=lambda x: x["date"])

        for inv_header in invoices[offset:]:
            # detalles Holded 
            inv   = await holded_api.invoice_details(inv_header["id"])
            pdf   = await holded_api.get_invoice_document_pdf(inv["id"])
            cli   = await holded_api.get_client(inv["contact"])

            # asegúrate de Serie + Cliente (Ya no se usa)
            # await self.ensure_serie(inv, cegid_api)
            # cuenta_cli = await self.ensure_cliente(cli, cegid_api)

            # transformar & subir
            factura = await self.transform_invoice_holded_to_cegid(inv, cli, cuenta_cliente)
            print("die factura -> ", factura)
            print(f"La factura {factura["Documento"]} sería creada ahora")
            # await cegid_api.crear_factura(factura)

            doc_meta = {
                "Ejercicio": factura["Ejercicio"],
                "Serie":     factura["Serie"],
                "Documento": factura["Documento"],
                "NombreArchivo": f"{factura['Serie']}-{factura['Documento']}.pdf",
                "Archivo": pdf
            }
            print(f"*El archivo de la factura sería creada ahora*")
            # await cegid_api.add_documento_factura(doc_meta)

            increment_offset(holded_api.api_key)
            print(f"[OK] Subida factura {factura['NumeroFactura']}")

    # UTILITIES
    async def ensure_serie(self, holded_inv: dict, cegid: "CegidAPI"):
        serie = holded_inv["docNumber"].split("-")[0]
        series = await cegid.get_series() or []
        if not any(s["Codigo"] == serie for s in series):
            await cegid.add_serie(codigo=serie, descripcion=f"Serie auto {serie}")


    async def ensure_cliente(self, holded_client: dict, cegid: "CegidAPI") -> str:
        """
        Devuelve la subcuenta creada/ya existente para el contacto Holded.
        Para el ejemplo simple usamos el contactId como cuenta 430xxxxx.
        """
        subcuenta = f"43{holded_client['id'][-6:]}"     # 43 + últimos 6 dígitos
        # Aquí llamarías a get_clientes() y create_cliente() si no existe…
        # Ejemplo resumido:
        # clientes = await cegid.get_clientes()
        # if not any(c["Codigo"] == subcuenta for c in clientes):
        #     await cegid.create_cliente(..., codigo=subcuenta, ...)
        return subcuenta

    async def transform_invoice_holded_to_cegid(
        self,
        holded_invoice: dict,
        holded_client: dict,
        cuenta_cliente: str
    ):
        # --- 1) Identificación
        doc_number = holded_invoice["docNumber"]
        try:
            documento = int(doc_number.split("-")[-1])
        except ValueError:
            documento = 0

        # --- 2) Fechas
        issue_ts = holded_invoice.get("date") or 0                       # epoch-seconds
        dt_fact = datetime.fromtimestamp(issue_ts, self.tz_mad)
        fecha_int = int(dt_fact.strftime("%Y%m%d"))
        ejercicio = str(dt_fact.year)

        due_ts = holded_invoice.get("dueDate") or issue_ts
        fecha_venc = int(
            datetime.fromtimestamp(due_ts, self.tz_mad).strftime("%Y%m%d")
        )

        # --- 3) Bases e IVA
        from collections import defaultdict
        vat_groups = defaultdict(float)
        for p in holded_invoice["products"]:
            vat_groups[p["tax"]] += p["price"] * p["units"]

        factura = {
            "Ejercicio": ejercicio,
            "Serie": "2",
            "Documento": documento,
            "TipoAsiento": 2,
            "TipoVencimiento": 1,
            "Fecha": fecha_int,
            "FechaFactura": fecha_int,
            "CuentaCliente": cuenta_cliente,
            "NumeroFactura": doc_number,
            "Descripcion": holded_invoice.get("desc", ""),
            "TipoFactura": "OpInteriores",
            "NombreCliente": holded_invoice.get("contactName", ""),
            "ClaveRegimenIva1": "01"
        }

        if holded_client.get("vatnumber"):
            factura["CifCliente"] = holded_client["vatnumber"]

        base_total = iva_total = 0.0
        for idx, rate in enumerate(sorted(vat_groups), 1):
            base = round(vat_groups[rate], 2)
            cuota = round(base * rate / 100, 2)
            factura[f"BaseImponible{idx}"] = base
            factura[f"PorcentajeIVA{idx}"] = rate
            factura[f"CuotaIVA{idx}"] = cuota
            base_total += base
            iva_total += cuota

        factura["TotalFactura"] = round(base_total + iva_total, 2)

        # --- 4) Vencimiento único
        factura["Vencimientos"] = [{
            "Ejercicio": ejercicio,
            "Serie": "2",
            "Documento": documento,
            "NumeroVencimiento": 1,
            "FechaFactura": fecha_int,
            "CuentaCliente": cuenta_cliente,
            "NumeroFactura": doc_number,
            "FechaVencimiento": fecha_venc,
            "Importe": factura["TotalFactura"],
            "CodigoTipoVencimiento": 1
        }]

        return factura

    
    async def push_invoices_to_cegid(self, transformed_invoices, cegid_api: "CegidAPI"):
        for inv in transformed_invoices:
            try:
                result = await cegid_api.push_invoice(inv)
                print(f"[DEBUG] Invoice pushed, result: {result}")
            except Exception as e:
                print(f"[ERROR] Pushing invoice to Cegid failed: {e}")


async def main_test():
    async_service = AsyncService()
    '''
    # holded_invoice = {
        "id": "683178936d01d4ea2b081479",
        "contact": "683178566dcd08eda30f50b7",
        "contactName": "BUILDINGSAS SL (Imperfect Brunch)",
        "desc": "",
        "date": 1748037600,
        "dueDate": 1748124000,
        "multipledueDate": {
        "date": 1748124000,
        "amount": 279.55
        },
        "forecastDate": None,
        "notes": "",
        "tags": [],
        "products": [
        {
            "name": "LATA 250",
            "desc": "AOVE Ecológico Olivares de Altomira Lata 250ml",
            "price": 5.6,
            "units": 48,
            "projectid": None,
            "tax": 4,
            "taxes": [
            "s_iva_4"
            ],
            "tags": [],
            "discount": 0,
            "retention": 0,
            "weight": 0,
            "costPrice": 0,
            "sku": "L250224057",
            "account": "64227fd364fcfe702b0945ba",
            "productId": "6427013e668d8620630ff5e8",
            "variantId": "6427013e668d8620630ff5ea"
        }
        ],
        "tax": 10.75,
        "subtotal": 268.8,
        "discount": 0,
        "total": 279.55,
        "language": "es",
        "status": 0,
        "customFields": [],
        "docNumber": "A-2025-077",
        "currency": "eur",
        "currencyChange": 1,
        "paymentsTotal": 0,
        "paymentsPending": 279.55,
        "paymentsRefunds": 0,
        "shipping": "hidden"
    }
    # holded_client = {
        "id": "683178566dcd08eda30f50b7",
        "customId": None,
        "name": "BUILDINGSAS SL (Imperfect Brunch)",
        "code": "B88367925",
        "vatnumber": "",
        "tradeName": None,
        "email": None,
        "mobile": None,
        "phone": "627 63 94 03",
        "type": "client",
        "iban": "",
        "swift": "",
        "groupId": "",
        "clientRecord": {
            "num": 4300002015,
            "name": "BUILDINGSAS SL (Imperfect Brunch)"
        },
        "supplierRecord": 0,
        "billAddress": {
            "address": "C. Mayor 16",
            "city": "Guadalajara",
            "postalCode": "19001",
            "province": "Guadalajara",
            "country": "España",
            "countryCode": "ES",
            "info": ""
        },
        "customFields": [],
        "defaults": {
            "salesChannel": 0,
            "expensesAccount": 0,
            "dueDays": 1,
            "paymentDay": 0,
            "paymentMethod": 0,
            "discount": 0,
            "language": "es",
            "currency": "eur",
            "salesTax": [],
            "purchasesTax": [],
            "accumulateInForm347": "no"
        },
        "socialNetworks": {
            "website": ""
        },
        "tags": [],
        "notes": [],
        "contactPersons": [],
        "shippingAddresses": [],
        "isperson": 1,
        "createdAt": 1748072534,
        "updatedAt": 1748072534
        }
    '''
    # cegid_factura = await async_service.transform_invoice_holded_to_cegid(holded_invoice=holded_invoice, holded_client=holded_client); print(cegid_factura)
    async_service = await async_service.fetch_holded_accounts(); print(async_service)

if __name__ == "__main__":
    asyncio.run(main_test())
