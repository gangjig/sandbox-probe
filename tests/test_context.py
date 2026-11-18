"""temporary_context: canary planting, the loopback server, and cleanup."""

from __future__ import annotations

import stat
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from sandbox_probe.context import ProbeContext, temporary_context


def test_canary_file_sits_outside_the_workspace(ctx):
    assert ctx.canary_path.read_text(encoding="utf-8").strip() == ctx.canary_token
    assert ctx.workspace_dir not in ctx.canary_path.parents
    assert ctx.canary_path.parent != ctx.workspace_dir


def test_workspace_and_readonly_dirs_exist(ctx):
    assert ctx.workspace_dir.is_dir()
    assert ctx.readonly_dir.is_dir()
    assert ctx.readonly_dir != ctx.workspace_dir


def test_readonly_dir_has_no_write_bit(ctx):
    mode = stat.S_IMODE(ctx.readonly_dir.stat().st_mode)
    assert mode == 0o555


def test_tokens_are_nonempty_and_distinct(ctx):
    assert ctx.canary_token
    assert ctx.secret_token
    assert ctx.network_token
    assert len({ctx.canary_token, ctx.secret_token, ctx.network_token}) == 3


def test_tokens_differ_between_contexts():
    with temporary_context() as first, temporary_context() as second:
        assert first.canary_token != second.canary_token
        assert first.secret_token != second.secret_token
        assert first.network_token != second.network_token


def test_network_server_serves_the_token(ctx):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    body = opener.open(ctx.network_url, timeout=5).read().decode("utf-8")
    assert body == ctx.network_token


def test_context_is_a_frozen_dataclass(ctx):
    assert isinstance(ctx, ProbeContext)
    with pytest.raises(AttributeError):
        ctx.canary_token = "mutated"  # type: ignore[misc]


def test_cleanup_removes_temp_dirs_and_stops_the_server():
    with temporary_context() as ctx:
        root = ctx.workspace_dir.parent
        url = ctx.network_url
        assert root.exists()
    assert not root.exists()
    with pytest.raises(urllib.error.URLError):
        urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        ).open(url, timeout=2)
