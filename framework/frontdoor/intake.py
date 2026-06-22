"""framework.frontdoor.intake — durable Redis-Streams intake queue.

Pipes / triggers / officers ENQUEUE captain-bound items here instead of DMing
Telegram; the Chair DRAINs them. Redis Streams give durability: messages
persist + stay pending-until-ACK across an officer restart/compaction, which
satisfies the architecture's "durable intake — nothing lost" invariant (§7).

Connection mirrors ``cabinet/scripts/lib/triggers.sh``: REDIS_HOST (default
``redis``), REDIS_PORT (default 6379). Production stream key is
``cabinet:frontdoor:intake``, consumer group ``frontdoor``. Backend is redis-py
when importable, else a redis-cli subprocess wrapper (stdlib-only), so this
module has no hard third-party dependency at runtime.

intake is durable CAPTURE and is therefore NOT gated on ``allow_sends()`` —
writing to the queue is always safe; only the live Telegram send (channel.py)
is gated. This is the bottom of the front-door dependency stack: it imports no
sibling frontdoor module.
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any

# Canonical group + key. The key default is read at call time (env-overridable)
# so the runtime / tests can route without re-importing.
_GROUP = "frontdoor"
_DEFAULT_KEY_ENV = "CABINET_FRONTDOOR_STREAM"
_PRODUCTION_KEY = "cabinet:frontdoor:intake"

_VALID_TIERS = {"ping-now", "batch", "fyi"}
_REQUIRED_FIELDS = ("source", "kind", "ts", "payload")
_MAXLEN = 1000  # XTRIM ~ ceiling so the stream stays lean.


def _default_stream_key() -> str:
    return os.environ.get(_DEFAULT_KEY_ENV, _PRODUCTION_KEY)


def _resolve_key(stream_key: str | None) -> str:
    return stream_key if stream_key is not None else _default_stream_key()


# ---------------------------------------------------------------------------
# Item validation — fail-closed BEFORE enqueue.
# ---------------------------------------------------------------------------
def validate_item(item: Any) -> None:
    """Raise ValueError unless ``item`` is a valid canonical intake item.

    Requires source/kind/ts/payload, a payload carrying at least a 'summary',
    and (when present) a urgency_tier in {ping-now, batch, fyi}. A producer may
    omit urgency_tier (composer defaults it to 'batch'); but a *present*-and-bad
    tier is rejected.
    """
    if not isinstance(item, dict):
        raise ValueError("intake item must be a dict")
    for field in _REQUIRED_FIELDS:
        if field not in item or item[field] in (None, ""):
            raise ValueError(f"intake item missing required field: {field}")
    payload = item.get("payload")
    if not isinstance(payload, dict) or not payload.get("summary"):
        raise ValueError("intake item payload must be a dict with a 'summary'")
    tier = item.get("urgency_tier")
    if tier is not None and tier not in _VALID_TIERS:
        raise ValueError(
            f"intake item urgency_tier must be one of {sorted(_VALID_TIERS)}; "
            f"got {tier!r}")


# ---------------------------------------------------------------------------
# Backend factory — redis-py if importable, else redis-cli subprocess.
# ---------------------------------------------------------------------------
def _redis():
    """Return a minimal backend exposing the Stream verbs intake needs.

    Tries redis-py first; on ImportError (the cabinet's headless default) falls
    back to a redis-cli subprocess wrapper that speaks the same small surface.
    """
    host = os.environ.get("REDIS_HOST", "redis")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    try:
        import redis  # type: ignore

        return _RedisPyBackend(redis.Redis(
            host=host, port=port, decode_responses=True))
    except Exception:
        return _RedisCliBackend(host, port)


class _RedisPyBackend:
    """Thin adapter over redis-py so the two backends share a call surface."""

    def __init__(self, client):
        self._c = client

    def ping(self) -> bool:
        return bool(self._c.ping())

    def xadd(self, key: str, field: str, value: str) -> str:
        return self._c.xadd(key, {field: value})

    def _ensure_group(self, key: str) -> None:
        try:
            self._c.xgroup_create(key, _GROUP, id="0", mkstream=True)
        except Exception:
            pass  # BUSYGROUP — already exists.

    def xreadgroup_new(self, key: str, consumer: str, count: int):
        self._ensure_group(key)
        res = self._c.xreadgroup(_GROUP, consumer, {key: ">"}, count=count)
        return _flatten_xread(res, key)

    def xreadgroup_pending(self, key: str, consumer: str, count: int):
        self._ensure_group(key)
        res = self._c.xreadgroup(_GROUP, consumer, {key: "0"}, count=count)
        return _flatten_xread(res, key)

    def xack(self, key: str, ids: list[str]) -> int:
        if not ids:
            return 0
        return int(self._c.xack(key, _GROUP, *ids))

    def xtrim(self, key: str, maxlen: int) -> None:
        try:
            self._c.xtrim(key, maxlen=maxlen, approximate=True)
        except Exception:
            pass

    def delete(self, key: str) -> None:
        try:
            self._c.delete(key)
        except Exception:
            pass


def _flatten_xread(res, key: str) -> list[tuple[str, dict]]:
    """Normalize redis-py xreadgroup output to [(id, {field: val}), ...]."""
    out: list[tuple[str, dict]] = []
    if not res:
        return out
    for _stream, entries in res:
        for mid, fields in entries:
            if fields is None:
                continue
            out.append((mid, dict(fields)))
    return out


class _RedisCliBackend:
    """stdlib-only backend: shells out to redis-cli (mirrors triggers.sh)."""

    def __init__(self, host: str, port: int):
        self._host = host
        self._port = str(port)

    def _run(self, *args: str, raw: bool = False) -> str:
        cmd = ["redis-cli"]
        if raw:
            cmd.append("--raw")
        cmd += ["-h", self._host, "-p", self._port, *args]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"redis-cli failed ({proc.returncode}): "
                f"{proc.stderr.strip() or proc.stdout.strip()}")
        out = proc.stdout
        if "ERR" in out and args and args[0] not in ("XGROUP",):
            # redis-cli prints errors to stdout in non-raw mode.
            if out.strip().startswith("ERR") or out.strip().startswith("(error)"):
                raise RuntimeError(f"redis error: {out.strip()}")
        return out

    def ping(self) -> bool:
        return self._run("PING").strip().upper().endswith("PONG")

    def xadd(self, key: str, field: str, value: str) -> str:
        # Pass the JSON value as a single argv element (no shell, so safe).
        return self._run("XADD", key, "*", field, value).strip()

    def _ensure_group(self, key: str) -> None:
        # MKSTREAM so the group can be created before any XADD; ignore BUSYGROUP.
        try:
            self._run("XGROUP", "CREATE", key, _GROUP, "0", "MKSTREAM")
        except Exception:
            pass

    def _xreadgroup(self, key: str, consumer: str, start: str, count: int):
        self._ensure_group(key)
        out = self._run(
            "XREADGROUP", "GROUP", _GROUP, consumer, "COUNT", str(count),
            "STREAMS", key, start, raw=True)
        return _parse_cli_xread(out, key)

    def xreadgroup_new(self, key: str, consumer: str, count: int):
        return self._xreadgroup(key, consumer, ">", count)

    def xreadgroup_pending(self, key: str, consumer: str, count: int):
        return self._xreadgroup(key, consumer, "0", count)

    def xack(self, key: str, ids: list[str]) -> int:
        if not ids:
            return 0
        out = self._run("XACK", key, _GROUP, *ids, raw=True)
        try:
            return int(out.strip() or "0")
        except ValueError:
            return 0

    def xtrim(self, key: str, maxlen: int) -> None:
        try:
            self._run("XTRIM", key, "MAXLEN", "~", str(maxlen))
        except Exception:
            pass

    def delete(self, key: str) -> None:
        try:
            self._run("DEL", key)
        except Exception:
            pass


def _parse_cli_xread(raw: str, key: str) -> list[tuple[str, dict]]:
    """Parse `redis-cli --raw XREADGROUP ... STREAMS <key> <id>` output.

    Raw layout for our single-field ('item') entries:
        <key>
        <id-1>
        <field-name>
        <field-value>
        <id-2>
        ...
    Empty result -> "" (no entries). We parse defensively in field pairs.
    """
    lines = raw.split("\n")
    # Strip a trailing empty line from the redis-cli output.
    while lines and lines[-1] == "":
        lines.pop()
    if not lines:
        return []
    # First line is the stream key echo; drop it if present.
    if lines and lines[0] == key:
        lines = lines[1:]
    out: list[tuple[str, dict]] = []
    i = 0
    n = len(lines)
    while i < n:
        mid = lines[i]
        i += 1
        fields: dict[str, str] = {}
        # Consume field/value pairs until the next id-looking token. Stream ids
        # match '<digits>-<digits>'; field names ('item') do not, so a line
        # that looks like an id begins the next entry.
        while i + 1 < n and not _looks_like_id(lines[i]):
            fname = lines[i]
            fval = lines[i + 1]
            fields[fname] = fval
            i += 2
        # Handle a trailing single field/value pair at the very end.
        if i + 1 == n and not _looks_like_id(lines[i]):
            # malformed tail — ignore.
            i += 1
        out.append((mid, fields))
    return out


def _looks_like_id(tok: str) -> bool:
    if "-" not in tok:
        return False
    a, _, b = tok.partition("-")
    return a.isdigit() and b.isdigit()


# ---------------------------------------------------------------------------
# Serialization helpers — store item (sans id) as field 'item' = JSON.
# ---------------------------------------------------------------------------
def _serialize(item: dict) -> str:
    body = {k: v for k, v in item.items() if k != "id"}
    return json.dumps(body, default=str)


def _rehydrate(mid: str, fields: dict) -> dict:
    raw = fields.get("item")
    item = json.loads(raw) if raw else {}
    item["id"] = mid
    return item


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def enqueue(item: dict, *, stream_key: str | None = None) -> str:
    """Validate + XADD the item; return the Redis-assigned stream id.

    The id is assigned by Redis (via '*'); callers MUST NOT supply 'id'. The
    returned id is the key for ack().
    """
    validate_item(item)
    key = _resolve_key(stream_key)
    return _redis().xadd(key, "item", _serialize(item))


def drain(since: str | None = None, *, stream_key: str | None = None,
          count: int = 100, consumer: str = "chair") -> list[dict]:
    """Read NEW (undelivered) items via the consumer group, rehydrated.

    When ``since`` is given, filters to items with ts >= since (ISO-8601
    lexicographic compare is valid for the canonical 'YYYY-MM-DDTHH:MM:SSZ').
    Delivered items become pending until ack(); recover them via drain_pending.
    """
    key = _resolve_key(stream_key)
    rows = _redis().xreadgroup_new(key, consumer, count)
    items = [_rehydrate(mid, fields) for mid, fields in rows]
    if since is not None:
        items = [it for it in items if str(it.get("ts", "")) >= since]
    return items


def drain_pending(*, stream_key: str | None = None,
                  consumer: str = "chair") -> list[dict]:
    """Recover delivered-but-unacked items for this consumer (crash recovery).

    Mirrors trigger_read_pending: XREADGROUP ... STREAMS <key> '0'.
    """
    key = _resolve_key(stream_key)
    rows = _redis().xreadgroup_pending(key, consumer, 1000)
    return [_rehydrate(mid, fields) for mid, fields in rows]


def ack(id: str | list[str], *, stream_key: str | None = None) -> int:
    """XACK the given id(s); XTRIM the stream to stay lean. Returns count acked."""
    key = _resolve_key(stream_key)
    ids = [id] if isinstance(id, str) else list(id)
    backend = _redis()
    acked = backend.xack(key, ids)
    backend.xtrim(key, _MAXLEN)
    return acked
