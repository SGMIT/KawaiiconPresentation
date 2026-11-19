"""Detached git worktrees created only from resolved SHAs, and the change set
a worktree carries against its base."""
import re
from pathlib import Path

from graph.gitcmd import GitError, git

SHA40 = re.compile(r"^[0-9a-f]{40}$")


class WorktreeError(RuntimeError):
    pass


def resolve_sha(repo, rev):
    proc = git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", check=False)
    sha = proc.stdout.strip()
    if proc.returncode != 0 or not SHA40.match(sha):
        raise WorktreeError(f"cannot resolve {rev!r} to a commit in {repo}")
    return sha


def add_worktree(repo, path, sha):
    """Refuses anything but a full 40-hex SHA: HEAD, branch names and short SHAs are moving or ambiguous."""
    if not isinstance(sha, str) or not SHA40.match(sha):
        raise WorktreeError(f"worktrees are created from a resolved 40-hex SHA, not {sha!r}")
    path = Path(path)
    try:
        git(repo, "worktree", "add", "--detach", "--quiet", str(path), sha)
    except GitError as e:
        raise WorktreeError(str(e)) from None
    return path


def changed_paths(worktree, base_sha):
    """Every path the worktree changed against base_sha: committed, staged,
    unstaged, deleted, and untracked - ignored files included."""
    tracked = git(worktree, "diff", "--name-only", "--no-renames", "-z", base_sha).stdout
    untracked = git(worktree, "ls-files", "--others", "-z").stdout
    return sorted({p for p in (tracked + untracked).split("\0") if p})
