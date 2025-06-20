import asyncio
import aiohttp
from datetime import datetime
import json
import base64
import time
import re
import unicodedata
from src.config.settings import update_cegid_subcuenta_offset, get_cegid_subcuenta_offset

from src.config.settings import (
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
    _subcuentas_cache = None
    _subcuentas_lock  = asyncio.Lock()
    
    def __init__(self, cod_empresa):
        self.api_erp = "http://apierp.diezsoftware.com"
        self.api_con = "https://apicon.diezsoftware.com"
        self.username = USERNAME
        self.password = PASSWORD
        self.cod_empresa = cod_empresa

        # API CONTAVILIDAD
        self.client_id_con = CLIENT_ID_CONT
        self.client_secret_con = CLIENT_SECRET_CONT
        self.auth_token_con = token_con()

        # API ERP
        self.client_id_erp = CLIENT_ID_ERP
        self.client_secret_erp = CLIENT_SECRET_ERP
        # self.auth_token_erp = token_erp()

    # RENEW TOKENS
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
        """Renews token for the Contabilidad API"""
        url = self.api_con + "/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        body = {
            "grant_type": "password",
            "client_secret": self.client_secret_con,
            "username": self.username,
            "password": self.password,
            "cod_empresa": str(self.cod_empresa),
            "client_id": self.client_id_con
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=body, headers=headers) as res:
                if res.status == 200:
                    data = await res.json()
                    acces_token = data.get("access_token")
                    if acces_token:
                        update_token_con(acces_token)
                        self.auth_token_con = acces_token
                else:
                    return None
                   
    # CLIENT OPERATIONS
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

    async def _subcuentas(self):
        async with self._subcuentas_lock:
            if self._subcuentas_cache is None:
                c1, c2 = await asyncio.gather(
                    self.get_subcuentas(1),
                    self.get_subcuentas(2)
                )
                self._subcuentas_cache = [c for c in (c1 or []) + (c2 or []) if c]
        return self._subcuentas_cache

    async def search_cliente(self, nif, nombre_cliente):
        cuentas = await self._subcuentas()
        if not cuentas:
            return None

        def norm(t):
            if not t:
                return ""
            t = unicodedata.normalize("NFKD", t)
            t = t.encode("ascii", "ignore").decode()
            return re.sub(r"\s+", " ", t).strip().lower()

        def clean(n):
            return re.sub(r"[^A-Z0-9]", "", (n or "").upper())

        if nif:
            tn = clean(nif)
            for c in cuentas:
                if clean(c.get("NIF")) == tn:
                    return c.get("Codigo")

        if nombre_cliente:
            tgt = norm(nombre_cliente)
            for c in cuentas:
                if norm(c.get("Descripcion")).startswith(tgt) or norm(c.get("NombreComercial")).startswith(tgt):
                    return c.get("Codigo")
            for c in cuentas:
                if tgt in norm(c.get("Descripcion")) or tgt in norm(c.get("NombreComercial")):
                    return c.get("Codigo")

        return None

    
    # INVOICE OPERATIONS
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
                
                if res.status == 500:
                    print("Interval Server Error ocurred", res.text)
                    return 

                data = await res.json()
                print(data)

    async def crear_factura_nuevo_sistema(self, invoice: dict):
        url = self.api_con + "/api/facturas/addNuevoSistemaSII"
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
                    return await self.crear_factura_nuevo_sistema(invoice)

                if res.status != 200:
                    error = await res.json()
                    print(f"An error ocurred: {res.status} : {error}")
                
                if res.status == 500:
                    print("Interval Server Error ocurred", res.text)
                    return 

                data = await res.json()
                print(data)

    async def add_documento_factura(self, invoice_file: dict):
        """Uploads a document for a factura (invoice) to the Cegid API."""
        url = f"{self.api_con}/api/facturas/upload"
        headers = {
            "Authorization": f"Bearer {self.auth_token_con}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(url, json=invoice_file) as res:

                # 401: token caducado 
                if res.status == 401:
                    await self.renew_token_api_contabilidad()
                    return await self.add_documento_factura(invoice_file)

                # leemos el cuerpo UNA sola vez
                body_bytes = await res.read()
                body_text  = body_bytes.decode(errors="replace").strip()

                if res.status == 200:
                    if not body_text:
                        return None

                    try:
                        return json.loads(body_text)
                    except json.JSONDecodeError:
                        return body_text


                try:
                    error = json.loads(body_text) if body_text else {}
                except json.JSONDecodeError:
                    error = body_text or "<sin cuerpo>"

                raise RuntimeError(f"upload falló {res.status}: {error}")

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

    # SERIES
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

    # SUBCUENTAS (cientes)
    async def get_subcuentas(self, tipo_subcuenta: int = 1, top: int = 200):
        rows, page, total = [], 0, None
        async with aiohttp.ClientSession() as session:
            while True:
                url = (
                    f"{self.api_con}/api/subcuentas"
                    f"?$filter=TipoSubcuenta eq '{tipo_subcuenta}'"
                    f"&$top={top}"
                    f"&$skip={page}"
                )
                headers = {
                    "Authorization": f"Bearer {self.auth_token_con}",
                    "Content-Type": "application/json",
                }
                async with session.get(url, headers=headers) as res:
                    if res.status == 401:
                        await self.renew_token_api_contabilidad()
                        continue
                    if res.status != 200:
                        return None
                    payload = await res.json()
                if total is None:
                    total = payload.get("ResultadosTotales", 0)
                datos = payload.get("Datos", [])
                if not datos:
                    break
                rows.extend(datos)
                if len(rows) >= total:
                    break
                page += 1
                await asyncio.sleep(0.5)
        return rows



    
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

    async def add_subcuenta(self, name: str, nif: str | None = None, email: str | None = None, telefono: str | None = None, bill_address: dict | None = None):
        """Add new subcuenta (client) to the Cegid API"""

        def _safe_field(text: str, limit: int) -> str:
            """Return `text` trimmed to `limit` characters (or empty if None)."""
            return (text or "")[:limit].strip()


        # Get new codigo based on the last subcuenta
        cuentas = await self.get_subcuentas(1)
        
        offset = get_cegid_subcuenta_offset()
        new_code = str(int(43001000) + offset).zfill(6)
        update_cegid_subcuenta_offset()

        # Data to create the new subcuenta
        data = {
            "Codigo": new_code,
            "Descripcion": name,
            "CuentaContable": 430,
            "NIF": nif or "",
            "Email": email or "",
            "Telefonos": telefono or "",
            "TipoSubcuenta": 1
        }

        if bill_address:
            address = bill_address.get("address", "")
            if len(address) <= 60:
                data["DireccionCompleta"] = address

            data.update({
                "CodigoPostal" : bill_address.get("postalCode", "")[:5],
                "Poblacion"    : bill_address.get("city", "")[:40],
                "Provincia"    : bill_address.get("province", "")[:40],
                "Pais"         : (bill_address.get("country_code") or "")[:2].upper()
            })

        url = f"{self.api_con}/api/subcuentas/add"
        headers = {
            "Authorization": f"Bearer {self.auth_token_con}",
            "Content-Type": "application/json",
        }

        print("Data", data, "new_code", new_code)
        async with aiohttp.ClientSession() as session:
            attempts = 0
            code_int = int(new_code)
            while attempts < 10:
                data["Codigo"] = str(code_int).zfill(len(new_code))
                async with session.post(url, headers=headers, json=data) as res:
                    if res.status == 401:
                        await self.renew_token_api_contabilidad()
                        continue  # retry same code after token refresh

                    if res.status == 200:
                        return data["Codigo"]

                    detail = await res.json()
                    # if “already exists” error, bump code and retry
                    msgs = [m for v in detail.get("ModelState", {}).values() for m in v]
                    if any("Ya existe una subcuenta con el código" in m for m in msgs):
                        code_int += 1
                        attempts += 1
                        continue

                    # other errors: bail out
                    raise RuntimeError(f"Add subcuenta failed ({res.status}): {detail}")

            # exhausted retries
            return None

            
async def main_test():
    cegid = CegidAPI("72")
    await cegid.renew_token_api_contabilidad()


    # facturas = await cegid.get_subcuentas(1)
    # print(len(facturas), "subcuentas obtenidas")

    for _ in range(10):
        cliente_id = await cegid.search_cliente("", "GARCIA PRIETO"); print("Cliente ID", cliente_id)
    

    # pls = await cegid.add_subcuenta("Miguel Francisco", "14953199W", "zurrom@yahoo.es", "656709940", {'address': 'Calle D. Rodolfo Llopis, 5 2C', 'city': 'Cuenca', 'postalCode': '16002', 'province': 'Cuenca', 'country': 'España', 'countryCode': 'ES', 'info': ''})

if __name__ == "__main__":
    asyncio.run(main_test())
