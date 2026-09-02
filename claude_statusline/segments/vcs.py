"""Git state and the pull-request badge."""
from __future__ import annotations

from ..config import CFG, GLYPHS
from ..payload import repo_url
from ..util import dur
from . import Opt, Segment, register


@register
class Git(Segment):
    name = "git"
    doc = "Branch, ahead/behind, staged/dirty/untracked counts, stashes, and a nudge when a dirty tree goes stale."
    priority = 85
    format = ("<dim>{glyph} </dim><link><gitstate>{branch}</gitstate></link>"
              "[ <red>{state}</red>][ <cyan>{ahead}</cyan>][ <cyan>{behind}</cyan>]"
              "[ <dim>{noupstream}</dim>][ <green>{staged}</green>][ <yellow>{dirty}</yellow>]"
              "[ <gray>{untracked}</gray>][ <red>{conflict}</red>][ <gray>{stash}</gray>]"
              "[ <agecolor>{age}</agecolor>][ <dim>{wt}</dim>]")
    options = {
        "links": Opt(bool, True, "OSC-8 hyperlink on the branch when the host names the repo."),
        "last_commit": Opt(bool, True, "Read the last commit time (one more git call when dirty)."),
        "nudge_min": Opt(int, 45, "Minutes since the last commit before `age` appears on a dirty tree."),
    }
    fields = {"glyph": "the git glyph", "branch": "branch, @sha when detached", "url": "branch URL",
              "state": "REBASE, MERGE, CHERRY-PICK, REVERT or BISECT", "ahead": "↑n", "behind": "↓n",
              "noupstream": "∅ when the branch has no upstream", "staged": "+n", "dirty": "~n",
              "untracked": "?n", "conflict": "!n", "stash": "⚑n",
              "age": "⏱ time since last commit, once a dirty tree goes stale",
              "wt": "'wt' inside a linked worktree"}
    colors = {"gitstate": "green when clean, orange when dirty",
              "agecolor": "gray, then yellow past 2h, orange past 4h"}

    def fields_at(self, ctx, opts, level):
        g = ctx.git(opts["last_commit"])
        if not g:
            return None
        branch = g["branch"] or (f"@{g['sha']}" if g["sha"] else "?")
        clean = not (g["staged"] or g["dirty"] or g["untracked"] or g["conflict"])
        base = repo_url(ctx.data) if opts["links"] else None
        f = {
            "glyph": GLYPHS["git"], "branch": branch,
            "url": f"{base}/tree/{g['branch']}" if base and g["branch"] else "",
            "state": g["state"] or "",
            "ahead": f"{GLYPHS['ahead']}{g['ahead']}" if g["ahead"] else "",
            "behind": f"{GLYPHS['behind']}{g['behind']}" if g["behind"] else "",
            "noupstream": "∅" if (not g["behind"] and not g["upstream"] and g["branch"]) else "",
            "staged": f"+{g['staged']}" if g["staged"] else "",
            "dirty": f"~{g['dirty']}" if g["dirty"] else "",
            "untracked": f"?{g['untracked']}" if g["untracked"] else "",
            "conflict": f"!{g['conflict']}" if g["conflict"] else "",
            "stash": f"{GLYPHS['stash']}{g['stash']}" if g["stash"] else "",
            "age": "", "wt": "wt" if ctx.worktree else "",
            "_gitstate": "green" if clean else "orange", "_agecolor": "gray",
        }
        if g["last_commit"]:
            age = ctx.now - g["last_commit"]
            if age >= opts["nudge_min"] * 60:
                f["age"] = f"{GLYPHS['clock']}{dur(age)}"
                f["_agecolor"] = "gray" if age < 7200 else ("yellow" if age < 14400 else "orange")
        return f

    def colors_at(self, ctx, opts, fields):
        return {"gitstate": CFG["colors"][fields["_gitstate"]],
                "agecolor": CFG["colors"][fields["_agecolor"]]}


