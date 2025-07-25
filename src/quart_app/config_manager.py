# src/quart_app/config_manager.py
import json
from pathlib import Path
from typing import Dict, Any, List
from src.config.settings import CREDENTIALS_FILE as _CREDENTIALS_FILE  # viene como str

CREDENTIALS_FILE: Path = Path(_CREDENTIALS_FILE)  # <- lo convertimos aquí


def cargar_config() -> Dict[str, Any]:
    if not CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        config_inicial: Dict[str, Any] = {
            "holded_accounts": [],
            "cegid": {
                "username": "",
                "password": "",
                "subcuenta_offset": 0,
                "api_contavilidad": {
                    "auth_token": "",
                    "clientId": "",
                    "clientSecret": ""
                },
                "api_erp": {
                    "auth_token": "",
                    "clientId": "",
                    "clientSecret": ""
                }
            }
        }
        guardar_config(config_inicial)
        return config_inicial

    with CREDENTIALS_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def guardar_config(config: Dict[str, Any]) -> None:
    with CREDENTIALS_FILE.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)


def obtener_holded_por_id(config: Dict[str, Any], _id: str) -> Dict[str, Any] | None:
    for acc in config.get("holded_accounts", []):
        if acc.get("id") == _id:
            return acc
    return None


def validar_holded(form: Dict[str, Any]) -> List[str]:
    errores: List[str] = []
    obligatorios = [
        "nombre_empresa", "api_key",
        "codigo_empresa", "offset_documento", "tipo_cuenta"
    ]
    for campo in obligatorios:
        if not form.get(campo):
            errores.append(f"El campo '{campo}' es obligatorio.")

    cuentas = form.getlist("cuentas_a_migrar[]")
    offsets = form.getlist("offset_cuentas_a_migrar[]")

    # SOLO validar si hay algo en cuentas
    if cuentas and len(cuentas) != len(offsets):
        errores.append("Las listas de cuentas y offsets no coinciden.")

    for i, off in enumerate(offsets):
        if off and not off.strip().lstrip("-").isdigit():
            errores.append(f"Offset #{i+1} no es un entero.")

    return errores

def to_int(value, default=0):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default