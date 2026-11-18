#!/usr/bin/env python3
"""Tool-agnostic tamper guard for Taniko sandbox boundaries.

Single source of truth: .claude/harness.json sandbox.protected and
sandbox.read_only (plus .cursor/** so IDE adapter configs cannot rewrite
themselves). Invoked by thin per-CLI adapters (Claude Code PreToolUse,
Cursor preToolUse / beforeShellExecution). Stdlib only, deterministic,
fail-closed on parse or declaration errors. No model judgment.

What it matches:
  - file paths from tool payloads (path / file_path / target_file / ...)
  - path literals embedded in shell command strings
  - normalisation: NFC, backslash->slash, strip ./, reject .. escape,
    absolute paths only if under the repo root, os.path.normcase on Windows,
    Path.resolve() once (best-effort; no TOCTOU without an OS sandbox)

What it deliberately does not attempt:
  - full PowerShell / cmd / bash AST parsing
  - blocking out-of-band writers that never name a path in the tool call
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DECL_REL = ".claude/harness.json"
# Always guarded even if a declaration omits it: adapter configs must not
# rewrite the boundary that loads them.
ALWAYS_DENY = (".cursor/**",)

WRITE_TOOLS = {
    "write", "edit", "delete", "editnotebook", "notebookedit",
    "strreplace", "search_replace", "create", "writetofile",
}
SHELL_TOOLS = {"shell", "bash", "powershell", "cmd", "terminal"}

# Substrings that suggest a shell command will mutate the tree.
WRITE_SHELL_HINTS = (
    ">", ">>", "out-file", "set-content", "add-content", "clear-content",
    "copy-item", "move-item", "remove-item", "ren ", "rename-item",
    "new-item", "ni ", "mi ", "ri ", "cpi ", "echo ", "printf ",
    "tee ", "sed -i", "perl -i", "git checkout", "git restore",
    "git apply", "git reset", "git clean", "git commit", "git add ",
)


def deny(reason: str, event: str) -> int:
    msg = f"tamper_guard: {reason}"
    flat = {
        "permission": "deny",
        "user_message": msg,
        "agent_message": msg,
    }
    # Claude Code nested shape (also accepted by Cursor third-party import).
    if event.lower() in ("pretooluse", "permissionrequest"):
        flat["hookSpecificOutput"] = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": msg,
        }
    print(json.dumps(flat))
    return 2


def allow() -> int:
    print(json.dumps({"permission": "allow"}))
    return 0


def load_globs() -> tuple[list[str], str]:
    path = REPO / DECL_REL
    try:
        decl = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise RuntimeError(f"cannot read {DECL_REL}: {e}") from e
    sandbox = decl.get("sandbox")
    if not isinstance(sandbox, dict):
        raise RuntimeError(f"{DECL_REL} sandbox missing")
    globs: list[str] = []
    for key in ("protected", "read_only"):
        vals = sandbox.get(key) or []
        if not isinstance(vals, list) or not all(isinstance(g, str) for g in vals):
            raise RuntimeError(f"{DECL_REL} sandbox.{key} malformed")
        globs.extend(vals)
    for g in ALWAYS_DENY:
        if g not in globs:
            globs.append(g)
    state = decl.get("state", {})
    state_dir = state.get("dir", ".agent") if isinstance(state, dict) else ".agent"
    if not isinstance(state_dir, str) or not state_dir.strip():
        state_dir = ".agent"
    return globs, state_dir


def match_glob(rel: str, glob: str) -> bool:
    rel_posix = rel.replace("\\", "/")
    g = glob.replace("\\", "/")
    if g.endswith("/**"):
        prefix = g[:-3]
        if rel_posix == prefix or rel_posix.startswith(prefix + "/"):
            return True
    # fnmatch is case-insensitive on Windows via normcase.
    return fnmatch.fnmatch(os.path.normcase(rel_posix), os.path.normcase(g))


def blocked_by(rel: str, globs: list[str]) -> str | None:
    for g in globs:
        if match_glob(rel, g):
            return g
    return None


def to_repo_relative(raw: str) -> str | None:
    """Return a repo-relative posix path, or None if outside / unusable."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().strip('"').strip("'")
    text = text.replace("\\", "/")
    # file:// URLs
    if text.startswith("file:"):
        text = text[5:]
        if text.startswith("///"):
            text = text[3:]
        elif text.startswith("//"):
            text = text[1:]
    text = re.sub(r"^\./", "", text)
    p = Path(text)
    try:
        if p.is_absolute():
            resolved = p.resolve()
        else:
            resolved = (REPO / p).resolve()
        rel = resolved.relative_to(REPO.resolve())
    except (ValueError, OSError):
        return None
    parts = rel.parts
    if ".." in parts:
        return None
    return rel.as_posix()


