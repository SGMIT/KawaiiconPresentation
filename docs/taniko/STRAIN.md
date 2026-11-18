# Tāniko strain notes

Friction between what adopting Tāniko required and what its contracts offered.
Format per entry: **Needed** / **Offered** / **Implemented**. Entries whose delta
implies a spec change are marked `file-against-taniko`.

## Phase 0 — Doctor

### `python3` is not a real command on stock Windows — `file-against-taniko`

- **Needed:** a `python3` on PATH that runs Python 3.10+, because the Phase 0
  gates, the conformance README, and the reference adapter's declaration
  (`commands`, `verify.tiers[].command`, `toolchain[].detect`) all invoke
  `python3` by name.
- **Offered:** "requires Python 3.10+ and `jsonschema`", with `python3`
  assumed. On Windows, `python3` resolves to the Microsoft Store App Execution
  Alias stub (`%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe`), which
  exits 9009 with "Python was not found". The python.org installer
  (3.12.10 via winget) provides `python.exe` and `py.exe` but no `python3.exe`.
  Result before the fix: `selftest.py` reported the *clean* reference fixture
  as nonconformant (`doctor-runs`, `doctor-report-valid`, `verify-runs` FAIL)
  and two sabotaged variants as not caught. The suite blamed the harness for
  an interpreter-resolution problem.
- **Implemented:** copied `python.exe` → `python3.exe` in the install dir and
  prepended that dir to PATH ahead of WindowsApps. Self-test then passed
  (clean 15p/0f/0w/1s; all three sabotaged variants caught). Delta: the suite
  could run a preflight that `python3 --version` actually succeeds before
  judging, and report SUITE ERROR (exit 2) instead of attributing the failure
  to the adapter; the doctor of the reference adapter would also catch this
  if run standalone.

### `selftest.py` crashes on a cp1252 console — `file-against-taniko`

- **Needed:** the self-test's verdict printed on a default Windows console.
- **Offered:** `selftest.py` prints `→` (U+2192); under cp1252 stdout this
  raises `UnicodeEncodeError` after the first line, masking the real verdict.
- **Implemented:** run with `PYTHONIOENCODING=utf-8` (environment only; the
  suite is read-only). Delta: the suite could `sys.stdout.reconfigure(encoding="utf-8")`
  or use ASCII.

### No pre-existing CI

- **Needed:** "Your CI is (or will be) instructed to do the same clone."
- **Offered:** the clone command; no CI template.
- **Implemented:** `.github/workflows/taniko.yml` from scratch: checkout to
  `repo/`, clone the pinned tag to sibling `taniko/` (so `../taniko` holds),
  assert `describe --tags --exact-match` equals `TANIKO_VERSION`, run the
  suite's self-gates. Later phases extend it with `run.py`.

### Agent sandbox unavailable on this machine

- **Needed:** commands executed inside the agent CLI's filesystem sandbox.
- **Offered:** the prompt assumes a sandbox exists ("never inside your sandbox").
- **Implemented:** Cursor's Windows sandbox helper here provides only a network
  proxy, no filesystem isolation, so every command ran unsandboxed with
  per-command human approval. Consequence for Phase 4: tamper isolation must
  rest on permission-layer deny rules/hooks, not on a sandbox boundary.
