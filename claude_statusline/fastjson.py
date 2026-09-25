"""Parse the payload without importing `json`.

`json` imports `re` at start-up, which together cost more than drawing the
whole bar. The C scanner underneath (`_json`) needs neither, so the hot
path uses it directly and falls back to `json` only if it is missing.
"""
from __future__ import annotations


class _Ctx:
    strict = False
    object_hook = None
    object_pairs_hook = None
    parse_float = float
    parse_int = int
    parse_constant = {"-Infinity": float("-inf"), "Infinity": float("inf"), "NaN": float("nan")}.__getitem__
    memo = None


_scan = None


def loads(text):
    """The JSON value in `text` (str or bytes). Raises ValueError on junk."""
    global _scan
    if isinstance(text, (bytes, bytearray)):
        text = text.decode("utf-8", "replace")
    text = text.strip()
    if text.startswith("﻿"):
        text = text[1:]
    if _scan is None:
        try:
            import _json
            _scan = _json.make_scanner(_Ctx())
        except Exception:
            import json
            return json.loads(text)
    try:
        value, end = _scan(text, 0)
    except StopIteration as exc:
        raise ValueError(f"not JSON at {exc.value}") from None
    if text[end:].strip():
        raise ValueError(f"extra data at {end}")
    return value
