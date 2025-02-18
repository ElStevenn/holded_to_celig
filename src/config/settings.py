import os
import json


CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")

try:
    with open(CREDENTIALS_FILE) as f:
        credentials = json.load(f)
except FileNotFoundError:
    raise FileNotFoundError("File credentials.json not found")
except json.JSONDecodeError:
    raise json.JSONDecodeError("Error decoding credentials.json")


# Get Holded Accounts
HOLDED_ACCOUNTS = credentials["holded_accounts"]

# CEGID ACCOUNT
CEGID_ACCOUNT = credentials["cegid"]
CEGID_API_KEY = CEGID_ACCOUNT["api_key"]

