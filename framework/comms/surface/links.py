"""framework.comms.surface.links — deep-links from cards to the dashboard /queue.

The base URL is instance data (env ``CABINET_DASHBOARD_URL`` →
``instance/config/comms-surface.yml`` ``dashboard_url``) — framework code
never hardcodes a host. Fail-closed: unconfigured ⇒ empty strings ⇒ cards
simply render without links (never a dead link). Item ids are URL-encoded;
URL construction never incorporates any other user/model-controlled text.

Channel note: Telegram inline URL buttons reject many non-public hosts, so a
URL **button** is only offered for https URLs; every configured URL (http
included, e.g. a LAN dashboard) still renders as a plain "Details:" text line
that clients auto-link.
"""
from __future__ import annotations

from urllib.parse import quote


def dashboard_base(cfg: "dict | None" = None) -> str:
    """The configured dashboard origin, or "" (fail-closed)."""
    if cfg is None:
        from framework.comms.surface import config
        cfg = config.load()
    base = str(cfg.get("dashboard_url") or "").strip().rstrip("/")
    if base.startswith("http://") or base.startswith("https://"):
        return base
    return ""


def queue_url(cfg: "dict | None" = None) -> str:
    base = dashboard_base(cfg)
    return f"{base}/queue" if base else ""


def queue_item_url(item_id: str, cfg: "dict | None" = None) -> str:
    base = dashboard_base(cfg)
    if not base or not item_id:
        return ""
    return f"{base}/queue?item={quote(str(item_id), safe='')}"


def url_button(text: str, url: str) -> "dict | None":
    """A channel-neutral URL button — https only (Telegram-safe); otherwise
    None and the caller falls back to ``details_line``."""
    if url and url.startswith("https://"):
        return {"text": str(text), "url": url}
    return None


def details_line(url: str) -> str:
    """The plain-text fallback link line ("" when no URL is configured)."""
    return f"Details: {url}" if url else ""
