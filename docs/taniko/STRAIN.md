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

## Phase 1 — Harness declaration

### A code-centric declaration schema on a static-content repo — `file-against-taniko`

- **Needed:** a declaration for a reveal.js deck with no source code, build,
  package manager, or tests. What is checkable is (a) HTML well-formedness,
  (b) local `href`/`src`/`url()` references resolving to files, and
  (c) the deck agreeing with its own data (slide structure, speakers and links
  cross-referenced against `sources.md`).
- **Offered:** a schema whose vocabulary assumes code. `toolchain[].kind` is
  runtime/build-tool/sdk/package-manager/linter/test-runner; `cost_class` is
  static/build/unit/integration/ui/expensive; CONTRACTS §2 frames tiers as
  "lint, typecheck, build → unit → integration/UI"; `probe_file` is "a
  writable *source* file" and the destructive check corrupts it by appending
  `this is deliberately not valid source code (`.
- **Implemented:** the schema did fit, by mapping content concepts onto code
  ones:
  - **Toolchain:** the only declared tool is `python3` (the harness is
    standard library only). The deck's real runtime dependencies (reveal.js
    5.1.0 and Google Fonts from CDNs, plus a browser) cannot be declared.
    They are not machine tools with a `--version`, and checking them needs
    the network, which would make the verdict nondeterministic. So drift in
    the thing the deck most depends on is not representable.
  - **Tiers:** both are `cost_class: "static"`. `content` is not a unit test,
    and there is no `content`/`data` cost class. Array order carries the
    ordering, so this is harmless, but the label carries no information.
  - **Probe file:** `index.html`. The suite's corruption lands after
    `</html>`, which browsers silently tolerate. The probe is only caught
    because the static tier adopts a strict rule (no non-whitespace content
    after `</html>`). The probe design assumes a compiler-like tier where any
    appended garbage is fatal. For content formats that tolerate trailing
    junk (HTML, Markdown), the adapter has to pick a rule to match the probe.
  - **Writable paths:** least privilege is the content itself
    (`index.html`, `css/**`, `assets/**`, `notes.md`, `sources.md`). There is
    no `src/`/`tests/` split. The files the content tier cross-checks
    (`sources.md`) are also agent-writable, so the "tests" are not tamper
    isolated the way `tests/**` is in the reference. The agent can make
    slides and `sources.md` agree by editing either side. That is the honest
    shape of a self-consistency check. It is not a tamper hole in the
    verifier itself, which lives in `bin/**` (protected).
- **Delta:** the schema could make `kind` and `cost_class` admit content-shaped
  values (e.g. `kind: "validator"`, `cost_class: "content"`). It could also
  allow a declared non-machine dependency (`pinned_remote`: URL plus
  integrity hash, checked only by an opt-in networked doctor check). And
  `probe_file` could declare a corruption strategy, or the suite could
  document that the adapter must reject trailing garbage.

### Reference adapter declares `schema_version: "0.3.0"` against v0.4.0 schemas — `file-against-taniko`

- **Needed:** the schema-set version to pin. SCHEMAS.md says adapters should
  "pin exactly" while the set is 0.x.
- **Offered:** the v0.4.0 schema `$id` is `…:harness-declaration:0.4.0`, but
  the reference adapter (the "specification by example") and its doctor and
  verify envelopes still say `0.3.0`. The schema checks only the semver
  pattern, so the skew is invisible to conformance.
- **Implemented:** declared `0.4.0`. Delta: bump the reference adapter, or
  have `decl-present-valid` compare `schema_version` to the suite's schema
  `$id`.

### Protected-path matching on Windows works through `fnmatch` normcase

- **Needed:** `declaration-protected` to match `.claude/harness.json` against
  `.claude/**` on Windows.
