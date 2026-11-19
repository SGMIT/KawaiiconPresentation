# Kawaiicon 2026 deck — agent instructions

A task is not done until `python3 bin/harness verify` exits 0 (VERDICT: PASS).
Never edit `.claude/`, `bin/`, `.github/`, `AGENTS.md`, `CLAUDE.md`, `TANIKO_VERSION`, or `.gitignore` — they gate your work.

## Scope

- You may edit the deck content only: `index.html`, `css/**`, `assets/**`, `notes.md`, `sources.md`.
- You may edit graph layer code: `graph/**`.
- You may also append to `docs/taniko/STRAIN.md` and `docs/taniko/PROGRESS.md` (see Recording strain).
- `README.md` is read-only.
- The harness declaration is `.claude/harness.json`; session state lives in `.agent/` (gitignored, never commit it).

## Recording strain

- When the harness, the Tāniko suite, or a tool doesn't behave as expected,
  record it in `docs/taniko/STRAIN.md` before you report the task done.
- Append only. Add a new `## Correction Cn — <title>` or `### <finding>` entry
  at the end. Never edit, reorder, or delete existing entries; to correct one,
  add a new entry that names the one it supersedes.
- Each finding uses **Needed / Offered / Implemented / Delta**, cites evidence
  (commit, test counts red → green, exact deny output), and ends with the
  lesson learned.
- Record what you observed, not what you intended. Untested claims are listed
  as untested.
- `STRAIN.md` changes are reviewed in each commit's diff; append-only is not
  enforced by the guard.

## Verification

- `python3 bin/harness verify --quick` runs the static tier only; use it mid-edit. Only a full `verify` pass counts as done.
- Tiers, cheapest first:
  - `static` — `index.html` is well-formed (balanced tags, one `<html>` root, nothing after `</html>`), and every local `href`/`src` in `index.html` and every `url()`/`@import` in `css/` resolves to a file in the repo.
  - `content` — the deck agrees with its own data (see conventions below).
- Remote URLs are never fetched by verify; verdicts must not depend on the network.

## Conventions the content tier depends on

- Every talk slide is a `<section class="talk <theme>">` containing, in order: `p.talk-meta`, `h2` (title), `p.speaker`, the `.cols` block, `p.takeaway`, and `aside.notes`.
- Every speaker on a talk slide has a `#### <title> — <speaker>` entry in `sources.md`.
- Every external link on the Resources slide also appears in `sources.md`. Add the source there first.
- Placeholders such as `[Point]` and `[Action]` are allowed while the deck is in progress.

<!-- taniko-skills-start -->
## Tāniko skills
Read the matching skill before the activity it names. Installed by Tāniko's
install-skills.sh — do not edit between these markers; re-run it to refresh.
- .agents/skills/taniko-validate-run.md — Validate a completed agent run or phase against its evidence before accepting it
- .agents/skills/taniko-review-agent-work.md — Review work an agent claims to have done and correct it so the fix sticks
- .agents/skills/taniko-red-green.md — Enforceable test-first for agent-produced changes
- .agents/skills/taniko-protect-gates.md — Set up and defend tamper isolation
- .agents/skills/taniko-debug-verify-failure.md — Diagnose a failed verify or run from its bounded feedback
<!-- taniko-skills-end -->
