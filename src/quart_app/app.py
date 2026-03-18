import os
import uuid
import secrets
from functools import wraps
from typing import Dict
import asyncio
import logging
from quart import (
    Quart, render_template, request, jsonify, redirect,
    url_for, flash, Response, session
)

from src.quart_app.config_manager import (
    cargar_config, guardar_config,
    obtener_holded_por_id, validar_holded, to_int
)
from src.services.sync_service import AsyncService
from src.services.holded_service import HoldedAPI
from src.services.cegid_service import CegidAPI   
from src.services.logging_utils import (
    configure_logging,
    set_task_id,
    get_task_logs,
    task_id_ctx,
    record_task_start,
    record_task_done,
    list_tasks,
    get_task_meta,
)

# ------------------ Config básica ------------------
ADMIN_USER = "luis_cebrian" # os.environ.get("BASIC_AUTH_USER", "admin")
ADMIN_PASS = "holacegid123"# os.environ.get("BASIC_AUTH_PASS", "12345")
EXPORT_TASKS: Dict[str, asyncio.Task] = {}

app = Quart(__name__)

# Secret key - MUST be fixed for sessions to persist across app restarts
# Generate one with: python3 -c "import secrets; print(secrets.token_hex(32))"
# Then set it in .env as SECRET_KEY=your-generated-key
SECRET_KEY = "CHANGE_THIS_IN_PRODUCTION_USE_ENV_VAR_SECRET_KEY_12345678901234567890"

app.secret_key = SECRET_KEY

# Security settings for sessions
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True if using HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_NAME'] = 'holded_cegid_session'
# Session lifetime: 30 days (configurable via env var)
from datetime import timedelta
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(seconds=int(os.environ.get("SESSION_LIFETIME_SECONDS", 30 * 24 * 60 * 60)))

# Logging
configure_logging()
logger = logging.getLogger(__name__)


# ------------------ Session-based Authentication ------------------
def login_required(fn):
    """Decorator to require login for protected routes"""
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return await fn(*args, **kwargs)
    return wrapper

async def _run_export_job(acc: dict, cfg_cegid: dict, task_id: str):
    """
    Lanza el volcado para UNA cuenta Holded.
    Recorre sus tipos de documento y llama a process_account_invoices.
    """
    token = set_task_id(task_id)
    service = AsyncService()

    # Instancia APIs según tus clases reales
    holded_api = HoldedAPI(api_key=acc["api_key"])
    cegid_api  = CegidAPI(acc["codigo_empresa"])

    # (opcional pero típico)
    if hasattr(cegid_api, "renew_token_api_contabilidad"):
        await cegid_api.renew_token_api_contabilidad()

    nombre_empresa = acc["nombre_empresa"]
    tipo_cuenta    = acc["tipo_cuenta"]

    logger.info(f"[EXPORT] Inicio exportación: empresa='{nombre_empresa}', tipos={acc.get('cuentas_a_migrar', ['invoice'])}")
    try:
        # Si no hay lista, al menos procesar invoice
        for doc_type in acc.get("cuentas_a_migrar", ["invoice"]):
            logger.info(f"[EXPORT] Procesando doc_type='{doc_type}'")
            await service.process_account_invoices(
                holded_api=holded_api,
                cegid_api=cegid_api,
                nombre_empresa=nombre_empresa,
                tipo_cuenta=tipo_cuenta,
                doc_type=doc_type
            )
        logger.info("[EXPORT] Exportación finalizada correctamente")
    finally:
        # restore previous task_id
        try:
            task_id_ctx.reset(token)
        except Exception:
            pass



# ------------------ Authentication Routes ------------------
@app.route("/login", methods=["GET", "POST"])
async def login():
    if request.method == "POST":
        form = await request.form
        username = form.get("username", "").strip()
        password = form.get("password", "")
        
        # Secure constant-time comparison to prevent timing attacks
        username_match = secrets.compare_digest(username, ADMIN_USER)
        password_match = secrets.compare_digest(password, ADMIN_PASS)
        
        if username_match and password_match:
            session.clear()  # Clear any existing session data
            session['logged_in'] = True
            session['username'] = username
            session.permanent = True  # Make session persistent (survives browser restart)
            
            # Calculate session duration in days
            session_lifetime = app.config.get('PERMANENT_SESSION_LIFETIME')
            if hasattr(session_lifetime, 'total_seconds'):
                session_days = session_lifetime.total_seconds() / (24 * 60 * 60)
            else:
                session_days = 30  # fallback
            
            logger.info(f"Successful login for user: {username} (session valid for {int(session_days)} days)")
            # Flash message removed as per user request
            return redirect(url_for('index'))
        else:
            logger.warning(f"Failed login attempt for user: {username}")
            await flash("Usuario o contraseña incorrectos", "danger")
            return await render_template("login.html", error="Usuario o contraseña incorrectos")
    
    # If already logged in, redirect to index
    if session.get('logged_in'):
        return redirect(url_for('index'))
    
    return await render_template("login.html")

@app.route("/logout")
async def logout():
    username = session.get('username', 'Unknown')
    session.clear()
    logger.info(f"User logged out: {username}")
    await flash("Sesión cerrada correctamente", "success")
    return redirect(url_for('login'))

# ------------------ Rutas ------------------
@app.route("/")
@login_required
async def index():
    config = cargar_config()
    return await render_template("set_configuration.html", config=config)

@app.route("/documentation")
@login_required
async def documentation():
    return await render_template("documentation.html")