def walk_strings(obj, out: list[str]) -> None:
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in {
                "path", "file_path", "filepath", "target_file", "target",
                "file", "filename", "notebook_path", "uri",
            }:
                if isinstance(v, str):
                    out.append(v)
            walk_strings(v, out)
    elif isinstance(obj, list):
        for item in obj:
            walk_strings(item, out)


PATH_IN_CMD = re.compile(
    r"(?:^|[\s\"'`=(])("
    r"(?:\./)?(?:\.claude|\.cursor|\.github|bin|docs)/[^\s\"'`]*|"
    r"(?:\./)?(?:AGENTS\.md|CLAUDE\.md|TANIKO_VERSION|\.gitignore|README\.md)"
    r")"
)


def paths_from_command(command: str) -> list[str]:
    found: list[str] = []
    for m in PATH_IN_CMD.finditer(command.replace("\\", "/")):
        found.append(m.group(1))
    # Also catch absolute paths that resolve into the repo.
    for token in re.findall(r"[^\s\"'`]+", command):
        if "/" in token or "\\" in token or token.endswith((".md", ".json", ".py", ".yml")):
            found.append(token)
    return found


def command_looks_writey(command: str) -> bool:
    low = command.lower()
    return any(h in low for h in WRITE_SHELL_HINTS)


def git_head() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True, stdin=subprocess.DEVNULL, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace").strip() or None


def budget_exhausted(state_dir: str) -> tuple[bool, str]:
    """Recompute exhaustion from the attempt ledger + declaration budgets."""
    try:
        decl = json.loads((REPO / DECL_REL).read_text(encoding="utf-8"))
        budgets = decl.get("verify", {}).get("budgets", {})
        max_total = int(budgets.get("max_attempts_total", 0) or 0)
        per_tier = int(budgets.get("max_attempts_per_tier", 0) or 0)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False, ""
    if max_total <= 0 and per_tier <= 0:
        return False, ""
    head = git_head()
    if not head:
        return False, ""
    ledger_path = REPO / state_dir / "verify" / "attempts" / f"{head}.json"
    if not ledger_path.is_file():
        return False, ""
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        attempts = ledger.get("attempts")
        if not isinstance(attempts, list):
            return False, ""
    except (OSError, ValueError, json.JSONDecodeError):
        return False, ""
    used = len(attempts)
    # Same rule as bin/harness account_attempt: per tree, each failed_stage once.
    tier_fails: Counter[str] = Counter()
    for a in attempts:
        if not isinstance(a, dict):
            continue
        stages = {
            r.get("failed_stage")
            for r in (a.get("runs") or {}).values()
            if isinstance(r, dict) and r.get("verdict") == "fail" and r.get("failed_stage")
        }
        for stage in stages:
            tier_fails[str(stage)] += 1
    reasons = []
    if max_total and used >= max_total:
        reasons.append(f"{used} of {max_total} attempts used")
    if per_tier:
        for stage, n in tier_fails.items():
            if n >= per_tier:
                reasons.append(f"tier {stage} failed on {n} of {per_tier} allowed tree states")
    if not reasons:
        return False, ""
    return True, "; ".join(reasons)


