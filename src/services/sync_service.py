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

tz = pytz.timezone('Europe/Madrid')
VALID_VAT_RATES = {0, 4, 5, 7, 10, 21}

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
                print("MIGRANDO CUENTA: ", doc_type)
                break
            break
        print(f"Total Holded accounts to process: {len(tasks)}")
        await asyncio.gather(*tasks)


    async def process_account_invoices(self, holded_api: "HoldedAPI", cegid_api: "CegidAPI", nombre_empresa, tipo_cuenta: str, doc_type: str = "invoice"):
        """ Processes invoices for a given Holded account and pushes them to Cegid."""

        # Get curret offset and list invoices
        offset = get_offset(holded_api.api_key, doc_type)
        all_invoices = await holded_api.list_invoices(doc_type)

        invoices = list(reversed(all_invoices))[offset -1:]
        max_per_migration = 15
        for i, inv_header in enumerate(invoices):
            print("Migration num: ", i)
            if i >= max_per_migration:
                break

            try:
                # Detalles Holded
                inv = await holded_api.invoice_details(inv_header["id"], doc_type)
                pdf = await holded_api.get_invoice_document_pdf(inv["id"], doc_type)
                cli = await holded_api.get_client(inv["contact"])
            
                # Search cuenta cliente, otherwise create it
                cli_name = ' '.join(cli['name'].split()[:2])
                cli_nif = cli.get('vatnumber', '').strip() or cli.get('code', '').strip()
                print("Cliente name: ", cli['name'])

                # Determine type of client
                if doc_type in ["invoice"]:
                    client_type = 1
                elif doc_type in ["purchase", "estimate"]:
                    client_type = 2
                else:
                    raise ValueError("Doc type is wrong")

                cuenta_cliente = await cegid_api.search_cliente(nif=cli_nif, nombre_cliente=cli_name, cliente_type=client_type)

                print(f'Cuenta cliente encontrada: {cuenta_cliente}')
                if not cuenta_cliente:
                    print("Cuenta cliente no encontrada, creando...")
                    # Create new client in Cegid
                    cuenta_cliente = await cegid_api.add_subcuenta(
                        name=cli.get('name'),
                        sub_account_type=1 if doc_type == "invoice" else 2, # SO IMPORTANT THIS
                        nif=cli.get('vatnumber', '').strip() or cli.get('code', '').strip(),
                        email=cli.get("email", ""),
                        telefono=cli.get("mobile") or cli.get("phone"),
                        bill_address=cli.get("billAddress", {})
                    )
                
                open('holded_invoice.json', 'w').write(json.dumps(inv, indent=4, ensure_ascii=False))
                factura = await self.transform_invoice_holded_to_cegid(inv, cli, nombre_empresa, cuenta_cliente, doc_type)
                open('invoice.json', 'w').write(json.dumps(factura, indent=4, ensure_ascii=False))
                if pdf:
                    open('output.pdf', 'wb').write(base64.b64decode(pdf))

                if tipo_cuenta == "normal":
                    print(f'La factura {factura["Documento"]} sería creada ahora como normal')
                    # await cegid_api.crear_factura(factura)
                elif tipo_cuenta == "nuevo_sistema":
                    factura = self.transform_invoice_data(factura)
                    print(f'La factura {factura["Documento"]} sería creada ahora como nuevo sistema')
                    # await cegid_api.crear_factura_nuevo_sistema(factura)

                if pdf:
                    doc_meta = {
                        "Ejercicio": factura["Ejercicio"],
                        "Serie":     factura["Serie"],
                        "Documento": factura["Documento"],
                        "NombreArchivo": f'{factura["Serie"]}-{factura["Documento"]}.pdf',
                        "Archivo":       pdf,
                    }
                    open('invoice_data.json', 'w').write(json.dumps(doc_meta, indent=4, ensure_ascii=False))
            
                    # await cegid_api.add_documento_factura(doc_meta)

                print(f'[OK] Subida factura {factura["NumeroFactura"]}')
            except Exception as e:
                print(f"[ERROR] processing invoice {inv_header['id']}: {e}")
                traceback.print_exc()
            finally:
                # Esto SÍ se ejecuta aunque falle todo lo anterior
                # increment_offset(holded_api.api_key, doc_type)
                print(f'[DEBUG] Offset incrementado para API key {holded_api.api_key}')
                time.sleep(3)
                break
        return None
    
    # UTILITIES
    async def ensure_serie(self, holded_inv: dict, cegid: "CegidAPI"):
        serie = holded_inv["docNumber"].split("-")[0]
        series = await cegid.get_series() or []
        if not any(s["Codigo"] == serie for s in series):
            await cegid.add_serie(codigo=serie, descripcion=f"Serie auto {serie}")

            
    async def transform_invoice_holded_to_cegid(
            self,
            holded_invoice: dict,
            holded_client: dict,
            nombre_empresa: str,
            cuenta_cliente: str,
            doc_type: str
    ):
        iva_reg_code = "01"                               # Régimen general

        # ────── Identificación ───────────────────────────────────────────
        doc_number = get_offset_doc(nombre_empresa)
        ts_date    = datetime.fromtimestamp(holded_invoice["date"], self.tz_mad)
        ejercicio  = str(ts_date.year)
        fecha_int  = int(ts_date.strftime("%Y%m%d"))
        fecha_venc = int(datetime.fromtimestamp(
                            holded_invoice.get("dueDate") or holded_invoice["date"],
                            self.tz_mad).strftime("%Y%m%d"))

        contact_name   = (holded_invoice.get("contactName") or "").strip()
        numero_factura = holded_invoice.get("docNumber") or ts_date.strftime("%Y%m%d")

        # Serie / cuenta contable por tipo de documento
        if doc_type == "invoice":                         # FACTURA EMITIDA
            serie, tipo_asiento = "1", "FacturasEmitidas"
            sales_account       = "70000000"
        else:                                             # FACTURA RECIBIDA
            serie, tipo_asiento = "2", "FacturasRecibidas"
            sales_account       = "60100000"

        tipo_factura = 2 if "maquila" in contact_name.lower() else 1

        # ────── Cabecera base ────────────────────────────────────────────
        factura = {
            "Ejercicio"      : ejercicio,
            "Serie"          : serie,
            "Documento"      : doc_number,
            "TipoAsiento"    : tipo_asiento,
            "Fecha"          : fecha_int,
            "FechaFactura"   : fecha_int,
            "CuentaCliente"  : cuenta_cliente,
            "NumeroFactura"  : numero_factura,
            "Descripcion"    : f"{numero_factura} - {contact_name}"[:40],
            "TipoFactura"    : tipo_factura,
            "NombreCliente"  : contact_name[:40],
            "ClaveRegimenIva1": iva_reg_code,
            "ProrrataIva"    : False,
        }
        if vat := holded_client.get("vatnumber"):
            factura["CifCliente"] = vat

        # ────── Bases, cuotas y tipos de IVA ─────────────────────────────
        vat_groups       = defaultdict(float)
        ret_base, ret_pct = 0.0, 0.0
        total_descuentos  = 0.0

        for prod in holded_invoice.get("products", []):
            price  = prod["price"]
            units  = prod["units"]
            disc   = prod.get("discount", 0)              # %
            base   = price * units * (1 - disc / 100)
            rate   = prod.get("tax", 0) or 0              # 0, 4, 21, -2 …

            if rate < 0:                                  # → retención
                ret_base += base
                ret_pct   = abs(rate)
                continue
            if base < 0 and rate == 0:                    # corrección interna
                continue
            vat_groups[rate] += base

        if holded_invoice.get("discount"):                # descuento global
            total_descuentos += holded_invoice["discount"]

        if total_descuentos:
            resto = total_descuentos
            for r in sorted(vat_groups, reverse=True):
                if resto <= 0:
                    break
                rebaja = min(resto, vat_groups[r])
                vat_groups[r] -= rebaja
                resto         -= rebaja

        base_total = iva_total = 0.0
        idx = 1
        for rate, base in sorted(vat_groups.items()):
            if rate not in VALID_VAT_RATES:
                continue
            cuota = round(base * rate / 100, 2)
            factura[f"BaseImponible{idx}"] = round(base, 2)
            factura[f"PorcentajeIVA{idx}"] = rate
            factura[f"CuotaIVA{idx}"]      = cuota
            if idx > 1:
                factura[f"ClaveRegimenIva{idx}"] = iva_reg_code
            base_total += base
            iva_total  += cuota
            idx += 1
            if idx > 4:
                break

        if ret_base:                                      # bloque de retención
            factura["BaseRetencion"]       = round(ret_base, 2)
            factura["PorcentajeRetencion"] = ret_pct
            factura["CuotaRetencion"]      = round(ret_base * ret_pct / 100, 2)

        # ────── Totales & cobrado ─────────────────────────────────────────
        total_factura = round(
            base_total + iva_total - factura.get("CuotaRetencion", 0.0), 2
        )
        cobrado = holded_invoice.get("paymentsTotal")
        if cobrado is None:
            cobrado = holded_invoice.get("total", 0) - holded_invoice.get("paymentsPending", 0)

        factura["TotalFactura"]   = total_factura
        factura["ImporteCobrado"] = round(cobrado, 2)    # << BLOQUE 1 AÑADIDO

        # ────── Vencimiento único ──────────────────────────────────────────
        factura["TipoVencimiento"] = 1                   # << BLOQUE 2 AÑADIDO
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
            "CodigoTipoVencimiento": 1,
        }]

        # ────── Apunte contable principal (con Importe / TipoImporte) ───────
        importe_linea = round(base_total, 2)             # << BLOQUE 3 AÑADIDO
        factura["Apuntes"] = [{
            "Ejercicio":  ejercicio,
            "Serie":      serie,
            "Documento":  doc_number,
            "Linea":      1,
            "Cuenta":     ("70000000" if serie == "1" else "60100000"),
            "Concepto":   ("Ventas mercaderías" if serie == "1" else contact_name[:40]),
            "Fecha":      fecha_int,
            "Importe":    importe_linea,
            "TipoImporte": (2 if serie == "1" else 1)   # 2 = Haber, 1 = Debe
        }]

        update_offset_doc(nombre_empresa)
        return factura


    # Cegid (números)  ➜  FacturaData (textos + Debe/Haber)
    def transform_invoice_data(self, invoice: dict) -> dict:
        
        tipo_factura_map = {1: "OpInteriores", 2: "OpInteriores"}   # de momento los dos mapean igual

        result = {
            "Ejercicio"      : invoice["Ejercicio"],
            "Serie"          : invoice["Serie"],
            "Documento"      : invoice["Documento"],
            "TipoAsiento"    : invoice["TipoAsiento"],
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
                "Ejercicio":    a["Ejercicio"],
                "Serie":        a["Serie"],
                "Documento":    a["Documento"],
                "Linea":        a["Linea"],
                "Cuenta":       str(a["Cuenta"]),
                "Concepto":     a.get("Concepto", "")[:40],
                "Fecha":        a["Fecha"],
                "Importe":      a.get("Haber", 0.0) or a.get("Debe", 0.0),
                "TipoImporte":  2 if a.get("Haber", 0.0) else 1
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

    await async_service.fetch_holded_accounts()

    '''
    holded_invoice = {
        "id": "685918da5c16a8d10a051315",
        "contact": "6446a64abeb69cadb10dec9b",
        "contactName": "Semillando Sotillo s.c.m.",
        "desc": "",
        "date": 1750629600,
        "dueDate": None,
        "multipledueDate": [],
        "forecastDate": None,
        "notes": "",
        "tags": [],
        "products": [
            {
                "name": "VDVV 5",
                "desc": "AOV Ecológico ValdeVellisca 5l",
                "price": 42.21,
                "units": 9,
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
                "sku": "L2408EV25041",
                "account": "64227fd364fcfe702b0945ba",
                "productId": "6426ff225f758ef8b905a33b",
                "variantId": "6426ff225f758ef8b905a33c"
            }
        ],
        "tax": 15.2,
        "subtotal": 379.89,
        "discount": 0,
        "total": 395.09,
        "language": "es",
        "status": 0,
        "customFields": [],
        "docNumber": "A-2025-091",
        "currency": "eur",
        "currencyChange": 1,
        "paymentMethodId": "64227fce64fcfe702b094536",
        "paymentsTotal": 0,
        "paymentsPending": 395.09,
        "paymentsRefunds": 0,
        "shipping": "hidden"
    }
    holded_client = {
        "id": "6446a64abeb69cadb10dec9b",
        "customId": None,
        "name": "Semillando Sotillo s.c.m.",
        "code": "F86580578",
        "vatnumber": "",
        "tradeName": 0,
        "email": "semillandosotillo@gmail.com",
        "mobile": "",
        "phone": "",
        "type": "client",
        "iban": "",
        "swift": "",
        "groupId": "",
        "clientRecord": {
            "num": 43000022,
            "name": "Semillando Sotillo s.c.m."
        },
        "supplierRecord": 0,
        "billAddress": {
            "address": "Avenida Almendros 278. 3b",
            "city": "Rivas-Vaciamadrid",
            "postalCode": "28523",
            "province": "Madrid",
            "country": "España",
            "countryCode": "ES",
            "info": ""
        },
        "customFields": [],
        "defaults": {
            "salesChannel": 0,
            "expensesAccount": 0,
            "dueDays": 0,
            "paymentDay": 0,
            "paymentMethod": 0,
            "discount": 0,
            "language": "es",
            "currency": "eur",
            "salesTax": [],
            "purchasesTax": [],
            "accumulateInForm347": "yes"
        },
        "socialNetworks": {
            "website": ""
        },
        "tags": [],
        "notes": [],
        "contactPersons": [],
        "shippingAddresses": [],
        "isperson": 0,
        "createdAt": 1682351690,
        "updatedAt": 1683989538,
        "updatedHash": "7d8ae9f492941da734432d4d0cadab44"
        }

    cegid_factura = await async_service.transform_invoice_holded_to_cegid(holded_invoice=holded_invoice, holded_client=holded_client, nombre_empresa="Hermanos Pastor Vellisca SL", cuenta_cliente="41000763", doc_type="estimate")
    transformed = async_service.transform_invoice_data(cegid_factura)

    

    with open('transformed.json', 'w') as f:
        json.dump(transformed, f, indent=4)
    '''

async def invoice_converter():
    async_service = AsyncService()
    # Set here your inovice extracted from Holded API
    holded_invoice =  {
        "id": "685918da5c16a8d10a051315",
        "contact": "6446a64abeb69cadb10dec9b",
        "contactName": "Semillando Sotillo s.c.m.",
        "desc": "",
        "date": 1750629600,
        "dueDate": None,
        "multipledueDate": [],
        "forecastDate": None,
        "notes": "",
        "tags": [],
        "products": [
        {
            "name": "VDVV 5",
            "desc": "AOV Ecológico ValdeVellisca 5l",
            "price": 42.21,
            "units": 9,
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
            "sku": "L2408EV25041",
            "account": "64227fd364fcfe702b0945ba",
            "productId": "6426ff225f758ef8b905a33b",
            "variantId": "6426ff225f758ef8b905a33c"
        }
        ],
        "tax": 15.2,
        "subtotal": 379.89,
        "discount": 0,
        "total": 395.09,
        "language": "es",
        "status": 0,
        "customFields": [],
        "docNumber": "A-2025-091",
        "currency": "eur",
        "currencyChange": 1,
        "paymentMethodId": "64227fce64fcfe702b094536",
        "paymentsTotal": 0,
        "paymentsPending": 395.09,
        "paymentsRefunds": 0,
        "shipping": "hidden"
    }
   
    cegid_account = "Hermanos Pastor Vellisca SL"

    for account in HOLDED_ACCOUNTS:
        if account["nombre_empresa"] == cegid_account:
            holded_api = HoldedAPI(account["api_key"])
            cegid_api = CegidAPI(account["codigo_empresa"])
            await cegid_api.renew_token_api_contabilidad()

            current_invoice = await cegid_api.check_invoice_exists(holded_invoice["docNumber"])
            if not current_invoice:
                print("Invoice alreay exists in Cegid, skipping...")
                continue

            client = await holded_api.get_client(holded_invoice["contact"])
            client_id = await cegid_api.search_cliente(nif=client.get('vatnumber', '').strip() or client.get('code', '').strip(), nombre_cliente=client.get('name')); print("Client ID ->",client_id)
            if not client_id:
                raise ValueError(f"Cliente {cegid_account} no encontrado en Cegid, tendrás que crearlo.")


            transformed_invoice = await async_service.transform_invoice_holded_to_cegid(
                holded_invoice=holded_invoice,
                holded_client=await holded_api.get_client(holded_invoice["contact"]),
                nombre_empresa=cegid_account,
                cuenta_cliente=client_id,  
                doc_type="estimate"
            )


            re_trasformed_invoice = async_service.transform_invoice_data(transformed_invoice)

            pdf = await holded_api.get_invoice_document_pdf(holded_invoice["id"])

            doc_meta = {
                "Ejercicio": re_trasformed_invoice["Ejercicio"],
                "Serie": re_trasformed_invoice["Serie"],
                "Documento": re_trasformed_invoice["Documento"],
                "NombreArchivo": f'{re_trasformed_invoice["Serie"]}-{re_trasformed_invoice["Documento"]}.pdf',
                "Archivo": pdf,
            }

            # Save data
            open('holded_invoice.json', 'w').write(json.dumps(holded_invoice, indent=4, ensure_ascii=False))
            open('cegid_invoice.json', 'w').write(json.dumps(transformed_invoice, indent=4, ensure_ascii=False))
            open('invoice_data.json', 'w').write(json.dumps(doc_meta, indent=4, ensure_ascii=False))

if __name__ == "__main__":
    # asyncio.run(main_test())
    asyncio.run(main_test())
