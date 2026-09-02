"""SGR colour and OSC-8 hyperlink helpers."""
from __future__ import annotations

from .config import C


def c(color: str, text) -> str:
    if text == "" or text is None:
        return ""
    return f"{C.get(color, '')}{text}{C['reset']}"


def link(url: str | None, text: str) -> str:
    if not url:
        return text
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"
