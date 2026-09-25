#!/usr/bin/env python3
"""Entry point for Claude Code's statusLine command.

The engine lives in the claude_statusline package beside this file. With a
payload on stdin it prints the bar; in a terminal it opens the configurator;
`statusline.py help` lists everything else.
"""
import sys

from claude_statusline.main import main

if __name__ == "__main__":
    sys.exit(main())
