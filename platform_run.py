#!/usr/bin/env python3
"""Panoramix entrypoint for sos (binds PLATFORM_LISTEN_HTTP).

Thin Unit artifact — same pattern as panoramix-guest-httpbin: this file imports
domain from sos/ (sos.http) the way httpbin's platform_run imports
httpbin.core.app. Emulate digest is still entrypoint paths only; sibling edits
under sos/ must not be assumed to change it.
"""

from __future__ import annotations

import os

from sos.http import SosApp, SosServer, bind_handler

DEFAULT_PORT = 18280


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


def main() -> None:
    raw = (
        os.environ.get("PLATFORM_LISTEN_HTTP")
        or os.environ.get("PLATFORM_LISTEN_http")
        or str(DEFAULT_PORT)
    )
    host, port = parse_listen(raw)
    app = SosApp()
    httpd = SosServer((host, port), bind_handler(app))
    print(f"sos listening on {host}:{port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
