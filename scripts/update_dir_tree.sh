#!/usr/bin/env python3
"""Synchronize codebase structure directory tree in GEMINI.md."""

from pathlib import Path
import re

ROOT_DIR = Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {".venv", "__pycache__", ".git", ".pytest_cache", ".mypy_cache", "data", "rag.egg-info"}


def generate_tree(dir_path: Path, prefix: str = "") -> list[str]:
    lines: list[str] = []
    entries = sorted(
        [p for p in dir_path.iterdir() if p.name not in EXCLUDE_DIRS],
        key=lambda p: (not p.is_dir(), p.name),
    )
    for idx, entry in enumerate(entries):
        is_last = idx == len(entries) - 1
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{entry.name}")
        if entry.is_dir():
            sub_prefix = f"{prefix}    " if is_last else f"{prefix}│   "
            lines.extend(generate_tree(entry, sub_prefix))
    return lines


def main() -> None:
    tree_lines = [f"{ROOT_DIR.name}/"] + generate_tree(ROOT_DIR)
    tree_str = "\n".join(tree_lines)

    gemini_file = ROOT_DIR / "GEMINI.md"
    if not gemini_file.is_file():
        return
    content = gemini_file.read_text(encoding="utf-8")
    pattern = r"<!-- DIR_TREE_START -->.*?<!-- DIR_TREE_END -->"
    replacement = f"<!-- DIR_TREE_START -->\n```text\n{tree_str}\n```\n<!-- DIR_TREE_END -->"
    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    gemini_file.write_text(new_content, encoding="utf-8")


if __name__ == "__main__":
    main()
