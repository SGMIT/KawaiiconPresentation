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

## Phase 3 — Verify

### The reference verify takes shortcuts the contract forbids — `file-against-taniko`

- **Needed:** a verify that runs the declared tiers (CONTRACTS §2): each
  `verify.tiers[].command` argv in order under its `timeout_seconds`, fail
  fast, error kept distinct from fail, a budget that is counted, and an
  envelope that attests its own mode and tier set.
- **Offered:** the reference adapter's verify:
  - calls tier functions in-process and never runs a declared tier argv;
  - hardcodes `TIERS` and `PROFILES`, and ignores `timeout_seconds`,
    `cost_class` and `budgets`;
  - lets a timeout or tier exception escape as a traceback (exit 1, read as
    "fail"), and its `tier-*` CLIs return `0 if pass else 1`, so a tier error
    is also a fail;
  - drops `failed_stage` and `feedback` on error;
  - fills a fail without feedback with `"stage failed without feedback"`, and
    defaults a missed regex to `line: 1`;
  - computes `started_at` after the tiers have run, so it is really the end
    time;
  - hardcodes `attempt {number: 1, max_total: 5}` and never counts attempts;
  - emits `schema_version` 0.3.0 with no `mode` or `profile_tiers`;
  - keys the cache on tree hash plus profile only, so editing the verifier or
    the declaration replays the old verdict;
  - runs `git diff HEAD` without `--binary`, so two edits to one tracked
    binary hash the same;
  - splits untracked names on whitespace;
  - caches timeouts;
  - parses flags with `set(args)`, so `verify --quik` silently runs full.
  The suite sees none of this, because it checks only envelopes and exit codes.
- **Implemented:** `bin/harness verify` reads tiers, profiles and budgets from
  the declaration and runs each declared argv:
  - `argv[0]` is resolved with `shutil.which`; no shell, stdin null, declared
    timeout.
  - Declared features it does not implement are errors, never silently
    ignored: `preconditions`, `skippable`, `flaky_reruns`, `max_cost_usd` and
    `max_wall_clock_seconds`.
  - The cache key covers HEAD, `git diff HEAD --binary`, untracked names
    (NUL-separated) and contents, the profile, the declaration's sha256,
    `bin/harness`'s sha256, and the Python version.
  - Logs are kept under `.agent/verify/logs/` and referenced from `raw_refs`.

  Delta: bring the reference up to the contract, and add suite checks that
  would have caught these shortcuts:
  - a declared tier argv must actually run (e.g. point it at a sentinel
    script);
  - a tier timeout must yield `error`;
  - editing the declaration must invalidate the cache.

### Tier commands: "non-zero = fail" cannot carry error; crashes look like failures — `file-against-taniko`

- **Needed:** a tier must be able to report "could not judge" (a missing
  tool, or an unmet precondition) separately from "the deck is wrong".
- **Offered:** the declaration schema says a tier `command` is an "argv
  whose exit code is the verdict: 0 pass, non-zero fail". The verify-result
  schema has three verdicts, but the tier interface has two. Also, an
  uncaught Python traceback exits 1, which is the same exit code as a genuine
  fail.
- **Implemented:** tiers exit 0, 1 or 2. When `KC_TIER_RESULT` names a path,
  a tier also writes its outcome there (verdict, detail and bounded
  feedback). verify requires that record and treats each of these as `error`:
  - a missing or invalid record;
  - a record that disagrees with the exit code;
  - an exit code outside 0/1/2.

  In a temp copy, a tier script that only raises gives `verdict: error`, exit
  2: "exited 1 without a valid result record (a crash, or not a tier
  command)". Delta: specify a three-valued tier exit (or a result channel),
  so adapters do not each invent a side channel.

### Phase 2's vacuous verify passes now pass for real reasons

- **Needed:** `verify-deterministic` and `verify-replay-fast` passing because
  verify is deterministic and cached. In Phase 2 they passed on two identical
  argparse usage errors.
- **Offered:** the same checks; nothing in the suite changed.
- **Implemented:** on a clean tree, the gate's detail lines:
  - `verify-runs`: "verdict=pass, 2 stages, 0.3s, conforms"
  - `verify-deterministic`: "identical verdict on identical tree (exit 0 twice)"
  - `verify-replay-fast`: "unchanged tree replays in 0.1s (fresh 0.3s) and
    marks cache.replayed"
  - `profile-separation`: "'quick' verdict carries profile='quick', never
    'full'"

  These lines differ from Phase 2's ("exit 2 twice", "replays in 0.0s") only
  in content, not in kind. The checks still cannot tell a real pass from a
  vacuous one, so the Phase 2 delta (require a parseable verdict before
  judging determinism or replay) stands.

### The destructive probe only bites an HTML deck because of the strict after-`</html>` rule — `file-against-taniko`

- **Needed:** `fail-on-broken-code` to prove that the gate gates.
- **Offered:** the suite appends `\nthis is deliberately not valid source
  code (\n` to `conformance.probe_file`. For `index.html` that lands after
  `</html>`, where every browser silently moves the text into `<body>` and
  renders the deck. HTML5 calls it a parse error, but nothing breaks.
- **Implemented:** the static tier allows only whitespace after `</html>` (a
  comment there fails too), and before `<html>` it allows only whitespace,
  comments and the doctype. The probe is caught at
  `index.html:448:1: text after </html> ('this is deliberately not valid
  source code ('); only whitespace may appear outside the <html> root`. That
  gives `fail-on-broken-code` "exit 1 in 0.3s, verdict=fail,
  failed_stage=static", and `cache-restore-replay` "restored tree → baseline
  verdict in 0.1s". The rule is a real strictness choice that matches
  AGENTS.md ("nothing after `</html>`"). However, the suite cannot tell it
  from an adapter that string-matches the probe text, and a deck format
  without such a rule (Markdown, for instance) would get a false FAIL. The
  stdlib `html.parser` is lenient, so strictness is layered on top of it:
  - every non-void element needs an explicit end tag, optional ones included;
  - `/>` on a non-void element fails;
  - text containing `<` followed by a letter, `/`, `!` or `?` is treated as
    an unterminated tag or comment.

  An unterminated attribute quote can still swallow markup. The stack check
  usually catches it, at a less precise location. Delta: let `probe_file`
  declare a corruption strategy (e.g. "unclosed element"), or randomise the
  probe so it cannot be special-cased.

### What an attempt budget means for a stateless CLI — `file-against-taniko`

- **Needed:** `max_attempts_total: 3` and `max_attempts_per_tier: 2`
  enforced, with exhaustion "an explicit failure with the accumulated evidence
  attached".
- **Offered:** "per task", with no definition of a task or an attempt, and no
  owner for the counter. The `attempt` object allows only `number`,
  `max_total` and `exhausted`.