def tool_name_of(payload: dict) -> str:
    for key in ("tool_name", "toolName", "tool"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def event_of(payload: dict) -> str:
    for key in ("hook_event_name", "hookEventName"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def extract_tool_input(payload: dict) -> dict:
    for key in ("tool_input", "toolInput", "input"):
        v = payload.get(key)
        if isinstance(v, dict):
            return v
    return {}


def read_stdin_json() -> dict:
    """Parse hook stdin. Cursor-on-Windows may deliver UTF-16; Unix is UTF-8."""
    data = sys.stdin.buffer.read()
    if not data or not data.strip():
        raise ValueError("empty hook stdin (fail closed)")
    texts: list[str] = []
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        texts.append(data.decode("utf-16"))
    elif data.startswith(b"\xef\xbb\xbf"):
        texts.append(data.decode("utf-8-sig"))
    else:
        for enc in ("utf-8", "utf-16-le", "utf-16"):
            try:
                texts.append(data.decode(enc))
            except UnicodeDecodeError:
                continue
    last_err: Exception | None = None
    for text in texts:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            last_err = e
            continue
        if isinstance(payload, dict):
            return payload
        last_err = ValueError("hook payload is not an object (fail closed)")
    if last_err is not None:
        raise ValueError(f"invalid JSON on hook stdin (fail closed): {last_err}") from last_err
    raise ValueError("invalid JSON on hook stdin (fail closed)")


def main() -> int:
    try:
        payload = read_stdin_json()
    except ValueError as e:
        return deny(str(e), "PreToolUse")

    try:
        globs, state_dir = load_globs()
    except RuntimeError as e:
        return deny(f"{e} (fail closed)", "PreToolUse")

    event = event_of(payload)
    tool = tool_name_of(payload)
    tool_l = tool.lower().split(":")[-1].strip()
    tool_input = extract_tool_input(payload)
    command = ""
    if isinstance(payload.get("command"), str):
        command = payload["command"]
    elif isinstance(tool_input.get("command"), str):
        command = tool_input["command"]

    # Collect candidate paths from structured fields and the command string.
    candidates: list[str] = []
    walk_strings(tool_input, candidates)
    walk_strings({k: payload.get(k) for k in ("file_path", "path", "target_file")}, candidates)
    if command:
        candidates.extend(paths_from_command(command))

    hit_rel = None
    hit_glob = None
    for raw_path in candidates:
        rel = to_repo_relative(raw_path)
        if rel is None:
            continue
        g = blocked_by(rel, globs)
        if g:
            hit_rel, hit_glob = rel, g
            break

    is_write_tool = tool_l in WRITE_TOOLS or tool_l.endswith("write") or tool_l.endswith("edit")
    is_shell = (
        event.lower() in ("beforeshellexecution", "before_shell_execution")
        or tool_l in SHELL_TOOLS
    )

    read_like = tool_l in {"read", "grep", "glob", "semanticsearch", "readbytestream", "readfile"}
    harness_run = bool(is_shell and re.search(
        r"(?i)\bpython3?\s+(\.?[/\\])?bin[/\\]harness\b", command,
    ))
    git_meta = bool(is_shell and re.search(
        r"(?i)\bgit\s+(status|diff|log|show|rev-parse|add|commit|update-index|ls-files)\b",
        command,
    ))
    read_shell = bool(is_shell and re.search(
        r"(?i)\b(type|cat|Get-Content|gc|head|tail|less|more|git\s+show|git\s+diff|git\s+log)\b",
        command,
    ))
    if hit_rel and not read_like:
        # Structured write tools always deny. Shell: allow harness runs and
        # git meta even when the argv names a guarded path; deny other writey
        # or ambiguous shells that mention a guarded path.
        if is_write_tool or (not tool and not is_shell):
            return deny(
                f"refusing mutation of {hit_rel} (matches sandbox glob {hit_glob!r}); "
                "protected/read_only paths change only via a reviewed human-approved path",
                event or "PreToolUse",
            )
        if is_shell and not (harness_run or git_meta or read_shell):
            if command_looks_writey(command) or True:
                return deny(
                    f"refusing shell that targets {hit_rel} (matches sandbox glob {hit_glob!r}); "
                    "protected/read_only paths change only via a reviewed human-approved path",
                    event or "PreToolUse",
                )

    # Soft budget halt: mutating tools only. Ledger wipe remains possible
    # because state.dir must stay writable for doctor.
    exhausted, why = budget_exhausted(state_dir)
    if exhausted and (is_write_tool or (is_shell and command_looks_writey(command))):
        return deny(
            f"BUDGET EXHAUSTED ({why}): stop and escalate. "
            f"Human reset: delete {state_dir}/verify/attempts/<HEAD>.json",
            event or "PreToolUse",
        )

    return allow()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:  # noqa: BLE001 — fail closed
        raise SystemExit(deny(f"internal error (fail closed): {e}", "PreToolUse"))
