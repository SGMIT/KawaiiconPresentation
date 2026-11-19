# Tāniko adoption progress

Append-only log. Read it at the start of every session. Each prompt phase
runs in its own session: find the last entry marked **complete**, execute
the next phase only, then stop. Never edit, reorder, or delete entries; to
correct one, append a new entry that names the one it supersedes.

Each entry records: phase, status (`complete` / `blocked` / `setup`),
commit, and the gate evidence (pasted output with denominators).

Pinned suite: `TANIKO_VERSION` = `v0.4.0` (`../taniko`).

---

## P1 — Prompt 1 (harness and loop) — complete

Reconstructed on 2026-11-19 from git history and `docs/taniko/STRAIN.md`;
this log was not written during Prompt 1.

| Phase | Commit | Summary |
|---|---|---|
| 0 | `df68d7c` | Pin `TANIKO_VERSION` v0.4.0; CI clones pinned suite outside checkout |
| 1 | `90f6ba4` | Harness declaration, `AGENTS.md`/`CLAUDE.md` rules, `.agent` state gitignored |
| 2 | `9dc764c` | Declaration-driven doctor; static conformance in CI |
| 3 | `5a59685` | Declaration-driven verify, static + content tiers; full conformance in CI |
| 4 | `f096ef4` | Agnostic tamper guard and CLI adapters |
| C0 | `46ddadb` | Skills onto branch |
| C1 | `f65eba6` | Guard bypasses closed (red 15/31 → green 31/31) |
| C2 | `3d69f6f` | Copilot preToolUse adapter; Cursor dropped (red 12/51 → green 51/51) |
| C3 | `b4127a0` | Live proof of Copilot adapter; `STRAIN.md` writable |

## P2a-0 — Prompt 2a Phase 0 — blocked, then setup

Session 2026-11-19, branch `taniko/graph-layer-phase`.

Phase 0 preconditions as first found:

- `TANIKO_VERSION` `v0.4.0` = `../taniko` tag `v0.4.0`: pass.
- Static conformance: NONCONFORMANT, 5 pass / 1 fail / 1 skip
  (`decl-present-valid`: "jsonschema not installed").
- Branch: was `taniko/harness-loop`; operator created `taniko/graph-layer-phase`.
- This file: absent.
- Graph code had no writable location.

Operator setup (protected files, human-made):

- `.claude/harness.json`: `graph/**` added to `sandbox.writable`; new
  verify tier `graph` (`cost_class: unit`, `python3 bin/tier-graph`).
- `bin/tier-graph`: graph-test tier adapter (drafted by the agent, smoke-tested
  outside the repo: missing dir → error/2, 0 tests → error/2, import error →
  error/2, failing test → fail/1, passing test → pass/0).
- `AGENTS.md`: `graph/**` editable; `PROGRESS.md` append allowed.
- Interpreter: gates run from `~/.venvs/taniko` (Python 3.12.7, jsonschema 4.26.0).

Evidence after setup, with `~/.venvs/taniko/bin` first on PATH:

```
python3 ../taniko/conformance/run.py --repo . --tiers static
  ── 6 pass, 0 fail, 0 warn, 1 skip
  VERDICT: CONFORMANT
```

Known state: full `verify` returns ERROR on the `graph` tier until Phase 1
creates `graph/tests` (zero executed tests is not evidence). Do not push
until Phase 1 is green — CI's behavioral conformance runs `verify`.

Next: Prompt 2a Phase 1 (routing log appender), in a new session.
