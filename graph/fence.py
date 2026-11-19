"""Test fence: git-mutating test helpers and the stub runner operate only on
repositories that carry the fixture marker at their main worktree root.

The marker is created only by graph/tests/fixture.py inside temp directories.
A real checkout never carries it; creating one there shows up in `git status`.
"""
from pathlib import Path

from graph.gitcmd import git

MARKER = ".taniko-graph-fixture"


class FenceError(RuntimeError):
    pass


def main_worktree_root(path):
    """Root of the main worktree for `path`, even when `path` is a linked worktree."""
    proc = git(path, "rev-parse", "--path-format=absolute", "--git-common-dir", check=False)
    if proc.returncode != 0:
        return None
    return Path(proc.stdout.strip()).resolve().parent


def is_fixture(path):
    root = main_worktree_root(path)
    return root is not None and (root / MARKER).is_file()


def require_fixture(path):
    if not Path(path).is_dir() or not is_fixture(path):
        raise FenceError(f"{path} is not a graph test fixture (no {MARKER} at its main worktree root); refusing")
    return main_worktree_root(path)
