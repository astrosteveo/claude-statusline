"""Reading the host payload where its shape is not fixed."""
from __future__ import annotations

from .config import CFG
from .util import dig, num


def repo_url(data) -> str | None:
    if not CFG["features"]["repo_links"]:
        return None
    host = dig(data, "workspace", "repo", "host")
    owner = dig(data, "workspace", "repo", "owner")
    name = dig(data, "workspace", "repo", "name")
    if host and owner and name:
        return f"https://{host}/{owner}/{name}"
    return None

def _norm_key(key) -> str:
    """fiveHour / five-hour / FiveHour -> five_hour."""
    out = []
    prev_lower = False
    for ch in str(key):
        if ch.isupper() and prev_lower:
            out.append("_")
        out.append(ch.lower())
        prev_lower = ch.islower() or ch.isdigit()
    return "".join(out).replace("-", "_")


def find_windows(data):
    """Locate the 5h / 7d windows, tolerating key-name and shape variants."""
    node = data.get("rate_limits") or data.get("rateLimits") or data
    found = {}

    def take(slot, obj, label=None):
        if not isinstance(obj, dict) or slot in found:
            return
        pct = num(obj.get("used_percentage", obj.get("usedPercentage")))
        if pct is None:
            return
        found[slot] = {"pct": pct, "label": label,
                       "resets_at": obj.get("resets_at", obj.get("resetsAt"))}

    def classify(key, obj):
        k = _norm_key(key)
        if "five_hour" in k or k in ("5h", "five", "session"):
            take("5h", obj)
        elif "seven_day" in k or "week" in k or k in ("7d", "seven"):
            model = next((m for m in ("opus", "sonnet", "haiku") if m in k), None)
            take("7d_model" if model else "7d", obj, model)
        else:
            return False
        return True

    def walk(obj, depth=0):
        if depth > 3:
            return
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    tag = item.get("window") or item.get("type") or ""
                    if not classify(tag, item):
                        walk(item, depth + 1)
            return
        if not isinstance(obj, dict):
            return
        for key, val in obj.items():
            if isinstance(val, (dict, list)) and not classify(key, val):
                walk(val, depth + 1)

    walk(node)
    if "7d" not in found and "7d_model" in found:
        found["7d"] = found["7d_model"]
    return found
