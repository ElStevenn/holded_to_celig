import aiohttp
import asyncio
import json
import base64
import requests
import os

"""API class to interactuate with Holded"""


class HoldedAPI():
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.holded.com/v1"
        self.docType_invoice = "invoice"

    async def list_invoices(self, starttmp = None, endtmp = None):
        url = self.base_url + f"/invoicing/v1/documents/{self.docType_invoice}"
        query_params = {
            "start": starttmp,
            "end": endtmp,
        }

    async def invoice_details(self, documentId):
        url = self.base_url + f"/invoicing/v1/documents/{self.docType_invoice}/{documentId}"


    async def list_clients(self):
        pass


    
    async def invoice_pdf(self, documentId, output_filename="invoice.pdf"):
        url = f"{self.base_url}/invoicing/v1/documents/{self.docType_invoice}/{documentId}/pdf"
        headers = {"accept": "application/json", "key": self.api_key}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as res:
                    if res.status != 200:
                        return None

                    data = await res.json()
                    if data.get("status") != 1 or "data" not in data:
                        return None

                    pdf_data = base64.b64decode(data["data"])

                    with open(output_filename, "wb") as pdf_file:
                        pdf_file.write(pdf_data)

                    return output_filename  

            except aiohttp.ClientError:
                return None
            

    async def client_details(self, client_id):
        pass


    async def payments(self, client_id, doc_id):
        """Optional"""
        pass
    
def get_invoice_pdf():
    url = "https://api.holded.com/api/invoicing/v1/documents/invoice/67af388ecad68cc3060adba3/pdf"
    headers = {"accept": "application/json", "key": "dc280045a98d2dfa0b8a49f74adbd60a"}

    res = requests.get(url, headers=headers)
    data = res.json()

    if data.get("status") == 1 and "data" in data:
        pdf_data = base64.b64decode(data["data"])
        with open("invoice.pdf", "wb") as pdf_file:
            pdf_file.write(pdf_data)
        print("PDF saved as invoice.pdf")
    else:
        print("Error fetching invoice")

async def main_test():
    get_invoice_pdf()

if __name__ == "__main__":
    asyncio.run(main_test())