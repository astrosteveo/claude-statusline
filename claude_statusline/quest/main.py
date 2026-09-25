"""`statusline.py quest ...` and `claude-quest ...`: the hook and the game's commands."""
import sys


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["hook"]:
        from .hooks import run
        return run()
    from .cli import main as cli
    return cli(argv)
