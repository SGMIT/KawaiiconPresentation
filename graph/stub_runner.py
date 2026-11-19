"""Deterministic stand-in for an agent runner. No agent session runs.

Self-identifies via `identity` (logged on every node enter) and refuses any
repository that is not a graph test fixture, so it cannot produce evidence
about a real checkout.
"""
from pathlib import Path

from graph.fence import require_fixture


class StubRunner:
    identity = "stub-runner (deterministic test stand-in; no agent session)"

    def __init__(self, writes, exit_codes=None):
        """writes: {node_id: {relpath: text | None}}; None deletes the file."""
        self.writes = writes
        self.exit_codes = exit_codes or {}
        self.calls = []

    def check(self, repo):
        require_fixture(repo)

    def run(self, node, worktree):
        require_fixture(worktree)
        self.calls.append(node.id)
        plan = self.writes.get(node.id, {})
        for rel, text in plan.items():
            path = Path(worktree) / rel
            if text is None:
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
        return self.exit_codes.get(node.id, 0), f"stub wrote/deleted {len(plan)} path(s)"
