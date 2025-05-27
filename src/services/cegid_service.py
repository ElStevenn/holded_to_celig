import asyncio
import aiohttp
from datetime import datetime
import json
import base64

from config.settings import (
        USERNAME,
        PASSWORD, 
        CLIENT_ID_ERP, 
        CLIENT_SECRET_ERP, 
        CLIENT_ID_CONT, 
        CLIENT_SECRET_CONT, 
        token_con,
        token_erp,
        update_token_con, 
        update_token_erp 
    )

"""API class to interactuate with Holded"""

class CegidAPI:
    def __init__(self):
        self.api_erp = "http://apierp.diezsoftware.com"
        self.api_con = "https://apicon.diezsoftware.com"
        self.api_rec = "https://apirec.diezsoftware.com"
        self.username = USERNAME
        self.password = PASSWORD

        # API CONTAVILIDAD
        self.client_id_con = CLIENT_ID_CONT
        self.client_secret_con = CLIENT_SECRET_CONT
        self.auth_token_con = token_con()

        # API ERP
        self.client_id_erp = CLIENT_ID_ERP
        self.client_secret_erp = CLIENT_SECRET_ERP
        self.auth_token_erp = token_erp()

    # Token nenew
    async def renew_token_erp(self):
        """Renews token for the ERP API"""
        url = self.api_erp + "/api/auth/login"
        body = {
            "username": self.username,
            "password": self.password,
            "clientId": self.client_id_erp,
            "clientSecret": self.client_secret_erp,
            "cod_empresa": 8
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body) as res:

                if res.status != 200:
                    return None

                if res.content_type == 'application/json':
                    data = await res.json()
                else:
                    data = json.loads(await res.text())

                auth_token = data.get("auth_token")
                if auth_token:
                    print("New auth token generated: ", auth_token)
                    update_token_erp(auth_token)
                else:
                    print("Auth token not found in the response")

    async def renew_token_api_contabilidad(self):
        url = self.api_con + "/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            # "Cookie": "ARRAffinity=d4e7f1765b153fe7b523c609e183d777b6e3886e1149a117ca33ca6afd0901cd"
        }

        body = {
            "grant_type": "password",
            "client_secret": self.client_secret_con,
            "username": self.username,
            "password": self.password,
            "cod_empresa": "8",
            "client_id": self.client_id_con
        }

        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, data=body, headers=headers) as res:
    
                    if res.status == 200:
                        data = await res.json()
                        acces_token = data.get("access_token")
                        print("new acces token for api contavilidad: ", acces_token)
                        update_token_con(acces_token)
                    else:
                        print(f"Error: {res.status} - {await res.text()}")        
            except aiohttp.ClientError as e:
                print(f"Request failed: {e}")
                   
    # Client Operatooms
    async def get_clientes(self):
        url = self.api_con + "/api/clientes"
        headers = {
            "Authorization": f"Bearer {self.auth_token_con}",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as res:
                 
                response_text = await res.text()

                try:
                    response_json = json.loads(response_text)  
                except json.JSONDecodeError:
                    print(f"Failed to decode JSON. Raw response:\n{response_text}")
                    return None

                print("Full API Response:", json.dumps(response_json, indent=4))

                if res.status == 401:
                    await self.renew_token_api_contabilidad()
                    return await self.get_clientes()

                if res.status != 200:
                    return response_json
                

                return response_json.get("Datos")

    async def create_cliente(self, nombre_fiscal, nombre_comercial, cif, direccion, codigo_postal, poblacion, provincia, telefono, aplicarRetencion: bool, aplicar_recargo_equivalencia: bool, grupo_ingresos, fax, cliente_generico: bool, no_incluir347: bool, no_activo: bool, pais, mail, empresa: int, tipo_identificador: int, criterio_caja: bool):
        url = self.api_con + "/api/clientes/add"
        headers = {
            "Authorization": f"Bearer {self.auth_token_con}",
            "Content-Type": "application/json"
        }

        clientes = await self.get_clientes()
        codigo = int(clientes[-1]['Codigo'] +1)

        body = {
            "Codigo": codigo,
            "NombreFiscal": nombre_fiscal,
            "NombreComercial": nombre_comercial,
            "CIF": cif,
            "Direccion": direccion,
            "CodigoPostal": codigo_postal,
            "Poblacion": poblacion,
            "Provincia": provincia,
            "Telefono": telefono,
            "AplicarRetencion": aplicarRetencion,
            "AplicarRecargoEquivalencia": aplicar_recargo_equivalencia,
            "GrupoIngresos": grupo_ingresos,
            "Fax": fax,
            "ClienteGenerico": cliente_generico,
            "NoIncluir347": no_incluir347,
            "NoActivo": no_activo,
            "Pais": pais,
            "Mail": mail,
            "Empresa": empresa,
            "TipoIdentificador": tipo_identificador,
            "CriterioCaja": criterio_caja
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url=url, json=body, headers=headers) as res:
                if res.status == 401:
                    await self.renew_token_api_contabilidad()
                    return await self.create_cliente(nombre_fiscal, nombre_comercial, cif, direccion, codigo_postal, poblacion, provincia, telefono, aplicarRetencion, aplicar_recargo_equivalencia, grupo_ingresos, fax, cliente_generico, no_incluir347, no_activo, pais, mail, empresa, tipo_identificador, criterio_caja)
                elif res.status != 200:
                    return None
                
                data = await res.json()
                print(data)
    
    # Invoices Operations
    async def crear_factura(self, invoice: dict):
        url = self.api_con + "/api/facturas/add"
        body = invoice
        headers = {
            "Authorization": f"Bearer {self.auth_token_con}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers) as res:
                print(res.status)
                
                if res.status == 401:
                    await self.renew_token_api_contabilidad()
                    return await self.crear_factura(invoice)

                if res.status != 200:
                    error = await res.json()
                    print(f"An error ocurred: {res.status} : {error}")
                

                data = await res.json()
                print(data)

    async def add_documento_factura(self, invoice_file: dict):
        url = self.api_con + "/api/facturas/upload"
        headers = {
            "Authorization": f"Bearer {self.auth_token_con}",
            "Content-Type": "application/json"
        }
        body = invoice_file

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers) as res:
                print(res.status)
                if res.status != 200:
                    error = await res.json()
                    print(f"An error ocurred: {res.status} : {error}")

                data = await res.json()
                print(data)

    async def get_facturas(self, filter=None, limit=None, offset=None):
        url = self.api_con + "/api/facturas"
        headers = {
            "Authorization": f"Bearer {self.auth_token_con}",
            "Content-Type": "application/json",
            "Cookie": "ARRAffinity=49d137dd25d1540f2af68d43ccaf5064e8eb8aeb9df9f51df15ff60af6a1ddd6"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as res:
                 
                response_text = await res.text()

                try:
                    response_json = json.loads(response_text)  
                except json.JSONDecodeError:
                    print(f"Failed to decode JSON. Raw response:\n{response_text}")
                    return None

                print("Full API Response:", json.dumps(response_json, indent=4))

                if res.status != 200:
                    return response_json

                return response_json.get('datos', None)  
            
    async def get_empresas(self):
        url = self.api_erp + "/api/Company/getCompanies"
        headers = {
            "Authorization": f"Bearer {self.client_secret_erp}",
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as res:
                print(res.status)
                if res.status != 200:
                    return None

                data = await res.json()
                return data['datos']

    async def get_codigo_empresa(self):
        """
        Get Codigo propio de la empresa
        """
        url = self.api_erp + "/api/Company/getOwnCompany"  

        headers = {
            "Authorization": f"Bearer {self.client_secret_erp}", 
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as res:
                response_json = await res.json()
                print("Response ->", response_json) 

                if res.status != 200:
                    return None

                return response_json

    # Series
    async def get_series(self):
        url = self.api_con + "/api/series"
        headers = {
            "Authorization": f"Bearer {self.auth_token_con}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as res:
                 
                response_text = await res.text()

                try:
                    response_json = json.loads(response_text)  
                except json.JSONDecodeError:
                    print(f"Failed to decode JSON. Raw response:\n{response_text}")
                    return None

                print("Full API Response:", json.dumps(response_json, indent=4))

                if res.status != 200:
                    return response_json

                return response_json.get('datos', None)

    async def add_serie(self, codigo: str, descripcion: str = None, actividad: int = None):
        url = self.api_con + "/api/series/add"
        headers = {
            "Authorization": f"Bearer {self.auth_token_con}",
            "Content-Type": "application/json"
        }
        body = {
            "Codigo": codigo,
            "Descripcion": descripcion,
            "Actividad": actividad
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers) as res:
                print(res.status)
                if res.status == 401:
                    await self.renew_token_api_contabilidad()
                    return await self.add_serie(codigo, descripcion, actividad)

                if res.status != 200:
                    error = await res.json()
                    print(f"An error ocurred: {res.status} : {error}")

                data = await res.json()
                print("Response -> ", data )

    async def get_subcuentas(self):
        url = self.api_con + "/api/subcuentas?$skip=100"
        headers = {
            "Authorization": f"Bearer {self.auth_token_con}",
            "Content-Type": "application/json"
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as res:
                 
                response_text = await res.text()

                try:
                    response_json = json.loads(response_text)  
                except json.JSONDecodeError:
                    print(f"Failed to decode JSON. Raw response:\n{response_text}")
                    return None

                if res.status != 200:
                    return response_json

                return response_json.get('Datos', None)

    async def get_subcuenta(self, subcuenta: str):
        url = self.api_con + f"api/subcuentas/subcuenta/{subcuenta}"
        headers = {
            "Authorization": f"Bearer {self.auth_token_con}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as res:
                response_text = await res.text()

                try:
                    response_json = json.loads(response_text)  
                except json.JSONDecodeError:
                    print(f"Failed to decode JSON. Raw response:\n{response_text}")
                    return None

                if res.status != 200:
                    return response_json

                return response_json.get('Datos', None)

async def main_test():
    cegid = CegidAPI()
    await cegid.renew_token_api_contabilidad()


    facturas = await cegid.get_subcuentas(); print(facturas)
    for factura in facturas:
        print(factura['Codigo'], factura['Descripcion'])
    print(len(facturas))
    # print(facturas)

if __name__ == "__main__":
    asyncio.run(main_test())
