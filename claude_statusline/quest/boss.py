"""Bosses: a failing test, build or lint run summons one; fixing it is the fight.

A boss's HP is the number of failures the run reported. Each later run of
the same kind in the same project sets HP to the new failure count, and a
clean run defeats it.
"""
import random
import re

KIND_ICON = {"test": "🐍", "build": "🗿", "lint": "👺"}
KIND_NOUN = {"test": "tests", "build": "build", "lint": "lint errors"}
NAMES = {
    "test": ["Flaky Test Hydra", "Assertion Wraith", "Mock Mimic", "Race Condition Twins",
             "Snapshot Doppelganger", "Off-by-One Ogre", "Null Pointer Poltergeist"],
    "build": ["Type Error Golem", "Linker Lich", "Dependency Hydra", "Circular Import Ouroboros",
              "Missing Semicolon Imp", "Webpack Behemoth", "Version Conflict Chimera"],
    "lint": ["Lint Goblin Horde", "Unused Import Swarm", "Trailing Whitespace Wisp",
             "Style Guide Stickler", "Shadowed Variable Shade"],
}
ESCAPE_AFTER = 24 * 3600
MAX_HP = 12

# Wrappers that may precede the real command in a segment.
_WRAPPERS = re.compile(
    r"^(?:(?:sudo|time|nice|env|command|exec|timeout\s+\S+|xvfb-run|npx|bunx|pnpm\s+exec|"
    r"pnpm\s+dlx|yarn\s+dlx|uv\s+run|poetry\s+run|pipenv\s+run|hatch\s+run|pdm\s+run|"
    r"dotenv\s+--|[A-Za-z_][A-Za-z0-9_]*=\S*)\s+)+")
_PM = r"(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?"
_RUNNERS = [
    ("test", re.compile(
        r"^(?:pytest|py\.test|nose2|tox|nox|jest|vitest|mocha|ava|jasmine|karma|rspec|phpunit|"
        r"pest|ctest|go\s+test|cargo\s+(?:test|nextest)|deno\s+test|bun\s+test|dotnet\s+test|"
        r"mix\s+test|swift\s+test|flutter\s+test|playwright\s+test|cypress\s+run|"
        r"python3?\s+-m\s+(?:pytest|unittest)|(?:mvnw?|\./mvnw|gradlew?|\./gradlew)\s+(?:\S+\s+)*test|"
        r"make\s+(?:\S+\s+)*(?:test|check)|" + _PM + r"test)\b")),
    ("lint", re.compile(
        r"^(?:eslint|biome\s+(?:check|lint|ci)|ruff(?:\s+check)?|flake8|pylint|mypy|pyright|"
        r"golangci-lint|shellcheck|stylelint|rubocop|cargo\s+clippy|prettier\s+(?:--check|-c)|"
        + _PM + r"(?:lint|typecheck|type-check))\b")),
    ("build", re.compile(
        r"^(?:tsc|cargo\s+(?:build|check)|go\s+(?:build|vet)|dotnet\s+build|cmake\s+--build|ninja|"
        r"(?:mvnw?|\./mvnw)\s+(?:\S+\s+)*(?:compile|package|install)|"
        r"(?:gradlew?|\./gradlew)\s+(?:\S+\s+)*(?:build|assemble)|vite\s+build|next\s+build|"
        r"webpack|esbuild|rollup|swift\s+build|zig\s+build|javac|make|" + _PM + r"(?:build|compile))\b")),
]

_COUNTS = [
    re.compile(r"(\d+)\s+(?:failed|failing|failures?)\b"),       # pytest, jest, vitest, mocha
    re.compile(r"test result: FAILED\.\s*\d+ passed;\s*(\d+) failed"),  # cargo
    re.compile(r"Found (\d+) errors?"),                           # tsc
    re.compile(r"due to (\d+) previous errors?"),                 # rustc
    re.compile(r"\((\d+) errors?,"),                              # eslint "(3 errors, 0 warnings)"
    re.compile(r"(\d+) errors? (?:generated|found|emitted)"),     # clang, mypy
    re.compile(r"Found (\d+) errors? in"),                        # mypy
]
_UNITTEST = re.compile(r"FAILED \((?:failures|errors)=(\d+)(?:, (?:failures|errors)=(\d+))?")
_LINE_MARKERS = re.compile(r"^(?:FAILED |FAIL[:\s]|--- FAIL|✗|×|error(?:\[\w+\])?:)", re.M)
_PASS_ZERO = re.compile(r"\b0 (?:failed|failures|errors)\b")


def segments(command):
    for part in re.split(r"\|\||&&|[;|\n]", command):
        part = part.strip().lstrip("({").strip()
        part = re.sub(r"^(?:then|do|else)\s+", "", part)
        part = _WRAPPERS.sub("", part)
        if part:
            yield part


def classify(command):
    """'test', 'lint', 'build' or None, from the commands a shell line runs."""
    found = None
    for part in segments(command or ""):
        bare = re.sub(r"^(?:pnpm|yarn|bun)\s+(?!run\b|test\b|build\b|lint\b)", "", part)
        for kind, rx in _RUNNERS:
            if rx.match(part) or rx.match(bare):
                if kind == "test":
                    return "test"
                found = found or kind
                break
    return found


def count_failures(text):
    """Failures a run reported: an int, 0 for an explicit all-clear, None if silent."""
    text = text or ""
    m = _UNITTEST.search(text)
    if m:
        return sum(int(g) for g in m.groups() if g)
    best = None
    for rx in _COUNTS:
        for m in rx.finditer(text):
            n = int(m.group(1))
            best = n if best is None else max(best, n)
    if best is not None:
        return best
    markers = len(_LINE_MARKERS.findall(text))
    if markers:
        return markers
    if _PASS_ZERO.search(text):
        return 0
    return None


def spawn(kind, project, failures, now, rng=None, names=None):
    rng = rng or random.Random()
    hp = max(1, min(MAX_HP, failures or 3))
    return {"name": rng.choice(names or NAMES[kind]), "kind": kind, "icon": KIND_ICON[kind],
            "project": project, "hp": hp, "max_hp": hp, "spawned": now, "attempts": 1}
