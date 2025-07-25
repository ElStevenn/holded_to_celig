import os
import uuid
import base64
from functools import wraps
from typing import Dict
import asyncio
from quart import (
    Quart, render_template, request, jsonify, redirect,
    url_for, flash, Response
)

from src.quart_app.config_manager import (
    cargar_config, guardar_config,
    obtener_holded_por_id, validar_holded, to_int
)
from src.services.sync_service import AsyncService
from src.services.holded_service import HoldedAPI
from src.services.cegid_service import CegidAPI   

# ------------------ Config básica ------------------
ADMIN_USER = os.environ.get("BASIC_AUTH_USER", "admin")
ADMIN_PASS = os.environ.get("BASIC_AUTH_PASS", "12345")
EXPORT_TASKS: Dict[str, asyncio.Task] = {}

app = Quart(__name__)
app.secret_key = "cambia_esto_por_una_clave_segura"


# ------------------ Basic Auth ------------------
def _unauthorized():
    return Response(
        "Auth required", 401,
        {"WWW-Authenticate": 'Basic realm="Integración Holded↔Cegid"'}
    )

def _check_auth(header_value: str) -> bool:
    if not header_value or not header_value.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header_value.split(" ", 1)[1]).decode("utf-8")
        user, pwd = decoded.split(":", 1)
    except Exception:
        return False
    return user == ADMIN_USER and pwd == ADMIN_PASS

def basic_auth_required(fn):
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        if _check_auth(request.headers.get("Authorization")):
            return await fn(*args, **kwargs)
        return _unauthorized()
    return wrapper

# Si quieres proteger TODO salvo estáticos:
@app.before_request
async def proteger_todo():
    # permite estáticos y favicon sin auth (comenta si no quieres)
    if request.path.startswith("/static") or request.path == "/favicon.ico":
        return None
    if _check_auth(request.headers.get("Authorization")):
        return None
    return _unauthorized()

async def _run_export_job(acc: dict, cfg_cegid: dict):
    """
    Lanza el volcado para UNA cuenta Holded.
    Recorre sus tipos de documento y llama a process_account_invoices.
    """
    service = AsyncService()

    # Instancia APIs según tus clases reales
    holded_api = HoldedAPI(api_key=acc["api_key"])
    cegid_api  = CegidAPI(acc["codigo_empresa"])

    # (opcional pero típico)
    if hasattr(cegid_api, "renew_token_api_contabilidad"):
        await cegid_api.renew_token_api_contabilidad()

    nombre_empresa = acc["nombre_empresa"]
    tipo_cuenta    = acc["tipo_cuenta"]

    # Si no hay lista, al menos procesar invoice
    for doc_type in acc.get("cuentas_a_migrar", ["invoice"]):
        await service.process_account_invoices(
            holded_api=holded_api,
            cegid_api=cegid_api,
            nombre_empresa=nombre_empresa,
            tipo_cuenta=tipo_cuenta,
            doc_type=doc_type
        )



# ------------------ Rutas ------------------
@app.route("/")
@basic_auth_required
async def index():
    config = cargar_config()
    return await render_template("set_configuration.html", config=config)


# ------- API JSON -------
@app.route("/api/config", methods=["GET"])
@basic_auth_required
async def api_get_config():
    return jsonify(cargar_config())

@app.route("/api/config", methods=["POST"])
@basic_auth_required
async def api_post_config():
    data = await request.get_json()
    if not data:
        return jsonify({"error": "JSON inválido"}), 400
    guardar_config(data)
    return jsonify({"ok": True})


# ------- CRUD Holded -------
@app.route("/holded/nuevo", methods=["POST"])
@basic_auth_required
async def crear_holded():
    form = await request.form
    errores = validar_holded(form)
    if errores:
        for e in errores:
            await flash(e, "danger")
        return redirect(url_for("index"))

    config = cargar_config()

    # Limpia listas (quita vacíos si quieres)
    cuentas_raw = form.getlist("cuentas_a_migrar[]")
    offsets_raw = form.getlist("offset_cuentas_a_migrar[]")

    nuevo = {
        "id": str(uuid.uuid4()),
        "nombre_empresa": form.get("nombre_empresa"),
        "api_key": form.get("api_key"),
        "codigo_empresa": form.get("codigo_empresa"),
        "offset_documento": to_int(form.get("offset_documento"), 0),
        "tipo_cuenta": form.get("tipo_cuenta"),
        "cuentas_a_migrar": cuentas_raw,
        "offset_cuentas_a_migrar": [to_int(x, 0) for x in offsets_raw],
    }

    config["holded_accounts"].append(nuevo)
    guardar_config(config)
    await flash("Cuenta de Holded creada.", "success")
    return redirect(url_for("index"))


