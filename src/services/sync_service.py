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
            tasks.append(self.process_account_invoices(h_api, cegid_api, acc["nombre_empresa"], acc["tipo_cuenta"]))
        
        print(f"Total Holded accounts to process: {len(tasks)}")
        await asyncio.gather(*tasks)


    async def process_account_invoices(self, holded_api: "HoldedAPI", cegid_api: "CegidAPI", nombre_empresa, tipo_cuenta: str):

        offset = get_offset(holded_api.api_key)
        all_invoices = await holded_api.list_invoices()
        print(f"Total invoices in Holded: {len(all_invoices)}")
        print("offset of configuration ->", offset)
        invoices = list(reversed(all_invoices))[offset -1:]

        for inv_header in invoices:
            try:
                # Detalles Holded
                inv = await holded_api.invoice_details(inv_header["id"])
                pdf = await holded_api.get_invoice_document_pdf(inv["id"])
                cli = await holded_api.get_client(inv["contact"])

                # Transformar & subir
                
                # open('holded_invoice.json', 'w').write(json.dumps(inv, indent=4, ensure_ascii=False))
                factura = await self.transform_invoice_holded_to_cegid(inv, cli, nombre_empresa)
                
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
                """
                open('output.pdf', 'wb').write(base64.b64decode(pdf))
                open('invoice_data.json', 'w').write(json.dumps(doc_meta, indent=4, ensure_ascii=False))
                open('invoice.json', 'w').write(json.dumps(factura, indent=4, ensure_ascii=False))
                """
                await cegid_api.add_documento_factura(doc_meta)

                print(f'[OK] Subida factura {factura["NumeroFactura"]}')
            except Exception as e:
                print(f"[ERROR] processing invoice {inv_header['id']}: {e}")
                traceback.print_exc()
            finally:
                # Esto SÍ se ejecuta aunque falle todo lo anterior
                increment_offset(holded_api.api_key)
                print(f'[DEBUG] Offset incrementado para API key {holded_api.api_key}')
                time.sleep(3)
                
        return None
    
    # UTILITIES
    async def ensure_serie(self, holded_inv: dict, cegid: "CegidAPI"):
        serie = holded_inv["docNumber"].split("-")[0]
        series = await cegid.get_series() or []
        if not any(s["Codigo"] == serie for s in series):
            await cegid.add_serie(codigo=serie, descripcion=f"Serie auto {serie}")


    async def ensure_cliente(self, subcuenta_id, cegid: "CegidAPI"):
        """
        comprueba que la subcuenta (cliente) existe en Cegid
        """

       
    async def transform_invoice_holded_to_cegid(self, holded_invoice: dict, holded_client: dict, nombre_empresa: str) -> dict:
        # Identificación y número Cegid
        doc_number = get_offset_doc(nombre_empresa)
        ts_date = datetime.fromtimestamp(holded_invoice["date"], self.tz_mad)
        ejercicio = str(ts_date.year)

        # Fechas en YYYYMMDD
        fecha_int = int(ts_date.strftime("%Y%m%d"))
        due_ts = holded_invoice.get("dueDate") or holded_invoice["date"]
        fecha_venc_single = int(datetime.fromtimestamp(due_ts, self.tz_mad).strftime("%Y%m%d"))

        # Bases e IVA
        vat_groups = defaultdict(float)
        for p in holded_invoice.get("products", []):
            net = p["price"] * p["units"] * (1 - p.get("discount", 0) / 100)
            vat_groups[p["tax"]] += net

        # Número de factura
        raw_doc = holded_invoice.get("docNumber")
        if raw_doc and raw_doc.isdigit():
            numero_factura = raw_doc
        else:
            numero_factura = ts_date.strftime("%Y%m%d")

        # Cuenta cliente
        cuenta_cliente = holded_client["clientRecord"].get("num", "43009981")

        # Tipo de factura según el contacto (“maquila”)
        contact_name = holded_invoice.get("contactName", "")
        tipo_factura = 2 if re.search(r"maquila", contact_name, re.IGNORECASE) else 1

        # Serie y TipoAsiento según tipo de cliente/proveedor
        if holded_client.get("type") == "client":
            serie = "1"      # Factura expedida
            tipo_asiento = 1
        elif holded_client.get("type") == "supplier":
            serie = "2"      # Factura recibida
            tipo_asiento = 2
        else:
            serie = "1"
            tipo_asiento = 0

        # Descripción
        desc_orig = holded_invoice.get("desc")
        if desc_orig:
            descripcion = desc_orig
        else:
            descripcion = f"Factura de {contact_name} Nº {numero_factura}"

        if len(descripcion) > 40:
            descripcion = descripcion[:40]


        # Construcción preliminar de la factura
        factura = {
            "Ejercicio": ejercicio,
            "Serie": serie,
            "Documento": doc_number,
            "TipoAsiento": tipo_asiento,
            "Fecha": fecha_int,
            "FechaFactura": fecha_int,
            "CuentaCliente": self.ajusta_cuenta(cuenta_cliente),
            "NumeroFactura": numero_factura,
            "Descripcion": descripcion,
            "TipoFactura": tipo_factura,
            "NombreCliente": contact_name,
            "ClaveRegimenIva1": "01",
            "ProrrataIva": False,
        }
        if holded_client.get("vatnumber"):
            factura["CifCliente"] = holded_client["vatnumber"]

        # Calcular Bases y cuotas de IVA
        base_total = iva_total = 0.0
        for idx, rate in enumerate(sorted(vat_groups), 1):
            base = round(vat_groups[rate], 2)
            cuota = round(base * rate / 100, 2)
            factura[f"BaseImponible{idx}"] = base
            factura[f"PorcentajeIVA{idx}"] = rate
            factura[f"CuotaIVA{idx}"] = cuota
            if idx > 1:
                factura[f"ClaveRegimenIva{idx}"] = "01"
            base_total += base
            iva_total += cuota
        factura["TotalFactura"] = round(base_total + iva_total, 2)

        # Vencimientos (único vs. múltiple)
        md = holded_invoice.get("multipledueDate")
        if isinstance(md, dict):
            multi = [md]
        elif isinstance(md, list):
            multi = md
        else:
            multi = []

        tipo_venc = 2 if multi else 1
        factura["TipoVencimiento"] = tipo_venc

        vencimientos = []
        if multi:
            for idx, plazo in enumerate(multi, start=1):
                # defensivamente, coger fecha sólo si viene bien
                fecha_plazo = plazo.get("date")
                if isinstance(fecha_plazo, (int, float)):
                    fv = int(datetime.fromtimestamp(fecha_plazo, self.tz_mad).strftime("%Y%m%d"))
                else:
                    fv = fecha_int
                importe = round(plazo.get("amount", factura["TotalFactura"]), 2)
                vencimientos.append({
                    "Ejercicio": ejercicio,
                    "Serie": serie,
                    "Documento": doc_number,
                    "NumeroVencimiento": idx,
                    "FechaFactura": fecha_int,
                    "CuentaCliente": self.ajusta_cuenta(cuenta_cliente),
                    "NumeroFactura": numero_factura,
                    "FechaVencimiento": fv,
                    "Importe": importe,
                    "CodigoTipoVencimiento": 1,
                })
        else:
            vencimientos.append({
                "Ejercicio": ejercicio,
                "Serie": serie,
                "Documento": doc_number,
                "NumeroVencimiento": 1,
                "FechaFactura": fecha_int,
                "CuentaCliente": self.ajusta_cuenta(cuenta_cliente),
                "NumeroFactura": numero_factura,
                "FechaVencimiento": fecha_venc_single,
                "Importe": factura["TotalFactura"],
                "CodigoTipoVencimiento": 1,
            })

        factura["Vencimientos"] = vencimientos

        # Apuntes mínimos
        concepto = f"{ejercicio}-{doc_number}-{contact_name}"
        if len(concepto) > 50:
            concepto = concepto[:50]

        factura["Apuntes"] = [{
            "Ejercicio": ejercicio,
            "Serie": serie,
            "Documento": doc_number,
            "Linea": 1,
            "Cuenta": self.ajusta_cuenta(cuenta_cliente),
            "Concepto": concepto,
            "Importe": factura["TotalFactura"],
            "Fecha": fecha_int,
        }]

        # Actualizar offset del documento
        update_offset_doc(nombre_empresa)

        return factura
    

    def transform_invoice_data(self, invoice: dict) -> dict:
        """
        Transforms Holded-derived invoice dict into API-ready FacturaData dict.
        """
        # Mapping definitions
        tipo_asiento_map = {
            1: "FacturasEmitidas",
            2: "FacturasRecibidas",
            0: "Asiento",
        }
        # Default TipoFactura mapping to OpInteriores for any numeric code
        tipo_factura_map = {
            1: "OpInteriores",
            2: "OpInteriores",  # adjust if different mapping needed
        }
        
        # Start building result
        result = {
            "Ejercicio": invoice["Ejercicio"],
            "Serie": invoice["Serie"],
            "Documento": invoice["Documento"],
            "TipoAsiento": tipo_asiento_map.get(invoice["TipoAsiento"], "Asiento"),
            "FechaFactura": invoice["FechaFactura"],
            "CuentaCliente": str(invoice["CuentaCliente"]),
            "NumeroFactura": invoice["NumeroFactura"],
            "Descripcion": invoice["Descripcion"],
            "TotalFactura": invoice["TotalFactura"],
            "TipoFactura": tipo_factura_map.get(invoice["TipoFactura"], "OpInteriores"),
            "TipoVencimiento": str(invoice["TipoVencimiento"]),
        }
        
        # Copy BaseImponible, PorcentajeIVA, CuotaIVA fields dynamically
        for idx in range(1, 5):
            bi_key = f"BaseImponible{idx}"
            pi_key = f"PorcentajeIVA{idx}"
            ci_key = f"CuotaIVA{idx}"
            if bi_key in invoice:
                result[bi_key] = invoice[bi_key]
                result[pi_key] = invoice[pi_key]
                result[ci_key] = invoice[ci_key]
        
        # Transform Vencimientos list
        transformed_venc = []
        for v in invoice.get("Vencimientos", []):
            tv = {
                "Ejercicio": v["Ejercicio"],
                "Serie": v["Serie"],
                "Documento": v["Documento"],
                "NumeroVencimiento": v["NumeroVencimiento"],
                "FechaFactura": v["FechaFactura"],
                "CuentaCliente": str(v["CuentaCliente"]),
                "NumeroFactura": v["NumeroFactura"],
                "FechaVencimiento": v["FechaVencimiento"],
                "Importe": v["Importe"],
                "CodigoTipoVencimiento": v["CodigoTipoVencimiento"],
            }
            transformed_venc.append(tv)
        result["Vencimientos"] = transformed_venc
        
        # Transform Apuntes list
        transformed_apunts = []
        for a in invoice.get("Apuntes", []):
            ta = {
                "Ejercicio": a["Ejercicio"],
                "Serie": a["Serie"],
                "Documento": a["Documento"],
                "Linea": a["Linea"],
                "Cuenta": str(a["Cuenta"]),
                "Concepto": a["Concepto"],
                "Importe": a["Importe"],
                "Fecha": a["Fecha"],
            }
            transformed_apunts.append(ta)
        result["Apuntes"] = transformed_apunts
        
        return result

    def ajusta_cuenta(self, cuenta):
        """ Ajusta el número de cuenta a 8 dígitos según las reglas de Cegid."""
        s = str(cuenta)

        if len(s) > 8:
            resultado = []
            ceros_a_quitar = len(s) - 8
            for c in s:
                if ceros_a_quitar and c == "0":
                    ceros_a_quitar -= 1
                    continue
                resultado.append(c)
            s = "".join(resultado)

        if len(s) > 8:
            s = s[-8:]

        if len(s) < 8:
            s = s.zfill(8)

        return s

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
