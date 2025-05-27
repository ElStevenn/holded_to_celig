import asyncio
from services.sync_service import AsyncService
from services.cegid_service import CegidAPI

async def test1():
    cegid_api = CegidAPI()

    # account = await cegid_api.get_subcuenta("43009999"); print("account -> ", account)

    
    # await cegid_api.renew_token_api_contabilidad()
    # sub_accounts = await cegid_api.get_subcuentas(); print("sub_accounts -> ", sub_accounts)


    # for acc in sub_accounts:
    #     print("Código",acc.get("Codigo"))
    #     print("Nombre",acc.get("Descripcion"))
    #     print("*****")
    

async def main():
    await test1()


if __name__ == "__main__":
    asyncio.run(main())


