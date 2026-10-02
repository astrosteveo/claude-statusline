"""The git panels: what they read from a real repository, and how they fill the block."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from claude_statusline import gitpanels  # noqa: E402
from claude_statusline.context import Context  # noqa: E402
from claude_statusline.layout import compile_config  # noqa: E402
from claude_statusline.panels import PANELS, SEP, columns  # noqa: E402
from claude_statusline.render import render_lines  # noqa: E402

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
           GIT_COMMITTER_EMAIL="t@t", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")


def git(cwd, *args, check=True):
    return subprocess.run(["git", *args], cwd=cwd, env=ENV, check=check, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True).stdout


def write(path, text, mode="w"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode) as fh:
        fh.write(text)


def fixture():
    """A repository with an upstream, two branches, a stash, a dirty tree and a rebase stopped
    on a conflict."""
    top = tempfile.mkdtemp()
    origin, work = os.path.join(top, "origin.git"), os.path.join(top, "work")
    git(top, "init", "-q", "--bare", origin)
    git(top, "init", "-q", "-b", "main", work)
    write(os.path.join(work, "docs", "readme.md"), "base\n")
    for i in (1, 2, 3):
        write(os.path.join(work, "src", f"f{i}.py"), f"line {i}\n")
        git(work, "add", ".")
        git(work, "commit", "-qm", f"Add f{i}")
    git(work, "remote", "add", "origin", origin)
    git(work, "push", "-qu", "origin", "main")
    git(work, "checkout", "-qb", "feat/panels")
    write(os.path.join(work, "src", "f1.py"), "x\n", "a")
    git(work, "commit", "-qam", "Draft panels")
    git(work, "push", "-qu", "origin", "feat/panels")
    git(work, "checkout", "-q", "main")
    git(work, "branch", "fix/old")
    write(os.path.join(work, "docs", "readme.md"), "main side\n")
    git(work, "commit", "-qam", "Docs on main")
    git(work, "checkout", "-q", "feat/panels")
    write(os.path.join(work, "src", "f3.py"), "w\n", "a")
    git(work, "stash", "-q", "-m", "tidy f3")
    write(os.path.join(work, "docs", "readme.md"), "feat side\n")
    git(work, "commit", "-qam", "Touch readme on feat")
    git(work, "rebase", "main", check=False)
    write(os.path.join(work, "src", "new.py"), "new\n")
    write(os.path.join(work, "src", "f2.py"), "more\nlines\n", "a")
    return top, work


@unittest.skipUnless(shutil.which("git"), "needs git")
class ReadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.top, cls.work = fixture()
        root, gitdir, common = gitpanels.find_repo(cls.work)
        cls.gitdir, cls.common = gitdir, common
        cls.d = gitpanels.refresh(root, gitdir, common)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.top, ignore_errors=True)

    def test_files(self):
        files = {f[1]: f for f in self.d["files"]}
        self.assertEqual(files["docs/readme.md"][0], "UU")
        self.assertEqual(files["src/f2.py"][:3], (" M", "src/f2.py", 2))
        self.assertEqual(files["src/new.py"][0], "??")

    def test_graph(self):
        commits = [r for r in self.d["graph"] if r[1]]
        self.assertTrue(all(len(r[1]) == 40 for r in commits))
        self.assertIn("Docs on main", [r[4] for r in commits])
        self.assertTrue(any("|/" in r[0] for r in self.d["graph"] if not r[1]))

    def test_branches(self):
        b = {r[1]: r for r in self.d["branches"]}
        self.assertEqual(b["feat/panels"][2], "origin/feat/panels")
        self.assertEqual(b["main"][3], "ahead 1")
        self.assertTrue(b["fix/old"][5])                     # merged into main
        self.assertFalse(b["main"][5])                       # the default branch is never "merged"

    def test_stash_and_rebase(self):
        self.assertEqual([(s[0], s[2]) for s in self.d["stashes"]], [("0", "On feat/panels: tidy f3")])
        p = gitpanels.progress(self.gitdir)
        self.assertEqual((p["op"], p["branch"], p["step"], p["total"]), ("rebasing", "feat/panels", "2", "2"))

    def test_key_moves_on_a_commit(self):
        tmp = tempfile.mkdtemp()
        try:
            git(tmp, "init", "-q", "-b", "main")
            write(os.path.join(tmp, "a"), "1\n")
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "one")
            _, gd, cd = gitpanels.find_repo(tmp)
            before = gitpanels.panel_key(gd, cd)
            write(os.path.join(tmp, "a"), "2\n")
            git(tmp, "commit", "-qam", "two")
            self.assertNotEqual(gitpanels.panel_key(gd, cd), before)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_new_branch_is_not_merged(self):
        tmp = tempfile.mkdtemp()
        try:
            git(tmp, "init", "-q", "-b", "main")
            write(os.path.join(tmp, "a"), "1\n")
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "one")
            git(tmp, "checkout", "-qb", "feat/new")
            b = {r[1]: r for r in gitpanels.branches(tmp, 2.0)}
            self.assertTrue(b["feat/new"][0])
            self.assertFalse(b["feat/new"][5])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_before_git_answers_every_title_shows(self):
        tmp = tempfile.mkdtemp()
        try:
            git(tmp, "init", "-q", "-b", "main")
            comp = compile_config({"preset": "dev"})
            data = {"cwd": tmp}
            ctx = Context(data, comp, cols=160, env={}, live=False)
            rows = [f for f, ln in zip(render_lines(data, comp, ctx=ctx), comp["lines"]) if "panel" in ln]
            self.assertIn("Reading git…", rows[1].text.plain())
            for title in ("Changes", "History", "Branches"):
                self.assertIn(title, rows[0].text.plain())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_no_row_is_only_spaces(self):
        for cols in (40, 200):
            for f in self.block(cols, {"preset": "dev", "panels": {"rows": 12}})[1]:
                self.assertTrue(f.text.plain().strip(), cols)

    def block(self, cols, raw=None):
        comp = compile_config(raw or {"preset": "dev"})
        data = {"model": {"display_name": "Opus"}, "cwd": self.work}
        ctx = Context(data, comp, cols=cols, now=None, env={"COLORTERM": "truecolor"}, sync_git=True)
        fits = render_lines(data, comp, ctx=ctx)
        return ctx, [f for f, ln in zip(fits, comp["lines"]) if "panel" in ln]

    def test_block_keeps_its_height_and_fits(self):
        for cols in (40, 80, 120, 200):
            ctx, rows = self.block(cols)
            self.assertEqual(len(rows), 6, cols)
            for f in rows:
                self.assertIsNotNone(f, cols)
                self.assertLessEqual(f.text.width, ctx.avail, cols)
        text = "\n".join(f.text.plain() for f in self.block(200)[1])
        for word in ("Changes", "History", "Branches", "Stash 1", "rebasing feat/panels", "docs/readme.md"):
            self.assertIn(word, text)

    def test_narrow_drops_the_last_panels(self):
        text = "\n".join(f.text.plain() for f in self.block(80)[1])
        self.assertIn("History", text)
        self.assertNotIn("Branches", text)

    def test_outside_a_repository_there_is_no_block(self):
        comp = compile_config({"preset": "dev"})
        data = {"cwd": tempfile.gettempdir()}
        ctx = Context(data, comp, cols=120, env={}, sync_git=True)
        fits = render_lines(data, comp, ctx=ctx)
        self.assertTrue(all(f is None for f, ln in zip(fits, comp["lines"]) if "panel" in ln))


class LayoutTests(unittest.TestCase):
    def test_dev_preset(self):
        comp = compile_config({"preset": "dev"})
        self.assertEqual(comp["problems"], [])
        self.assertEqual([ln.get("panel") for ln in comp["lines"]], [None, 0, 1, 2, 3, 4, 5])

    def test_dev_holds_live_activity_in_its_one_line(self):
        comp = compile_config({"preset": "dev", "activity": {"enabled": True}})
        self.assertEqual([ln.get("panel") for ln in comp["lines"]], [None, 0, 1, 2, 3, 4, 5])

    def test_panels_come_after_the_activity_line(self):
        comp = compile_config({"preset": "classic", "activity": {"enabled": True}, "panels": {"show": ["files"]}})
        self.assertEqual(comp["problems"], [])
        self.assertEqual([ln.get("panel") for ln in comp["lines"]][:4], [None, None, None, 0])

    def test_bad_settings(self):
        comp = compile_config({"panels": {"show": ["files", "grpah"], "rows": 40}})
        where = [p[1] for p in comp["problems"]]
        self.assertIn("panels.show", where)
        self.assertIn("panels.rows", where)
        self.assertEqual(comp["panels"]["show"], ["files"])
        self.assertEqual(comp["panels"]["rows"], 6)

    def test_game_mode_hides_them(self):
        comp = compile_config({"preset": "arcade", "panels": {"show": ["files"]}})
        self.assertIn(("warning", "panels.show"), [p[:2] for p in comp["problems"]])
        self.assertFalse(any("panel" in ln for ln in comp["lines"]))

    def test_columns(self):
        names = list(PANELS)
        for avail in (20, 60, 100, 140, 300):
            cols = columns(avail, names)
            self.assertTrue(cols)
            self.assertEqual(sum(w for _, w in cols) + len(SEP) * (len(cols) - 1), avail)
            self.assertEqual([n for n, _ in cols], names[:len(cols)])
        self.assertEqual(len(columns(300, names)), 4)


if __name__ == "__main__":
    unittest.main()
