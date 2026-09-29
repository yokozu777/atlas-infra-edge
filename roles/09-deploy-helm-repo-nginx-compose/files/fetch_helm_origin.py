#!/usr/bin/env python3
"""Fetch a Helm index or chart from the primary origin, then the backup.

Returns a body only when the download finishes. A stall or a short body
(CloudFront sending headers and then stopping) is a failure, not a 200.
"""

from __future__ import annotations

import argparse
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urljoin


def fetch_complete(url: str, *, stall: float, overall: float, limit: int) -> bytes | None:
    """Return the full body, or None when the origin errors, stalls, or truncates."""
    request = urllib.request.Request(url, headers={"User-Agent": "atlas-helm-origin-fetch"})
    deadline = time.monotonic() + overall
    try:
        response = urllib.request.urlopen(request, timeout=stall)
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
        return None
    expected_raw = response.headers.get("Content-Length")
    try:
        expected = int(expected_raw) if expected_raw else None
    except ValueError:
        expected = None
    if expected is not None and expected > limit:
        response.close()
        return None
    chunks: list[bytes] = []
    size = 0
    try:
        while time.monotonic() < deadline:
            try:
                chunk = response.read(65536)
            except (TimeoutError, socket.timeout):
                return None
            if not chunk:
                if expected is None or size == expected:
                    return b"".join(chunks)
                return None
            size += len(chunk)
            if size > limit:
                return None
            chunks.append(chunk)
            if expected is not None and size >= expected:
                return b"".join(chunks)
    finally:
        response.close()
    return None


def choose_body(primary: str, backup: str, *, stall: float, overall: float, limit: int) -> bytes | None:
    body = fetch_complete(primary, stall=stall, overall=overall, limit=limit)
    if body:
        return body
    if not backup:
        return None
    return fetch_complete(backup, stall=stall, overall=overall, limit=limit)


class FetchHandler(BaseHTTPRequestHandler):
    config: dict[str, dict[str, str]] = {}
    index_stall = 8.0
    index_overall = 20.0
    chart_stall = 20.0
    chart_overall = 300.0
    limit = 200 * 1024 * 1024

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        path = unquote(self.path.split("?", 1)[0])
        kind, host, suffix = self._split(path)
        spec = self.config.get(host) if host else None
        if kind is None or spec is None:
            self.send_error(404)
            return
        primary = urljoin(spec["primary"].rstrip("/") + "/", suffix.lstrip("/"))
        backup_base = (spec.get("backup") or "").strip()
        backup = urljoin(backup_base.rstrip("/") + "/", suffix.lstrip("/")) if backup_base else ""
        if kind == "index":
            body = choose_body(
                primary, backup, stall=self.index_stall, overall=self.index_overall, limit=self.limit
            )
            content_type = "application/yaml"
        else:
            body = choose_body(
                primary, backup, stall=self.chart_stall, overall=self.chart_overall, limit=self.limit
            )
            content_type = "application/octet-stream"
        if not body:
            self.send_error(502)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _split(path: str) -> tuple[str | None, str | None, str | None]:
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 3 and parts[0] == "raw" and parts[-1] == "index.yaml":
            return "index", parts[1], "index.yaml"
        if len(parts) >= 3 and parts[0] == "chart":
            return "chart", parts[1], "/".join(parts[2:])
        return None, None, None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=18081)
    args = parser.parse_args()
    FetchHandler.config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    server = ThreadingHTTPServer((args.bind, args.port), FetchHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        thread.join()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
