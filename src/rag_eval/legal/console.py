"""Makes Vietnamese output survive being redirected to a file.

Python takes its stdout encoding from the console when there is one and from
the locale when there is not. On Windows that second case is cp1252, which
cannot encode "tập" -- so a program here runs fine in a terminal and dies with
UnicodeEncodeError the moment its output is sent to a file. That is exactly how
the files under `evidence/` are produced, and exactly the commands
`evidence/README.md` tells the next person to run. `rich` does not save us:
measured, it raises the same error and prints advice to set PYTHONIOENCODING.

Setting that variable in the shell does work, but invisibly: the same command
then succeeds or fails depending on state nobody can see in the repo. Doing it
in the process keeps the fix next to the code that needs it.

Call this from an entry point only, never at import time -- deciding how the
host process talks to its terminal is not a library's business.
"""

from __future__ import annotations

import sys


def use_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        # Absent once the stream has been replaced, as test harnesses do.
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
