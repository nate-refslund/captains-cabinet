#!/usr/bin/env python3
"""egress-proxy.py — allowlisting forward proxy for the officer runtime.

Part of the OPT-IN enforced egress allowlist (framework/defaults/egress.yml,
docs/runbooks/egress-allowlist.md). Started by cabinet/scripts/egress-guard.sh
when `enforce: true`. Pure python3 stdlib — adds no new dependency.

WHAT IT DOES
  A minimal HTTP forward proxy bound to 127.0.0.1 that permits outbound
  requests ONLY to hosts on a resolved allowlist and refuses everything else
  with 403 BEFORE opening any upstream connection (deny-by-default: a blocked
  host is never resolved or dialed). It handles:
    * HTTP CONNECT       — the tunnel method HTTPS clients (curl, python-
      requests, most MCPs) use; on allow it returns 200 and relays bytes raw,
      on block it returns 403 without connecting. CONNECT is additionally
      restricted to the HTTPS port (443) by default so an allowlisted host
      cannot be used as a generic TCP tunnel to arbitrary ports (:22/:25/...);
      widen only via --connect-ports / EGRESS_CONNECT_PORTS if you must.
    * absolute-URI HTTP  — plain-HTTP proxying (GET http://host/... etc.); on
      allow it forwards via http.client and streams the response back.

HOST MATCH
  A host is allowed iff it equals an allowlist entry OR is a subdomain of one
  (case-insensitive, trailing dot ignored): `foo.com` covers `foo.com` and
  `api.foo.com`; it does NOT cover `evilfoo.com`.

LOGGING
  Deliberately logs only `EGRESS-BLOCK <host>` (host only) to stderr. It NEVER
  logs full request URLs, query strings, headers, or bodies — those can carry
  secrets/tokens. The default http.server per-request logging is suppressed.

SECURITY NOTE
  The allowlist is matched on the HOSTNAME presented by the client. This is a
  proxy-honouring control: it does not bind clients that ignore proxy env or
  open raw sockets, and it does not defend against DNS rebinding of an
  allowlisted name. Plain HTTP rewrites Host to the validated URI authority so
  a client cannot domain-front another virtual host. CONNECT is opaque after
  the tunnel opens: without TLS interception the proxy cannot verify SNI, so
  allowlisted shared/CDN endpoints remain an explicitly documented residual.
  See the runbook's residual section.
"""
from __future__ import annotations

import argparse
import http.client
import os
import select
import signal
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

# hop-by-hop headers must not be forwarded end-to-end (RFC 7230 §6.1).
HOP_BY_HOP = {
    "connection", "proxy-connection", "keep-alive", "transfer-encoding",
    "te", "trailer", "upgrade", "proxy-authenticate", "proxy-authorization",
}


def atomic_write(path: str, text: str) -> None:
    """Publish a small runtime marker atomically, mode 0600, same directory.

    A launchd crash restart may race stale files from the prior PID; readers
    must see either the complete old marker or the complete new one, never a
    truncated intermediate file.
    """
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, mode=0o700, exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def remove_marker_if_owned(path: str, expected: str) -> None:
    """Remove only this process's marker; never erase a restart successor's."""
    if not path:
        return
    try:
        with open(path, "r", encoding="utf-8") as handle:
            current = handle.read()
        if current == expected:
            os.unlink(path)
    except OSError:
        pass


def load_allowlist(path, env_val=None):
    """Read hosts from a file (one per line, # comments) and/or an env string
    (comma/space separated). Lowercased, trailing dot stripped, order-preserving
    dedup. Missing file / empty inputs yield an empty list (blocks everything)."""
    hosts = []
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        hosts.append(s.lower().rstrip("."))
        except OSError:
            pass
    if env_val:
        for tok in env_val.replace(",", " ").split():
            tok = tok.strip().lower().rstrip(".")
            if tok:
                hosts.append(tok)
    seen = set()
    out = []
    for h in hosts:
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out


