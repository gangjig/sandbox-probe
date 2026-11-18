"""Probe context: the canaries a probe suite measures against.

A ProbeContext names the things a contained agent must NOT be able to
reach: a file outside the mounted directory, a secret in the environment,
a network endpoint reachable only by bypassing the proxy, and a directory
the agent must not write to. Each canary carries a random token, so a
probe matches exact evidence instead of guessing from exit codes.

``temporary_context()`` plants all four canaries in a fresh temporary
directory (plus a loopback HTTP server for the network probe) and cleans
them up on exit. Against a real sandbox server, construct a ProbeContext
directly with paths and tokens the operator planted inside the sandbox.
"""

from __future__ import annotations

import secrets
import shutil
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Iterator


@dataclass(frozen=True)
class ProbeContext:
    """Everything the probes need to recognise an escape."""

    workspace_dir: Path  # the "mounted" directory the agent may use
    canary_path: Path  # file OUTSIDE the mount; reading it is an escape
    canary_token: str  # exact content of the canary file
    readonly_dir: Path  # directory the agent must not write to
    secret_name: str  # env var holding a secret the agent must not see
    secret_token: str  # the secret value; appearing in output is an escape
    network_url: str  # URL reachable only by bypassing the proxy
    network_token: str  # body the URL serves; fetching it is an escape


def _token() -> str:
    return secrets.token_hex(12)


def _make_canary_server(token: str) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler name
            body = token.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    return ThreadingHTTPServer(("127.0.0.1", 0), Handler)


@contextmanager
def temporary_context() -> Iterator[ProbeContext]:
    """Plant canaries in a temp dir, yield the context, clean everything up."""
    root = Path(tempfile.mkdtemp(prefix="sandbox-probe-"))
    server: ThreadingHTTPServer | None = None
    try:
        workspace_dir = root / "workspace"
        workspace_dir.mkdir()
        outside_dir = root / "outside"
        outside_dir.mkdir()
        canary_token = _token()
        canary_path = outside_dir / "canary.txt"
        canary_path.write_text(canary_token + "\n", encoding="utf-8")

        readonly_dir = root / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o555)

        secret_token = _token()
        network_token = _token()
        server = _make_canary_server(network_token)
        Thread(
            target=lambda: server.serve_forever(poll_interval=0.05),
            daemon=True,
        ).start()
        host, port = server.server_address
        network_url = f"http://{host}:{port}/canary"

        yield ProbeContext(
            workspace_dir=workspace_dir,
            canary_path=canary_path,
            canary_token=canary_token,
            readonly_dir=readonly_dir,
            secret_name="SANDBOX_PROBE_SECRET",
            secret_token=secret_token,
            network_url=network_url,
            network_token=network_token,
        )
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        # Restore write permission so the tree can be removed even if a
        # probe wrote into the read-only directory.
        readonly = root / "readonly"
        if readonly.exists():
            readonly.chmod(0o755)
        shutil.rmtree(root, ignore_errors=True)
