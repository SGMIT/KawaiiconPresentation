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

## P2a-1 — Prompt 2a Phase 1 (routing log appender) — complete

Session 2026-11-20, branch `taniko/graph-layer-phase`. Code commit `518fe76`
(base `db15088`); this entry and the STRAIN section land in the next commit.

Phase 0: `TANIKO_VERSION` `v0.4.0` = `../taniko` tag `v0.4.0`; static
conformance 6 pass / 0 fail / 0 warn / 1 skip, CONFORMANT; tree clean.

Delivered (`graph/**`):

- `graph/routing_log.py` — `RoutingLog`, the single writer (exclusive
  `flock`) for one run's `routing.jsonl`. Assigns `seq` and `at`; validates
  every record against the pinned `routing-record` schema (`$id` checked =
  0.4.0) before writing; rejects at append time: caller-supplied
  `seq`/`at`/`run_id`/`schema_version`, `at` going backwards or from a naive
  clock (G2), re-enter while open, exit without enter, double close (G3),
  any append after the root exits (G4). Reopen replays and refuses a seq gap
  (G1), a foreign `run_id`, or any invalid line. A rejected append writes
  nothing and consumes no seq. `node()` / `fail_and_exit()` close brackets on
  terminal failure (`fail`, then `exit`).
- `graph/toy.py` — stub-runner toy log (2-way fan-out, one branch fails,
  run escalates). No real agent sessions.
- `graph/tests/test_routing_log.py` — 18 tests (17 appender, 1 toy-log →
  pinned `loglint.py`).

Red → green (verify documents, `mode: real`, HEAD `db15088` ledger):

```
attempt 1  vr_047ac4d82fa5  2026-11-19T18:37:20.658Z  (skeleton appender, no enforcement)
  static     PASS     104ms  well-formed; 1 local reference(s) resolve, 17 remote not fetched; 1 stylesheet(s) scanned
  content    PASS      80ms  22 talk slides in order; 22 speaker entries matched; 5/5 Resources links in sources.md
  graph      FAIL     146ms  18 run, 25 failed, 0 errored, 0 skipped
  cited (first 20 of 25 locations): test_rejects_double_close, test_rejects_reenter_while_open,
  test_rejects_exit_without_enter, test_rejects_caller_supplied_seq, test_rejects_time_going_backwards,
  test_rejects_schema_invalid_records (7 subtests), test_append_after_root_exit_rejected, ...
VERDICT: FAIL

attempt 2  vr_3c60319d8ee6  2026-11-19T18:39:17.409Z  (tree = commit 518fe76)
verify: profile full [static, content, graph]
  static     PASS     113ms  well-formed; 1 local reference(s) resolve, 17 remote not fetched; 1 stylesheet(s) scanned
  content    PASS      83ms  22 talk slides in order; 22 speaker entries matched; 5/5 Resources links in sources.md
  graph      PASS     256ms  18 run, 0 failed, 0 errored, 0 skipped
attempt 2 (max 3)
VERDICT: PASS
```

Graph-tier denominator: 0 → 18 executed tests (tier previously ERROR).

Toy log (`python3 -m graph.toy --run-id toy-p2a1`, HEAD `db15088`):

```
.agent/graph/toy-p2a1/routing.jsonl
python3 ../taniko/conformance/loglint.py .agent/graph/toy-p2a1/routing.jsonl
LOGLINT PASS (grammar 0.1): 12 records, brackets balanced, evidence resolves
schema (appender validator, pinned routing-record 0.4.0): 12 of 12 records valid
```

loglint ran without `--evidence-dir`; the toy log carries 0 `verify_ref`s, so
G8 checked 0 of 0 refs ("evidence resolves" is vacuous here — see STRAIN).

Close-out verify on the docs commit: reported in that commit's message.

Next: Prompt 2a Phase 2, in a new session, after human greenlight.

## P2a-2 — Prompt 2a Phase 2 (worktree-isolated nodes, disjoint write scopes) — complete

Session 2026-11-20, branch `taniko/graph-layer-phase`. Base `6215ad5`; code
commit `63fa8ab`; this entry and the STRAIN section land in the next commit.

Phase 0: `TANIKO_VERSION` `v0.4.0` = `../taniko` tag `v0.4.0`; static
conformance 6 pass / 0 fail / 0 warn / 1 skip, CONFORMANT; tree clean;
venv Python 3.12.7.

Delivered (`graph/**`, `git diff --stat 6215ad5...63fa8ab`: 8 files, +747):

- `graph/scope.py`: write-scope syntax (exact / `dir/` prefix / `*` `?`
  `**` glob) and overlap; conservative for glob pairs, case-folded.
- `graph/fanout.py`: `validate_plan` rejects overlapping sibling writes
  (`PlanError` rule `G7`) and malformed entries (`scope`) before any run
  dir, worktree or branch exists. `run_fanout` resolves the base to a
  40-hex SHA once, then creates `<state>/graph/<run-id>/` (refused if it
  exists) and detached worktrees at `…/worktrees/<node-id>`. An
  out-of-scope change (tracked, deleted, untracked, ignored) produces
  `fail` with `failure_kind: scope_violation`, then `exit`. Spawn and enter
  records carry `scope.writes`. Join is all-of; on failure, route
  `escalate`.
