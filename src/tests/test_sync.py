import asyncio, base64, time
from services.sync_service import AsyncService
from services.holded_service import HoldedAPI
from services.cegid_service import CegidAPI
from pprint import pprint

def base_64_to_pdf(b64: str) -> str:
    pdf_data = base64.b64decode(b64)
    out_path = "output.pdf"
    with open(out_path, "wb") as f:
        f.write(pdf_data)
    print(f"PDF saved as {out_path}")
    return out_path


async def obtain_holded_invoices():
    holdedService = HoldedAPI("ca61cda9434830f1a913d4d8f2ab88db")
    cegidService = CegidAPI()
    async_service = AsyncService()

    offset = 9
    invoices = list(reversed(await holdedService.list_invoices()))[offset:]


    for invoice in invoices:
        client = await holdedService.get_client(invoice["contact"])
        transformed = await async_service.transform_invoice_holded_to_cegid(invoice, client)
        pdf_b64 = await holdedService.get_invoice_document_pdf(invoice["id"])

        data_to_new_pdf = {
            "Ejercicio": "2025",
            "Serie": "2",
            "Documento": 77,
            "Archivo": pdf_b64,
        }


        # await cegidService.crear_factura(transformed_invoice)
        # await cegidService.add_documento_factura(data_to_new_pdf)
        print(data_to_new_pdf)
        base_64_to_pdf(pdf_b64)

        # time.sleep(5)  # Simulate processing time



    print("Invoices:", len(invoices))

async def main():
    await obtain_holded_invoices()

if __name__ == "__main__":
    asyncio.run(main())
