import json
import os

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")

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