@app.route("/holded/<id>/editar", methods=["POST"])
@basic_auth_required
async def editar_holded(id):
    form = await request.form
    print("EL form es:", form)
    errores = validar_holded(form)
    if errores:
        for e in errores:
            await flash(e, "danger")
        return redirect(url_for("index"))

    config = cargar_config()
    cuenta = obtener_holded_por_id(config, id)
    if not cuenta:
        await flash("Cuenta no encontrada.", "danger")
        return redirect(url_for("index"))

    cuenta.update({
        "nombre_empresa": form.get("nombre_empresa"),
        "api_key": form.get("api_key"),
        "codigo_empresa": form.get("codigo_empresa"),
        "offset_documento": int(form.get("offset_documento")),
        "tipo_cuenta": form.get("tipo_cuenta"),
        "cuentas_a_migrar": form.getlist("cuentas_a_migrar[]"),
        "offset_cuentas_a_migrar": [
            int(x) for x in form.getlist("offset_cuentas_a_migrar[]") if x.strip().isdigit()
        ]

    })
    guardar_config(config)
    print("✅ Config actualizada y guardada:", config)
    await flash("Cuenta de Holded actualizada.", "success")
    return redirect(url_for("index"))


@app.route("/holded/<id>/eliminar", methods=["POST"])
@basic_auth_required
async def eliminar_holded(id):
    config = cargar_config()
    antes = len(config["holded_accounts"])
    config["holded_accounts"] = [a for a in config["holded_accounts"] if a.get("id") != id]
    despues = len(config["holded_accounts"])
    if antes == despues:
        await flash("No se encontró la cuenta a eliminar.", "warning")
    else:
        await flash("Cuenta eliminada.", "success")
    guardar_config(config)
    return redirect(url_for("index"))



@app.route("/holded/<id>/duplicar", methods=["POST"])
@basic_auth_required
async def duplicar_holded(id):
    config = cargar_config()
    cuenta = obtener_holded_por_id(config, id)
    if not cuenta:
        await flash("Cuenta no encontrada para duplicar.", "danger")
        return redirect(url_for("index"))

    copia = cuenta.copy()
    copia["id"] = str(uuid.uuid4())
    copia["nombre_empresa"] += " (copia)"
    config["holded_accounts"].append(copia)
    guardar_config(config)
    await flash("Cuenta duplicada.", "success")
    return redirect(url_for("index"))


@app.route("/holded/<id>/exportar", methods=["POST"])
@basic_auth_required
async def exportar_holded(id):
    config = cargar_config()
    cuenta = obtener_holded_por_id(config, id)
    if not cuenta:
        return jsonify({"ok": False, "error": "Cuenta no encontrada"}), 404

    task_id = str(uuid.uuid4())
    task = asyncio.create_task(_run_export_job(cuenta, config["cegid"]))
    EXPORT_TASKS[task_id] = task

    def _done_callback(t: asyncio.Task, tid=task_id):
        # quítala de la tabla siempre
        EXPORT_TASKS.pop(tid, None)

        if t.cancelled():
            print(f"[EXPORT TASK CANCELLED] {tid}")
            return

        try:
            t.result() 
        except asyncio.CancelledError:
            print(f"[EXPORT TASK CANCELLED] {tid}")
        except Exception as e:
            print(f"[EXPORT TASK ERROR] {tid}: {e}")

    task.add_done_callback(_done_callback)
    return jsonify({"ok": True, "task_id": task_id}), 202


@app.route("/tasks/<task_id>", methods=["GET"])
@basic_auth_required
async def task_status(task_id):
    t = EXPORT_TASKS.get(task_id)
    return jsonify({"exists": bool(t), "done": (t.done() if t else True)})


if __name__ == "__main__":
    # Usa hypercorn o el server integrado
    app.run(debug=True)
