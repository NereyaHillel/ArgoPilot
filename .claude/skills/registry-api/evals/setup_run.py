#!/usr/bin/env python3
"""Make a scratch copy of the repo (from git HEAD) for one eval run.

    setup_run.py <dest> with_skill|without_skill

The copy is a fresh git repo, so checks.py can diff what the agent changed. The
skill's own evals/ folder is removed from the copy, because it holds the expected
answers. without_skill also drops .claude/, so the agent cannot find the skill.
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def main(dest: Path, config: str) -> None:
    dest.mkdir(parents=True)
    archive = subprocess.run(
        ["git", "-C", str(REPO), "archive", "HEAD"], check=True, capture_output=True
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive, check=True)
    shutil.rmtree(dest / ".claude/skills/registry-api/evals")
    if config == "without_skill":
        shutil.rmtree(dest / ".claude")
    git = ["git", "-C", str(dest), "-c", "user.name=eval", "-c", "user.email=eval@example.com"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "baseline"], check=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
