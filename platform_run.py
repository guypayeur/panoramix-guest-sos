#!/usr/bin/env python3
"""Panoramix entrypoint for sos (binds PLATFORM_LISTEN_HTTP).

Stdlib-only HTTP stub. Domain code may grow under sos/; this file stays the
Unit artifact / entrypoint and does not import that package (apply digest is
entrypoint paths only).
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 18280

HEALTH_PAYLOAD = {"status": "ok"}
INFO_PAYLOAD = {
    "name": "sos",
    "product": "panoramix-guest-sos",
    "kind": "placeholder",
    "contract_version": "0.5",
    "status": "skeleton",
    "iec_equivalent": False,
    "engines": "runtime-bindings-only",
}


def parse_listen(raw: str) -> tuple[str, int]:
    """Accept port, :port, or host:port. Port-only keeps emulate loopback."""
    raw = (raw or str(DEFAULT_PORT)).strip()
    if raw.startswith(":"):
        return "0.0.0.0", int(raw[1:])
    if ":" in raw:
        host, port = raw.rsplit(":", 1)
        if host in ("", "*", "[::]"):
            host = "0.0.0.0"
        return host, int(port)
    return "127.0.0.1", int(raw)


class SosHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def _send_json(self, status: int, payload: dict) -> None:
        body = (json.dumps(payload) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._send_json(200, HEALTH_PAYLOAD)
            return
        if path == "/v0/info":
            self._send_json(200, INFO_PAYLOAD)
            return
        self._send_json(404, {"error": "not_found", "path": path})


class SosServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main() -> None:
    raw = (
        os.environ.get("PLATFORM_LISTEN_HTTP")
        or os.environ.get("PLATFORM_LISTEN_http")
        or str(DEFAULT_PORT)
    )
    host, port = parse_listen(raw)
    httpd = SosServer((host, port), SosHandler)
    print(f"sos listening on {host}:{port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