- **Offered:** `checks.py` builds the path with `str(Path.relative_to(...))`,
  which on Windows gives `.claude\harness.json`. The `startswith(g[:-3] + "/")`
  fallback in `_match_any` would miss it. It still PASSes only because
  `fnmatch.fnmatch` applies `os.path.normcase`, which turns `/` into `\` on
  both sides on Windows.
- **Implemented:** nothing; recorded as a latent portability dependency. If
  `_match_any` ever switches to `fnmatchcase` or pure string matching, the
  check will falsely FAIL on Windows. Delta: use `.as_posix()`.

### Rules file vs per-tool pointer is not distinguished

- **Needed:** one canonical rules file (CONTRACTS §1) plus per-tool pointer
  files carrying the one or two key rules inline.
- **Offered:** the reference has only `AGENTS.md`, which it marks
  `read_only`. `instructions-present` reports every `AGENTS.md`/`CLAUDE.md`
  found as "canonical rules file", so a pointer looks the same as a second
  canonical file.
- **Implemented:** `AGENTS.md` is canonical (rules, scope, tiers, and the
  conventions the content tier depends on, per the skills clause's
  "defend the convention"). `CLAUDE.md` is a pointer that repeats the two key
  rules. Both are `protected`, not `read_only` like the reference: the rules
  file holds the "not done until verify passes" rule, so editing it weakens
  the loop. `AGENTS.md` names `bin/harness`, which does not exist until
  Phases 2–3. The rules run ahead of the implementation for one phase.

### Gaps the declaration cannot close yet

- **Tamper enforcement:** `tamper-rules-crosscheck` WARNs because there is no
  `.claude/settings.json`. Deferred to Phase 4 by decision.
- **Forbidden paths:** none declared because the repo holds no secrets, so
  `forbidden-untracked` SKIPs.
- **`.gitignore` is protected:** the verdict cache's tree hash (as in the
  reference) leaves out ignored files. An agent able to edit `.gitignore`
  could hide a file from the cache key. This exposure comes from tree-hash
  caching itself, and CONTRACTS §2 does not mention it.

## Phase 2 — Doctor

### The reference doctor takes shortcuts the contract forbids — `file-against-taniko`

- **Needed:** a doctor that detects drift against the committed declaration
  (CONTRACTS §1): run each `toolchain[].detect.command`, apply its
  `version_pattern`, compare against its `requirement`.
- **Offered:** the reference adapter (the README's "specification by
  example") does none of that. It runs `sys.executable --version` (the
  interpreter running the harness, not the declared `python3` on PATH, which is
  exactly the Windows Store-stub failure from Phase 0). It hardcodes the id,
  `>=3.10`, and the regex, and never reads `toolchain[]`, so a second entry
  would never be checked. Its comparison handles only major.minor and `>=`, and
  crashes on `3.13.0rc1`. It hashes the declaration but never parses it or
  checks `schema_version`, and crashes on a missing or invalid file (exit 1 by
  traceback). It hardcodes `.agent` instead of reading `state.dir` and never
  checks it is gitignored. It has no disk check, emits `schema_version`
  `0.3.0`, and never produces `warn`, `error`, or `remediation`. Its plain-text
  output drops requirement and remediation, and it silently ignores unknown
  flags. The suite cannot see any of this: `doctor-runs` checks only the exit
  code and output size, and `doctor-report-valid` checks only the envelope.
- **Implemented:** `bin/harness doctor` reads everything from
  `.claude/harness.json`. Toolchain entries are detected by their declared
  argv, with no shell and a 10s timeout. Health checks cover declaration
  (parses, `schema_version` 0.4.0, consumed fields well-typed),
  `TANIKO_VERSION` pin, git repo with a commit, `state.dir` writable and
  gitignored, disk >=500MB, `conformance.probe_file` present, and `bin/harness`
  LF in the index. A missing tool is `fail` with the declared remediation.
  Delta: fix the reference doctor to be declaration-driven, since adapters
  copy it.

### Windows `CreateProcess` finds the parent's own interpreter before PATH — `file-against-taniko`

- **Needed:** `detect.command: ["python3", "--version"]` to resolve `python3`
  the way a shell would, so a Store stub ahead on PATH is caught.
- **Offered:** "argv, no shell interpretation". On Windows,
  `subprocess.run(["python3", ...])` goes to `CreateProcess`, which searches
  the parent executable's directory *before* PATH. Run from
  `Python312\python3.exe`, a bare `python3` always finds itself, whatever PATH
  says. A naive declaration-driven doctor would rebuild the reference's
  `sys.executable` shortcut by accident.
- **Implemented:** resolve `argv[0]` with `shutil.which` (honours PATH and
  PATHEXT) and run the resolved path. `found` reports only the version, never
  the path. The suite's own `Target.run` passes bare argv, so its invocations
  have the same quirk. Delta: specify that `detect.command[0]` is resolved via
  PATH lookup, and do so in the suite and reference.

### Range syntax: the schema permits all of node-semver; a stdlib doctor implements a subset — `file-against-taniko`

- **Needed:** a defined meaning for every legal `requirement` value.
- **Offered:** "Exact version ('5.10.1') or a range in node-semver syntax
  ('>=20 <21')", i.e. the whole node-semver grammar (caret, tilde, hyphen
  ranges, X-ranges, prerelease ordering, `||`), with no subset named and no
  conformance check. Full node-semver is a dependency or several hundred
  lines; standard-library Python has no semver.
- **Implemented:** exact versions (`1.2.3`, `=1.2.3`, `v1.2.3`); bare partials
  as X-ranges (`3.12` means `>=3.12.0 <3.13.0`); `>= <= > < =` with node
  semantics for partials (`>3.10` means `>=3.11.0`, `<=3.10` means
  `<3.11.0`); space-AND; `||`. `^`, `~`, hyphen ranges, wildcards,
  prerelease/build tags, and more than three components are rejected as check
  status `error` (exit 1) with the construct named, never a silent pass.
  Delta: the schema should name a portable subset (or a regex for
  `requirement`), so an adapter's "unsupported" is a declaration error the
  suite can catch statically rather than a runtime surprise.

### No portable drift-detection invocation; the only evidence of halting is manual — `file-against-taniko`

- **Needed:** proof that doctor halts on drift.
- **Offered:** the conformance README says so itself: "Doctor drift detection
  (report a mismatch against a modified declaration) has no portable
  invocation yet and is exercised only indirectly." `doctor-runs` passes any
  exit in {0,1,2}, so a doctor that always exits 0 passes.
- **Implemented:** the only evidence is a manual run. Copy the repo to
  `%TEMP%`, set the copy's `python3` requirement to `>=99`, run doctor: exit 2,
  `status: drift`, `python3` FAIL "3.12.10 does not satisfy >=99" with the
  declared remediation, and both modes schema-valid. Also checked in the copy:
  a missing detect binary gives exit 2 and `fail` "not found on PATH" with
  remediation; `^3.10` gives exit 1 and `error`. The committed declaration
  was never touched. Delta: the suite already has everything it needs for a
  portable check. Copy the target to a temp dir, rewrite `toolchain[0].requirement`
  to an unsatisfiable exact version, run `commands.doctor` plus `json_flag`, and
  require exit 2, `status: drift`, and a failing check whose `id` matches.

### Verify checks PASS vacuously when verify does not exist — `file-against-taniko`

- **Needed:** before Phase 3, every verify check FAILs or SKIPs.
- **Offered:** with `commands.verify` declared but no `verify` subcommand
  (argparse exits 2 with usage), `verify-runs` FAILs and `profile-separation`
  WARNs, but `verify-deterministic` PASSes ("exit 2 twice") and
  `verify-replay-fast` PASSes ("replays in 0.0s"). Two identical usage errors
  read as a deterministic, cached verdict.
- **Implemented:** reported verbatim; not worked around, and no stub verify.
  Delta: those checks should require a parseable verdict (or exit 0/1)
  from the first run before judging determinism or replay, and SKIP or FAIL
  otherwise.

### Exit-code and status precedence are underspecified — `file-against-taniko`

- **Needed:** one exit code when checks both `fail` and `error`, a meaning for
  check-level `error`, and a code for CLI usage errors.
- **Offered:** report-level `drift` means "at least one fail" and `error` means
  "doctor could not complete". The schema does not say which wins when both
  apply, and does not say whether an unusable declaration is drift or error.
  `doctor-runs` FAILs any exit outside {0,1,2}, so usage errors cannot get
  their own code and share 2 with drift.
- **Implemented:** error > drift > warn > ok. A check `error` (unevaluable
  requirement, bad regex, uninterpretable capture) or an unusable declaration
  gives `error` and exit 1, because drift attestation is then untrustworthy.
  Usage errors exit 2 with usage on stderr and print no JSON, so
  `--json` callers can still tell them apart. Delta: state precedence in the
  schema and reserve a usage code (or bless 2 with no JSON).

### Remediation text is static and can contradict the requirement

- **Needed:** remediation that matches the failing requirement.
- **Offered:** `remediation` is free text beside `requirement`. In the `>=99`
  drift run, doctor surfaced "Install Python 3.10+", which is correct for the
  committed declaration but wrong for the mutated one.
- **Implemented:** surfaced verbatim, as the schema says. Not a spec change. A
  real requirement bump must update the remediation in the same reviewed
  commit.

### `core.autocrlf=true` vs an LF-only executable

- **Needed:** `bin/harness` committed with LF and mode 100755, so Linux CI can
  run it via the shebang.
- **Offered:** Git for Windows sets `core.autocrlf=true` system-wide. The index
  stays LF, but any checkout on this machine writes CRLF to the working tree.
  A doctor check on the working tree would warn permanently here for a
  harmless reason.
- **Implemented:** committed with `git update-index --chmod=+x` (index shows
  `100755`, `i/lf`). The `harness-lf` check inspects the index blob (what CI
  receives) and falls back to the working tree only when untracked. No
  `.gitattributes`: it is outside this repo's editable scope and not needed
  while the index is LF.

### CI edits go through the protected path

- `.github/**` is in `sandbox.protected`. The Phase 2 step adding
  `run.py --tiers static` to `.github/workflows/taniko.yml` was made as an
  explicitly human-approved change and is labelled so in the commit message.
  Behavioral joins in Phase 3, once verify exists: running it now would make
  CI red on a known, expected FAIL.
