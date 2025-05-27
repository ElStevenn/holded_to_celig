import aiohttp
import asyncio
import json
import base64
import requests
import os

from config.settings import HOLDED_ACCOUNTS


class HoldedAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.holded.com/api"
        self.docType_invoice = "invoice"


    async def list_invoices(self):
        url = self.base_url + "/invoicing/v1/documents/invoice"  

        headers = {
            "Accept": "application/json",
            "Key": self.api_key,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as res:
                response_text = await res.text()

                if res.status != 200:
                    print(f"Error: {res.status} - {response_text}")
                    return []

                # Force JSON parsing manually
                try:
                    data = json.loads(response_text)  
              
                    return data  
                except json.JSONDecodeError as e:
                    print(f"JSON Parsing Error: {e}")
                    return []


    async def invoice_details(self, document_id):
        url = f"{self.base_url}/invoicing/v1/documents/{self.docType_invoice}/{document_id}"
        headers = {
            "accept": "application/json",
            "key": self.api_key
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as res:
                if res.status != 200:
                    print(f"Error getting invoice details for {document_id}")
                    return None
                try:
                    return await res.json()
                except:
                    return None

    async def get_client(self, client_id):
        url = f"{self.base_url}/invoicing/v1/contacts/{client_id}"
        headers = {
            "accept": "application/json",
            "key": self.api_key
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as res:
           
                data = await res.json()

                if res.status != 200:
                    return None
            
                return data

    async def invoice_pdf(self, document_id, output_filename="invoice.pdf"):
        url = f"{self.base_url}/invoicing/v1/documents/{self.docType_invoice}/{document_id}/pdf"
        headers = {"accept": "application/json", "key": self.api_key}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers) as res:
                    if res.status != 200:
                        print(f"Error downloading PDF for {document_id}")
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

    async def get_invoice_document_pdf(self, document_id):
        url = self.base_url + f"/invoicing/v1/documents/{self.docType_invoice}/{document_id}/pdf"
        headers = {
            # Even though it's JSON, you might just omit the Accept
            # or set it to 'application/json' if the endpoint specifically requires it:
            "Accept": "application/json",
            "key": self.api_key
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as res:
                if res.status != 200:
                    print(f"Error {res.status} fetching invoice PDF for {document_id}")
                    return None
                try:
                    resp_bytes = await res.read()
                    resp_str = resp_bytes.decode("utf-8")
                    resp_json = json.loads(resp_str)
                    # Now we can access the 'data' key
                    base64_pdf = resp_json.get("data")
                    # If you just need the raw base64 string, return it:
                    return base64_pdf
                except Exception as e:
                    print("Error reading PDF JSON data:", e)
                    return None

async def fetch_and_prepare_invoices(holded_api, starttmp=None, endtmp=None):
    invoices = await holded_api.list_invoices(starttmp, endtmp)
    full_invoices_data = []
    for inv in invoices:
        invoice_id = inv.get("id")
        if not invoice_id:
            continue
        details = await holded_api.invoice_details(invoice_id)
        if not details:
            continue
        # Optionally fetch client data if you need it
        client_id = details.get("contactId")
        client_info = None
        if client_id:
            client_info = await holded_api.get_client(client_id)
        # Build a combined structure that merges invoice + details + client
        full_data = {
            "invoice_summary": inv,
            "invoice_details": details,
            "client_info": client_info
        }
        full_invoices_data.append(full_data)
    return full_invoices_data


async def migrate_invoices_from_all_accounts(starttmp=None, endtmp=None):
    all_data = []
    tasks = []

    for account_key in HOLDED_ACCOUNTS:
        holded_api = HoldedAPI(account_key)
        tasks.append(fetch_and_prepare_invoices(holded_api, starttmp, endtmp))

    results = await asyncio.gather(*tasks)

    for res_per_account in results:
        all_data.extend(res_per_account)

    # Here is where you would insert or transform the data for your own system:
    # For example, you might iterate `all_data` and store each invoice in a DB.
    # For now, just return everything.
    return all_data


async def main_test():
    # Example with a single account key for testing
    holded_account = HoldedAPI("ca61cda9434830f1a913d4d8f2ab88db")

    # 1. Fetch summarized invoice list
    invoice_list = await holded_account.list_invoices()
    # print("List Invoices:", invoice_list[0])
    print(invoice_list[0])

    client = await holded_account.get_invoice_document_pdf(invoice_list[0].get("id"))
    print(client)

    # # 2. Fetch details of a single invoice if needed
    # if invoice_list:
    #     some_invoice_id = invoice_list[0].get("id")
    #     details = await holded_account.invoice_details(some_invoice_id)
    #     print("Invoice Details:", details)

    # # 3. Migrate from multiple accounts (if HOLDED_ACCOUNTS is set)
    # # data = await migrate_invoices_from_all_accounts()
    # # print("Data from all accounts:", data)

if __name__ == "__main__":
    asyncio.run(main_test())
