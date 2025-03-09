import asyncio
import json
import pytz
from datetime import datetime
from collections import defaultdict
import traceback

from src.services.cegid_service import CegidAPI
from src.services.holded_service import HoldedAPI
from src.config.settings import HOLDED_ACCOUNTS, increment_offset, get_offset, set_offset

tz = pytz.timezone('Europe/Madrid')

class AsyncService:
    
    def __init__(self):
        pass

    async def process_account_invoices(self, holded_api: "HoldedAPI", cegid_api: "CegidAPI", apply_offset=True):
        invoices = await holded_api.list_invoices()
        invoices.sort(key=lambda x: x["date"])  # oldest first

        total_invoices = len(invoices)
        offset = get_offset(holded_api.api_key) if apply_offset else 0
        if offset >= total_invoices:
            print("Offset >= total invoices, nothing to process.")
            return

        invoices_to_process = invoices[offset:]
        for invoice in invoices_to_process:
            details = await holded_api.invoice_details(invoice["id"])
            client_data = await holded_api.get_client(invoice.get("contact"))
            invoice_pdf = await holded_api.get_invoice_document_pdf(invoice["id"])
            transformed = await self.transform_invoice_holded_to_cegid(details, client_data)

            # print(f"Processing doc {doc}")
            print(transformed)

            
            # Cegid Calls
            document = {
                "Ejercicio": transformed["Ejercicio"],
                "Serie": transformed["Serie"],
                "Documento": transformed["Documento"],
                "NombreArchivo": f"{transformed['Serie']}-{transformed['Documento']}.pdf",
                "Archivo": invoice_pdf
            }
            # print(document)

            await cegid_api.crear_factura(transformed)
            # await cegid_api.add_documento_factura(document)

            # increment_offset(holded_api.api_key)
            

            break

    async def transform_invoice_holded_to_cegid(self, holded_invoice: dict, holded_client: dict) -> dict:
        """
        Convert a single Holded invoice + client data into a Cegid-compatible JSON structure,
        including multi-VAT-rate handling for up to four distinct rates.
        """

        # -- 1) BASIC INFO FROM docNumber --
        doc_number = holded_invoice.get("docNumber", "")
        parts = doc_number.split("-")
        serie = "-".join(parts[:2]) if len(parts) >= 2 else f"A-{datetime.now().year}"
        ejercicio = parts[1] if len(parts) >= 2 else str(datetime.now().year)
        documento = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0

        # -- 2) DATES --
        now_ts = int(datetime.now().timestamp())
        fecha = holded_invoice.get("date", now_ts)  # e.g. invoice date
        fecha_vencimiento = holded_invoice.get("dueDate") or fecha

        # -- 3) DESCRIPTION (check 'customFields' for Factura simplificada) --
        descripcion_factura = holded_invoice.get("desc", "")
        for cf in holded_invoice.get("customFields", []):
            if cf.get("field") == "Factura simplificada":
                descripcion_factura = cf["field"]

        # -- 4) CLIENT INFO --
        nombre_cliente = holded_invoice.get("contactName", "")
        cuenta_cliente = holded_invoice.get("contact", "")  # ID interno de Holded

        # Extract from holded_client if available
        vat_number = holded_client.get("vatnumber", "") or None
        bill_address = holded_client.get("billAddress", {})
        direccion = bill_address.get("address", "")
        ciudad = bill_address.get("city", "")
        cp = bill_address.get("postalCode", "")
        provincia = bill_address.get("province", "")
        pais = bill_address.get("country", "")

        # -- 5) GATHER LINES & GROUP BY TAX RATE (for multi-VAT) --
        vat_groups = defaultdict(float)  # {tax_rate: total_net_base}
        lines = holded_invoice.get("products", [])

        for prod in lines:
            net_line = prod.get("price", 0.0) * prod.get("units", 0.0)
            tax_rate = prod.get("tax", 0.0)  # e.g. 10, 4, 21
            vat_groups[tax_rate] += net_line

        # Summaries for total invoice
        base_total = 0.0
        iva_total = 0.0

        # -- 6) BUILD THE FACTURA SKELETON (excluding base/iva for now) --
        factura = {
            "Ejercicio": ejercicio,
            "Serie": serie,
            "Documento": documento,
            "TipoAsiento": "FacturasEmitidas",
            "Fecha": fecha,                 # Fecha del asiento
            "FechaFactura": fecha,         # Fecha de la factura
            "CuentaCliente": cuenta_cliente,
            "Descripcion": descripcion_factura,
            "TipoFactura": "OpInteriores", # Adjust if needed
            "NombreCliente": nombre_cliente,
            # We add lines in 'Detalles' below
            # We'll add 'Vencimientos' below
        }

        # If we have a valid VAT number
        if vat_number:
            factura["CifCliente"] = vat_number

        # Optional address fields, if your Cegid setup wants them
        factura["DireccionCliente"] = direccion
        factura["CiudadCliente"] = ciudad
        factura["CPCliente"] = cp
        factura["ProvinciaCliente"] = provincia
        factura["PaisCliente"] = pais

        # -- 7) MULTI-VAT-FIELD HANDLING (BaseImponible1..4, CuotaIVA1..4, PorcentajeIVA1..4) --
        # Sort rates so you always fill in a consistent order
        sorted_rates = sorted(vat_groups.keys())
        max_vat_slots = 4
        idx = 1

        for rate in sorted_rates:
            if idx > max_vat_slots:
                # If you exceed 4 rates, choose how to handle (merge or throw an error).
                # We'll just break here. Real code might do something else.
                break

            base_i = vat_groups[rate]
            cuota_i = base_i * (rate / 100.0)

            factura[f"BaseImponible{idx}"] = round(base_i, 2)
            factura[f"CuotaIVA{idx}"] = round(cuota_i, 2)
            factura[f"PorcentajeIVA{idx}"] = rate

            base_total += base_i
            iva_total += cuota_i
            idx += 1

        # Summation for the total (base + IVA)
        total_factura = base_total + iva_total
        factura["TotalFactura"] = round(total_factura, 2)

        # -- 8) CREATE "DETALLES" LINES --
        detalles = []
        for i, prod in enumerate(lines, start=1):
            neto_linea = prod.get("price", 0.0) * prod.get("units", 0.0)
            line_desc = prod.get("desc", "")
            detalles.append({
                "Ejercicio": ejercicio,
                "Serie": serie,
                "Documento": documento,
                "Linea": i,
                "Concepto": 1001,
                "Cuenta": prod.get("account", ""),
                "Fecha": fecha,
                "Debe": neto_linea,
                "Haber": 0,
                "Descripcion": line_desc,
                "Contrapartida": "400001",      # Adjust according to your chart of accounts
                "Justificante": prod.get("sku", ""),
                "PunteoBancario": 0,
                "PunteoCuenta": "",
                "Tercero": cuenta_cliente
            })

        factura["Detalles"] = detalles

        # -- 9) VENCIMIENTOS --
        vencimientos = []
        mdd = holded_invoice.get("multipledueDate")
        # If it's an array of partial payments
        if isinstance(mdd, list) and mdd:
            for idx, v in enumerate(mdd, start=1):
                vencimientos.append({
                    "Ejercicio": ejercicio,
                    "Serie": serie,
                    "Documento": documento,
                    "NumeroVencimiento": idx,
                    "FechaFactura": fecha,
                    "CuentaCliente": cuenta_cliente,
                    "NumeroFactura": doc_number,
                    "FechaVencimiento": v.get("date", fecha),
                    "Importe": v.get("amount", 0.0),
                    "CodigoTipoVencimiento": 1
                })
        elif isinstance(mdd, dict) and mdd:
            vencimientos.append({
                "Ejercicio": ejercicio,
                "Serie": serie,
                "Documento": documento,
                "NumeroVencimiento": 1,
                "FechaFactura": fecha,
                "CuentaCliente": cuenta_cliente,
                "NumeroFactura": doc_number,
                "FechaVencimiento": mdd.get("date", fecha),
                "Importe": mdd.get("amount", 0.0),
                "CodigoTipoVencimiento": 1
            })
        else:
            # Single payment = entire total
            vencimientos.append({
                "Ejercicio": ejercicio,
                "Serie": serie,
                "Documento": documento,
                "NumeroVencimiento": 1,
                "FechaFactura": fecha,
                "CuentaCliente": cuenta_cliente,
                "NumeroFactura": doc_number,
                "FechaVencimiento": fecha_vencimiento,
                "Importe": round(total_factura, 2),
                "CodigoTipoVencimiento": 1
            })

        factura["Vencimientos"] = vencimientos

        return factura
    
    async def push_invoices_to_cegid(self, transformed_invoices, cegid_api: "CegidAPI"):
        for inv in transformed_invoices:
            try:
                result = await cegid_api.push_invoice(inv)
                print(f"[DEBUG] Invoice pushed, result: {result}")
            except Exception as e:
                print(f"[ERROR] Pushing invoice to Cegid failed: {e}")

    async def fetch_holded_accounts(self, apply_offset=True):
        cegid_api = CegidAPI()
        for account in HOLDED_ACCOUNTS:
            holded_api = HoldedAPI(account['api_key'])
            await self.process_account_invoices(holded_api, cegid_api, apply_offset)
            # remove 'break' if you want all accounts processed
            break

async def main_test():
    async_service = AsyncService()
    await async_service.fetch_holded_accounts(True)

if __name__ == "__main__":
    asyncio.run(main_test())