- **Implemented:** the smallest honest version:
  - **Task:** the HEAD commit.
  - **Attempt:** one distinct working tree fresh-verified under that HEAD.
    Replays, `--no-cache` reruns of the same tree, and quick plus full on one
    tree are all the same attempt.
  - **Ledger:** `.agent/verify/attempts/<HEAD>.json`.
  - **Per-tier count:** the number of distinct trees on which that tier
    *failed*. Errors are harness bugs and are not charged to the agent.
  - **Exhaustion:** a non-pass with `used >= max_attempts_total`, or with the
    failing tier's count at `max_attempts_per_tier`, sets `exhausted: true`.
    The summary is then prefixed "BUDGET EXHAUSTED (...): stop and escalate",
    and `details` lists every attempt's failed stage and summary.

  In a temp copy, three failing trees gave attempt 1 not exhausted. Attempt 2
  was exhausted because "tier static failed on 2 of 2 allowed tree states".
  Attempt 3 was exhausted with "3 of 3 attempts used". What it cannot do:
  - After exhaustion, verify still runs the tiers and reports the real
    verdict. Refusing to run would mean fabricating a fail.
  - The agent can reset the count by deleting `.agent/` (which must be
    writable) or by committing.

  The CLI counts and attests, but halting belongs to the loop driver (a
  Phase 4 hook, CI, or a graph edge). Delta: define task identity and the
  attempt unit, say who enforces, and add per-tier counters to `attempt`.

### What verify-result could not express for a content deck — `file-against-taniko`

- **Needed:** an honest envelope for a deck whose checks are not tests, and
  for errors that happen before any tier runs.
- **Offered:**
  - `stages[].counts` is test-shaped (`tests_run`, `passed` and so on).
  - `stages` needs `minItems: 1` and `attempt` is required, so there is no
    shape for "verify failed before its first tier" or for "budget state
    unknown".
  - A location has a single file, so a cross-file mismatch cannot point at
    both sides.
  - There is no place to say evidence was deliberately scoped. The 17 remote
    URLs (reveal.js, fonts, the Resources links) are never fetched, so the
    verdict does not cover them.
