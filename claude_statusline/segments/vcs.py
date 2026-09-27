"""Git state, the pull request, and the worktree."""
from __future__ import annotations

from ..fit import LEAN, LESS, NARROW, TEXT
from ..payload import find_pr, repo_url
from ..util import dur
from ..width import clip
from . import Opt, Segment, register


@register
class Git(Segment):
    name = "git"
    doc = ("Branch, ahead/behind, staged/modified/untracked counts, stashes, conflicts, and a "
           "nudge when a dirty tree has gone a while without a commit.")
    priority = 85
    tone = "green"
    glance = True
    format = ("<link><gitstate><bold>{branch}</bold></gitstate></link>[ <red><bold>{state}</bold></red>]"
              "[ <cyan>{sync}</cyan>][ <muted>{noupstream}</muted>][ <green>{staged}</green>]"
              "[ <yellow>{dirty}</yellow>][ <subtext>{untracked}</subtext>][ <red>{conflict}</red>]"
              "[ <subtext>{stash}</subtext>][ <agecolor>{age}</agecolor>]")
    options = {
        "links": Opt(bool, True, "Make the branch a link when the host names the repository."),
        "last_commit": Opt(bool, True, "Read the last commit's time, for the {age} nudge."),
        "nudge_min": Opt(int, 45, "Minutes without a commit before {age} appears on a dirty tree."),
        "max_branch": Opt(int, 32, "Longest branch name shown; longer ones end in …"),
    }
    fields_doc = {"branch": "the branch, or @sha when detached", "url": "the branch's web URL",
                  "state": "REBASE, MERGE, CHERRY-PICK, REVERT or BISECT", "sync": "⇡ahead ⇣behind",
                  "ahead": "commits ahead", "behind": "commits behind",
                  "noupstream": "∅ when the branch has no upstream", "staged": "+staged",
                  "dirty": "~modified", "untracked": "?untracked", "conflict": "!conflicted",
                  "stash": "stash count", "age": "time since the last commit, once a dirty tree goes stale",
                  "changes": "all local changes as one count", "clean": "✓ when nothing is changed"}
    colors_doc = {"gitstate": "green when clean, orange with changes, red with conflicts",
                  "agecolor": "subtext, yellow past 2h, orange past 4h"}

    def fields(self, ctx, opts, level):
        g = ctx.git(opts["last_commit"])
        if not g:
            return None
        m = ctx.mark
        branch = g.get("branch") or (f"@{g['sha']}" if g.get("sha") else "HEAD")
        cap = opts["max_branch"] if level < LEAN else (20 if level < NARROW else 14)
        branch = clip(branch, max(6, cap))
        staged, dirty = g.get("staged", 0), g.get("dirty", 0)
        untracked, conflict = g.get("untracked", 0), g.get("conflict", 0)
        changes = staged + dirty + untracked + conflict
        ahead, behind = g.get("ahead", 0), g.get("behind", 0)
        sync = (f"{m('ahead')}{ahead}" if ahead else "") + (f"{m('behind')}{behind}" if behind else "")
        base = repo_url(ctx.data) if opts["links"] else None
        f = {"branch": branch, "url": f"{base}/tree/{g['branch']}" if base and g.get("branch") else "",
             "state": g.get("state") or "", "sync": sync, "ahead": str(ahead) if ahead else "",
             "behind": str(behind) if behind else "",
             "noupstream": m("noupstream") if (not g.get("pending") and not g.get("upstream")
                                                and g.get("branch") and level < LESS) else "",
             "staged": f"{m('staged')}{staged}" if staged else "",
             "dirty": f"{m('dirty')}{dirty}" if dirty else "",
             "untracked": f"{m('untracked')}{untracked}" if untracked and level < LEAN else "",
             "conflict": f"{m('conflict')}{conflict}" if conflict else "",
             "stash": f"{m('stash')}{g['stash']}" if g.get("stash") and level < LESS else "",
             "age": "", "changes": str(changes) if changes else "",
             "clean": m("ok") if not changes and not g.get("pending") else "",
             "_tone": "red" if conflict else ("orange" if changes else "green"), "_age": "subtext"}
        if level >= NARROW:
            # One mark for "there are changes" instead of every count.
            f.update(staged="", untracked="", stash="", sync="",
                     dirty=f"{m('dirty')}{changes}" if changes else "")
        if level >= TEXT:
            f["noupstream"] = ""
        last = g.get("last_commit")
        if last and changes and level < LESS:
            age = ctx.now - last
            if age >= opts["nudge_min"] * 60:
                f["age"] = f"{m('age')}{dur(age)}"
                f["_age"] = "subtext" if age < 7200 else ("yellow" if age < 14400 else "orange")
        return f

    def colors(self, ctx, opts, f):
        return {"gitstate": f["_tone"], "agecolor": f["_age"]}

    def tone_at(self, ctx, opts, f):
        return f["_tone"]


