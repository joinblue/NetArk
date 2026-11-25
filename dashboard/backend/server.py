"""Standalone Dual-Protocol HTTP/HTTPS Server (`dashboard/backend/server.py`)."""
from __future__ import annotations

import json
import mimetypes
import socket
import ssl
import subprocess
import sys
import tempfile
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

    def __init__(self, server_address: Tuple[str, int], RequestHandlerClass: Any) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.ssl_ctx: ssl.SSLContext | None = self._create_self_signed_ssl_context()

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


def run_server(host: str = "127.0.0.1", port: int = 8765, cwd: str | None = None) -> None:
    """Start the PM Control Center Dual HTTP/HTTPS server."""
    if cwd:
        ws_root = Path(cwd).resolve()
        if (ws_root / "memory").is_dir() and not (ws_root / "memory" / "index" / "CONTEXT_INDEX.json").is_file():
            repo_root = DASHBOARD_ROOT.parent
            if str(repo_root) not in sys.path and (repo_root / "schemas").is_dir():
                sys.path.insert(0, str(repo_root))
            from schemas.mcp_tools_core import compile_and_write_indices

            compile_and_write_indices(ws_root)
        set_workspace_root(ws_root)
    server = DualProtocolHTTPServer((host, port), ControlNotebookHandler)
    print(f"🚀 NetArk 專案控管中心已啟動 (同時支援 HTTP 與 HTTPS): http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    run_server("127.0.0.1", port_arg)