def host_allowed(host, allow):
    """True iff host equals, or is a subdomain of, an allowlist entry."""
    if not host:
        return False
    h = host.strip().lower().rstrip(".")
    if h.startswith("[") and h.endswith("]"):   # bracketed IPv6 literal
        h = h[1:-1]
    for a in allow:
        if not a:
            continue
        if h == a or h.endswith("." + a):
            return True
    return False


def parse_ports(spec):
    """Strictly parse a comma/space-separated CONNECT-port contract.

    The guard canonicalises this input before launch, but the backend also
    rejects malformed/direct invocation rather than silently dropping a token
    and running with a policy different from the Captain-reviewed arguments.
    """
    tokens = (spec or "").replace(",", " ").split()
    if not tokens:
        raise ValueError("CONNECT port list is empty")
    ports = set()
    for tok in tokens:
        if not tok.isascii() or not tok.isdigit():
            raise ValueError("invalid CONNECT port: %s" % tok)
        p = int(tok, 10)
        if not 0 < p <= 65535:
            raise ValueError("CONNECT port out of range: %s" % tok)
        ports.add(p)
    return ports


def split_authority(authority):
    """`host:port` -> (host, port_str_or_None). Handles [ipv6]:port and bare."""
    authority = authority.strip()
    if authority.startswith("["):
        idx = authority.find("]")
        if idx == -1:
            return authority, None
        host = authority[: idx + 1]
        rest = authority[idx + 1:]
        if rest.startswith(":"):
            return host, rest[1:]
        return host, None
    if ":" in authority:
        host, _, port = authority.rpartition(":")
        return host, port
    return authority, None


def _make_handler(allow, connect_ports):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        _allow = allow
        _connect_ports = connect_ports

        # ---- silence secret-bearing default request logging ----------
        def log_message(self, fmt, *args):   # noqa: N802 (base signature)
            return

        def _deny(self, host):
            sys.stderr.write("EGRESS-BLOCK %s\n" % (host or "?"))
            sys.stderr.flush()
            body = b"egress blocked by allowlist\n"
            self.close_connection = True
            try:
                self.send_response(403)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                pass

        # ---- HTTPS tunnel --------------------------------------------
        def do_CONNECT(self):   # noqa: N802
            self.close_connection = True
            host, port = split_authority(self.path)
            if not host_allowed(host, self._allow):
                self._deny(host)
                return
            try:
                p = int(port) if port else 443
            except ValueError:
                self._deny(host)
                return
            # Restrict the tunnel to allowed ports (default 443): an allowlisted
            # host must not become a generic TCP tunnel to :22/:25/etc.
            if p not in self._connect_ports:
                self._deny(host)
                return
            dial = host[1:-1] if host.startswith("[") and host.endswith("]") else host
            try:
                upstream = socket.create_connection((dial, p), timeout=15)
            except OSError:
                try:
                    self.send_response(502)
                    self.send_header("Connection", "close")
                    self.end_headers()
                except OSError:
                    pass
                return
            try:
                self.send_response(200, "Connection Established")
                self.end_headers()
            except OSError:
                upstream.close()
                return
            self._relay(self.connection, upstream)

        def _relay(self, client, upstream):
            socks = [client, upstream]
            try:
                while True:
                    r, _, x = select.select(socks, [], socks, 30)
                    if x or not r:
                        break
                    for s in r:
                        other = upstream if s is client else client
                        try:
                            data = s.recv(65536)
                        except OSError:
                            return
                        if not data:
                            return
                        try:
                            other.sendall(data)
                        except OSError:
                            return
            finally:
                try:
                    upstream.close()
                except OSError:
                    pass

        # ---- plain HTTP forward --------------------------------------
        def _forward(self):
            self.close_connection = True
            parts = urlsplit(self.path)
            host = parts.hostname
            if not host_allowed(host, self._allow):
                self._deny(host)
                return
            port = parts.port or 80
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            body = b""
            length = self.headers.get("Content-Length")
            if length:
                try:
                    body = self.rfile.read(int(length))
                except (ValueError, OSError):
                    body = b""
            fwd = {}
            for k in self.headers.keys():
                if k.lower() in HOP_BY_HOP or k.lower() == "host":
                    continue
                fwd[k] = self.headers.get(k)
            # The absolute URI is the policy input. Never forward an attacker-
            # supplied Host header that names a different vhost on the same
            # upstream address. Preserve an explicit/non-default port only.
            host_header = host
            if ":" in host and not host.startswith("["):
                host_header = f"[{host}]"
            if parts.port is not None and parts.port != 80:
                host_header = f"{host_header}:{parts.port}"
            fwd["Host"] = host_header
            fwd["Connection"] = "close"
            conn = None
            try:
                conn = http.client.HTTPConnection(host, port, timeout=15)
                conn.request(self.command, path, body=body, headers=fwd)
                resp = conn.getresponse()
                data = resp.read()
            except OSError:
                try:
                    self.send_response(502)
                    self.send_header("Connection", "close")
                    self.end_headers()
                except OSError:
                    pass
                if conn is not None:
                    conn.close()
                return
            try:
                self.send_response(resp.status, resp.reason)
                for k, v in resp.getheaders():
                    if k.lower() in HOP_BY_HOP or k.lower() == "content-length":
                        continue
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)
            except OSError:
                pass
            finally:
                conn.close()

        do_GET = _forward
        do_POST = _forward
        do_PUT = _forward
        do_DELETE = _forward
        do_HEAD = _forward
        do_PATCH = _forward
        do_OPTIONS = _forward

    return Handler


