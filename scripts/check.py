"""Run QA verification pipeline (Ruff and ty) across platforms."""

import subprocess
import sys


def run_step(title: str, cmd: list[str]) -> None:
    print(f"==> {title}...")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    run_step("Running Ruff linter & auto-fix", ["uv", "run", "ruff", "check", "--fix"])
    run_step("Running static type checking (ty)", ["uv", "run", "ty", "check"])


if __name__ == "__main__":
    main()
