"""Reading the host payload where its shape is not fixed."""
from __future__ import annotations

from .util import dig, num


def repo_url(data) -> str | None:
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


# Model families that qualify a weekly window's key, e.g. `seven_day_fable`.
MODEL_KEYS = ("opus", "sonnet", "haiku", "fable")

# Keys that mean the overall weekly window rather than a slice of it.
SEVEN_DAY_KEYS = ("seven_day", "7d", "seven", "week", "weekly")


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

    def take_scoped(obj):
        """`model_scoped`: the documented per-model weekly windows, each entry
        naming its own model rather than qualifying a key. Nothing sends it
        today; reading it here means `limit_7d_model` lights up on its own if
        anything ever does.
        """
        scoped = obj.get("model_scoped", obj.get("modelScoped"))
        for item in scoped if isinstance(scoped, list) else ():
            if not isinstance(item, dict):
                continue
            name = item.get("display_name", item.get("displayName"))
            if name:
                take("7d_model",
                     {"used_percentage": item.get("utilization", item.get("used_percentage")),
                      "resets_at": item.get("resets_at", item.get("resetsAt"))},
                     str(name).strip())

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
            # Anything else qualifying the weekly window — seven_day_oauth_apps,
            # seven_day_overage_included — meters something narrower than the
            # plain one. Drawing it as the plain one would be worse than
            # leaving it out.
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
