"""Fixture repositories for graph tests.

Every helper that touches git state calls `require_fixture` first, so a test
pointed at a real checkout (this repository included) is refused before any
worktree, branch, commit, or run directory exists.
"""
import os
import tempfile
from pathlib import Path

from graph.fence import MARKER, require_fixture
from graph.gitcmd import git

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = ("-c", "user.name=graph-fixture", "-c", "user.email=fixture@invalid",
            "-c", "commit.gpgsign=false")

FILES = {
    MARKER: "graph test fixture; never present in a real checkout\n",
    ".gitignore": ".agent/\n*.log\n",
    "docs/a.md": "a\n",
    "docs/b.md": "b\n",
    "src/x.txt": "x\n",
    "src/y.txt": "y\n",
}


def make_fixture_repo(parent):
    """Create a fresh git repo under `parent` (which must be outside ROOT)."""
    parent = Path(parent).resolve()
    if parent == ROOT or ROOT in parent.parents:
        raise RuntimeError(f"refusing to create a fixture inside the real checkout: {parent}")
    repo = Path(tempfile.mkdtemp(prefix="fixture-", dir=parent))
    for rel, text in FILES.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    git(repo, "init", "-q", "-b", "main")
    require_fixture(repo)
    fixture_git(repo, "add", "-A")
    fixture_git(repo, *IDENTITY, "commit", "-q", "-m", "fixture base")
    return repo


def fixture_git(repo, *args, check=True):
    require_fixture(repo)
    return git(repo, *args, check=check)


def fixture_commit(repo, rel, text):
    """Add a commit to the fixture, so HEAD moves away from an earlier SHA."""
    require_fixture(repo)
    (Path(repo) / rel).write_text(text, encoding="utf-8")
    fixture_git(repo, "add", rel)
    fixture_git(repo, *IDENTITY, "commit", "-q", "-m", f"touch {rel}")
    return fixture_git(repo, "rev-parse", "HEAD").stdout.strip()


def git_state(repo):
    """Read-only snapshot of worktrees and branches (safe on any repository)."""
    worktrees = git(repo, "worktree", "list", "--porcelain").stdout
    branches = git(repo, "branch", "--list").stdout
    return worktrees, branches


def listing(path):
    path = Path(path)
    return sorted(os.listdir(path)) if path.is_dir() else None
