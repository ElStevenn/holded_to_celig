import aiohttp
import asyncio
import json
import base64
import requests
import os

from src.config.settings import HOLDED_ACCOUNTS


class HoldedAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.holded.com/api"
        self.docType_invoice = "invoice"

    async def list_invoices(self, starttmp=None, endtmp=None):
        url = f"{self.base_url}/invoicing/v1/documents/{self.docType_invoice}"
        params = {}
        if starttmp:
            params["starttmp"] = starttmp
        if endtmp:
            params["endtmp"] = endtmp

        headers = {
            "accept": "application/json",
            "key": self.api_key,
            "User-Agent": "Mozilla/5.0 (compatible; MyApp/1.0)"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as res:
                try:
                    data = await res.json()
                except Exception as e:
                    print("JSON Decode Error:", e)
                    return []
                if res.status != 200:
                    print("Error listing invoices:", data)
                    return []
                return data

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
                if res.status != 200:
                    return None
                try:
                    data = await res.json()
                except:
                    return None
                if "data" not in data:
                    return None
                return data["data"]

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
        print("Error fetching invoice PDF")


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
    holded_account = HoldedAPI("dc280045a98d2dfa0b8a49f74adbd60a")

    # 1. Fetch summarized invoice list
    invoice_list = await holded_account.list_invoices()
    print("List Invoices:", invoice_list)

    # 2. Fetch details of a single invoice if needed
    if invoice_list:
        some_invoice_id = invoice_list[0].get("id")
        details = await holded_account.invoice_details(some_invoice_id)
        print("Invoice Details:", details)

    # 3. Migrate from multiple accounts (if HOLDED_ACCOUNTS is set)
    # data = await migrate_invoices_from_all_accounts()
    # print("Data from all accounts:", data)

if __name__ == "__main__":
    asyncio.run(main_test())
