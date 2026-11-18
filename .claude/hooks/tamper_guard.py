#!/usr/bin/env python3
"""Tool-agnostic tamper guard for Taniko sandbox boundaries.

Single source of truth: .claude/harness.json sandbox.protected and
sandbox.read_only (plus .cursor/** so IDE adapter configs cannot rewrite
themselves). Invoked by thin per-CLI adapters (Claude Code PreToolUse,
Cursor preToolUse / beforeShellExecution). Stdlib only, deterministic,
fail-closed on parse or declaration errors. No model judgment.

What it matches:
  - file paths from tool payloads (path / file_path / target_file / ...)
  - patch bodies: "*** Update|Add|Delete File: <path>" and unified diff
    "--- a/<path>" / "+++ b/<path>" headers in any tool payload string
  - shell commands, decided per segment (split on ; && || | & newlines,
    $( ) and backticks): a segment that names a guarded path denies unless
    its own leading command is a reader, git metadata, or bin/harness; any
    redirection (> >> &>) into a guarded path denies; after cd into a
    guarded directory every non-reader segment denies
  - unknown tools that name a guarded path deny (fail closed); only known
    read tools are exempt
  - normalisation: NFC, backslash->slash, strip ./, reject .. escape,
    absolute paths only if under the repo root, os.path.normcase on Windows,
    Path.resolve() once (best-effort; no TOCTOU without an OS sandbox)

What it deliberately does not attempt:
  - full PowerShell / cmd / bash AST parsing (quoting, variables, eval)
  - blocking out-of-band writers that never name a path in the tool call
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
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
    "apply_patch", "applypatch", "multiedit", "create_file", "edit_file",
    "str_replace", "str_replace_editor", "replace_string_in_file",
    "insert_edit_into_file",
}
SHELL_TOOLS = {"shell", "bash", "powershell", "cmd", "terminal", "run_in_terminal"}
READ_TOOLS = {
    "read", "grep", "glob", "ls", "view", "semanticsearch", "readbytestream",
    "readfile", "read_file", "readlints", "list_dir", "file_search",
    "grep_search", "codebase_search",
}

# Substrings that suggest a shell command will mutate the tree. Used only for
# the soft budget halt; guarded-path decisions do not depend on it.
WRITE_SHELL_HINTS = (
    ">", ">>", "out-file", "set-content", "add-content", "clear-content",
    "copy-item", "move-item", "remove-item", "ren ", "rename-item",
    "new-item", "ni ", "mi ", "ri ", "cpi ", "echo ", "printf ",
    "tee ", "sed -i", "perl -i", "git checkout", "git restore",
    "git apply", "git reset", "git clean", "git commit", "git add ",
    "rm ", "mv ", "cp ", "touch ", "chmod ", "ln ", "dd ", "truncate ",
    "install ", "unlink ", "mkdir ", "rmdir ", "apply_patch",
)

# Leading commands that only read. A segment led by one of these may name a
# guarded path; its redirections are still checked.
READ_COMMANDS = {
    "cat", "head", "tail", "less", "more", "type", "get-content", "gc",
    "wc", "grep", "egrep", "fgrep", "rg", "ls", "dir", "stat", "file",
    "diff", "cmp", "sha256sum", "shasum", "md5", "md5sum", "test", "[",
    "select-string", "sls", "get-childitem", "gci", "get-item", "gi",
    "cd", "pushd", "popd", "set-location", "sl", "pwd", "true", ":",
}
# git subcommands that do not touch the working tree. add/commit only stage
# and record what is already on disk. update-index is excluded: it can flip
# the exec bit or hide changes with skip-worktree.
GIT_READ_SUBCOMMANDS = {
    "status", "diff", "log", "show", "rev-parse", "ls-files", "blame",
    "describe", "branch", "add", "commit",
}
CD_COMMANDS = {"cd", "pushd", "set-location", "sl"}
PYTHONS = {"python", "python3", "py"}
SEGMENT_SPLIT = re.compile(r"\|\||&&|;|\n|(?<![>|])\|(?!\|)|(?<![<>&])&(?![>&])|\$\(|`|[()]")
REDIRECT = re.compile(r"(?:\d|&)?>>?\|?\s*(?!&)([^\s;&|<>()]+)")
PATCH_HEADER = re.compile(
    r"^(?:\*\*\* (?:Update|Add|Delete) File:|\*\*\* Move to:)\s*(.+?)\s*$"
    r"|^(?:\+\+\+|---) (?:[ab]/)?(\S+)",
    re.MULTILINE,
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


def patch_paths(text: str) -> list[str]:
    """Target paths named by apply_patch-style or unified-diff headers."""
    out: list[str] = []
    for m in PATCH_HEADER.finditer(text):
        path = (m.group(1) or m.group(2) or "").strip()
        if path and path != "/dev/null":
            out.append(path)
    return out


def rel_from(raw: str, cwd: Path) -> str | None:
    """Repo-relative path for raw, resolved from cwd (relative paths)."""
    text = raw.strip().strip('"').strip("'").replace("\\", "/")
    if not text or text.startswith("-"):
        return None
    if Path(text).is_absolute() or text.startswith("file:"):
        return to_repo_relative(text)
    try:
        rel = (cwd / text).resolve().relative_to(REPO.resolve())
    except (ValueError, OSError):
        return None
    return None if ".." in rel.parts else rel.as_posix()


def guarded_hit(raw: str, cwds: list[Path], globs: list[str]) -> tuple[str, str] | None:
    for cwd in cwds:
        rel = rel_from(raw, cwd)
        if rel is None:
            continue
        g = blocked_by(rel, globs)
        if g:
            return rel, g
    return None


def segment_tokens(segment: str) -> list[str]:
    text = segment.replace("\\", "/")
    try:
        tokens = shlex.split(text, posix=True)
    except ValueError:
        tokens = text.split()
    while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
        tokens.pop(0)
    return tokens


def leading_is_exempt(tokens: list[str]) -> bool:
    """True when the segment's own leading command is a reader, git metadata,
    or a bin/harness run. Applies to that segment only."""
    if not tokens:
        return True
    head = tokens[0].lower()
    if head.rsplit("/", 1)[-1] in PYTHONS:
        args = [t for t in tokens[1:] if t != "-3"]
        return bool(args) and args[0].lstrip("./") == "bin/harness"
    if head.lstrip("./") == "bin/harness":
        return True
    if head == "git":
        rest = tokens[1:]
        while rest and rest[0].startswith("-"):
            flag = rest.pop(0)
            if flag in ("-C", "-c") and rest:
                rest.pop(0)
        return bool(rest) and rest[0].lower() in GIT_READ_SUBCOMMANDS
    return head in READ_COMMANDS


def shell_violation(command: str, start_cwd: Path, globs: list[str]) -> str | None:
    """Return a deny reason for the first offending segment, else None."""
    for raw in patch_paths(command):
        hit = guarded_hit(raw, [start_cwd, REPO], globs)
        if hit:
            return f"shell patch body targets {hit[0]} (matches sandbox glob {hit[1]!r})"
    cwd = start_cwd
    cwd_guard: str | None = None
    for segment in SEGMENT_SPLIT.split(command):
        if not segment.strip():
            continue
        cwds = [cwd, REPO] if cwd != REPO else [REPO]
        for target in REDIRECT.findall(segment):
            hit = guarded_hit(target, cwds, globs)
            if hit:
                return f"shell redirection into {hit[0]} (matches sandbox glob {hit[1]!r})"
        tokens = segment_tokens(segment)
        exempt = leading_is_exempt(tokens)
        if tokens and tokens[0].lower() in CD_COMMANDS:
            dest = next((t for t in tokens[1:] if not t.startswith("-")), "")
            rel = rel_from(dest, cwd) if dest else None
            if rel is None:
                cwd, cwd_guard = REPO, None
            else:
                cwd = REPO / rel
                g = blocked_by(rel, globs) or blocked_by(rel + "/x", globs)
                cwd_guard = f"{rel} (matches sandbox glob {g!r})" if g else None
            continue
        if exempt:
            continue
        if cwd_guard:
            return f"shell mutation after cd into {cwd_guard}"
        words = list(tokens)
        for t in tokens:
            if "=" in t:
                words.append(t.split("=", 1)[1])
        words.extend(m.group(1) for m in PATH_IN_CMD.finditer(segment.replace("\\", "/")))
        for word in words:
            hit = guarded_hit(word, cwds, globs)
            if hit:
                return f"shell segment {segment.strip()[:80]!r} targets {hit[0]} (matches sandbox glob {hit[1]!r})"
    return None


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

    is_write_tool = tool_l in WRITE_TOOLS or tool_l.endswith("write") or tool_l.endswith("edit")
    is_shell = (
        event.lower() in ("beforeshellexecution", "before_shell_execution")
        or tool_l in SHELL_TOOLS
    )
    read_like = tool_l in READ_TOOLS
    guard_note = "protected/read_only paths change only via a reviewed human-approved path"

    if is_shell:
        cwd = REPO
        raw_cwd = payload.get("cwd")
        if isinstance(raw_cwd, str):
            rel = to_repo_relative(raw_cwd)
            if rel is not None:
                cwd = REPO / rel
        why = shell_violation(command, cwd, globs)
        if why:
            return deny(f"refusing {why}; {guard_note}", event or "PreToolUse")
    elif not read_like:
        # Structured payloads: explicit path fields plus patch headers in any
        # string. Unknown tools fail closed when they name a guarded path.
        strings: list[str] = []
        walk_strings(tool_input, strings)
        walk_strings({k: payload.get(k) for k in ("file_path", "path", "target_file")}, strings)
        candidates = list(strings)
        for text in strings:
            candidates.extend(patch_paths(text))
        for raw_path in candidates:
            rel = to_repo_relative(raw_path)
            if rel is None:
                continue
            g = blocked_by(rel, globs)
            if g:
                kind = "mutation" if (is_write_tool or not tool) else f"unrecognised tool {tool!r} on"
                return deny(
                    f"refusing {kind} {rel} (matches sandbox glob {g!r}); {guard_note}",
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
