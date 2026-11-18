#!/usr/bin/env python3
"""Decision tests for tamper_guard.py: feed PreToolUse payloads, assert the verdict.

Stdlib unittest; each case runs the guard as a subprocess exactly as an agent
CLI hook would. Run from the repo root:

    python3 -m unittest discover -s .claude/hooks -p 'test_*.py' -v
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().with_name("tamper_guard.py")


def run_guard(stdin: bytes) -> tuple[str, int, str]:
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=stdin, capture_output=True, timeout=30, check=False,
    )
    out = proc.stdout.decode("utf-8", "replace").strip()
    try:
        decision = json.loads(out.splitlines()[-1]).get("permission", "")
    except (IndexError, ValueError, AttributeError):
        decision = f"<unparseable: {out!r}>"
    return decision, proc.returncode, out


def claude(tool: str, tool_input: dict) -> bytes:
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": tool_input,
    }).encode("utf-8")


def bash(command: str) -> bytes:
    return claude("Bash", {"command": command})


def patch(*headers: str, body: str = "@@\n-a\n+b\n") -> bytes:
    text = "*** Begin Patch\n" + "".join(f"{h}\n{body}" for h in headers) + "*** End Patch\n"
    return claude("apply_patch", {"input": text})


def budget_exhausted() -> bool:
    spec = importlib.util.spec_from_file_location("tamper_guard", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _, state_dir = mod.load_globs()
    return mod.budget_exhausted(state_dir)[0]


DENY = {
    # Defect 1: a benign shortcut token whitelisted the whole compound command.
    "shell_cat_redirect_into_bin_harness": bash("cat notes.md > bin/harness"),
    "shell_git_status_then_echo_into_claude_md": bash("git status && echo x > CLAUDE.md"),
    "shell_harness_verify_then_sed_declaration": bash(
        "python3 bin/harness verify; sed -i s/3/99/ .claude/harness.json"),
    "shell_cd_guarded_dir_then_rm": bash("cd .claude && rm harness.json"),
    # Same class: redirection and segment variants.
    "shell_redirect_without_space": bash("cat notes.md >bin/harness"),
    "shell_append_redirect": bash("git log >> AGENTS.md"),
    "shell_pipe_into_tee": bash("cat notes.md | tee AGENTS.md"),
    "shell_or_chain": bash("git diff || cp notes.md .github/workflows/taniko.yml"),
    "shell_newline_segment": bash("git status\nrm bin/harness"),
    "shell_subshell": bash("echo ok $(rm .claude/harness.json)"),
    "shell_cd_guarded_dir_then_redirect": bash("cd .github && echo x > workflows/taniko.yml"),
    # Defect 2: patch-format write tools.
    "apply_patch_update_bin_harness": patch("*** Update File: bin/harness"),
    "apply_patch_add_under_claude": patch("*** Add File: .claude/hooks/evil.py", body="+x\n"),
    "apply_patch_delete_agents_md": patch("*** Delete File: AGENTS.md", body=""),
    "apply_patch_second_file_guarded": patch(
        "*** Update File: index.html", "*** Update File: bin/harness"),
    "apply_patch_unified_diff": claude("apply_patch", {
        "input": "--- a/bin/harness\n+++ b/bin/harness\n@@ -1 +1 @@\n-a\n+b\n"}),
    "shell_apply_patch_heredoc": bash(
        "apply_patch <<'EOF'\n*** Begin Patch\n*** Update File: bin/harness\n@@\n-a\n+b\n*** End Patch\nEOF"),
    # Structured writes stay denied.
    "write_declaration": claude("Write", {"file_path": ".claude/harness.json", "content": "{}"}),
    "edit_read_only_docs": claude("Edit", {
        "file_path": "docs/taniko/STRAIN.md", "old_string": "a", "new_string": "b"}),
    # Fail closed on bad input.
    "empty_stdin": b"",
    "whitespace_stdin": b"  \n",
    "malformed_stdin": b"{not json",
    "non_object_stdin": b"[]",
}

ALLOW = {
    "write_index_html": claude("Write", {"file_path": "index.html", "content": "<html></html>"}),
    "shell_harness_verify": bash("python3 bin/harness verify"),
    "shell_harness_doctor_json": bash("python3 bin/harness doctor --json"),
    "shell_read_guarded_then_status": bash("cat bin/harness && git status"),
    "shell_redirect_into_writable": bash("echo hi > notes.md"),
    "shell_cd_guarded_dir_read_only": bash("cd .claude && cat harness.json"),
    "apply_patch_writable_only": patch("*** Update File: index.html"),
    "read_guarded": claude("Read", {"file_path": ".claude/harness.json"}),
}

# Allow cases that mutate are subject to the soft budget halt.
MUTATING_ALLOWS = {"write_index_html", "shell_redirect_into_writable", "apply_patch_writable_only"}


class GuardDecisions(unittest.TestCase):
    pass


def _deny_case(payload: bytes):
    def test(self):
        decision, code, out = run_guard(payload)
        self.assertEqual(decision, "deny", out)
        self.assertNotEqual(code, 0, out)
    return test


def _allow_case(name: str, payload: bytes):
    def test(self):
        if name in MUTATING_ALLOWS and budget_exhausted():
            self.skipTest("verify budget exhausted at HEAD; guard correctly halts writes")
        decision, code, out = run_guard(payload)
        self.assertEqual(decision, "allow", out)
        self.assertEqual(code, 0, out)
    return test


for _name, _payload in DENY.items():
    setattr(GuardDecisions, f"test_deny_{_name}", _deny_case(_payload))
for _name, _payload in ALLOW.items():
    setattr(GuardDecisions, f"test_allow_{_name}", _allow_case(_name, _payload))


if __name__ == "__main__":
    unittest.main()