@app.route("/api/session/status")
async def get_session_status():
    """Get current session status"""
    # Get session lifetime and convert to days
    session_lifetime = app.config.get('PERMANENT_SESSION_LIFETIME')
    if hasattr(session_lifetime, 'total_seconds'):
        # It's a timedelta object
        session_days = int(session_lifetime.total_seconds() / (24 * 60 * 60))
    else:
        # It's an integer (seconds)
        session_days = int(session_lifetime / (24 * 60 * 60)) if session_lifetime else 30
    
    return jsonify({
        "logged_in": session.get('logged_in', False),
        "username": session.get('username'),
        "session_lifetime_days": session_days
    })

@app.route("/api/auto-migration/status")
@login_required
async def get_auto_migration_status():
    """Get current auto-migration configuration"""
    from src.config import settings
    
    # Check if Celery is available
    celery_available = False
    try:
        from src.workers.celery_config import celery_app
        # Try to inspect Celery
        celery_app.control.inspect().stats()
        celery_available = True
    except:
        celery_available = False
    
    return {
        "enabled": settings.AUTO_MIGRATION_ENABLED,
        "interval_days": settings.AUTO_MIGRATION_INTERVAL_DAYS,
        "next_run": "Calculated by Celery Beat" if celery_available else "Celery no disponible",
        "celery_available": celery_available
    }

@app.route("/api/auto-migration/trigger", methods=["POST"])
@login_required
async def trigger_auto_migration():
    """Manually trigger auto-migration task"""
    try:
        from src.workers.tasks import auto_migrate_invoices
        # Trigger the task asynchronously
        task = auto_migrate_invoices.delay()
        logger.info(f"Manual auto-migration triggered, task_id: {task.id}")
        return {"success": True, "task_id": task.id, "message": "Auto-migration initiated"}
    except Exception as e:
        logger.error(f"Error triggering auto-migration: {str(e)}")
        return {"success": False, "error": str(e)}, 500


# ------- API JSON -------
@app.route("/api/config", methods=["GET"])
@login_required
async def api_get_config():
    return jsonify(cargar_config())

@app.route("/api/config", methods=["POST"])
@login_required
async def api_post_config():
    data = await request.get_json()
    if not data:
        return jsonify({"error": "JSON inválido"}), 400
    guardar_config(data)
    return jsonify({"ok": True})


# ------- CRUD Holded -------
@app.route("/holded/nuevo", methods=["POST"])
@login_required
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
@login_required
async def editar_holded(id):
    form = await request.form
    logger.debug("Formulario recibido para editar cuenta Holded")
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
    logger.info("Config de Holded actualizada")
    await flash("Cuenta de Holded actualizada.", "success")
    return redirect(url_for("index"))


@app.route("/holded/<id>/eliminar", methods=["POST"])
@login_required
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
@login_required
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
@login_required
async def exportar_holded(id):
    config = cargar_config()
    cuenta = obtener_holded_por_id(config, id)
    if not cuenta:
        return jsonify({"ok": False, "error": "Cuenta no encontrada"}), 404

    task_id = str(uuid.uuid4())
    # registra invocación
    record_task_start(task_id, {
        "account_id": id,
        "empresa": cuenta.get("nombre_empresa"),
        "doc_types": cuenta.get("cuentas_a_migrar", ["invoice"]),
        "tipo_cuenta": cuenta.get("tipo_cuenta"),
    })
    task = asyncio.create_task(_run_export_job(cuenta, config["cegid"], task_id))
    EXPORT_TASKS[task_id] = task

    def _done_callback(t: asyncio.Task, tid=task_id):
        # quítala de la tabla siempre
        EXPORT_TASKS.pop(tid, None)

        if t.cancelled():
            logger.warning(f"[EXPORT] Tarea cancelada: {tid}")
            return

        try:
            t.result() 
        except asyncio.CancelledError:
            logger.warning(f"[EXPORT] Tarea cancelada: {tid}")
            record_task_done(tid, status="cancelled")
        except Exception as e:
            logger.exception(f"[EXPORT] Error en tarea {tid}: {e}")
            record_task_done(tid, status="error")
        else:
            record_task_done(tid, status="done")

    task.add_done_callback(_done_callback)
    return jsonify({"ok": True, "task_id": task_id}), 202


@app.route("/tasks/<task_id>", methods=["GET"])
@login_required
async def task_status(task_id):
    t = EXPORT_TASKS.get(task_id)
    meta = get_task_meta(task_id) or {}
    return jsonify({"exists": bool(t), "done": (t.done() if t else True), "meta": meta})


@app.route("/tasks/<task_id>/logs", methods=["GET"])
@login_required
async def task_logs(task_id):
    try:
        start = int(request.args.get("start", 0))
        end = int(request.args.get("end", -1))
    except Exception:
        start, end = 0, -1
    logs = get_task_logs(client=None, task_id=task_id, start=start, end=end)
    return jsonify({"ok": True, "task_id": task_id, "logs": logs})


@app.route("/tasks", methods=["GET"])
@login_required
async def tasks_list():
    acc = request.args.get("account_id")
    try:
        start = int(request.args.get("start", 0))
        limit = int(request.args.get("limit", 50))
    except Exception:
        start, limit = 0, 50
    items = list_tasks(account_id=acc, start=start, limit=limit)
    return jsonify({"ok": True, "invocations": items})


if __name__ == "__main__":
    # Usa hypercorn o el server integrado
    # Escucha en todas las interfaces (0.0.0.0) para acceso externo
    app.run(debug=True, host="0.0.0.0", port=5000)
