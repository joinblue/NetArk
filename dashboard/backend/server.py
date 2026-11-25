"""Standalone Dual-Protocol HTTP/HTTPS Server (`dashboard/backend/server.py`)."""
from __future__ import annotations

import json
import mimetypes
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Tuple
from urllib.parse import parse_qs, unquote, urlparse

DASHBOARD_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = DASHBOARD_ROOT / "frontend"
if __package__:
    from .graph_scanner import (
        build_project_graph_payload,
        get_node_detail,
        list_registered_projects,
        set_workspace_root,
        trigger_project_rescan,
    )
else:
    if str(DASHBOARD_ROOT) not in sys.path:
        sys.path.insert(0, str(DASHBOARD_ROOT))
    from backend.graph_scanner import (
        build_project_graph_payload,
        get_node_detail,
        list_registered_projects,
        set_workspace_root,
        trigger_project_rescan,
    )


def _read_frontend_asset(rel: str) -> Tuple[bytes, str] | None:
    clean_rel = (rel or "index.html").lstrip("/") or "index.html"
    if ".." in Path(clean_rel).parts:
        return None
    if FRONTEND_DIR.is_dir():
        fe_root = FRONTEND_DIR.resolve()
        target = (FRONTEND_DIR / clean_rel).resolve()
        if not target.is_relative_to(fe_root) or not target.is_file():
            target = FRONTEND_DIR / "index.html"
        if not target.is_file():
            return None
        mime, _ = mimetypes.guess_type(str(target))
        return target.read_bytes(), mime or "text/html"
    repo_root = DASHBOARD_ROOT.parent
    if str(repo_root) not in sys.path and (repo_root / "schemas").is_dir():
        sys.path.insert(0, str(repo_root))
    from schemas.mcp_tools_core import get_embedded_asset_text

    for candidate in (f"dashboard/frontend/{clean_rel}", "dashboard/frontend/index.html"):
        try:
            text = get_embedded_asset_text(candidate)
        except FileNotFoundError:
            continue
        mime, _ = mimetypes.guess_type(candidate)
        return text.encode("utf-8"), mime or "text/html"
    return None


def dispatch_api_request(method: str, path: str) -> Tuple[int, Dict[str, Any]]:
    """Route REST API requests for the PM Control Center."""
    parsed = urlparse(path)
    clean_path = parsed.path.rstrip("/")

    if method == "GET" and clean_path == "/api/projects":
        return 200, {"projects": list_registered_projects()}

    parts = [unquote(p) for p in clean_path.split("/") if p]
    if len(parts) == 4 and parts[0] == "api" and parts[1] == "project" and parts[3] == "overview":
        pid = parts[2]
        qs = parse_qs(parsed.query)
        raw_arch = (qs.get("include_archived", [""])[0] or "").strip().lower()
        include_archived = raw_arch in ("1", "true", "yes")
        category = (qs.get("category", ["all"])[0] or "all").strip() or "all"
        blueprint = (qs.get("blueprint", [""])[0] or "").strip()
        topic = (qs.get("topic", [""])[0] or "").strip()
        try:
            return 200, build_project_graph_payload(
                pid,
                include_archived=include_archived,
                category=category,
                blueprint=blueprint,
                topic=topic,
            )
        except ValueError as exc:
            return 404, {"error": str(exc)}
        except Exception as exc:
            return 500, {"error": str(exc)}

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "project" and parts[3] == "handovers":
        pid = parts[2]
        try:
            payload = build_project_graph_payload(pid)
            return 200, {"handovers": payload.get("handovers", []), "handover": payload.get("handover", {})}
        except Exception as exc:
            return 404, {"error": str(exc)}

    if len(parts) == 4 and parts[0] == "api" and parts[1] == "project" and parts[3] == "rescan":
        pid = parts[2]
        try:
            return 200, trigger_project_rescan(pid)
        except Exception as exc:
            return 500, {"error": str(exc)}

    if len(parts) >= 5 and parts[0] == "api" and parts[1] == "project" and parts[3] == "node":
        pid = parts[2]
        node_key = "/".join(parts[4:])
        try:
            return 200, get_node_detail(pid, node_key)
        except KeyError as exc:
            return 404, {"error": str(exc)}
        except Exception as exc:
            return 500, {"error": str(exc)}

    return 404, {"error": f"Unknown API endpoint: {method} {clean_path}"}


class ControlNotebookHandler(BaseHTTPRequestHandler):
    """HTTP handler serving both /api/* JSON endpoints and frontend static assets."""

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            status, data = dispatch_api_request("GET", self.path)
            self._send_json(status, data)
            return

        rel = urlparse(self.path).path.lstrip("/") or "index.html"
        asset = _read_frontend_asset(rel)
        if asset is None:
            self._send_json(404, {"error": "Frontend asset not found"})
            return

        content, mime = asset
        self.send_response(200)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_POST(self) -> None:
        if self.path.startswith("/api/"):
            status, data = dispatch_api_request("POST", self.path)
            self._send_json(status, data)
            return
        self._send_json(404, {"error": "Not found"})


