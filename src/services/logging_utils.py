import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, List, Optional

import redis
import contextvars

# Context var to associate logs with a specific task/invocation
task_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("task_id", default=None)


class TaskIdFilter(logging.Filter):
    """Injects current task_id from contextvars into LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        setattr(record, "task_id", task_id_ctx.get())
        return True


class RedisListHandler(logging.Handler):
    """Logging handler that writes structured logs to a Redis list per task_id.

    - Key: logs:{task_id}
    - Entry: JSON string with {ts, level, name, message}
    - Sets TTL on first write
    """

    def __init__(self, redis_url: str, ttl_seconds: int = 7 * 24 * 3600):
        super().__init__()
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self._client: Optional[redis.Redis] = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            # decode_responses=True to work with str directly
            self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def emit(self, record: logging.LogRecord) -> None:  # type: ignore[override]
        try:
            task_id = getattr(record, "task_id", None)
            if not task_id:
                # Not a task-scoped log → ignore for Redis handler
                return

            key = f"logs:{task_id}"

            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "name": record.name,
                "message": self.format(record),
            }
            self.client.rpush(key, json.dumps(entry, ensure_ascii=False))
            # ensure TTL is set
            self.client.expire(key, self.ttl_seconds)
        except Exception:
            # Never raise from a logging handler
            self.handleError(record)


def configure_logging(default_level: int = logging.INFO) -> None:
    """Configure root logging with console + Redis handlers.

    Console logs always on; Redis handler only stores task-scoped logs.
    """
    root = logging.getLogger()
    if getattr(root, "_configured", False):
        return

    root.setLevel(default_level)

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(default_level)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    console.addFilter(TaskIdFilter())
    root.addHandler(console)

    # Redis handler for task logs
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    redis_handler = RedisListHandler(redis_url=redis_url)
    redis_handler.setLevel(logging.DEBUG)
    # store the raw message; formatter can still expand if needed
    redis_handler.setFormatter(logging.Formatter("%(message)s"))
    redis_handler.addFilter(TaskIdFilter())
    root.addHandler(redis_handler)

    # Sentinel to avoid double config
    setattr(root, "_configured", True)


def set_task_id(task_id: Optional[str]) -> contextvars.Token:
    """Set current task_id in context and return token for reset()."""
    return task_id_ctx.set(task_id)


def get_task_logs(client: Optional[redis.Redis], task_id: str, start: int = 0, end: int = -1) -> List[dict[str, Any]]:
    """Fetch logs for a task_id from Redis list as Python dicts."""
    r = client or redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    key = f"logs:{task_id}"
    entries = r.lrange(key, start, end)
    results: List[dict[str, Any]] = []
    for e in entries:
        try:
            results.append(json.loads(e))
        except Exception:
            # fallback if someone pushed plain text
            results.append({"ts": datetime.now(timezone.utc).isoformat(), "level": "INFO", "name": "logs", "message": str(e)})
    return results


# --------- Invocations registry (metadata) ---------

def _client_from_env() -> redis.Redis:
    return redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)


def record_task_start(task_id: str, meta: dict[str, Any], *, keep_last: int = 500) -> None:
    r = _client_from_env()
    key = f"task:{task_id}"
    payload = {
        "task_id": task_id,
        "account_id": str(meta.get("account_id") or ""),
        "empresa": meta.get("empresa") or "",
        "doc_types": json.dumps(meta.get("doc_types") or [] , ensure_ascii=False),
        "tipo_cuenta": meta.get("tipo_cuenta") or "",
        "created_at": meta.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "status": meta.get("status") or "running",
    }
    r.hset(key, mapping=payload)
    r.expire(key, 7 * 24 * 3600)

    # lists (global and by account)
    r.lpush("invocations", task_id)
    r.ltrim("invocations", 0, keep_last - 1)
    if payload["account_id"]:
        list_key = f"invocations:{payload['account_id']}"
        r.lpush(list_key, task_id)
        r.ltrim(list_key, 0, keep_last - 1)


def record_task_done(task_id: str, status: str = "done") -> None:
    r = _client_from_env()
    key = f"task:{task_id}"
    r.hset(key, mapping={
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat()
    })
    r.expire(key, 7 * 24 * 3600)


def get_task_meta(task_id: str) -> Optional[dict[str, Any]]:
    r = _client_from_env()
    key = f"task:{task_id}"
    data = r.hgetall(key)
    if not data:
        return None
    # normalize
    if "doc_types" in data:
        try:
            data["doc_types"] = json.loads(data["doc_types"]) or []
        except Exception:
            data["doc_types"] = []
    return data


def list_tasks(account_id: Optional[str] = None, start: int = 0, limit: int = 50) -> List[dict[str, Any]]:
    r = _client_from_env()
    list_key = f"invocations:{account_id}" if account_id else "invocations"
    ids = r.lrange(list_key, start, start + limit - 1)
    items: List[dict[str, Any]] = []
    for tid in ids:
        meta = get_task_meta(tid)
        if meta:
            items.append(meta)
    return items


