import asyncio
import aiohttp
from datetime import datetime
import json
import base64
import time
import re
import unicodedata
from src.config.settings import update_cegid_subcuenta_offset, get_cegid_subcuenta_offset
from urllib.parse import quote_plus

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


_DUP_RE = re.compile(
    r"duplicate key value is\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)",
    re.IGNORECASE
)

def _norm_country(value: str | None) -> str:
    if not value:
        return ""
    v = value.strip()
    if len(v) == 2 and v.isalpha():
        return v.upper()
    k = v.lower()
    return COUNTRY_NAME_TO_ISO2.get(k, "")  # devuelve "" si no mapea

def _extract_postal_code(raw: str | None) -> int | None:
    if not raw:
        return None
    # Prioriza dígitos (ej. "NY 101280" -> "101280")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return None
    # Algunos zips USA son 5, pueden venir con 9 (ZIP+4). Tomamos primeros 5.
    digits = digits[:5]
    try:
        return int(digits)
    except ValueError:
        return None

"""API class to interactuate with Holded"""
COUNTRY_NAME_TO_ISO2 = {
    "españa": "ES",
    "spain": "ES",
    "estados unidos": "US",
    "united states": "US",
    "francia": "FR",
    "france": "FR",
    "alemania": "DE",
    "germany": "DE",
    "italia": "IT",
    "italy": "IT",
    "portugal": "PT",
    "united kingdom": "GB",
    "reino unido": "GB",
}



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

    def _is_duplicate_invoice_error(self, text: str) -> bool:
        t = text.lower()
        if _DUP_RE.search(text):
            return True
        if ("cannot insert duplicate key" in t or
            "violation of primary key constraint" in t or
            "duplicate key" in t):
            return True
        return False


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

    async def search_cliente_by_api(self, nif):
        url = self.api_con + f"/api/subcuentas?$filter=NIF eq '{nif}'"
        headers = {
            "Authorization": f"Bearer {self.auth_token_con}",
            "Content-Type": "application/json"
        }

        

    async def _subcuentas(self):
        """Get all subcuentas from both type of client"""
        async with self._subcuentas_lock:
            if self._subcuentas_cache is None:                

                c1, c2 = await asyncio.gather(
                    self.get_subcuentas(1), # Client
                    self.get_subcuentas(2)  # Provider
                )
                self._subcuentas_cache = [c for c in (c1 or []) + (c2 or []) if c]
        return self._subcuentas_cache

    async def search_cliente(self, nif: str , nombre_cliente: str, cliente_type: int): # 1 = cliente → 43…,   2 = proveedor → 40…/41…
        """
        Look up the sub-account code in Cegid.

        * cliente_type = 1  → return only codes starting with '43'
        * cliente_type = 2  → return only codes starting with '40' or '41'
        * otherwise        → always return None
        """
        cuentas = await self._subcuentas()
        if not cuentas or cliente_type not in (1, 2):
            return None

        #  helpers
        def norm(text: str | None) -> str:
            if not text:
                return ""
            txt = unicodedata.normalize("NFKD", text)
            txt = txt.encode("ascii", "ignore").decode()
            return re.sub(r"\s+", " ", txt).strip().lower()

        def clean(n: str | None) -> str:
            return re.sub(r"[^A-Z0-9]", "", (n or "").upper())

        def prefix_ok(codigo: str) -> bool:
            if cliente_type == 1:
                return codigo.startswith("43")
            return codigo.startswith(("40", "41"))   # cliente_type == 2

        # NIF match 
        if nif:
            tn = clean(nif)
            for c in cuentas:
                if prefix_ok(c["Codigo"]) and clean(c.get("NIF")) == tn:
                    return c["Codigo"]

        #  Nombre exacto  
        if nombre_cliente:
            tgt = norm(nombre_cliente)
            for c in cuentas:
                if not prefix_ok(c["Codigo"]):
                    continue
                descr = norm(c.get("Descripcion"))
                nomcom = norm(c.get("NombreComercial"))
                if descr.startswith(tgt) or nomcom.startswith(tgt):
                    return c["Codigo"]

            # Nombre contiene
            for c in cuentas:
                if not prefix_ok(c["Codigo"]):
                    continue
                descr = norm(c.get("Descripcion"))
                nomcom = norm(c.get("NombreComercial"))
                if tgt in descr or tgt in nomcom:
                    return c["Codigo"]

        # nothing found with the required prefix
        return None

    
    # INVOICE OPERATIONS
    async def crear_factura(self, invoice: dict):
        url = f"{self.api_con}/api/facturas/add"
        headers = {
            "Authorization": f"Bearer {self.auth_token_con}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=invoice, headers=headers) as res:
                raw_text = await res.text()

                if res.status == 401:
                    await self.renew_token_api_contabilidad()
                    return await self.crear_factura(invoice)

                try:
                    body = json.loads(raw_text)
                except ValueError:
                    body = {"raw": raw_text}

                if res.status == 500:
                    if self._is_duplicate_invoice_error(raw_text):
                        return "duplicated"
                    return f"Error 500: {body.get('ExceptionMessage') or raw_text}"

                if res.status != 200:
                    return f"Error {res.status}: {body.get('ExceptionMessage') or raw_text}"

                return body

    async def crear_factura_nuevo_sistema(self, invoice: dict):
        url = f"{self.api_con}/api/facturas/addNuevoSistemaSII"
        headers = {
            "Authorization": f"Bearer {self.auth_token_con}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=invoice, headers=headers) as res:
                raw_text = await res.text()

                if res.status == 401:
                    await self.renew_token_api_contabilidad()
                    return await self.crear_factura_nuevo_sistema(invoice)

                try:
                    body = json.loads(raw_text)
                except ValueError:
                    body = {"raw": raw_text}

                if res.status == 500:
                    if self._is_duplicate_invoice_error(raw_text):
                        return "duplicated"
                    return f"Error 500: {body.get('ExceptionMessage') or raw_text}"

                if res.status != 200:
                    return f"Error {res.status}: {body.get('ExceptionMessage') or raw_text}"

                return body
        
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

    async def check_invoice_exists(self, invoice_number: str):
        """Return True/False if the invoice exists, None on unexpected error. | invoice number in holded equals to docNumber"""
        filter_expr = quote_plus(f"NumeroFactura eq '{invoice_number}'")
        url = f"{self.api_con}/api/facturas?$filter={filter_expr}"
        headers = {
            "Authorization": f"Bearer {self.auth_token_con}", 
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as res:
                if res.status == 401:
                    await self.renew_token_api_contabilidad()
                    # retry once with fresh token
                    return await self.check_invoice_exists(invoice_number)

                if res.status != 200:
                    print(f"[WARN] Unexpected status {res.status}: {await res.text()}")
                    return None

                payload = await res.json()
                # print("Response ->", json.dumps(payload, indent=4))
                # Most Cegid endpoints respond with {"value":[…]}
                invoices = payload.get("Datos")

                print(type(invoices))

                return invoices
    
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

    async def add_subcuenta(self, name: str, sub_account_type: int, nif: str = None, email: str = None, telefono: str  = None, bill_address: dict  = None):  # 1 = client | 2 = provider
        """
        Create a Cegid sub-account.
            """
        if sub_account_type == 1:
                base_code = 43_001_000
                cuenta_contable = 430
                tipo_subcuenta = 1
        elif sub_account_type == 2:
                base_code = 40_001_000
                cuenta_contable = 400
                tipo_subcuenta = 2
        else:
                return None

        offset = get_cegid_subcuenta_offset()
        next_code_int = base_code + offset
        update_cegid_subcuenta_offset()

        # Payload base
        data: dict[str, int | str] = {
            "Codigo": str(next_code_int),          # si la API realmente quiere 6 dígitos, ajusta aquí
            "Descripcion": (name or "")[:60],
            "CuentaContable": cuenta_contable,
            "TipoSubcuenta": tipo_subcuenta,
        }

        # Campos opcionales limpios
        if nif:
            data["NIF"] = nif.strip()[:14]
        if email:
            data["Email"] = email.strip()[:60]
        if telefono:
            data["Telefonos"] = telefono.strip()[:30]

        if bill_address:
            addr = (bill_address.get("address") or "").strip()[:60]
            if addr:
                data["DireccionCompleta"] = addr

            # Postal
            postal_raw = (
                bill_address.get("postalCode")
                or bill_address.get("postal_code")
                or bill_address.get("zip")
            )
            postal_int = _extract_postal_code(postal_raw)
            if postal_int is not None:
                data["CodigoPostal"] = postal_int

            city = (bill_address.get("city") or "").strip()[:40]
            if city:
                data["Poblacion"] = city

            prov = (bill_address.get("province") or bill_address.get("state") or "")
            prov = prov.strip()[:40]
            if prov:
                data["Provincia"] = prov

            country = (
                bill_address.get("countryCode")
                or bill_address.get("country_code")
                or bill_address.get("country")
            )
            iso2 = _norm_country(country)
            if iso2:
                data["Pais"] = iso2

        url = f"{self.api_con}/api/subcuentas/add"
        headers = {
            "Authorization": f"Bearer {self.auth_token_con}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            code_int = next_code_int
            for attempt in range(10):
                data["Codigo"] = str(code_int)
                async with session.post(url, headers=headers, json=data) as res:
                    if res.status == 401:
                        await self.renew_token_api_contabilidad()
                        continue
                    if res.status == 200:
                        return data["Codigo"]
                    if res.status == 400:
                        # Mirar si es duplicado
                        try:
                            detail = await res.json()
                        except:
                            detail = {}
                        msgs = [
                            m
                            for v in detail.get("ModelState", {}).values()
                            for m in v
                        ]
                        if any("Ya existe una subcuenta con el código" in m for m in msgs):
                            code_int += 1
                            continue
                        # Postal inválido u otro error: si fue postal y no hemos limpiado, intentar una vez quitarlo
                        if any("CodigoPostal" in k for k in detail.get("ModelState", {})):
                            if "CodigoPostal" in data:
                                data.pop("CodigoPostal", None)
                                # reintenta sin cambiar código
                                continue
                        # Otro 400 → error definitivo
                        raise RuntimeError(
                            f"Add subcuenta failed (400): {detail}"
                        )
                    # Otros códigos
                    text = await res.text()
                    raise RuntimeError(
                        f"Add subcuenta failed ({res.status}): {text}"
                    )

        return None 


            
async def main_test():
    cegid = CegidAPI("72")
    await cegid.renew_token_api_contabilidad()

    factura = {
        "Ejercicio": "2025",
        "Serie": "2",
        "Documento": 654,
        "TipoAsiento": "FacturasRecibidas",
        "Fecha": 20250521,
        "FechaFactura": 20250521,
        "CuentaCliente": "40000550",
        "NumeroFactura": "R-2025-008",
        "Descripcion": "R-2025-008 – ANGEL JESUS PALOMINO DE LA ",
        "TipoFactura": "OpInteriores",
        "NombreCliente": "ANGEL JESUS PALOMINO DE LA OLIVA",
        "ClaveRegimenIva1": "01",
        "ProrrataIva": False,
        "BaseImponible1": 4219.9,
        "PorcentajeIVA1": 12,
        "CuotaIVA1": 506.39,
        "BaseRetencion": 4726.29,
        "PorcentajeRetencion": 2,
        "CuotaRetencion": 94.53,
        "TipoRetencion": "Agricultores",
        "TotalFactura": 4631.76,
        "ImporteCobrado": 4631.76,
        "FechaIntroduccionFactura": 20250521,
        "TipoVencimiento": 1,
        "Vencimientos": [
            {
                "Ejercicio": "2025",
                "Serie": "2",
                "Documento": 654,
                "NumeroVencimiento": 1,
                "FechaFactura": 20250521,
                "CuentaCliente": "40000550",
                "NumeroFactura": "R-2025-008",
                "FechaVencimiento": 20250521,
                "Importe": 4631.76,
                "CodigoTipoVencimiento": 1
            }
        ],
        "Apuntes": [
            {
                "Ejercicio": "2025",
                "Serie": "2",
                "Documento": 654,
                "Linea": 1,
                "Cuenta": "60100000",
                "Concepto": "ACEITUNA ECOLÓGICA VARIEDAD VERDEJA",
                "Fecha": 20250521,
                "Importe": 4219.9,
                "TipoImporte": 1
            }
        ]
    }

    res = await cegid.crear_factura(factura)
    print("THE RES: ", res)




if __name__ == "__main__":
    asyncio.run(main_test())
