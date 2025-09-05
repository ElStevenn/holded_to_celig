import asyncio
import json
import logging
import pytz
import re
import base64
from datetime import datetime
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
import random
import traceback
import time
import re

from src.services.cegid_service import CegidAPI
from src.services.holded_service import HoldedAPI
from src.config.settings import HOLDED_ACCOUNTS, increment_offset, get_offset, set_offset, update_offset_doc, get_offset_doc, generate_cif

tz = pytz.timezone('Europe/Madrid')
VALID_VAT_RATES = {0, 4, 10, 12, 21} 

logger = logging.getLogger(__name__)

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
                logger.info(f"[EXPORT] Migrando doc_type='{doc_type}'")
                
            break
        logger.info(f"[EXPORT] Total tareas a procesar: {len(tasks)}")
        await asyncio.gather(*tasks)

    async def process_account_invoices(self, holded_api: "HoldedAPI", cegid_api: "CegidAPI", nombre_empresa, tipo_cuenta: str, doc_type: str = "invoice"):
        """Processes Holded invoices and pushes them to Cegid. 
        If Cegid returns 'duplicated', increments Documento and retries."""

        offset = get_offset(holded_api.api_key, doc_type)
        all_invoices = await holded_api.list_invoices(doc_type)
        invoices = list(reversed(all_invoices))[offset - 1:]
        max_per_migration = 15

        for i, inv_header in enumerate(invoices):
            res_created_invoice = None
            cli_name = None
            logger.debug(f"[EXPORT] Migration num: {i}")
            if i >= max_per_migration:
                break

            try:
                inv = await holded_api.invoice_details(inv_header["id"], doc_type)
                pdf = await holded_api.get_invoice_document_pdf(inv["id"], doc_type)
                cli = await holded_api.get_client(inv["contact"])

                if cli:
                    cli_name = ' '.join(str(cli.get('name', inv.get("contactName", "-"))).split()[:2])
                    vatnumber = str(cli.get('vatnumber', '')).strip() or generate_cif()
                    match = re.search(r'\b\d{7,8}[A-Z]\b', vatnumber, re.IGNORECASE)
                    cli_nif = match.group(0) if match else ''
                else:
                    cli = self.create_unreal_client(inv)
                    cli_nif = cli["nif"]

                if doc_type == "invoice":
                    client_type = 1
                elif doc_type in ("purchase", "estimate"):
                    client_type = 2
                else:
                    raise ValueError("Doc type is wrong")

                # Save invoice
                open('holded_invoice.json', 'w').write(json.dumps(inv, indent=4, ensure_ascii=False))
                if not cli_name:
                    cli_name = f"Cliente {cli_nif}"

                cuenta_cliente = await cegid_api.search_cliente(
                    nif=cli_nif, nombre_cliente=cli_name, cliente_type=client_type
                )
                if not cuenta_cliente:
                    cuenta_cliente = await cegid_api.add_subcuenta(
                        name=cli.get('name'),
                        sub_account_type=1 if doc_type == "invoice" else 2,
                        nif=cli_nif,
                        email=cli.get("email", ""),
                        telefono=cli.get("mobile") or cli.get("phone"),
                        bill_address=cli.get("billAddress", {})
                    )

                factura = await self.transform_invoice_holded_to_cegid(
                    holded_invoice=inv,
                    holded_client=cli,
                    nombre_empresa=nombre_empresa,
                    cuenta_cliente=cuenta_cliente,
                    doc_type=doc_type
                )

                open('invoice.json', 'w').write(json.dumps(factura, indent=4, ensure_ascii=False))

                if pdf:
                    open('der_output.pdf', 'wb').write(base64.b64decode(pdf))

                # Primer intento + reintentos si 'duplicated'
                max_retries = 3
                intento = 0
                while True:
                    # Create invpice normal if tipo_cuenta is normal and doc_type is not purchase
                    if tipo_cuenta == "normal" and doc_type != "purchase":
                        logger.info("[EXPORT] Creando factura NORMAL")
                        res_created_invoice = await cegid_api.crear_factura(factura)
                    else:
                        logger.info("[EXPORT] Creando factura NUEVO SISTEMA")
                        res_created_invoice = await cegid_api.crear_factura_nuevo_sistema(factura)

                    if res_created_invoice != "duplicated":
                        break

                    if intento >= max_retries:
                        logger.error("[EXPORT] Demasiados duplicados, abortando.")
                        break

                    logger.warning("[EXPORT] Cegid devolvió 'duplicated'. Incrementando Documento y reintentando...")
                    factura = self._bump_document(factura, nombre_empresa)
                    intento += 1

                # Subir PDF solo si la creación no falló
                if pdf and res_created_invoice != "duplicated":
                    doc_meta = {
                        "Ejercicio": factura["Ejercicio"],
                        "Serie": factura["Serie"],
                        "Documento": factura["Documento"],
                        "NombreArchivo": f'{factura["Serie"]}-{factura["Documento"]}.pdf',
                        "Archivo": pdf,
                    }
                    await cegid_api.add_documento_factura(doc_meta)

                if res_created_invoice == "duplicated":
                    logger.error(f"[EXPORT] No se pudo subir la factura {factura['NumeroFactura']} (duplicated persistente)")
                else:
                    logger.info(f"[EXPORT] Subida factura {factura['NumeroFactura']}")

            except Exception as e:
                logger.exception(f"[EXPORT] Error procesando invoice {inv_header['id']}: {e}")
            finally:
                increment_offset(holded_api.api_key, doc_type)
                logger.debug(f"[EXPORT] Offset incrementado para API key {holded_api.api_key}")
                time.sleep(0.5)

        return None
        
    # UTILITIES
    async def ensure_serie(self, holded_inv: dict, cegid: "CegidAPI"):
        serie = holded_inv["docNumber"].split("-")[0]
        series = await cegid.get_series() or []
        if not any(s["Codigo"] == serie for s in series):
            await cegid.add_serie(codigo=serie, descripcion=f"Serie auto {serie}")

    def _bump_document(self, factura: dict, nombre_empresa: str) -> dict:
        new_doc = int(factura["Documento"]) + 1
        factura["Documento"] = new_doc
        for v in factura.get("Vencimientos", []):
            v["Documento"] = new_doc
        for a in factura.get("Apuntes", []):
            a["Documento"] = new_doc
        update_offset_doc(nombre_empresa)
        return factura
    
    def create_unreal_client(self, invoice: dict):
        client = {
            "nif": generate_cif(),
            "name": invoice.get("contactName", "")[:50],
            "emai": ""
        }

        return client

    async def transform_invoice_holded_to_cegid(self, holded_invoice: dict, holded_client: dict, nombre_empresa: str, cuenta_cliente: str, doc_type: str):
        logger.debug("[EXPORT] transform_invoice_holded_to_cegid called with parameters:")
        logger.debug(f"  holded_invoice: {json.dumps(holded_invoice, indent=2, ensure_ascii=False)}")
        logger.debug(f"  holded_client: {json.dumps(holded_client, indent=2, ensure_ascii=False)}")
        logger.debug(f"  nombre_empresa: {nombre_empresa}")
        logger.debug(f"  cuenta_cliente: {cuenta_cliente}")
        logger.debug(f"  doc_type: {doc_type}")
        iva_reg_code = "01"
        cuenta_compras_agrarias = ""

        # ───── identificación ─────
        doc_number = get_offset_doc(nombre_empresa)
        ts_date    = datetime.fromtimestamp(holded_invoice["date"], self.tz_mad)
        ejercicio  = str(ts_date.year)
        fecha_int  = int(ts_date.strftime("%Y%m%d"))
        fecha_venc = int(datetime.fromtimestamp(
                            holded_invoice.get("dueDate") or holded_invoice["date"],
                            self.tz_mad).strftime("%Y%m%d"))

        raw_contact = (holded_invoice.get("contactName") or "").strip()
        clean_name  = re.sub(r"\s*\(.*?\)\s*$", "", raw_contact)         # quita (CAMPO), (RENTA)…
        numero_fact = holded_invoice.get("docNumber") or ts_date.strftime("%Y%m%d")

        # ───── serie / asiento ─────
        if doc_type in ("invoice", "sales"):
            serie, tipo_asiento = "1", "FacturasEmitidas"
            cuenta_gasto        = "70000000"
            concepto_linea      = "Ventas mercaderías"
        else:                                                           # estimate / purchase / bill
            serie, tipo_asiento = "2", "FacturasRecibidas"
            cuenta_gasto        = "60100000"
            concepto_linea      = (holded_invoice["products"][0]["name"][:40]
                                if holded_invoice.get("products") else clean_name[:40])

        tipo_factura = "OpInteriores"

        factura = {
            "Ejercicio"      : ejercicio,
            "Serie"          : serie,
            "Documento"      : doc_number,
            "TipoAsiento"    : tipo_asiento,
            "Fecha"          : fecha_int,
            "FechaFactura"   : fecha_int,
            "CuentaCliente"  : cuenta_cliente,
            "NumeroFactura"  : numero_fact,
            "Descripcion"    : f"{numero_fact} – {clean_name}"[:40],
            "TipoFactura"    : tipo_factura,
            "NombreCliente"  : clean_name[:40],
            "ClaveRegimenIva1": iva_reg_code,
            "ProrrataIva"    : False,
        }
        if vat := holded_client.get("vatnumber"):
            factura["CifCliente"] = vat

        # ───── bases / IVA ─────
        vat_groups       = defaultdict(float)
        ret_base         = 0.0
        ret_pct          = 0.0
        total_descuentos = holded_invoice.get("discount", 0.0) or 0.0

        for prod in holded_invoice.get("products", []):
            price = prod["price"]
            units = prod["units"]
            disc  = prod.get("discount", 0)
            base  = price * units * (1 - disc / 100)
            rate  = prod.get("tax", 0) or 0

            # 👉  RETENCIÓN 2 %
            if rate == -2 or "s_retencion2" in prod.get("taxes", []):
                logger.debug("[EXPORT] ***HAY RETENCION!***")
                ret_base += base
                ret_pct   = 2
                continue

            #  resto de líneas normales
            if rate < 0:            # (por si llegara otra retención distinta)
                continue            #  – de momento no la contemplamos
            if base < 0 and rate == 0:
                continue            #  línea de corrección interna
            vat_groups[rate] += base


        if total_descuentos:                              # descuento global
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
            factura[f"BaseImponible{idx}"] = base 
            factura[f"PorcentajeIVA{idx}"] = rate
            factura[f"CuotaIVA{idx}"]      = cuota
            
            if idx > 1:
                factura[f"ClaveRegimenIva{idx}"] = iva_reg_code
            base_total += base
            iva_total  += cuota
            idx += 1
            if idx > 4:
                break

        # ───── retención solo en recibidas ─────
        ret_to_subtract = 0.0
        if serie == "2" and ret_base:
            cuota_ret = round(ret_base * 0.02, 2)
            ret_to_subtract  = cuota_ret

            factura.update({
                "BaseRetencion":       round(ret_base, 2),
                "PorcentajeRetencion": 2,
                "CuotaRetencion":      cuota_ret,
                "TipoRetencion":       "Agricultores",
            })
        
        total_factura = round(base_total + iva_total - ret_to_subtract, 2)

        cobrado = holded_invoice.get("paymentsTotal")
        if cobrado is None:
            cobrado = holded_invoice.get("total", 0) - holded_invoice.get("paymentsPending", 0)


        factura["TotalFactura"]   = total_factura
        
        factura["ImporteCobrado"] = round(cobrado, 2)

        
        if doc_type == "estimate" or doc_type == "purchase":
            factura["FechaIntroduccionFactura"] = fecha_int

        # ───── vencimiento único ─────
        factura["TipoVencimiento"] = 1
        factura["Vencimientos"] = [{
            "Ejercicio": ejercicio,
            "Serie": serie,
            "Documento": doc_number,
            "NumeroVencimiento": 1,
            "FechaFactura": fecha_int,
            "CuentaCliente": cuenta_cliente,
            "NumeroFactura": numero_fact,
            "FechaVencimiento": fecha_venc,
            "Importe": total_factura,
            "CodigoTipoVencimiento": 1,
        }]

        # ───── apunte de gasto / ingreso ─────
        factura["Apuntes"] = [{
            "Ejercicio"   : ejercicio,
            "Serie"       : serie,
            "Documento"   : doc_number,
            "Linea"       : 1,
            "Cuenta"      : cuenta_gasto, # 60100000 en recibidas
            "Concepto"    : concepto_linea,
            "Fecha"       : fecha_int,
            "Importe"     : round(base_total, 2),
            "TipoImporte" : 2 if serie == "1" else 1
        }]




        update_offset_doc(nombre_empresa)
        return factura


    # Cegid (números)  ➜  FacturaData (textos + Debe/Haber)
    def transform_invoice_data(self, invoice: dict) -> dict:
        """Transforms invoice data from Cegid format to FacturaData format."""
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
            "TipoFactura"    : invoice["TipoFactura"],
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
            # 1) ¿viene ya con “Importe” y “TipoImporte”?  (caso nuevo)
            if "Importe" in a and "TipoImporte" in a:
                importe      = a["Importe"]
                tipo_importe = a["TipoImporte"]
            else:
                # 2) Formato antiguo Debe / Haber  → los convertimos
                importe      = a.get("Haber", 0.0) or a.get("Debe", 0.0)
                tipo_importe = 2 if a.get("Haber", 0.0) else 1

            res_apuntes.append({
                "Ejercicio":   a["Ejercicio"],
                "Serie":       a["Serie"],
                "Documento":   a["Documento"],
                "Linea":       a["Linea"],
                "Cuenta":      str(a["Cuenta"]),
                "Concepto":    a.get("Concepto", "")[:40],
                "Fecha":       a["Fecha"],
                "Importe":     round(importe, 2),
                "TipoImporte": tipo_importe
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
        "id": "687e0ba1c2c30b417a0909f5",
        "contact": "661688e91cbed494180f467a",
        "contactName": "Virginia Serrano Pastor (RENTA)",
        "desc": "",
        "date": 1752876000,
        "dueDate": None,
        "multipledueDate": [],
        "forecastDate": None,
        "notes": "",
        "tags": [
        "campo",
        "renta"
        ],
        "products": [
        {
            "name": "RENTA",
            "desc": "Olivar",
            "price": 0.72,
            "units": 51,
            "projectid": None,
            "tax": 0,
            "taxes": [],
            "tags": [
            "campo",
            "renta"
            ],
            "discount": 0,
            "retention": 0,
            "weight": 0,
            "costPrice": 0.89243,
            "sku": "",
            "account": "64227fd264fcfe702b0945ac",
            "productId": "66165849bee0fb81ab01f814",
            "variantId": "66165849bee0fb81ab01f815"
        }
        ],
        "tax": 0,
        "subtotal": 36.72,
        "discount": 0,
        "total": 36.72,
        "language": "",
        "status": 1,
        "customFields": [],
        "docNumber": "R-2025-052",
        "currency": "eur",
        "currencyChange": 1,
        "paymentsDetail": [
        {
            "id": "687e0ba895b3ee0270086aeb",
            "amount": 36.72,
            "date": 1753048800,
            "bankId": "64254034bfaa10ac2a0abab2"
        }
        ],
        "paymentsTotal": 36.72,
        "paymentsPending": 0,
        "paymentsRefunds": 0
    }
   
    cegid_account = "Hermanos Pastor Vellisca SL"

    for account in HOLDED_ACCOUNTS:
        if account["nombre_empresa"] == cegid_account:
            holded_api = HoldedAPI(account["api_key"])
            cegid_api = CegidAPI(account["codigo_empresa"])
            await cegid_api.renew_token_api_contabilidad()

            # current_invoice = await cegid_api.check_invoice_exists(holded_invoice["docNumber"])

            client = await holded_api.get_client(holded_invoice["contact"])
            client_id = await cegid_api.search_cliente(nif=client.get('vatnumber', '').strip() or client.get('code', '').strip(), nombre_cliente=client.get('name'), cliente_type=2)
            if not client_id:
                raise ValueError(f"Cliente {cegid_account} no encontrado en Cegid, tendrás que crearlo.")

            print("*Dcc type es estimate**")
            transformed_invoice = await async_service.transform_invoice_holded_to_cegid(
                holded_invoice=holded_invoice,
                holded_client=await holded_api.get_client(holded_invoice["contact"]),
                nombre_empresa=cegid_account,
                cuenta_cliente=client_id,  
                doc_type="estimate"
            )


            re_trasformed_invoice = async_service.transform_invoice_data(transformed_invoice)

            pdf = await holded_api.get_invoice_document_pdf(holded_invoice["id"], "estimate")

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
