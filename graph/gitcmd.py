"""Run git against an explicit directory, never an inherited one.

Repository-locating GIT_* variables are dropped so a caller's environment
(a hook, a harness, a parent git process) can't redirect a command at a
different repository than the one named.
"""
import os
import subprocess
from pathlib import Path

_LOCATORS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
             "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE",
             "GIT_PREFIX")


class GitError(RuntimeError):
    def __init__(self, args, proc):
        super().__init__(f"git {' '.join(args)} exited {proc.returncode}: {proc.stderr.strip()[:500]}")
        self.returncode = proc.returncode


def git(cwd, *args, check=True):
    env = {k: v for k, v in os.environ.items() if k not in _LOCATORS}
    proc = subprocess.run(["git", "-C", str(Path(cwd)), *args], capture_output=True, text=True,
                          env=env, timeout=60)
    if check and proc.returncode != 0:
        raise GitError(args, proc)
    return proc
