#!/usr/bin/env python3
"""Decision tests for tamper_guard.py: feed PreToolUse payloads, assert the verdict.

Stdlib unittest; each case runs the guard as a subprocess exactly as an agent
CLI hook would. Run from the repo root:

    python3 -m unittest discover -s .claude/hooks -p 'test_*.py' -v
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().with_name("tamper_guard.py")
REPO = GUARD.parents[2]
COPILOT_ADAPTER = REPO / ".github" / "hooks" / "tamper-guard.json"


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


def copilot(tool: str, tool_args) -> bytes:
    """Copilot camelCase preToolUse payload; toolArgs is typed `unknown`."""
    return json.dumps({
        "sessionId": "test",
        "timestamp": 0,
        "cwd": str(REPO),
        "toolName": tool,
        "toolArgs": tool_args,
    }).encode("utf-8")


def vscode(tool: str, tool_input) -> bytes:
    """Copilot PascalCase PreToolUse payload: Claude tool names, snake_case."""
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "session_id": "test",
        "timestamp": "1970-01-01T00:00:00Z",
        "cwd": str(REPO),
        "tool_name": tool,
        "tool_input": tool_input,
    }).encode("utf-8")


def abs_path(rel: str) -> str:
    return str(REPO / rel)


def patch_text(*headers: str, body: str = "@@\n-a\n+b\n") -> str:
    return "*** Begin Patch\n" + "".join(f"{h}\n{body}" for h in headers) + "*** End Patch\n"


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
    # Copilot camelCase: toolArgs as object, JSON string, or raw patch text.
    "copilot_create_declaration_abs": copilot("create", {
        "path": abs_path(".claude/harness.json"), "file_text": "{}"}),
    "copilot_edit_args_json_string": copilot("edit", json.dumps({
        "path": abs_path("bin/harness"), "old_str": "a", "new_str": "b"})),
    "copilot_str_replace_editor_agents_md": copilot("str_replace_editor", {
        "command": "str_replace", "path": abs_path("AGENTS.md"),
        "old_str": "a", "new_str": "b"}),
    "copilot_apply_patch_raw_string": copilot(
        "apply_patch", patch_text("*** Update File: bin/harness")),
    "copilot_apply_patch_json_string": copilot(
        "apply_patch", json.dumps(patch_text("*** Update File: bin/harness"))),
    "copilot_bash_compound": copilot("bash", {
        "command": "git status && echo x > CLAUDE.md", "description": "status"}),
    "copilot_bash_args_json_string": copilot("bash", json.dumps({
        "command": "cat notes.md > bin/harness"})),
    "copilot_powershell_set_content": copilot("powershell", {
        "command": "git status; Set-Content -Path bin/harness -Value x"}),
    "copilot_create_adapter_config": copilot("create", {
        "path": abs_path(".github/hooks/other.json"), "file_text": "{}"}),
    # Copilot PascalCase: apply_patch arrives as Edit with a raw-string input.
    "vscode_edit_raw_patch": vscode("Edit", patch_text("*** Update File: bin/harness")),
    "vscode_bash_compound": vscode("Bash", {"command": "git status && echo x > CLAUDE.md"}),
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
    "copilot_create_index_html_abs": copilot("create", {
        "path": abs_path("index.html"), "file_text": "<html></html>"}),
    "copilot_apply_patch_writable": copilot(
        "apply_patch", patch_text("*** Update File: index.html")),
    "copilot_bash_harness_verify": copilot("bash", {"command": "python3 bin/harness verify"}),
    "copilot_view_guarded": copilot("view", {"path": abs_path(".claude/harness.json")}),
    "copilot_rg_guarded": copilot("rg", {"pattern": "deny", "path": abs_path("bin/harness")}),
}

# Allow cases that mutate are subject to the soft budget halt.
MUTATING_ALLOWS = {
    "write_index_html", "shell_redirect_into_writable", "apply_patch_writable_only",
    "copilot_create_index_html_abs", "copilot_apply_patch_writable",
}


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


class CopilotContract(unittest.TestCase):
    """Copilot reads top-level permissionDecision; see docs.github.com
    /en/copilot/reference/hooks-reference ("preToolUse decision control")."""

    def test_deny_carries_permission_decision_and_reason(self):
        _, code, out = run_guard(copilot("create", {
            "path": abs_path("bin/harness"), "file_text": "x"}))
        body = json.loads(out.splitlines()[-1])
        self.assertEqual(body.get("permissionDecision"), "deny", out)
        self.assertTrue(body.get("permissionDecisionReason"), out)
        self.assertNotEqual(code, 0, out)

    def test_allow_does_not_preapprove(self):
        # "allow" would skip Copilot's normal permission prompt for every call.
        _, code, out = run_guard(copilot("view", {"path": abs_path("index.html")}))
        body = json.loads(out.splitlines()[-1])
        self.assertNotIn("permissionDecision", body, out)
        self.assertEqual(code, 0, out)


@unittest.skipIf(shutil.which("bash") is None, "adapter command is bash-only")
class CopilotAdapter(unittest.TestCase):
    """Run the adapter's own configured command, as Copilot CLI would."""

    def entries(self) -> list[dict]:
        config = json.loads(COPILOT_ADAPTER.read_text(encoding="utf-8"))
        self.assertEqual(config.get("version"), 1)
        entries = config.get("hooks", {}).get("preToolUse", [])
        self.assertTrue(entries, "no preToolUse entries")
        return entries

    def run_entry(self, entry: dict, payload: bytes) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-c", entry["bash"]], cwd=REPO / entry.get("cwd", "."),
            input=payload, capture_output=True, timeout=30, check=False,
        )

    def test_adapter_denies_protected_write(self):
        for entry in self.entries():
            proc = self.run_entry(entry, copilot("apply_patch", patch_text(
                "*** Update File: .claude/harness.json")))
            out = proc.stdout.decode("utf-8", "replace")
            self.assertNotEqual(proc.returncode, 0, out)
            self.assertEqual(json.loads(out.splitlines()[-1]).get("permissionDecision"), "deny", out)

    def test_adapter_allows_writable(self):
        if budget_exhausted():
            self.skipTest("verify budget exhausted at HEAD; guard correctly halts writes")
        for entry in self.entries():
            proc = self.run_entry(entry, copilot("create", {
                "path": abs_path("index.html"), "file_text": "x"}))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
