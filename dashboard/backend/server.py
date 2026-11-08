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
from urllib.parse import unquote, urlparse

DASHBOARD_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = DASHBOARD_ROOT / "frontend"
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

from backend.graph_scanner import (
    build_project_graph_payload,
    get_node_detail,
    list_registered_projects,
    trigger_project_rescan,
)


def dispatch_api_request(method: str, path: str) -> Tuple[int, Dict[str, Any]]:
    """Route REST API requests for the PM Control Center."""
    parsed = urlparse(path)
    clean_path = parsed.path.rstrip("/")

    if method == "GET" and clean_path == "/api/projects":
        return 200, {"projects": list_registered_projects()}

    parts = [unquote(p) for p in clean_path.split("/") if p]
    if len(parts) == 4 and parts[0] == "api" and parts[1] == "project" and parts[3] == "overview":
        pid = parts[2]
        try:
            return 200, build_project_graph_payload(pid)
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
        target = (FRONTEND_DIR / rel).resolve()
        if not str(target).startswith(str(FRONTEND_DIR.resolve())) or not target.is_file():
            target = FRONTEND_DIR / "index.html"
        if not target.exists():
            self._send_json(404, {"error": "Frontend asset not found"})
            return

        content = target.read_bytes()
        mime, _ = mimetypes.guess_type(str(target))
        self.send_response(200)
        self.send_header("Content-Type", f"{mime or 'text/html'}; charset=utf-8")
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
            tmp_dir = Path(tempfile.gettempdir()) / "prism_dashboard_tls"
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
            pass
        return conn, addr


def run_server(host: str = "0.0.0.0", port: int = 8765) -> None:
    """Start the PM Control Center Dual HTTP/HTTPS server."""
    server = DualProtocolHTTPServer((host, port), ControlNotebookHandler)
    print(f"🚀 P.R.I.S.M. 專案控管中心已啟動 (同時支援 HTTP 與 HTTPS): http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    run_server("0.0.0.0", port_arg)
