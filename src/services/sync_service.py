import asyncio
import json
import pytz
import re
import base64
from datetime import datetime
from collections import defaultdict
import random
import traceback
import time

from src.services.cegid_service import CegidAPI
from src.services.holded_service import HoldedAPI
from src.config.settings import HOLDED_ACCOUNTS, increment_offset, get_offset, set_offset, update_offset_doc, get_offset_doc
HOLDED_ACCOUNTS
tz = pytz.timezone('Europe/Madrid')

class AsyncService:
    def __init__(self):
        self.tz_mad = pytz.timezone("Europe/Madrid")
    
    async def fetch_holded_accounts(self):
        """Fetches Holded accounts and processes their invoices."""

        tasks = []

        # print("Holded account: ", HOLDED_ACCOUNTS)

        for acc in HOLDED_ACCOUNTS:
            h_api = HoldedAPI(acc["api_key"])
            cegid_api = CegidAPI(acc["codigo_empresa"])
            await cegid_api.renew_token_api_contabilidad()

            for doc_type in acc["cuentas_a_migrar"]:
                tasks.append(self.process_account_invoices(h_api, cegid_api, acc["nombre_empresa"], acc["tipo_cuenta"], doc_type))
            break

        print(f"Total Holded accounts to process: {len(tasks)}")
        await asyncio.gather(*tasks)


    async def process_account_invoices(self, holded_api: "HoldedAPI", cegid_api: "CegidAPI", nombre_empresa, tipo_cuenta: str, doc_type: str = "invoice"):
        """ Processes invoices for a given Holded account and pushes them to Cegid."""

        # Get curret offset and list invoices
        offset = get_offset(holded_api.api_key)
        all_invoices = await holded_api.list_invoices(doc_type)

        invoices = list(reversed(all_invoices))[offset -1:]
        max_per_migration = 5
        for i, inv_header in enumerate(invoices):
            print("Migration num: ", i)
            if i >= max_per_migration:
                break

            try:
                # Detalles Holded
                inv = await holded_api.invoice_details(inv_header["id"])
                pdf = await holded_api.get_invoice_document_pdf(inv["id"])
                cli = await holded_api.get_client(inv["contact"])
            
                # Search cuenta cliente, otherwise create it
                cli_name = ' '.join(cli['name'].split()[:2])
                cli_nif = cli.get('vatnumber', '').strip() or cli.get('code', '').strip()
                print("Cliente: ", cli_name)
                print("Cliente name fill: ", cli['name'])
                cuenta_cliente = await cegid_api.search_cliente(nif=cli_nif, nombre_cliente=cli_name)

                print(f'Cuenta cliente encontrada: {cuenta_cliente}')
                if not cuenta_cliente:
                    print("Cuenta cliente no encontrada, creando...")
                    # Create new client in Cegid
                    cuenta_cliente = await cegid_api.add_subcuenta(
                        name=cli.get('name'),
                        nif=cli.get('vatnumber', '').strip() or cli.get('code', '').strip(),
                        email=cli.get("email", ""),
                        telefono=cli.get("mobile") or cli.get("phone"),
                        bill_address=cli.get("billAddress", {})
                    )
                
                open('holded_invoice.json', 'w').write(json.dumps(inv, indent=4, ensure_ascii=False))
                factura = await self.transform_invoice_holded_to_cegid(inv, cli, nombre_empresa, cuenta_cliente)
                open('invoice.json', 'w').write(json.dumps(factura, indent=4, ensure_ascii=False))
                open('output.pdf', 'wb').write(base64.b64decode(pdf))

                if tipo_cuenta == "normal":
                    print(f'La factura {factura["Documento"]} sería creada ahora como normal')
                    await cegid_api.crear_factura(factura)
                elif tipo_cuenta == "nuevo_sistema":
                    factura = self.transform_invoice_data(factura)
                    print(f'La factura {factura["Documento"]} sería creada ahora como nuevo sistema')
                    await cegid_api.crear_factura_nuevo_sistema(factura)

                doc_meta = {
                    "Ejercicio": factura["Ejercicio"],
                    "Serie":     factura["Serie"],
                    "Documento": factura["Documento"],
                    "NombreArchivo": f'{factura["Serie"]}-{factura["Documento"]}.pdf',
                    "Archivo":       pdf,
                }
                open('invoice_data.json', 'w').write(json.dumps(doc_meta, indent=4, ensure_ascii=False))
         
                
                
                await cegid_api.add_documento_factura(doc_meta)

                print(f'[OK] Subida factura {factura["NumeroFactura"]}')
            except Exception as e:
                print(f"[ERROR] processing invoice {inv_header['id']}: {e}")
                traceback.print_exc()
            finally:
                # Esto SÍ se ejecuta aunque falle todo lo anterior
                increment_offset(holded_api.api_key)
                print(f'[DEBUG] Offset incrementado para API key {holded_api.api_key}')
                # break
                time.sleep(3)
        return None
    
    # UTILITIES
    async def ensure_serie(self, holded_inv: dict, cegid: "CegidAPI"):
        serie = holded_inv["docNumber"].split("-")[0]
        series = await cegid.get_series() or []
        if not any(s["Codigo"] == serie for s in series):
            await cegid.add_serie(codigo=serie, descripcion=f"Serie auto {serie}")

        
    async def transform_invoice_holded_to_cegid(
        self,
        holded_invoice : dict,
        holded_client  : dict,
        nombre_empresa : str,
        cuenta_cliente : str
    ) -> dict:

        sales_account = "70000000"
        iva_reg_code  = "01"

        # --- Identificación ----------------------------------------------------
        doc_number  = get_offset_doc(nombre_empresa)
        ts_date     = datetime.fromtimestamp(holded_invoice["date"], self.tz_mad)
        ejercicio   = str(ts_date.year)
        fecha_int   = int(ts_date.strftime("%Y%m%d"))
        fecha_venc  = int(datetime.fromtimestamp(
                            holded_invoice.get("dueDate") or holded_invoice["date"],
                            self.tz_mad).strftime("%Y%m%d"))

        contact_name   = holded_invoice.get("contactName", "").strip()
        numero_factura = holded_invoice.get("docNumber") or ts_date.strftime("%Y%m%d")

        #  Siempre serie-1 / FacturasEmitidas
        serie         = "1"
        tipo_asiento  = 1                       # 1 = Facturas expedidas
        tipo_factura  = 2 if "maquila" in contact_name.lower() else 1

        # --- Cabecera ----------------------------------------------------------
        factura = {
            "Ejercicio"      : ejercicio,
            "Serie"          : serie,
            "Documento"      : doc_number,
            "TipoAsiento"    : tipo_asiento,
            "Fecha"          : fecha_int,
            "FechaFactura"   : fecha_int,
            "CuentaCliente"  : cuenta_cliente,
            "NumeroFactura"  : numero_factura,
            "Descripcion"    : f"Factura de {contact_name}"[:40],
            "TipoFactura"    : tipo_factura,
            "NombreCliente"  : contact_name[:40],
            "ClaveRegimenIva1": iva_reg_code,
            "ProrrataIva"    : False,
        }
        if vat := holded_client.get("vatnumber"):
            factura["CifCliente"] = vat

        # --- Bases y cuotas de IVA --------------------------------------------
        vat_groups  = defaultdict(float)
        for p in holded_invoice.get("products", []):
            net = p["price"] * p["units"] * (1 - p.get("discount", 0)/100)
            vat_groups[p["tax"]] += net

        base_total = iva_total = 0.0
        for idx, rate in enumerate(sorted(vat_groups), 1):
            base  = round(vat_groups[rate], 2)
            cuota = round(base * rate / 100, 2)
            factura[f"BaseImponible{idx}"] = base
            factura[f"PorcentajeIVA{idx}"] = rate
            factura[f"CuotaIVA{idx}"]      = cuota
            if idx > 1:
                factura[f"ClaveRegimenIva{idx}"] = iva_reg_code
            base_total += base
            iva_total  += cuota

        total_factura               = round(base_total + iva_total, 2)
        factura["TotalFactura"]     = total_factura
        factura["ImporteCobrado"]   = round(holded_invoice.get("paymentsTotal", 0), 2)

        # --- Vencimiento único -------------------------------------------------
        factura["TipoVencimiento"] = 1
        factura["Vencimientos"] = [{
            "Ejercicio"        : ejercicio,
            "Serie"            : serie,
            "Documento"        : doc_number,
            "NumeroVencimiento": 1,
            "FechaFactura"     : fecha_int,
            "CuentaCliente"    : cuenta_cliente,
            "NumeroFactura"    : numero_factura,
            "FechaVencimiento" : fecha_venc,
            "Importe"          : total_factura,
            "CodigoTipoVencimiento": 1
        }]

        # --- UN solo apunte: base total ---------------------------------------
        factura["Apuntes"] = [{
            "Ejercicio" : ejercicio,
            "Serie"     : serie,
            "Documento" : doc_number,
            "Linea"     : 1,
            "Cuenta"    : sales_account,
            "Concepto"  : "Ventas maquila (base total)"[:50],
            "Fecha"     : fecha_int,
            "Debe"      : 0.0,
            "Haber"     : round(base_total, 2)   # 307,16 en tu ejemplo
        }]

        update_offset_doc(nombre_empresa)
        return factura

    # ---------------------------------------------------------------------------
    # 2)  Cegid (números)  ➜  FacturaData (textos + Debe/Haber)
    # ---------------------------------------------------------------------------
    def transform_invoice_data(self, invoice: dict) -> dict:
        tipo_asiento_map = {1: "FacturasEmitidas", 2: "FacturasRecibidas", 0: "Asiento"}
        tipo_factura_map = {1: "OpInteriores", 2: "OpInteriores"}   # de momento los dos mapean igual

        result = {
            "Ejercicio"      : invoice["Ejercicio"],
            "Serie"          : invoice["Serie"],
            "Documento"      : invoice["Documento"],
            "TipoAsiento"    : tipo_asiento_map[invoice["TipoAsiento"]],
            "Fecha"          : invoice["Fecha"],
            "FechaFactura"   : invoice["FechaFactura"],

            "CuentaCliente"  : str(invoice["CuentaCliente"]),
            "NumeroFactura"  : invoice["NumeroFactura"],
            "Descripcion"    : invoice["Descripcion"],
            "TipoFactura"    : tipo_factura_map[invoice["TipoFactura"]],
            "TotalFactura"   : invoice["TotalFactura"],
            "ImporteCobrado" : invoice.get("ImporteCobrado", 0.0),
            "TipoVencimiento": invoice["TipoVencimiento"],
        }

        # ▸ Bases / Cuotas / % IVA (1-4)
        for i in range(1, 5):
            for k in ("BaseImponible", "PorcentajeIVA", "CuotaIVA"):
                key = f"{k}{i}"
                if key in invoice:
                    result[key] = invoice[key]

        # ▸ Vencimientos
        result["Vencimientos"] = invoice.get("Vencimientos", [])

        # ▸ Apuntes  (convertimos Debe/Haber)
        res_apuntes = []
        for a in invoice.get("Apuntes", []):
            res_apuntes.append({
                "Ejercicio": a["Ejercicio"],
                "Serie"    : a["Serie"],
                "Documento": a["Documento"],
                "Linea"    : a["Linea"],
                "Cuenta"   : str(a["Cuenta"]),
                "Concepto" : a.get("Concepto", ""),
                "Fecha"    : a["Fecha"],
                "Importe"  : a["Haber"] if a["Haber"] else a["Debe"],
                "TipoImporte": 2 if a["Haber"] else 1
            })
        result["Apuntes"] = res_apuntes
        return result


    
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
