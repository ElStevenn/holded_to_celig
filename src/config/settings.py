import json
import os
from dotenv import load_dotenv

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
print("Credentials file path:", CREDENTIALS_FILE)
try:
    with open(CREDENTIALS_FILE, "r") as f:
        credentials = json.load(f)
except json.JSONDecodeError as e:
    raise json.JSONDecodeError("Error decoding credentials.json", e.doc, e.pos)
except FileNotFoundError:
    raise FileNotFoundError(f"Credentials file not found: {CREDENTIALS_FILE}")

HOLDED_ACCOUNTS  = credentials["holded_accounts"]

USERNAME = credentials["cegid"]["username"]
PASSWORD = credentials["cegid"]["password"]

# API CONTAVILIDAD
CLIENT_ID_CONT = credentials["cegid"]["api_contavilidad"]["clientId"]
CLIENT_SECRET_CONT = credentials["cegid"]["api_contavilidad"]["clientSecret"]

# REDIS
REDIS_URL = 'redis://redis:6379/0'

def update_token_con(new_token):
    with open(CREDENTIALS_FILE, "w") as f:
        credentials["cegid"]["api_contavilidad"]["auth_token"] = new_token
        json.dump(credentials, f, indent=4)

def token_con():
    with open(CREDENTIALS_FILE, "r") as f:
        credentials = json.load(f)
        return credentials["cegid"]["api_contavilidad"]["auth_token"]

# API ERP
CLIENT_ID_ERP = credentials["cegid"]["api_erp"]["clientId"]
CLIENT_SECRET_ERP = credentials["cegid"]["api_erp"]["clientSecret"]

def token_erp():
    with open(CREDENTIALS_FILE, "r") as f:
        credentials = json.load(f)
        return credentials["cegid"]["api_erp"]["auth_token"]

def update_token_erp(new_token):
    with open(CREDENTIALS_FILE, "w") as f:
        credentials["cegid"]["api_erp"]["auth_token"] = new_token
        json.dump(credentials, f, indent=4)

# HANDLE OFFSET
def set_offset(api_key, new_offset):
    with open(CREDENTIALS_FILE, "w") as f:
        for account in HOLDED_ACCOUNTS:
            if account["api_key"] == api_key:
                account["offset"] = new_offset
        json.dump(credentials, f, indent=4)

def increment_offset(api_key):
    with open(CREDENTIALS_FILE, "r") as f:
        data = json.load(f)
    for account in data["holded_accounts"]:
        if account["api_key"] == api_key:
            account["offset"] += 1
            break
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_offset(api_key: str) -> int:
    try:
        with open(CREDENTIALS_FILE, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0

    for acct in data.get("holded_accounts", []):
        if acct.get("api_key") == api_key:
            # devolvemos siempre el campo "offset"
            return int(acct.get("offset", 0))
    return 0

# UTILS
def get_offset_doc(nombre_empresa):
    with open(CREDENTIALS_FILE, "r") as f:
        data = json.load(f)

    for account in data["holded_accounts"]:
        if account.get("nombre_empresa") == nombre_empresa:
            return account.get("offset_documento", 0)

    return 0

def update_offset_doc(nombre_empresa):
    with open(CREDENTIALS_FILE, "r") as f:
        data = json.load(f)

    for account in data["holded_accounts"]:
        if account.get("nombre_empresa") == nombre_empresa:
            account["offset_documento"] = account.get("offset_documento", 0) + 1
            break  # Stop once we've found and updated the correct company

    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_cegid_subcuenta_offset():
    with open(CREDENTIALS_FILE, "r") as f:
        data = json.load(f)

    offset = data["cegid"]["subcuenta_offset"]
    return offset

def update_cegid_subcuenta_offset():
    with open(CREDENTIALS_FILE, "r") as f:
        data = json.load(f)

    data["cegid"]["subcuenta_offset"] += 1

    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(data, f, indent=4)