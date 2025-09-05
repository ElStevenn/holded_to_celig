import json
import os
from dotenv import load_dotenv
import random
import logging

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
logging.getLogger(__name__).debug("[Config] Credentials file path: %s", CREDENTIALS_FILE)
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
def set_offset(api_key: str, account_type: str, new_offset: int) -> None:
    """
    Update the offset_cuentas_a_migrar value for a given api_key and account_type.
    """
    try:
        with open(CREDENTIALS_FILE, "r") as f:
            creds = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        creds = {"holded_accounts": []}

    for acct in creds.get("holded_accounts", []):
        if acct.get("api_key") == api_key:
            cuentas = acct.setdefault("cuentas_a_migrar", [])
            offsets = acct.setdefault("offset_cuentas_a_migrar", [])
            if account_type in cuentas:
                idx = cuentas.index(account_type)
                # ensure the offsets list is long enough
                if idx < len(offsets):
                    offsets[idx] = new_offset
                else:
                    offsets.extend([0] * (idx - len(offsets) + 1))
                    offsets[idx] = new_offset
            else:
                cuentas.append(account_type)
                offsets.append(new_offset)
            break

    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(creds, f, indent=4)
        
def increment_offset(api_key: str, account_type: str) -> None:
    """
    Increment by 1 the offset corresponding to `account_type`
    within `offset_cuentas_a_migrar` for the given `api_key`.
    If the account or the type doesn’t exist yet, add it with initial value 1.
    """
    try:
        with open(CREDENTIALS_FILE, "r") as f:
            creds = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # No file or invalid JSON → initialize structure
        creds = {"holded_accounts": []}

    for acct in creds.get("holded_accounts", []):
        if acct.get("api_key") == api_key:
            # Ensure both lists exist
            types = acct.setdefault("cuentas_a_migrar", [])
            offsets = acct.setdefault("offset_cuentas_a_migrar", [])
            if account_type in types:
                idx = types.index(account_type)
                # Make sure offsets list is long enough
                if idx < len(offsets):
                    offsets[idx] += 1
                else:
                    # Extend with zeros up to this index
                    offsets.extend([0] * (idx - len(offsets) + 1))
                    offsets[idx] = 1
            else:
                # If this type isn't present yet, append it
                types.append(account_type)
                offsets.append(1)
            break
    else:
        # If the api_key wasn't found, create a new entry
        creds.setdefault("holded_accounts", []).append({
            "api_key": api_key,
            "cuentas_a_migrar": [account_type],
            "offset_cuentas_a_migrar": [1]
        })

    # Write changes back to disk
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(creds, f, indent=4)

def get_offset(api_key: str, account_type: str) -> int:
    """
    Return the offset corresponding to `account_type` from
    `offset_cuentas_a_migrar`, or 0 if not found.
    """
    try:
        with open(CREDENTIALS_FILE, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0

    for acct in data.get("holded_accounts", []):
        if acct.get("api_key") == api_key:
            cuentas = acct.get("cuentas_a_migrar", [])
            offsets = acct.get("offset_cuentas_a_migrar", [])
            if account_type in cuentas:
                idx = cuentas.index(account_type)
                if 0 <= idx < len(offsets):
                    return int(offsets[idx])
            # no match → return zero (we no longer use `offset`)
            return 0

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


def generate_cif():
    digits = f"{random.randint(0, 99999999):08d}"
    letters = "TRWAGMYFPDXBNJZSQVHLCKE"  # 23 letras del NIF español
    control_letter = letters[int(digits) % len(letters)]
    return digits + control_letter

if __name__ == "__main__":
    res = get_offset("dc280045a98d2dfa0b8a49f74adbd60a", "estimate"); print(res)
    set_offset("dc280045a98d2dfa0b8a49f74adbd60a", "estimate", 20)
    # increment_offset("dc280045a98d2dfa0b8a49f74adbd60a", "estimate")
    