def main(argv=None):
    ap = argparse.ArgumentParser(prog="egress-proxy.py")
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("EGRESS_PROXY_PORT", "8899")))
    ap.add_argument("--allow-file", default=os.environ.get("EGRESS_ALLOW_FILE", ""))
    ap.add_argument("--ready-file", default="")
    ap.add_argument("--pid-file", default="")
    ap.add_argument("--connect-ports",
                    default=os.environ.get("EGRESS_CONNECT_PORTS", "443"),
                    help="comma/space-separated ports CONNECT tunnels may target "
                         "(default 443; malformed values are rejected)")
    ap.add_argument("--check", default="",
                    help="print ALLOW/BLOCK for HOST against the allowlist and exit")
    args = ap.parse_args(argv)

    allow = load_allowlist(args.allow_file, os.environ.get("EGRESS_ALLOW_HOSTS"))
    try:
        connect_ports = parse_ports(args.connect_ports)
    except ValueError as exc:
        ap.error(str(exc))

    if args.check:
        ok = host_allowed(args.check, allow)
        sys.stdout.write("ALLOW\n" if ok else "BLOCK\n")
        return 0 if ok else 1

    handler = _make_handler(allow, connect_ports)
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    except OSError as exc:
        sys.stderr.write(
            "egress-proxy: bind failed on 127.0.0.1:%d: %s\n" % (args.port, exc))
        return 1
    httpd.daemon_threads = True
    bound_port = httpd.server_address[1]
    own_pid = os.getpid()
    pid_token = "%d" % own_pid
    pid_marker = "%s\n" % pid_token
    ready_marker = "READY %d PID %s\n" % (bound_port, pid_token)
    try:
        if args.pid_file:
            atomic_write(args.pid_file, pid_marker)
        if args.ready_file:
            atomic_write(args.ready_file, ready_marker)
    except OSError as exc:
        sys.stderr.write("egress-proxy: state publication failed: %s\n" % exc)
        httpd.server_close()
        remove_marker_if_owned(args.pid_file, pid_marker)
        remove_marker_if_owned(args.ready_file, ready_marker)
        return 1

    def terminate(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        httpd.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        remove_marker_if_owned(args.pid_file, pid_marker)
        remove_marker_if_owned(args.ready_file, ready_marker)
    return 0


if __name__ == "__main__":
    sys.exit(main())
