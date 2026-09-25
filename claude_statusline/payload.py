"""Reading the host payload where its shape is not fixed.

Claude Code documents most fields, but rate-limit windows have arrived in
snake_case, camelCase, as lists and nested one level down, and the parser
accepts all of them rather than go blank when the host changes its mind.
"""
from __future__ import annotations

from .util import dig, num


def repo_url(data):
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


MODEL_KEYS = ("opus", "sonnet", "haiku", "fable")
SEVEN_DAY_KEYS = ("seven_day", "7d", "seven", "week", "weekly")


def find_windows(data):
    """The 5h / 7d / per-model / spend windows: {slot: {pct, label, resets_at}}."""
    node = data.get("rate_limits") or data.get("rateLimits") or data
    found = {}

    def take(slot, obj, label=None):
        if not isinstance(obj, dict) or slot in found:
            return
        pct = num(obj.get("used_percentage", obj.get("usedPercentage", obj.get("utilization"))))
        if pct is None:
            return
        found[slot] = {"pct": max(0.0, min(100.0, pct)), "label": label,
                       "resets_at": obj.get("resets_at", obj.get("resetsAt"))}

    def take_scoped(obj):
        scoped = obj.get("model_scoped", obj.get("modelScoped"))
        for item in scoped if isinstance(scoped, list) else ():
            if isinstance(item, dict):
                name = item.get("display_name", item.get("displayName"))
                if name:
                    take("7d_model", item, str(name).strip())

    def classify(key, obj):
        k = _norm_key(key)
        if "five_hour" in k or k in ("5h", "five", "session"):
            take("5h", obj)
        elif "spend" in k:
            take("spend", obj)
        elif "seven_day" in k or "week" in k or k in ("7d", "seven"):
            model = next((m for m in MODEL_KEYS if m in k), None)
            if model:
                take("7d_model", obj, model)
            elif k in SEVEN_DAY_KEYS:
                take("7d", obj)
            # Anything else qualifying the weekly window meters something
            # narrower than the plain one; drawing it as the plain one would
            # be worse than leaving it out.
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

    if isinstance(node, dict):
        take_scoped(node)
    walk(node)
    if "7d" not in found and "7d_model" in found:
        found["7d"] = found["7d_model"]
    return found


def find_pr(data):
    """The PR/MR object from the documented `pr` field or older shapes."""
    node = data.get("pr") or data.get("github") or data.get("gitlab") or data.get("pull_request")

    def hunt(n, depth=0):
        if depth > 3 or not isinstance(n, dict):
            return None
        number = n.get("number") or n.get("pr_number") or n.get("prNumber") or n.get("id")
        if isinstance(number, int) and not isinstance(number, bool):
            return n
        for v in n.values():
            got = hunt(v, depth + 1)
            if got:
                return got
        return None
    return hunt(node) if isinstance(node, dict) else None
