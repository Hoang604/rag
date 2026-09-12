"""Guards the encoding fix, at both levels it can fail at.

The bug it exists for was silent and expensive: every eval script ran fine in
a terminal and raised UnicodeEncodeError the moment its output was redirected
to a file, which is how every file under `evidence/` is produced. Two of them
had already been lost to it, and the commands `evidence/README.md` gives the
next person were the exact commands that failed.

One test checks the helper does what it claims. The other checks it is
actually wired into every program that prints Vietnamese -- because the helper
being correct and unused is the state the repository was already in.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest

from rag_eval.legal.console import use_utf8_stdout

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
ENTRY_POINTS = sorted(SCRIPTS.glob("*.py")) + [
    REPO / "src" / "rag_eval" / "legal" / "eval" / "smoke_runner.py"
]


def _cp1252_stream() -> io.TextIOWrapper:
    """What a redirect hands a process on Windows."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")


def test_a_cp1252_stream_really_cannot_hold_vietnamese() -> None:
    """Establishes the premise, so the next test is not testing a tautology."""
    with pytest.raises(UnicodeEncodeError):
        _cp1252_stream().write("mức phạt")


def test_the_helper_switches_the_stream_to_utf8(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = _cp1252_stream()
    monkeypatch.setattr("sys.stdout", stream)
    use_utf8_stdout()
    assert stream.encoding.lower().replace("-", "") == "utf8"
    stream.write("mức phạt")  # would raise before the call


def test_the_helper_survives_a_stream_it_cannot_reconfigure() -> None:
    """pytest and other harnesses replace stdout with objects lacking it."""

    class Bare:
        def write(self, text: str) -> int:
            return len(text)

    import sys

    original = sys.stdout
    sys.stdout = Bare()  # type: ignore[assignment]
    try:
        use_utf8_stdout()  # must not raise
    finally:
        sys.stdout = original


def _calls_in_main_guard(source: str) -> set[str]:
    """Names called inside `if __name__ == "__main__":`, at any depth."""
    tree = ast.parse(source)
    called: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = ast.unparse(node.test)
        if "__name__" not in test:
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
                called.add(inner.func.id)
    return called


def _prints_non_ascii(source: str) -> bool:
    tree = ast.parse(source)
    return any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and not node.value.isascii()
        for node in ast.walk(tree)
    )


@pytest.mark.parametrize("path", ENTRY_POINTS, ids=lambda p: p.name)
def test_every_program_printing_vietnamese_fixes_its_stdout(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    if not _prints_non_ascii(source):
        pytest.skip("ASCII only, cannot hit the bug")
    assert "use_utf8_stdout" in _calls_in_main_guard(source), (
        f"{path.name} prints non-ASCII but never calls use_utf8_stdout(), so "
        "its output cannot be redirected to a file on Windows"
    )