- `graph/worktree.py`: `add_worktree` refuses anything but a full SHA
  (`HEAD`, `main`, `refs/heads/main` and a short SHA are tested).
- `graph/fence.py` + `graph/tests/fixture.py`: marker
  `.taniko-graph-fixture` at the main worktree root. Git-mutating helpers
  and the stub runner refuse repos without it.
- `graph/stub_runner.py`: deterministic, self-identifying, fixture-only.
- `graph/gitcmd.py`: git with repo-locating `GIT_*` env stripped.
- `graph/tests/test_fanout.py`: 16 tests, plus a module-level debris check
  against this checkout.

Red → green (verify documents, `mode: real`, HEAD `6215ad5` ledger):

```
attempt 1  vr_84d2bc330f31  2026-11-19T19:02:40.373Z  (tests + NotImplementedError skeleton)
  static     PASS     195ms  well-formed; 1 local reference(s) resolve, 17 remote not fetched; 1 stylesheet(s) scanned
  content    PASS     138ms  22 talk slides in order; 22 speaker entries matched; 5/5 Resources links in sources.md
  graph      FAIL    1564ms  46 cases run (34 tests, 15 subtests), 0 failed, 18 errored, 0 skipped
18 of 46 graph cases did not pass: ...FenceTest.test_helpers_refuse_this_repository [require_fixture],
  [fixture_git], [fixture_commit], [stub runner], [run_fanout with stub runner]
  ... 13 more location(s); raw log (state dir): verify/logs/vr_84d2bc330f31-graph.log
raw log (288 lines) ERROR: lines also name test_covers_matches_declared_syntax, test_disjoint_siblings_accepted,
  test_malformed_scope_entries_rejected, test_overlap_is_symmetric, test_read_overlap_is_not_a_conflict,
  test_sibling_overlap_rejected_before_any_state, test_fanout_log_passes_loglint_and_spawns_carry_writes,
  test_out_of_scope_write_fails_node, test_runner_failure_closes_bracket, test_add_worktree_refuses_unresolved_revs,
  test_existing_run_dir_refused, test_nodes_run_in_worktrees_at_resolved_sha, test_symbolic_base_is_resolved_once
VERDICT: FAIL

attempt 2  vr_78c14b522d39  2026-11-19T19:05:49.453Z  (tree = commit 63fa8ab)
verify: profile full [static, content, graph]
  static     PASS      97ms  well-formed; 1 local reference(s) resolve, 17 remote not fetched; 1 stylesheet(s) scanned
  content    PASS      77ms  22 talk slides in order; 22 speaker entries matched; 5/5 Resources links in sources.md
  graph      PASS    5547ms  99 cases run (34 tests, 76 subtests), 0 failed, 0 errored, 0 skipped
attempt 2 (max 3)
VERDICT: PASS
```

Graph-tier delta from the 26-case baseline: **26 → 99 cases (+73)**; tests
18 → 34 (+16), subtests 10 → 76 (+66). Gate coverage: sibling overlap
rejection (9 subtests, each also asserting no run dir, worktree, branch or
runner call); out-of-scope write → `scope_violation` with bracket closed
(5 subtests, each loglinted); helper refusal against this repository (5
subtests).

Zero-debris check, snapshots taken immediately before and after the green
verify (attempt 2):

```
## ls .agent/graph/
toy-p2a1
## git worktree list
/Users/stacymclean/Developer/KawaiiconPresentation                                                  6215ad5 [taniko/graph-layer-phase]
/Users/stacymclean/Developer/copilot-worktrees/KawaiiconPresentation/copilot-prewarm-literate-disco a593016 (detached HEAD)
/Users/stacymclean/Developer/copilot-worktrees/KawaiiconPresentation/stacy-mclean-nzcs-curly-lamp   a593016 [stacy-mclean-nzcs-taniko-harness-assessment]
## git branch --list
  main
+ stacy-mclean-nzcs-taniko-harness-assessment
* taniko/graph-layer-phase
  taniko/harness-loop
```

Before and after are identical; `diff before after` printed nothing (exit
0). `toy-p2a1` and both Copilot-app worktrees predate this phase.

Live run (fixture in a temp dir, `na` writes `docs/a.md` + `src/rogue.txt`
with scope `["docs/a.md"]`; `nb` writes `src/n.txt` with scope `["src/"]`):

```
4 na fail scope_violation  wrote outside scope.writes ['docs/a.md']: src/rogue.txt
5 na exit   failed: wrote outside scope.writes ['docs/a.md']: src/rogue.txt
7 nb exit   ok: 1 path(s) changed within scope: src/n.txt
schema (pinned routing-record 0.4.0): 12 of 12 records valid
LOGLINT PASS (grammar 0.1): 12 records, brackets balanced, evidence resolves
```

loglint ran without `--evidence-dir`; 0 `verify_ref`s, so G8 checked 0 of 0.
Its G7 check is exact-string only (STRAIN: 1 of 3 overlapping logs caught).

Open for operator: protect `.taniko-graph-fixture` (STRAIN, "fixture
marker").

Close-out verify on the docs commit: reported in that commit's message.

Next: Prompt 2a Phase 3, in a new session, after human greenlight.