REVIEW = {"approved": ("green", "approved"), "changes_requested": ("orange", "changes"),
          "pending": ("yellow", "review"), "review_required": ("yellow", "review"),
          "draft": ("muted", "draft"), "merged": ("purple", "merged"), "closed": ("red", "closed"),
          "open": ("green", "")}


@register
class PR(Segment):
    name = "pr"
    doc = "The pull or merge request for this branch, its review state and checks."
    priority = 70
    tone = "purple"
    glance = True
    format = "<link><prstate><bold>{sigil}{number}</bold></prstate></link>[ <muted>{review}</muted>][ {checks}]"
    options = {"links": Opt(bool, True, "Link the number to the pull request.")}
    fields_doc = {"sigil": "# for GitHub, ! for GitLab", "number": "the number", "url": "its URL",
                  "state": "approved, pending, changes_requested, draft…", "review": "a word for the state",
                  "checks": "✓ ✗ or ● for the checks", "kind": "github or gitlab"}
    colors_doc = {"prstate": "green approved/open, yellow awaiting review, orange changes requested, "
                             "grey draft, purple merged, red closed"}

    def fields(self, ctx, opts, level):
        data = ctx.data
        pr = find_pr(data)
        if not pr:
            return None
        number = pr.get("number") or pr.get("pr_number") or pr.get("prNumber") or pr.get("id")
        state = str(pr.get("review_state") or pr.get("state") or pr.get("status") or "open").lower()
        if pr.get("draft") or pr.get("is_draft"):
            state = "draft"
        checks = str(pr.get("checks") or pr.get("check_status") or "").lower()
        m = ctx.mark
        mark = {"failure": ("fail", "red"), "failing": ("fail", "red"), "error": ("fail", "red"),
                "success": ("ok", "green"), "passing": ("ok", "green"),
                "pending": ("wait", "yellow"), "running": ("wait", "yellow")}.get(checks)
        kind = str(pr.get("kind") or ("gitlab" if "gitlab" in data else "github")).lower()
        url = pr.get("url") or pr.get("html_url") or ""
        if not url:
            base = repo_url(data)
            url = f"{base}/pull/{number}" if base else ""
        role, word = REVIEW.get(state, ("purple", state))
        from ..text import Text
        return {"sigil": "!" if kind in ("gitlab", "mr") else "#", "number": str(number), "state": state,
                "review": word if level < LEAN else "", "kind": kind,
                "checks": Text.of(m(mark[0]), (ctx.color(mark[1]), None, 0, None)) if mark else "",
                "url": url if opts["links"] else "", "_role": role}

    def colors(self, ctx, opts, f):
        return {"prstate": f["_role"]}

    def tone_at(self, ctx, opts, f):
        return f["_role"]


@register
class Worktree(Segment):
    name = "worktree"
    doc = "The worktree this session runs in, and its branch."
    priority = 62
    tone = "teal"
    format = "<teal>{name}</teal>[ <muted>{branch}</muted>]"
    fields_doc = {"name": "the worktree's name", "branch": "its branch",
                  "original_branch": "the branch it was cut from"}

    def fields(self, ctx, opts, level):
        from ..util import dig
        wt = ctx.data.get("worktree")
        if not isinstance(wt, dict):
            name = dig(ctx.data, "workspace", "git_worktree")
            if not name:
                return None
            wt = {"name": name}
        name = wt.get("name") or ""
        if not name:
            return None
        return {"name": str(name), "branch": str(wt.get("branch") or "") if level < LEAN else "",
                "original_branch": str(wt.get("original_branch") or "")}