- **Implemented:**
  - Counts go in `detail` ("22 talk slides in order; 22 speaker entries
    matched; 5/5 Resources links in sources.md").
  - A setup failure emits one stage `pipeline` (`cost_class: static`,
    `verdict: error`) with `attempt {1, 1}`, and its `details` say so
    explicitly: "No declared tier ran ... attempt.number/max_total are not
    budget evidence".
  - Cross-file hints go in the message ("sources.md:46 has this speaker under
    a different title").
  - "17 remote not fetched" is stated in the static stage's `detail`.

  Delta: give stages a non-test count shape, allow an empty `stages` array
  (or a reserved stage) on pipeline error with an optional `attempt`, add
  `related` locations, and add an `unverified` or `scope` field.

### Verdict caching: error is unspecified; timeouts are not deterministic — `file-against-taniko`

- **Needed:** to know whether `error` verdicts may be replayed.
- **Offered:** "pass and fail are both cacheable", and replay legitimacy
  "rests entirely on the determinism requirement". The contract says nothing
  about error. The reference caches everything, including timeouts.
- **Implemented:** deterministic tier errors are cached, such as a crash or a
  bad result record. Timeouts and start failures are not cached, because they
  depend on machine load and PATH rather than on the tree. In the temp copy,
  a rerun after the timeout had `replayed: false`, while a rerun after the
  crash had `replayed: true`. Delta: state that an error caused by the
  environment must not be replayed.

### The `.gitignore` exposure is closed by construction

- **Needed:** (Phase 1 gap) a file hidden from the tree hash by an ignore
  rule must not be able to change a cached verdict.
- **Offered:** nothing; CONTRACTS §2 does not mention it.
- **Implemented:**
  - The tiers read only files inside the key: tracked files (`index.html`,
    `sources.md`), plus the CSS from `git ls-files --cached --others
    --exclude-standard -- css/`.
  - The static tier fails any local reference that resolves to an ignored
    file ("a clone or the published deck will not have it").
  - `.gitignore` is protected. A pattern added to `.git/info/exclude` hides a
    file from the tier and the key together, consistently.
  - Accepted: the key uses git's line-ending-normalised view while the tiers
    read working-tree bytes, so a change that only swaps CRLF and LF is
    invisible to the key. The tiers do not depend on line endings.

### The real deck violated its own convention; the matching rules live only in code

- **Needed:** "Every speaker on a talk slide has a `#### <title> — <speaker>`
  entry in `sources.md`", checked exactly.
- **Offered:** AGENTS.md does not say whether `<title>` is the slide title,
  how the Resources slide is identified, or what "external link" means.
- **Implemented:** strict matching. Text is HTML-unescaped and NFC
  normalised, whitespace is collapsed, and headings are split on their last
  `" — "` (the Wizard heading contains two). There is no quote, dash or case
  folding. The first verify on the real deck FAILed: 4 of 22 slides use a
  shortened title (LPE, NZ Digital Identity, Want me to take it from here?,
  Heed The Wizard's Warnings). Fixed by human decision in `sources.md`: each
  heading uses the slide's title, and the official title moves to a
  `**Full title:**` bullet. Resources is the one `section` whose `h2` reads
  "Resources", and external means `http(s)`. These definitions are stated
  only in `bin/harness`. The skills clause ("defend the convention") says they
  belong in AGENTS.md, which is protected; proposed, not done.

### Smaller frictions

- **No escalation path yet:** `raw_refs` point at retained logs, but the
  debug skill that CONTRACTS §2 pairs with bounded feedback does not exist.
- **The gate needs committed work:** destructive conformance refuses a dirty
  tree, so the gate ran on a local commit that was amended (code unchanged)
  before handoff.
- **CI edit:** this phase's `.github/workflows/taniko.yml` change (doctor
  step, then `--tiers static,behavioral,destructive`) is again the reviewed,
  human-approved path and is labelled so in the commit message.

## Phase 4 — Tamper isolation

### `tamper-rules-crosscheck` is textual, not enforcement — `file-against-taniko`

- **Needed:** proof that protected paths cannot be modified by the agent under
  verification (CONTRACTS §2).
- **Offered:** `check_tamper_rules` WARNs or PASSes by looking for each
  protected glob's first path segment as a substring of
  `.claude/settings.json`. It never loads the agent CLI, never fires a hook,
  and never attempts a write. A settings file that mentions `.claude` in a
  comment would PASS.
- **Implemented:** `.claude/settings.json` with `permissions.deny` Edit/Write
  for every `sandbox.protected` and `sandbox.read_only` glob (plus allow for
  writable deck paths), which turns the suite check green. Real enforcement
  is separate (below). Delta: a conformance check that would prove enforcement
  would have to drive the agent CLI (or an OS sandbox) and attempt a write;
  the suite cannot do that from outside today.

### Agnostic core vs per-CLI adapters

- **Needed:** teammates on Cursor, Claude Code, or neither can use the same
  harness without forking policy.
- **Offered:** "enforced by the agent CLI's permission layer" with the
  cross-check hard-coded to `.claude/settings.json` (Claude-shaped).
- **Implemented:**
  - **SoT:** `.claude/harness.json` sandbox globs.
  - **Shared enforcer:** `.claude/hooks/tamper_guard.py` (stdlib, fail-closed,
    reads the declaration every call). Soft budget halt when the attempt
    ledger shows exhaustion; human reset is deleting
    `.agent/verify/attempts/<HEAD>.json`.
  - **Claude adapter:** `.claude/settings.json` deny list + `PreToolUse` →
    `python3 .claude/hooks/tamper_guard.py`.
  - **Cursor adapter:** `.cursor/hooks.json` → `.claude/hooks/run_guard.ps1`
    (PATH bootstrap + UTF-8 stdin forward on Windows) → same guard.
  - **Declaration:** `.cursor/**` added to `sandbox.protected` so the Cursor
    adapter cannot rewrite itself without a reviewed path.
  - **Drift:** doctor check `tamper-rules-aligned` (not a verify tier).

### Which layers enforce on this machine

- **Cursor (this session):** project hooks enforce when they load and when
  stdin reaches the guard. `.cursor/permissions.json` is allowlist-only and
  is not used. Claude `permissions.deny` is not Cursor's deny layer; Cursor
  may import Claude *hooks* from settings when Third-Party Imports is on.
- **Claude Code:** would honour `permissions.deny` and `PreToolUse` if used
  here; not the active CLI for this phase's live proof.
- **CI:** honours none of the above; runs shell directly. Destructive probe
  still edits writable `index.html` only.
- **OS sandbox:** unavailable on this Windows host (Phase 0). Isolation is
  CLI permission/hook layer only.

### Bypass routes that remain open

- Arbitrary shell that never names a protected path in the tool payload
  (obfuscated writers, indirection).
- Full PowerShell/cmd AST is not parsed; only heuristics + path literals.
- Symlink/junction races (best-effort `Path.resolve()` only).
- Editing/removing the hook config if the hook fails to load (fail-closed
  helps only while the adapter is loaded).
- Deleting `.agent/` resets the budget ledger (must stay writable for doctor).
- Committing creates a new task identity (HEAD) and resets attempt counting.
- Raw terminals, humans, and CI outside the agent loop.
- During this phase, a broken Cursor launcher (`python3` missing from the GUI
  PATH, or empty stdin when `& python` did not inherit `$input`) fail-closed
  *every* tool — including repairs to the guard. Recovery required renaming
  the adapter off. Recorded as operational strain, not a contract win.

### Budget exhaustion: attested + soft hook halt, not OS-enforced

- Phase 3 attested exhaustion in the verify envelope.
- Phase 4 guard denies mutating Write/Delete and write-like shell when the
  ledger shows exhaustion. It cannot stop a ledger wipe. Still not
  OS-enforced.

### Boundary config protection

- Guard and Claude settings live under `.claude/**` (already protected).
- `.cursor/**` is now in `sandbox.protected` and deny-listed. The declaration
  can express adapter paths this way; it still cannot express "the hook
  process must load" — that is CLI behaviour outside the schema.

## Correction C0 — Skills onto the branch

### Adoption kit is absent at the pinned tag — `file-against-taniko`

- **Needed:** the Tāniko skills and the conformance suite pinned to one
  version, so a reviewer knows which guidance and which gates the harness was
  built against.
- **Offered:** `TANIKO_VERSION` pins the suite at `v0.4.0`, but
  `adoption/` (prompts, skills, `install-skills.sh`) does not exist at that
  tag. It exists only on Tāniko `master`.
- **Implemented:** skills installed with
  `adoption/install-skills.sh --tool all` from Tāniko `master` at `0d53fee`
  (`v0.4.0-13-g0d53fee`) into `.agents/skills/`, `.claude/skills/`,
  `.cursor/rules/` and `.github/skills/`. The installer merged its
  `taniko-skills-start`/`-end` marker block into the existing `AGENTS.md`
  without touching existing rules. Delta: skills and suite are now versioned
  independently. Nothing in the declaration records the skills commit, and
  doctor's `taniko-pin` check does not cover it.

### The installer's source checkout and the pinned suite share a path

- **Needed:** `../taniko` stays at the pinned tag (doctor `taniko-pin`, CI
  clone).
- **Offered:** the adoption kit has to be run from a `master` checkout.
- **Implemented:** the first install switched `../taniko` itself to `master`,
  and the gates briefly ran against `master` before it was moved back to
  `v0.4.0` (`git switch --detach v0.4.0`). Doctor's `taniko-pin` check reads
  `TANIKO_VERSION`, not the suite checkout, so it did not catch the drift.
  Use a separate clone for `master`.
- An earlier attempt also installed the skills on `main` and pushed them; that
  was undone before this install.

### Local interpreter differs from the declaration

- `/usr/bin/python3` on this macOS host is 3.9.6, and doctor halts on
  `python3 >=3.10`. Gates were run with Homebrew Python 3.12.7 plus
  `jsonschema` in a venv outside the repo, matching CI (`setup-python 3.12`).

## Correction C1 — Guard bypasses closed (red → green)

### Shell shortcuts exempted the whole command

- **Needed:** a guard that denies any shell command that writes a protected
  path, even when the command also contains a harmless token.
- **Offered:** the Phase 4 guard ran `read_shell`, `git_meta` and
  `harness_run` as regex searches over the whole command string. One
  benign token (`cat`, `git status`, `python3 bin/harness`) allowed
  `cat notes.md > bin/harness`, `git status && echo x > CLAUDE.md`,
  `python3 bin/harness verify; sed -i ... .claude/harness.json` and
  `cd .claude && rm harness.json`. The suite's textual
  `tamper-rules-crosscheck` could not see this.
- **Implemented:** the guard now decides per segment (split on `;` `&&` `||`
  `|` `&` newlines `$(` backticks and parentheses):
  - a segment that names a guarded path denies unless its *own* leading
    command is a reader (`cat`, `grep`, `ls`, ...), git metadata
    (`status`, `diff`, `log`, `show`, `add`, `commit`, ...) or `bin/harness`;
  - any redirection (`>`, `>>`, `&>`, `>|`) whose target resolves into a
    guarded path denies, even after a reader;
  - `cd`/`pushd`/`Set-Location` is tracked: relative paths resolve from the
    new directory, and after a cd into a guarded directory every non-reader
    segment denies.
- **The `or True` is gone; the writey heuristic no longer decides.** Every
  non-reader segment that names a guarded path denies. Write hints cannot
  enumerate writers (`python -c`, `cp`, `find -delete`, `install`, `dd`, ...);
  a reader allowlist fails closed instead. `WRITE_SHELL_HINTS` now only
  feeds the soft budget halt, extended with `rm`, `mv`, `cp`, and others.
- **Tightened:** `git update-index` is no longer exempt (it can flip the exec
  bit or set skip-worktree on a protected file). Reading a guarded path with
  a non-allowlisted reader (`sed -n`) is denied.

### Patch-style write tools were unrecognised

- **Needed:** Copilot and Codex `apply_patch` edits are writes.
- **Offered:** the guard extracted only path-keyed fields; a patch body
  naming `bin/harness` was allowed, and any unknown tool name fell through
  to allow.
- **Implemented:** `*** Update|Add|Delete File:`, `*** Move to:` and unified
  `--- a/` / `+++ b/` headers are parsed from every payload string (and from
  shell commands, for heredoc'd patches). `apply_patch` and similar
  editor tool names are write tools. An unrecognised tool that names a
  guarded path now denies; only a known read-tool list is exempt.

### Evidence and wiring

- `.claude/hooks/test_tamper_guard.py`: 31 stdlib `unittest` cases that run
  the guard as a subprocess, as a hook would. Red against `f096ef4`'s guard:
  15 failures, all defect-1/2 payloads. Green after the fix: 31/31.
- **Wired as a CI step, not a verify tier.** The guard is boundary machinery,
  not deck content. A verify tier would charge guard regressions to the deck
  author's attempt budget, and the author cannot fix them because the guard
  is protected. The CI step runs on every push and pull request, before
  doctor.

### Bypass routes that remain open (updated)

- Quoting, variables and indirection are still not parsed
  (`f=bin/harness; echo x > "$f"`, `eval`, `bash -c "$(...)"`, base64).
  The guard only sees path literals.
- `cd` to a variable or to an unresolvable directory resets tracking to the
  repo root.
- An unknown tool that writes but never names a path in its payload is still
  allowed.

## Correction C2 — Copilot adapter; Cursor support dropped

### Scope decision: Cursor is no longer a supported tool

- **Needed:** guard the tools the operator actually uses. The operator is
  now on macOS with GitHub Copilot (and Claude Code if installed); Cursor is
  no longer in use.
- **Offered:** the correction prompt asked for a cross-platform Cursor
  launcher (POSIX `sh` beside the `.ps1`) and a doctor WARN for a missing
  launcher interpreter.
- **Implemented (operator decision, deviates from the prompt):** Cursor
  support is removed rather than made cross-platform.
  - Removed: `.cursor/hooks.json`, `.claude/hooks/run_guard.ps1`, and the
    `.cursor/rules/*.mdc` skill copies.
  - Kept: `.cursor/**` in `sandbox.protected`, in the Claude deny list, and in
    the guard's `ALWAYS_DENY`. A Cursor config can only reappear through a
    reviewed path.
  - Doctor no longer checks a Cursor adapter. The interpreter WARN from the
    prompt now applies to the Copilot adapter.
  - Re-running the Tāniko skills installer will recreate `.cursor/rules/`;
    delete it again or install without the Cursor target.
- **Delta:** opening this repo in Cursor now gets no hook enforcement. The C2
  exit criterion "Cursor launcher runs on macOS" is replaced by "Cursor
  removed, recorded here".

### Copilot adapter

- **Source:** GitHub Copilot hooks reference,
  https://docs.github.com/en/copilot/reference/hooks-reference (read
  2026-11-19).
  - Repository hook files: `.github/hooks/*.json`, format
    `{"version": 1, "hooks": {"preToolUse": [{"type": "command", "bash": ...}]}}`.
  - camelCase `preToolUse` payload: `{sessionId, timestamp, cwd, toolName,
    toolArgs}`, where `toolArgs` is typed `unknown`.
  - PascalCase `PreToolUse` payload: `{hook_event_name, session_id, cwd,
    tool_name, tool_input}` with Claude tool names (`apply_patch` → `Edit`,
    `bash` → `Bash`).
  - Decision: top-level `permissionDecision` (`allow`/`deny`/`ask`) plus
    `permissionDecisionReason`, required on deny.
  - Command hooks fail closed on a crash or any non-zero exit, including 2.
    **Timeouts fail open.**
- **Needed:** Copilot sessions on this repo run the same guard, fail-closed.
- **Offered:** Phase 4 had no Copilot adapter. The guard read only
  `tool_input` objects, so every camelCase Copilot call (including
  `apply_patch` raw text) was allowed. Deny output had no top-level
  `permissionDecision`.
- **Implemented:**
  - `.github/hooks/tamper-guard.json`: one `preToolUse` command entry,
    `python3 .claude/hooks/tamper_guard.py`, `cwd` `.`, `timeoutSec` 30, no
    matcher (every tool). Covered by `.github/**` in `sandbox.protected`, and
    `.github/hooks/**` is added to the guard's `ALWAYS_DENY`.
  - Guard:
    - reads `toolArgs` / `tool_input` as an object, JSON text, or raw text;
    - adds `rg` to the read tools;
    - deny output adds top-level `permissionDecision: "deny"` plus a reason,
      and writes the reason to stderr for Claude's exit-2 path.
  - Allow output deliberately never sets `permissionDecision`. `"allow"`
    would skip Copilot's normal permission prompt for every call. A test pins
    this.
  - Doctor `tamper-rules-aligned`: FAIL when no `.github/hooks/*.json`
    `preToolUse` entry runs the guard, and WARN when that entry's interpreter
    is not on PATH, since fail-closed would then deny every tool call.
  - Tests: 51 cases. They add Copilot camelCase payloads (object, JSON-string
    and raw-string `toolArgs`; `create`, `edit`, `str_replace_editor`,
    `apply_patch`, `bash`, `powershell`), PascalCase `Edit` with a raw patch,
    the deny/allow output contract, and the adapter's own `bash` command run
    as Copilot would run it.
    - Red against `f65eba6`'s guard: 12 failures out of 51.
    - Green: 51/51 on Python 3.12 and on macOS `/usr/bin/python3` 3.9.6
      (the interpreter the app's hook PATH resolves).
- **Delta:**
  - Bash-only adapter. Copilot on Windows would run no hook. A `powershell`
    entry was left out because the Cursor experience showed stdin forwarding
    under PowerShell can fail closed on every call.
  - Copilot also reads `.claude/settings.json` hooks (PascalCase, matcher
    `Edit|Write|Bash`), so those tools run the guard twice. The result is the
    same and harmless.
  - Repository hooks need workspace trust. A user-level
    `~/.copilot/settings.json` with `disableAllHooks` is outside the repo and
    outside the boundary.

### Which layers enforce on this machine (supersedes the Phase 4 entry)

- **Host:** macOS. No OS sandbox is configured for this repo. Isolation is
  the agent CLI hook layer only.
- **GitHub Copilot (CLI and app sessions):** the `.github/hooks/tamper-guard.json`
  `preToolUse` hook runs the guard for every tool when repository hooks load
  (trusted workspace). The `.claude/settings.json` `PreToolUse` hook also runs
  for `Edit|Write|Bash`. Copilot does not honour Claude `permissions.deny`.
  Live proof is C3.
- **Claude Code:** honours `permissions.deny` and the `PreToolUse` hook if
  used here.
- **Cursor:** unsupported (see above). No adapter.
- **CI:** honours none of the hook layers. It runs the guard tests as a step,
  then doctor and conformance.

### Bypass routes that remain open (updated)

- Everything listed under C1 still applies.
- A guard that hangs past `timeoutSec` lets the tool call through (Copilot
  timeouts fail open).
- Long free-text arguments (subagent prompts, memory citations) are walked as
  strings. A string that is exactly a guarded path makes an unknown tool deny
  — a false positive, which fails closed.

## Correction C3 — Live proof of the Copilot adapter

### The hook loads and denies in a GitHub Copilot app session

- **Needed:** evidence that `.github/hooks/tamper-guard.json` fires in a real
  Copilot session, not only in the guard's subprocess tests (C2).
- **Offered:** C2 proved the guard against recorded payloads. Nothing had
  driven the agent CLI itself.
- **Implemented:** probes run from a Copilot app session (in-place checkout,
  branch `taniko/harness-loop`, HEAD `3d69f6f`, macOS `/usr/bin/python3`
  3.9.6) on 2026-11-19. Each probe was chosen to change nothing if the hook
  failed to load: the edits used an `old_str` that does not exist, and the
  shell probe only reads.

  | Probe | Tool | Result |
  |---|---|---|
  | edit `bin/harness` | `edit` | Denied: `refusing mutation bin/harness (matches sandbox glob 'bin/**')` |
  | `sed -n 1p bin/harness` | `bash` | Denied: `refusing shell segment 'sed -n 1p bin/harness' targets bin/harness` |
  | edit `.github/hooks/tamper-guard.json` | `edit` | Denied: `matches sandbox glob '.github/**'` |
  | `ls bin/harness` (control) | `bash` | Allowed |
  | edit `notes.md` (control) | `edit` | Allowed through the hook; the tool then reported no change |

  Every deny came back as `Denied by preToolUse hook: tamper_guard: ...`, so
  the denials came from the repository hook, not a Claude deny rule.
  `git status` was clean afterwards, and `python3 bin/harness verify` gave
  VERDICT: PASS.
- **Delta / untested:**
  - `apply_patch` was not probed; this app session has no such tool.
  - Redirect writes (`cat notes.md > bin/harness`) were not probed live; if
    the hook had not loaded, they would have overwritten the file. They
    remain covered only by the C1/C2 tests.
  - The fail-open timeout and the Claude `PreToolUse` double-run were not
    exercised.
- **Lesson:** design live tamper probes so that a missing hook leaves nothing
  changed. Then a pass shows the hook works, and a failure costs nothing.

### `docs/**` was read-only, so the agent could not record strain

- **Needed:** agents append what they run into, and the lessons learned, to
  this file.
- **Offered:** Phase 1 declared `docs/**` in `sandbox.read_only`, and
  `AGENTS.md` repeated it. The guard denies every path that matches
  `protected` or `read_only`, so this file could not be written. The C3
  results had to be reported in chat instead.
- **Implemented (operator change, commit `708d371`):**
  - `.claude/harness.json`: `docs/**` moved from `read_only` to `writable`.
    `read_only` is now `["README.md"]`.
  - `.claude/settings.json`: dropped the `docs/**` deny entries and added
    allow entries for `docs/taniko/STRAIN.md`.
  - `AGENTS.md`: Scope now allows appending to `STRAIN.md`, and a new
    *Recording strain* section sets the rules: append only, Needed /
    Offered / Implemented / Delta, cite evidence, record lessons.
  - Doctor `tamper-rules-aligned` PASS. A no-op edit probe on this file
    passed the hook.
  - Getting there took three tries. The first moved `docs/**` into
    `protected`, which locked the file more tightly, and left a trailing
    comma that made `.claude/settings.json` invalid JSON. The second emptied
    the `AGENTS.md` Scope section. Doctor caught the JSON error, and the
    no-op probe and a re-read caught the other two.
- **Delta:**
  - The guard ignores `sandbox.writable` and cannot carve an exception out of
    a protected glob. A single writable file therefore means unlocking its
    whole glob: the agent can now write any file under `docs/`, not only
    `STRAIN.md`.
  - Nothing enforces append-only. Review each commit's diff of this file.
  - The agent being verified now writes part of its own record, so its
    self-reports need checking against evidence.
- **Lesson:** decide early which records the agent must write and declare
  them writable. A blanket read-only glob silently blocks the feedback loop.

### Attempt budget exhaustion blocked this entry

- **Needed:** the agent writes this entry once C3 completes.
- **Offered:** the ledger counts one attempt per distinct working-tree state
  per HEAD; re-verifying an unchanged tree reuses its attempt. The ledger for
  `3d69f6f` held three:
  1. a pass at 01:13Z, from before the C3 session;
  2. a fail at 01:13Z on a deliberately broken `index.html` (text after
     `</html>`). This looks like the conformance suite's destructive probe,
     which spends an attempt on every HEAD in the ledger (`46ddadb`,
     `f65eba6`, `3d69f6f`);
  3. a pass at 02:15Z: the agent re-verified after the operator's
     uncommitted harness edits, which changed the tree.

  The agent's first C3 verify (01:56Z) reused attempt 1. The append was then
  denied: `tamper_guard: BUDGET EXHAUSTED (3 of 3 attempts used): stop and
  escalate. Human reset: delete .agent/verify/attempts/<HEAD>.json`.
- **Implemented:** the agent did not reset its own budget. It escalated, and
  the operator committed the harness change (`708d371`), which started a
  fresh ledger.
- **Delta:**
  - The soft halt checks no path. It denied every write tool, including
    `create` on a draft in the session folder outside the repository.
  - Harness edits spend the deck author's budget, because the ledger counts
    any tree change.
  - The suite's destructive probe leaves one fewer attempt for the author
    on every HEAD.
  - The halt blocks strain recording at the moment the agent hits the
    limit, so the record of that strain cannot be written then.
- **Lesson:** after a harness-only change, check it with doctor rather than
  a full verify, or commit it first. Consider exempting `STRAIN.md` appends
  from the halt, and keeping the suite's probe out of the author's ledger.

### Smaller observations

- **Reader allowlist false positive:** `python3 -m json.tool
  .claude/settings.json >/dev/null`, a read-only JSON check, was denied
  because `python3 -m` is not on the reader list. This fails closed as
  designed. `python3 bin/harness doctor` is the allowed way to validate
  settings.
- **Doctor python3 FAIL:** still fails on `/usr/bin/python3` 3.9.6, as noted
  in C0. Not new.

## Prompt 2a Phase 0 — Graph foundations setup

### Phase 0 conformance failed on interpreter, not declaration — `file-against-taniko`

- **Needed:** `python3 ../taniko/conformance/run.py --repo . --tiers static`
  to judge the declaration.
- **Offered:** `decl-present-valid` imports `jsonschema`
  (`conformance/checks.py:105`) and reports a missing import as a FAIL:
  5 pass / 1 fail / 1 skip, NONCONFORMANT. `python3` on PATH was
  `/usr/bin/python3` 3.9.6, below the declared `>=3.10`, with no jsonschema;
  Homebrew 3.12/3.13/3.14 also lacked it.
- **Implemented:** venv at `~/.venvs/taniko` (Python 3.12.7, jsonschema
  4.26.0), put first on PATH per command. Result: 6 pass / 0 fail / 1 skip,
  CONFORMANT. No repo files changed.
- **Delta:** a missing suite dependency is a suite error (exit 2), not a
  conformance failure attributed to the adopter. Same class as the Phase 0
  Windows `python3` entry.
- **Lesson:** the gate environment is part of Phase 0; record which
  interpreter ran each gate.

### `PROGRESS.md` was assumed by the prompt but never created — `file-against-taniko`

- **Needed:** Prompt 2a's re-issue rule reads `docs/taniko/PROGRESS.md` to
  pick the phase.
- **Offered:** Prompt 1 never produced it; the rules file permitted only
  `STRAIN.md` appends.
- **Implemented:** reconstructed Prompt 1 entries from commits `df68d7c`..
  `b4127a0`; the operator added `PROGRESS.md` to the rules file's append
  scope. The file is an append-only log. The first draft was a mutable
  status table, which contradicted append-only; it was replaced before
  its first commit.
- **Delta:** the progress file is a cross-prompt contract with no producer
  in Prompt 1. Name it as a Prompt 1 deliverable.
- **Lesson:** a rule that gates a session must have a phase that creates
  its input.

### No writable home for graph code — `file-against-taniko`

- **Needed:** a location for the appender, worktree runner, and their tests.
- **Offered:** `sandbox.writable` covered deck content and `docs/**` only;
  `bin/**` (the verifier) is protected. CONTRACTS §1 says the engine should
  be a pinned dependency, not vendored code.
- **Implemented:** the operator added `graph/**` to `sandbox.writable` and
  to the rules file. Graph code lives in-repo; run evidence goes under
  `.agent/graph/<run-id>/` (gitignored, per EVIDENCE-LAYOUT).
- **Delta:** building the graph layer in the adopting repo contradicts the
  "engine is a pinned dependency" placement rule; the suite ships no graph
  engine at v0.4.0 to pin.
- **Lesson:** decide placement before Phase 1, in a protected-file change
  the operator makes.

### Graph tests need a tier adapter; plain `unittest` does not satisfy the contract

- **Needed:** graph tests counted by `verify`, so they are evidence.
- **Offered:** `bin/harness` treats a tier that exits without writing a
  `$KC_TIER_RESULT` record as error, so `python3 -m unittest discover`
  cannot be a tier directly.
- **Implemented:** the agent drafted `bin/tier-graph` in the session folder;
  the operator installed it (byte-identical, `diff` clean) and declared tier
  `graph` (`cost_class: unit`). Smoke-tested outside the repo on throwaway
  fixtures: missing `graph/tests` → error/2; 0 tests → error/2; import
  error → error/2; 1 failing of 2 → fail/1; 1 passing → pass/0.
- **Delta:** the CI comment at `.github/workflows/taniko.yml:41` keeps
  boundary-machinery tests (the guard's) out of verify. The graph tier is a
  deliberate exception: these tests gate agent-produced work. Untested: the
  tier inside a full `verify` run (deferred; see next entry).
- **Lesson:** a new tier ships with its adapter and a refusal for zero
  executed tests, or it passes vacuously.

### Full verify deferred to protect the attempt budget

- **Needed:** a full `verify` after declaring the graph tier.
- **Offered:** the ledger for `b4127a0` already held 2 attempts (earlier
  verifies on changed trees); a third would exhaust it before the setup was
  committed. Separately, the tier reports error until `graph/tests` exists.
- **Implemented:** checked with static conformance only; full verify left
  to Phase 1, on the new commit's fresh ledger.
- **Delta:** same as C3: operator harness edits spend the author's budget.
- **Lesson:** commit harness changes before verifying, then verify once.

### Tamper guard false positives on non-writing shell commands — `file-against-taniko`

- **Needed:** read and execute protected files, and write prose that names
  them, without writing the protected files.
- **Offered:** the Copilot preToolUse guard denied all four:
  - `grep -n -i "attempt\|budget" bin/harness`: `refusing shell segment
    'budget" bin/harness' targets bin/harness`. The `\|` inside quotes was
    split as a pipe.
  - `KC_TIER_RESULT=/tmp/kc_r.json python3 bin/tier-graph`: denied as
    targeting `bin/tier-graph`.
  - `python3 bin/tier-graph`: denied likewise. `python3 bin/harness verify`
    is allowed, so executing `bin/**` is allowlisted per command, not judged
    by read/write intent.
  - `cat >> docs/taniko/STRAIN.md <<'EOF' … EOF`: `refusing shell segment
    'AGENTS.md' targets AGENTS.md`. A file name inside heredoc text was
    treated as a write target.
- **Implemented:** used the grep tool for reads and the edit tool for this
  append; did not run the tier directly. `verify` still runs it as a child
  process, which the guard does not see.
- **Delta:** the segment splitter ignores shell quoting and heredoc bodies,
  and executing a protected script counts as writing it. Fails closed, as
  designed, but blocks legitimate inspection.
- **Lesson:** inspect protected files with non-shell read tools, write docs
  with the edit tool, and exercise tiers only through `verify`.

## Prompt 2a Phase 1 — Routing log appender

Code commit `518fe76`. Red `vr_047ac4d82fa5` (graph FAIL, 18 run) → green
`vr_3c60319d8ee6` (graph PASS, 18 run, 0 failed). Toy log: loglint PASS,
12 records; schema 12 of 12 valid.

### tier-graph reports more failures than tests run

- **Needed:** a red verify whose counts are a coherent denominator.
- **Offered:** `graph FAIL — 18 run, 25 failed`; summary "25 of 18 graph
  tests did not pass". `unittest` counts `testsRun` per method but one
  failure per failing `subTest` (two tests carry 3 + 7 subtests).
- **Implemented:** nothing; `bin/tier-graph` is protected. Counts read as
  "18 methods run; 25 failing cases".
- **Delta:** numerator and denominator count different units.
- **Lesson:** a tier that uses `subTest` must count subtests in both
  numbers, or neither. Operator fix in `bin/tier-graph`, not a suite issue.

### Red evidence cites only 20 of 25 failures

- **Needed:** the red document to cite every new test that bit.
- **Offered:** `feedback.locations` is capped at 20; the raw tier log
  (`verify/logs/vr_047ac4d82fa5-graph.log`) is the tier's 8-line stdout,
  not the unittest output. 5 failing cases (among them, by elimination,
  `test_reopen_rejects_seq_gap`, `test_second_writer_rejected`,
  `test_reopen_rejects_other_run_id`, `test_reopen_continues_seq_and_bracket_state`,
  `test_toy_log_passes_loglint`) are not named in any artifact.
- **Implemented:** listed the cited cases in PROGRESS; the uncited five are
  claimed failing by reasoning about the skeleton, not by artifact —
  **untested** as evidence.
- **Delta:** red→green for those five rests on narrative.
- **Lesson:** the tier should keep the full runner output in its raw log.
  Operator fix in `bin/tier-graph`.

### loglint says "evidence resolves" after checking zero refs — `file-against-taniko`

- **Needed:** a denominator on every lint claim (validate-run rule 5).
- **Offered:** v0.4.0 `loglint.py` without `--evidence-dir` prints
  `LOGLINT PASS (grammar 0.1): 12 records, brackets balanced, evidence resolves`;
  G8 is skipped entirely and the toy log has 0 `verify_ref`s. The
  taniko-validate-run skill names this exact message as a past defect.
- **Implemented:** PROGRESS states G8 checked 0 of 0.
- **Delta:** the pinned lint still prints the vacuous claim.
- **Lesson:** print "G8 skipped (no --evidence-dir)" or "N of M refs
  resolved"; never the bare phrase.

### loglint does not schema-validate records — `file-against-taniko`

- **Needed:** "a log is conformant only when every record passes the schema
  AND the whole log passes the lint" (routing-log-grammar.md).
- **Offered:** `loglint.py` checks grammar only (schema use is limited to
  G8 verify-result docs). No suite command validates a routing log's
  records against `routing-record.schema.json`.
- **Implemented:** the appender validates each record before writing; the
  12-of-12 count was produced with the appender's validator.
- **Delta:** the half of conformance the grammar calls mandatory has no
  executable form in the suite.
- **Lesson:** loglint (or a sibling) should run the record schema per line.

### `format: date-time` is silently unenforced — `file-against-taniko`

- **Needed:** `at` to be a real RFC 3339 timestamp.
- **Offered:** jsonschema 4.26.0 with `FormatChecker()` accepts
  `"not-a-date"` for `format: date-time` (returns 0 errors) because
  `rfc3339-validator` is not installed; CI installs only `jsonschema`.
- **Implemented:** the appender owns `at`: tz-aware clock required (naive
  clock rejected as G2, tested), formatted as UTC `…%fZ`.
- **Delta:** any consumer relying on the schema for `at` validity gets
  nothing; the suite's own install line (`pip install jsonschema`) doesn't
  pull the format extra.
- **Lesson:** install `jsonschema[format]`, or don't rely on `format`.

### `__pycache__/` not gitignored

- **Needed:** a clean tree after running graph tests.
- **Offered:** `graph/__pycache__/` and `graph/tests/__pycache__/` appear
  untracked; `.gitignore` is protected.
- **Implemented:** staged source files by name; left the caches untracked.
- **Delta:** `git status` is never clean after verify; `git add graph` would
  commit bytecode.
- **Lesson:** operator should add `__pycache__/` to `.gitignore`.

### Scope decisions and what stays untested

- **Needed:** G1–G3 at append time, schema conformance, closed brackets on
  failure.
- **Offered:** the grammar also has G4–G9; `fail` outside a bracket is not
  forbidden by the grammar.
- **Implemented:** G1–G3 plus G4's "nothing after the root exits". `fail` is
  accepted only via the schema; `fail_and_exit()` requires an open bracket.
  G5–G7 and G9-beyond-schema are left to loglint.
- **Delta / untested:** concurrent appends from multiple threads (an
  `RLock` is held, no test); cross-process single-writer (tested only as two
  opens in one process — `flock` is per open file description on macOS and
  Linux, so this should carry, but is unproven); Windows (`fcntl` absent).
- **Lesson:** "enforced by the appender" is bounded by what the tests reach;
  the threading claim is design, not evidence.

## Correction C4 — operator fixes after Prompt 2a Phase 1

Resolves three Prompt 2a Phase 1 entries (above), which stay as written.
Operator-made (protected files); the agent drafted the `tier-graph` patch
and tested it outside the repo.

### tier-graph counts subtests as cases — resolves "tier-graph reports more failures than tests run" and "Red evidence cites only 20 of 25 failures"

- **Needed:** numerator and denominator in one unit; every failing case
  named in an artifact.
- **Offered:** `bin/tier-graph` counted methods run but subtest failures.
- **Implemented:** commit `73def13`. A `TextTestResult` subclass counts each
  subtest as a case in place of its parent method; on fail the full verbose
  runner output goes to stdout (the harness's raw tier log), with a note when
  feedback locations are cut at 20. Smoke test outside the repo, fixture of
  1 passing test, 1 failing test, 1 test with 3 subtests (2 failing):
  `FAIL - 5 cases run (3 tests, 3 subtests), 3 failed`, exit 1, all 3 named
  in the output. In-harness: `vr_c0f7b88716d0` (`mode: real`,
  2026-11-19T18:50:43.395Z, HEAD `0d41757`), graph `PASS - 26 cases run
  (18 tests, 10 subtests), 0 failed, 0 errored, 0 skipped`.
- **Delta:** the denominator unit changed: Phase 1's "18 run" and this "26
  cases" count the same 18 tests. Compare later counts in cases. The raw-log
  fix is **untested in-harness**: no red verify has run since `73def13`.
  The five uncited Phase 1 red failures stay uncited; this doesn't change
  past evidence.
- **Lesson:** fix a tier's counting unit before its numbers become
  history, and note the unit change where the counts are recorded.

### `__pycache__/` ignored — resolves "`__pycache__/` not gitignored"

- **Implemented:** commit `0d41757` adds `__pycache__/` to `.gitignore`.
  `git status --short --ignored` now lists `graph/__pycache__/` and
  `graph/tests/__pycache__/` as ignored (`!!`); the tree is clean.
- **Delta:** none.

### Date-time format enforced in CI and the local gate venv — partially resolves "`format: date-time` is silently unenforced"

- **Implemented:** commit `0d41757`: CI installs
  `'jsonschema[format-nongpl]'` (chosen over `format`, which pulls a
  GPL-licensed package). Local `~/.venvs/taniko` now has
  `rfc3339-validator 0.1.4`; `FormatChecker` there rejects `"not-a-date"`
  ("'not-a-date' is not a 'date-time'").
- **Delta:** the CI change is **untested**: not pushed, no CI run yet. The
  suite-side finding stands (`file-against-taniko`): the suite's only install
  line, its own CI (`../taniko/.github/workflows/gates.yml:18`), is plain
  `pip install jsonschema`, and no suite doc names a format extra.
- **Lesson:** a schema keyword is only enforced if the validator's optional
  extras are installed; pin them where the gate runs, in CI and locally.

## Prompt 2a Phase 2 — Worktree-isolated nodes with disjoint write scopes

Session 2026-11-20, branch `taniko/graph-layer-phase`, base `6215ad5`,
code commit `63fa8ab`. Red `vr_84d2bc330f31`, green `vr_78c14b522d39`
(both `mode: real`, HEAD `6215ad5`).

### loglint G7 is exact-string intersection; prefix and glob overlap pass — `file-against-taniko`

- **Needed:** G7 auditable from the log: sibling spawns with overlapping
  write sets must fail the lint.
- **Offered:** the grammar says "pairwise-disjoint `scope.writes`"; the
  schema types entries as bare strings with no syntax. `loglint.py:94-100`
  intersects the entries as string sets. Probe (a phase log with `nb`'s
  spawn writes edited, `na` = `["docs/a.md"]`, 3 logs):
  `["docs/a.md"]` → `LOGLINT FAIL … G7: spawned siblings 'na' and 'nb' share write scope ['docs/a.md']`;
  `["docs/"]` → `LOGLINT PASS (grammar 0.1): 10 records`;
  `["docs/*.md"]` → `LOGLINT PASS (grammar 0.1): 10 records`.
- **Implemented:** `validate_plan` decides overlap on the declared syntax
  (below), so no plan this layer runs can produce such a log. The lint
  still can't catch one written by anything else.
- **Delta:** with prefix or glob scopes, G7 "auditable from the log alone"
  holds only for identical strings. 1 of 3 overlapping logs caught.
- **Lesson:** a disjointness rule needs a defined entry syntax and an
  overlap relation in the spec; set intersection over strings is only
  correct when every entry is an exact path.

### Decision: write-scope syntax and overlap

- **Needed:** a write-scope syntax and an overlap rule (prompt: implementation
  decision; conservative where undecidable).
- **Offered:** the schema's `scope.writes` is `array of string`, unique
  items, no syntax.
- **Implemented:** `graph/scope.py`. Repo-relative POSIX entries: exact path
  (`docs/a.md`), directory prefix (`docs/`, trailing slash), glob (`*`, `?`
  within a segment; `**` as a whole segment spans any depth). Rejected:
  empty, absolute, `.`/`..`/empty segments, backslashes, `[...]` classes,
  `**` inside a segment, a glob ending in `/` (10 malformed entries tested).
  Overlap is exact for exact/exact, exact/prefix, prefix/prefix and
  exact/glob. For glob/prefix and glob/glob: disjoint only when neither
  literal prefix (text before the first wildcard) is a prefix of the other,
  otherwise overlapping, so `docs/*.md` vs `docs/*.txt` is rejected. That
  pair is disjoint in fact; rejecting it is the conservative choice.
  Overlap compares case-folded text, since this checkout is on APFS
  (case-insensitive) and `docs/A.md` and `docs/a.md` name one file.
  Runtime membership is case-exact, so a write differing only in case
  counts as out of scope. Both directions fail closed. Tests: 9 overlapping
  pairs rejected, 6 disjoint accepted, symmetry over all 15, 10 `covers`
  cases.
- **Delta / untested:** Unicode normalization (NFC vs NFD names on APFS) is
  not handled or tested. The literal-prefix rule can reject disjoint glob
  pairs. Callers must split such scopes or serialize the nodes.
- **Lesson:** "conservative" has to name a direction for each side: plan
  time rejects anything it can't prove disjoint, and runtime rejects any
  write it can't prove is covered.

### Decision: fixture marker name and location

- **Needed:** helpers that refuse any repository without a fixture marker;
  the real repository never carries one.
- **Implemented:** `graph/fence.py`. Marker `.taniko-graph-fixture`, a
  regular file at the **main worktree root**, found through
  `git rev-parse --path-format=absolute --git-common-dir`, so linked
  worktrees of a fixture pass and worktrees of a real repo don't. The
  marker is committed in the fixture, not hidden under `.git/`, so if
  anyone creates it in a real checkout `git status` shows it as untracked.
  Fenced: `fixture_git`, `fixture_commit`, `make_fixture_repo` (which also
  refuses a parent inside this checkout), `StubRunner.check` and
  `StubRunner.run`, and therefore `run_fanout` with the stub, which runs
  `check` before resolving the base or creating anything. Asserted against
  this repository: 5 refusal subtests plus `test_this_repository_carries_no_marker`.
- **Delta:** the marker is visible but not *gated*: the tamper guard
  doesn't list it, so an agent could create one. Operator follow-up: add
  `.taniko-graph-fixture` to `sandbox.protected` in `.claude/harness.json`
  (I may not edit it).
- **Lesson:** a fence marker should be visible in review, and the operator
  should be the only one who can create it.

### Stub mode is not gated at operator level

- **Needed:** "stub mode must be unreachable without operator-level
  configuration."
- **Offered:** no operator-owned config surface I can write. `harness.json`
  is protected and has no graph/runner key.
- **Implemented:** the stub sets `identity` (logged on every enter, e.g.
  `runner: stub-runner (deterministic test stand-in; no agent session)`)
  and refuses non-fixture repos. `run_fanout` has no default runner and
  requires a non-empty `identity`.
- **Delta:** the stub is gated by the fixture fence, which isn't yet
  operator-gated (entry above). `graph/toy.py` (Phase 1) is still a stub
  path anyone can reach (`python3 -m graph.toy`) that writes into the real
  `.agent/graph/`. I didn't change it, because that's outside this phase.
- **Lesson:** I couldn't meet "operator-level" from the agent's side. It
  needs an operator-owned switch, either a protected marker or a
  declaration key.

### Red step: full runner output now in the raw tier log — resolves C4's "untested in-harness"

- **Needed:** confirm the `73def13` raw-log fix on a real red.
- **Offered/Implemented:** red `vr_84d2bc330f31`: `graph FAIL 46 cases run
  (34 tests, 15 subtests), 0 failed, 18 errored`. Feedback lists 5
  locations plus "13 more". The raw log
  `.agent/verify/logs/vr_84d2bc330f31-graph.log` is 288 lines and holds
  the verbose runner output, with all 18 non-passing cases named by
  `ERROR:` lines (13 methods, 5 subtests of
  `test_helpers_refuse_this_repository`).
- **Delta:** red and green denominators differ (46 vs 99). In red, the 13
  `FixtureCase` tests errored in `setUp`, before their subtests ran. Two
  new tests passed in red and so never bit:
  `test_this_repository_carries_no_marker` (a precondition, true before and
  after) and `test_fixture_helper_refuses_parent_inside_checkout` (the
  fixture helper was written as test infrastructure before the red run).
  Skeleton fence raised `NotImplementedError` rather than no-op, so no
  helper could touch the real checkout during red.
  Mutation probes after green (monkeypatched, not committed): `covers`
  always true → 5 failures in `ScopeViolationTest`; `first_overlap` never
  → 1 failure + 8 errors in `ScopeOverlapTest`; ignored files dropped from
  `changed_paths` → 1 failure.
- **Lesson:** when setUp errors, the red count doesn't show how many cases
  the suite will have. Compare red and green by test name, not by count.

### Zero-debris check, in-suite and by snapshot

- **Implemented:** `test_fanout.py` `setUpModule`/`tearDownModule` compare
  `ls .agent/graph/`, `git worktree list --porcelain` and `git branch
  --list` of this checkout and raise if they changed. The manual
  before/after snapshot around the green verify had an empty diff (in
  PROGRESS). `graph/gitcmd.py` strips repo-locating `GIT_*` variables
  (`GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, …) so an inherited
  environment can't redirect a fixture command at the real repo.
- **Delta:** the snapshot includes two Copilot-app worktrees
  (`copilot-prewarm-literate-disco`, `stacy-mclean-nzcs-curly-lamp`). They
  predate this phase and are outside my control. If the app adds or reaps
  one mid-run, the in-suite check gives a false failure. Untested.
- **Lesson:** a debris check on a shared checkout also sees other tools'
  state. It works here only because the window is a few seconds.

### What runtime scope detection does not see

- **Implemented:** changes against the base SHA from `git diff --name-only
  --no-renames <base>` (committed, staged, unstaged, deletions, both sides
  of renames) plus `git ls-files --others` without `--exclude-standard`, so
  ignored files count. Tested: untracked, modified, deleted, ignored, and
  nested-new-directory violations; the sibling stays green.
- **Delta / untested:** writes outside the worktree (absolute paths, `..`,
  symlinks out of the worktree, the main checkout) are not detected. That
  needs process sandboxing, not git. Not detected either: mode-only
  changes when `core.fileMode=false`, and writes into `.git` of the
  worktree. Nodes run sequentially, so concurrency is untested. Worktrees
  aren't reaped (there's no `clean` yet). Fixture worktrees disappear with
  the temp dir, but a real run's would stay.
- **Lesson:** "detected from the worktree's actual changes" covers only
  what git can see. A runner that escapes the worktree needs an OS-level
  sandbox.

### Smaller observations

- The tamper guard denied a read-only `sed -n 80,200p bin/tier-graph`, the
  same false positive as the P2a-0 entry. `view` worked.
- `NodeSpec` has no input artifacts yet, so enters carry no
  `inputs_digest`. The grammar doesn't require one; deferred.