PR_STATE_COLOR = {"open": "green", "draft": "gray", "merged": "purple",
                  "closed": "red", "mr": "green", "approved": "green",
                  "changes_requested": "orange", "review_required": "yellow",
                  "pending": "yellow"}


def _hunt(n, depth=0):
    if depth > 3 or not isinstance(n, dict):
        return None
    number = n.get("number") or n.get("pr_number") or n.get("prNumber") or n.get("id")
    if isinstance(number, int) and not isinstance(number, bool):
        return n
    for v in n.values():
        if isinstance(v, dict):
            got = _hunt(v, depth + 1)
            if got:
                return got
    return None


@register
class PR(Segment):
    name = "pr"
    doc = "Pull or merge request number, state and check status, when the host supplies one."
    priority = 70
    format = "<link><prstate>{glyph} {sigil}{number}[ {checks}]</prstate></link>"
    options = {"links": Opt(bool, True, "OSC-8 hyperlink to the PR.")}
    fields = {"glyph": "the PR glyph", "sigil": "# for GitHub, ! for GitLab", "number": "PR number",
              "state": "open, draft, merged, closed, or the review state",
              "checks": "✓ ✗ or ● for the check status", "kind": "github or gitlab", "url": "PR URL"}
    colors = {"prstate": "green open/approved, gray draft, purple merged, red closed, "
                         "orange changes requested, yellow awaiting review"}

    def fields_at(self, ctx, opts, level):
        data = ctx.data
        # The host documents a top-level `pr` object (number, url, review_state,
        # kind); older and third-party shapes nest it under github/gitlab.
        node = (data.get("pr") or data.get("github") or data.get("gitlab")
                or data.get("pull_request"))
        pr = _hunt(node) if isinstance(node, dict) else None
        if not pr:
            return None
        number = pr.get("number") or pr.get("pr_number") or pr.get("prNumber") or pr.get("id")
        state = str(pr.get("state") or pr.get("status") or pr.get("review_state") or "open").lower()
        if pr.get("draft") or pr.get("is_draft"):
            state = "draft"
        checks = str(pr.get("checks") or pr.get("check_status") or "").lower()
        mark = {"failure": "✗", "failing": "✗", "error": "✗", "success": "✓", "passing": "✓",
                "pending": "●", "running": "●"}.get(checks, "")
        kind = str(pr.get("kind") or ("gitlab" if "gitlab" in data else "github")).lower()
        url = pr.get("url") or pr.get("html_url") or ""
        if not url:
            base = repo_url(data)
            url = f"{base}/pull/{number}" if base else ""
        return {"glyph": GLYPHS["pr"], "sigil": "!" if "gitlab" in kind or kind == "mr" else "#",
                "number": str(number), "state": state, "checks": mark, "kind": kind,
                "url": url if opts["links"] else "",
                "_color": PR_STATE_COLOR.get(state, "cyan")}

    def colors_at(self, ctx, opts, fields):
        return {"prstate": CFG["colors"][fields["_color"]]}


@register
class Worktree(Segment):
    name = "worktree"
    doc = "The worktree session the host reports (name and branch)."
    priority = 62
    format = "<cyan>{glyph} {name}</cyan><dim>[ {branch}]</dim>"
    fields = {"glyph": "the worktree glyph (⎇)", "name": "worktree name",
              "branch": "worktree branch", "original_branch": "branch the worktree was cut from"}

    def fields_at(self, ctx, opts, level):
        wt = ctx.data.get("worktree")
        if not isinstance(wt, dict):
            name = ctx.worktree
            if not name:
                return None
            wt = {"name": name}
        name = wt.get("name") or ""
        if not name:
            return None
        return {"glyph": GLYPHS["git"], "name": str(name), "branch": str(wt.get("branch") or ""),
                "original_branch": str(wt.get("original_branch") or "")}
