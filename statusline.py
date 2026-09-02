#!/usr/bin/env python3
"""Entry point for Claude Code's statusLine command.

The engine lives in the claude_statusline package beside this file; this
module exists so `python3 statusline.py` and the installer's shim keep
working. Run with --help for the subcommands.
"""
import sys

from claude_statusline.cli import main

if __name__ == "__main__":
    sys.exit(main())