class DualProtocolHTTPServer(ThreadingHTTPServer):
    """Supports both plain HTTP and HTTPS (TLS) on the same port."""

    def __init__(self, server_address: Tuple[str, int], RequestHandlerClass: Any, enable_tls: bool = True) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.ssl_ctx: ssl.SSLContext | None = self._create_self_signed_ssl_context() if enable_tls else None

    @staticmethod
    def _create_self_signed_ssl_context() -> ssl.SSLContext | None:
        try:
            tmp_dir = Path(tempfile.gettempdir()) / "netark_dashboard_tls"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            cert_file = tmp_dir / "cert.crt"
            key_file = tmp_dir / "cert.data"
            if not cert_file.exists() or not key_file.exists():
                subprocess.run(
                    [
                        "openssl", "req", "-x509", "-newkey", "rsa:2048",
                        "-keyout", str(key_file), "-out", str(cert_file),
                        "-days", "365", "-nodes", "-subj", "/CN=localhost",
                        "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(certfile=str(cert_file), keyfile=str(key_file))
            return ctx
        except Exception:
            return None

    def get_request(self) -> Tuple[Any, Any]:
        conn, addr = self.socket.accept()
        try:
            conn.settimeout(3.0)
            first_byte = conn.recv(1, socket.MSG_PEEK)
            conn.settimeout(None)
            if first_byte == b"\x16" and self.ssl_ctx is not None:
                conn = self.ssl_ctx.wrap_socket(conn, server_side=True)
        except Exception:
            conn.settimeout(None)
        return conn, addr


def _prepare_workspace(cwd: str) -> Path:
    """Resolve workspace root, compile missing indices if memory/ exists, and activate workspace."""
    ws_root = Path(cwd).resolve()
    if (ws_root / "memory").is_dir() and not (ws_root / "memory" / "index" / "CONTEXT_INDEX.json").is_file():
        repo_root = DASHBOARD_ROOT.parent
        if str(repo_root) not in sys.path and (repo_root / "schemas").is_dir():
            sys.path.insert(0, str(repo_root))
        from schemas.mcp_tools_core import compile_and_write_indices

        compile_and_write_indices(ws_root)
    set_workspace_root(ws_root)
    return ws_root


def _is_port_open(host: str, port: int, timeout: float = 0.15) -> bool:
    """Return True if a TCP listener accepts connections on host:port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _probe_existing_dashboard(host: str, port: int, ws_root: Path, timeout: float = 0.4) -> bool:
    """Return True if http://{host}:{port}/api/projects serves the exact ws_root."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/projects", timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    projects = payload.get("projects") if isinstance(payload, dict) else None
    return isinstance(projects, list) and any(
        isinstance(p, dict) and str(p.get("root") or "").strip() and Path(str(p["root"])).resolve() == ws_root
        for p in projects
    )


def start_background_dashboard(cwd: str, host: str = "127.0.0.1", base_port: int | None = None, max_port_scan: int = 11) -> Dict[str, Any]:
    """Start or reuse a plain-HTTP background dashboard daemon without touching stdout."""
    if os.environ.get("NETARK_DASHBOARD", "1").strip().lower() in ("0", "false", "no", "off"):
        return {"status": "disabled", "url": None, "port": None, "server": None}
    ws_root = Path(cwd).resolve()
    if not (ws_root / "memory").is_dir():
        return {"status": "skipped_no_memory", "url": None, "port": None, "server": None}
    try:
        start_port = int(base_port) if base_port is not None else int(os.environ.get("NETARK_DASHBOARD_PORT", "8765").strip() or "8765")
    except ValueError:
        start_port = 8765
    for port in range(start_port, start_port + max(1, max_port_scan)):
        url = f"http://{host}:{port}"
        if _is_port_open(host, port):
            if _probe_existing_dashboard(host, port, ws_root):
                return {"status": "reused", "url": url, "port": port, "server": None}
            continue
        try:
            server = DualProtocolHTTPServer((host, port), ControlNotebookHandler, enable_tls=False)
        except OSError:
            if _probe_existing_dashboard(host, port, ws_root):
                return {"status": "reused", "url": url, "port": port, "server": None}
            continue
        _prepare_workspace(str(ws_root))
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, name="netark-dashboard-bg", daemon=True).start()
        return {"status": "started", "url": url, "port": port, "server": server}
    return {"status": "port_exhausted", "url": None, "port": None, "server": None}


def run_server(host: str = "127.0.0.1", port: int = 8765, cwd: str | None = None) -> int:
    """Start the PM Control Center Dual HTTP/HTTPS server."""
    ws_root = Path(cwd).resolve() if cwd else DASHBOARD_ROOT.parent.resolve()
    if _is_port_open(host, port):
        if _probe_existing_dashboard(host, port, ws_root):
            print(f"ℹ️ NetArk Dashboard 已在 http://{host}:{port} 運行中（相同專案），請直接於瀏覽器開啟。", flush=True)
            return 0
        print(f"❌ 埠號 {host}:{port} 已被其他程式或專案佔用，請改用 --port {port + 1}。", file=sys.stderr, flush=True)
        return 1
    try:
        server = DualProtocolHTTPServer((host, port), ControlNotebookHandler, enable_tls=True)
    except OSError as exc:
        print(f"❌ 無法綁定 {host}:{port}: {exc}", file=sys.stderr, flush=True)
        return 1
    if cwd:
        _prepare_workspace(cwd)
    print(f"🚀 NetArk 專案控管中心已啟動 (同時支援 HTTP 與 HTTPS): http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
    return 0


if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    raise SystemExit(run_server("127.0.0.1", port_arg))
