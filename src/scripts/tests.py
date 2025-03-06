import asyncio
import pandas as pd

from src.services.holded_service import HoldedAPI



async def main_test():
    holded_account = HoldedAPI("dc280045a98d2dfa0b8a49f74adbd60a")

    clients = await holded_account.list_invoices()
    print(clients)


if __name__ == "__main__":
    asyncio.run(main_test())
