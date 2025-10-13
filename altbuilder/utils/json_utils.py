"""Utility helpers for CLI commands."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import typer


def is_json_mode(ctx: typer.Context) -> bool:
    """Return True if JSON output mode is enabled for the current context."""

    return bool(ctx and getattr(ctx, "obj", None) and ctx.obj.get("json"))


def json_response(
    ctx: typer.Context,
    status: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
    log_path: Optional[str] = None,
    code: Optional[int] = None,
    exit_code: Optional[int] = None,
    **extra: Any,
) -> None:
    """Emit a JSON response honoring the global JSON flag."""

    payload: Dict[str, Any] = {"status": status}
    if params is not None:
        payload["params"] = params
    if message is not None:
        payload["message"] = message
    if log_path is not None:
        payload["log_path"] = log_path
    if code is not None:
        payload["code"] = code
        if exit_code is None:
            exit_code = code
    if extra:
        payload.update(extra)

    typer.echo(json.dumps(payload, ensure_ascii=False))

    if exit_code is not None:
        raise typer.Exit(code=exit_code)
