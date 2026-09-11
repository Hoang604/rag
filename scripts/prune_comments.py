"""Trims over-long comment blocks, without touching the ones that carry weight.

This repository comments heavily, and much of it earns its place: a threshold
of 0.86 means nothing without the sentence saying it is the highest cut that
still warns on no real question. But explanation has a length past which it
stops being a note and becomes an essay sitting in the middle of a function,
and that is what this removes.

Three things it will not touch, because removing them breaks the build rather
than the prose:

  * Tool pragmas -- `# type:`, `# noqa`, `# ruff:`, `# fmt:`, `# pragma`,
    `# pylint:`. `ty` and `ruff` read these, and a stripped `# type: ignore`
    turns a passing check into a failing one.
  * The shebang and any encoding declaration on the first two lines.
  * Anything inside a string. Comments are found with `tokenize`, not with a
    regex over `#`, because `"# not a comment"` appears in this codebase and a
    regex would happily delete half of it.

By default it also **keeps any block containing a digit**, on the assumption
that a number in a comment is a measurement and the sentence around it is the
evidence for it. `--no-spare-numbers` turns that off.

Writes nothing without `--apply`.
"""

from __future__ import annotations

import argparse
import io
import pathlib
import re
import tokenize
from dataclasses import dataclass

_PRAGMA = re.compile(
    r"#\s*(type:|noqa|ruff:|fmt:|pragma|pylint:|mypy:|isort:|nosec|coding[:=])",
    re.IGNORECASE,
)
_DIGIT = re.compile(r"\d")


@dataclass(frozen=True)
class Block:
    """A run of consecutive whole-line comments at one indentation."""

    start: int  # 1-based, inclusive
    end: int  # 1-based, inclusive
    lines: tuple[str, ...]

    @property
    def size(self) -> int:
        return self.end - self.start + 1

    @property
    def has_pragma(self) -> bool:
        return any(_PRAGMA.search(line) for line in self.lines)

    @property
    def has_number(self) -> bool:
        return any(_DIGIT.search(line) for line in self.lines)


def find_blocks(source: str) -> list[Block]:
    """Returns the standalone comment blocks, in line order.

    Trailing comments (`x = 1  # why`) are excluded: they are one line by
    construction and never the thing being complained about.
    """
    lines = source.splitlines()
    comment_lines: set[int] = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type != tokenize.COMMENT:
                continue
            row = token.start[0]
            # Standalone only: nothing but whitespace before the `#`.
            if lines[row - 1][: token.start[1]].strip():
                continue
            comment_lines.add(row)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []

    blocks: list[Block] = []
    run: list[int] = []
    for row in sorted(comment_lines):
        if run and row == run[-1] + 1:
            run.append(row)
            continue
        if run:
            blocks.append(Block(run[0], run[-1], tuple(lines[r - 1] for r in run)))
        run = [row]
    if run:
        blocks.append(Block(run[0], run[-1], tuple(lines[r - 1] for r in run)))
    return blocks


def plan(source: str, max_block: int, spare_numbers: bool) -> list[Block]:
    """Returns the blocks that would be trimmed, longest first."""
    chosen = [
        block
        for block in find_blocks(source)
        if block.size > max_block
        and not block.has_pragma
        and block.start > 2
        and not (spare_numbers and block.has_number)
    ]
    return sorted(chosen, key=lambda b: -b.size)


def rewrite(source: str, blocks: list[Block], max_block: int) -> str:
    """Keeps the first `max_block` lines of each chosen block, drops the rest.

    Truncating rather than deleting: the first sentence of these blocks is
    almost always the claim, and the remainder the argument for it. Removing
    the whole thing loses the claim too.
    """
    lines = source.splitlines(keepends=True)
    drop: set[int] = set()
    for block in blocks:
        drop.update(range(block.start + max_block, block.end + 1))
    return "".join(line for index, line in enumerate(lines, 1) if index not in drop)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths", nargs="*", default=["src", "scripts", "tests"], help="thư mục cần dọn"
    )
    parser.add_argument(
        "--max-block",
        type=int,
        default=4,
        help="giữ lại mấy dòng đầu của mỗi khối; phần dài hơn bị cắt (mặc định 4)",
    )
    parser.add_argument(
        "--no-spare-numbers",
        action="store_true",
        help="cắt cả những khối có chứa con số (mặc định giữ, vì thường là số đo)",
    )
    parser.add_argument("--show", type=int, default=15, help="in thử mấy khối")
    parser.add_argument("--apply", action="store_true", help="ghi thật")
    args = parser.parse_args()

    files: list[pathlib.Path] = []
    for raw in args.paths:
        path = pathlib.Path(raw)
        files.extend(sorted(path.rglob("*.py")) if path.is_dir() else [path])

    spare = not args.no_spare_numbers
    total_files = total_lines = 0
    preview: list[tuple[int, str, Block]] = []

    for file in files:
        source = file.read_text(encoding="utf-8")
        blocks = plan(source, args.max_block, spare)
        if not blocks:
            continue
        total_files += 1
        total_lines += sum(block.size - args.max_block for block in blocks)
        preview.extend((block.size, str(file), block) for block in blocks)

        if args.apply:
            file.write_text(rewrite(source, blocks, args.max_block), encoding="utf-8")

    preview.sort(reverse=True, key=lambda item: item[0])
    print(f"{'dòng':>6}  {'vị trí':<52}  dòng đầu của khối")
    print("-" * 110)
    for size, name, block in preview[: args.show]:
        head = block.lines[0].strip()[:40]
        print(f"{size:>6}  {name + ':' + str(block.start):<52}  {head}")

    print(
        f"\n{total_files} file · cắt {total_lines} dòng "
        f"(giữ {args.max_block} dòng đầu mỗi khối)"
    )
    if spare:
        print("Khối có chứa số được GIỮ NGUYÊN — dùng --no-spare-numbers để cắt cả.")
    if not args.apply:
        print("\nCHẠY KHÔ — chưa sửa file nào. Thêm --apply để ghi thật.")
        print(
            "Sau khi --apply, chạy: uv run ruff check . && uv run ty check && uv run pytest -q"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
