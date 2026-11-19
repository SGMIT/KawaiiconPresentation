"""Phase 2: worktree-isolated nodes with disjoint write scopes, and test fencing."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from graph.fanout import NodeSpec, Plan, PlanError, run_fanout, validate_plan
from graph.fence import MARKER, FenceError, require_fixture
from graph.routing_log import default_suite_dir
from graph.scope import ScopeError, covers, overlaps, parse_entry
from graph.stub_runner import StubRunner
from graph.tests.fixture import ROOT, fixture_commit, fixture_git, git_state, listing, make_fixture_repo
from graph.worktree import WorktreeError, add_worktree

SHA40 = re.compile(r"^[0-9a-f]{40}$")
_real_before = None


def setUpModule():
    global _real_before
    _real_before = (listing(ROOT / ".agent" / "graph"), git_state(ROOT))


def tearDownModule():
    after = (listing(ROOT / ".agent" / "graph"), git_state(ROOT))
    if after != _real_before:
        raise AssertionError(f"graph tests left debris in the real checkout: before={_real_before!r} after={after!r}")


def records(run_dir):
    text = (Path(run_dir) / "routing.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def events_for(recs, node_id):
    return [r for r in recs if r["node"]["id"] == node_id]


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = make_fixture_repo(self.tmp.name)
        self.state = self.repo / ".agent"

    def tearDown(self):
        self.tmp.cleanup()

    def run_plan(self, plan, runner, run_id="run-p2", base="HEAD"):
        return run_fanout(self.repo, plan, base=base, run_id=run_id, state_dir=self.state, runner=runner)

    def loglint(self, run_dir):
        loglint = default_suite_dir() / "conformance" / "loglint.py"
        proc = subprocess.run([sys.executable, str(loglint), str(Path(run_dir) / "routing.jsonl")],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc.stdout


OVERLAPPING = [
    ("same exact path", ["docs/a.md"], ["docs/a.md"]),
    ("prefix contains exact", ["docs/"], ["docs/a.md"]),
    ("nested prefixes", ["src/"], ["src/lib/"]),
    ("glob matches exact", ["docs/*.md"], ["docs/a.md"]),
    ("globstar matches deep exact", ["src/**"], ["src/lib/deep/z.py"]),
    ("glob vs prefix, undecidable", ["docs/*.md"], ["docs/"]),
    ("glob vs glob, undecidable", ["docs/*.md"], ["docs/*.txt"]),
    ("case-only difference", ["docs/A.md"], ["docs/a.md"]),
    ("one shared entry among many", ["css/x.css", "docs/a.md"], ["src/", "docs/a.md"]),
]

DISJOINT = [
    ("distinct exact paths", ["docs/a.md"], ["docs/b.md"]),
    ("sibling prefixes", ["docs/"], ["src/"]),
    ("prefix is not a string prefix", ["doc/"], ["docs/a.md"]),
    ("glob literal prefixes diverge", ["docs/*.md"], ["src/*.md"]),
    ("glob does not match exact", ["docs/*.md"], ["docs/a.txt"]),
    ("star stays in one segment", ["docs/*.md"], ["docs/sub/a.md"]),
]


class ScopeOverlapTest(FixtureCase):
    def test_sibling_overlap_rejected_before_any_state(self):
        for label, wa, wb in OVERLAPPING:
            with self.subTest(label):
                before = git_state(self.repo)
                plan = Plan("fan", [NodeSpec("na", wa), NodeSpec("nb", wb)])
                runner = StubRunner({"na": {}, "nb": {}})
                with self.assertRaises(PlanError) as cm:
                    self.run_plan(plan, runner)
                self.assertEqual(cm.exception.rule, "G7", str(cm.exception))
                self.assertIn("na", str(cm.exception))
                self.assertIn("nb", str(cm.exception))
                self.assertFalse(self.state.exists(), "no run directory may exist for a rejected plan")
                self.assertEqual(git_state(self.repo), before, "no worktree or branch for a rejected plan")
                self.assertEqual(runner.calls, [], "runner must not run for a rejected plan")

    def test_disjoint_siblings_accepted(self):
        for label, wa, wb in DISJOINT:
            with self.subTest(label):
                validate_plan(Plan("fan", [NodeSpec("na", wa), NodeSpec("nb", wb)]))

    def test_read_overlap_is_not_a_conflict(self):
        validate_plan(Plan("fan", [NodeSpec("na", ["docs/a.md"], reads=["src/"]),
                                   NodeSpec("nb", ["docs/b.md"], reads=["src/"])]))

    def test_malformed_scope_entries_rejected(self):
        for entry in ["", "/etc/passwd", "../x", "docs/../src/x.txt", "./docs/a.md", "docs//a.md",
                      "docs\\a.md", "docs/[ab].md", "src/**x", "docs/**/"]:
            with self.subTest(entry=entry):
                with self.assertRaises(ScopeError):
                    parse_entry(entry)
                with self.assertRaises(PlanError) as cm:
                    validate_plan(Plan("fan", [NodeSpec("na", [entry])]))
                self.assertEqual(cm.exception.rule, "scope")

    def test_overlap_is_symmetric(self):
        for label, wa, wb in OVERLAPPING + DISJOINT:
            with self.subTest(label):
                a, b = parse_entry(wa[-1]), parse_entry(wb[-1])
                self.assertEqual(overlaps(a, b), overlaps(b, a))

    def test_covers_matches_declared_syntax(self):
        cases = [(["docs/a.md"], "docs/a.md", True), (["docs/a.md"], "docs/a.mdx", False),
                 (["docs/"], "docs/sub/z.md", True), (["docs/"], "docsx/z.md", False),
                 (["docs/*.md"], "docs/z.md", True), (["docs/*.md"], "docs/s/z.md", False),
                 (["src/**"], "src/a/b/c.py", True), (["src/**/*.py"], "src/c.py", True),
                 (["docs/?.md"], "docs/ab.md", False), (["docs/A.md"], "docs/a.md", False)]
        for writes, path, expected in cases:
            with self.subTest(writes=writes, path=path):
                self.assertEqual(covers(writes, path), expected)


class WorktreeTest(FixtureCase):
    def test_nodes_run_in_worktrees_at_resolved_sha(self):
        base = fixture_git(self.repo, "rev-parse", "HEAD").stdout.strip()
        branches_before = git_state(self.repo)[1]
        plan = Plan("fan", [NodeSpec("na", ["docs/a.md"]), NodeSpec("nb", ["src/"])])
        result = self.run_plan(plan, StubRunner({"na": {"docs/a.md": "A\n"}, "nb": {"src/new.txt": "n\n"}}))
        self.assertTrue(result.ok, result)
        self.assertEqual(result.base_sha, base)
        self.assertRegex(result.base_sha, SHA40)
        run_dir = self.state / "graph" / "run-p2"
        self.assertEqual(result.run_dir.resolve(), run_dir.resolve())
        for nid in ("na", "nb"):
            wt = run_dir / "worktrees" / nid
            with self.subTest(node=nid):
                self.assertTrue(wt.is_dir())
                self.assertEqual(fixture_git(wt, "rev-parse", "HEAD").stdout.strip(), base)
                self.assertNotEqual(fixture_git(wt, "symbolic-ref", "-q", "HEAD", check=False).returncode, 0,
                                    "node worktrees are detached at a SHA, not on a branch")
        self.assertEqual(git_state(self.repo)[1], branches_before, "no branches are created")
        enters = [r for r in records(run_dir) if r["event"] == "enter"]
        self.assertEqual({r["checkpoint"]["git_ref"] for r in enters}, {base})
        self.assertEqual((run_dir / "worktrees" / "na" / "docs" / "a.md").read_text(), "A\n")
        self.assertEqual((self.repo / "docs" / "a.md").read_text(), "a\n", "the main checkout is untouched")

    def test_symbolic_base_is_resolved_once(self):
        old = fixture_git(self.repo, "rev-parse", "HEAD").stdout.strip()
        fixture_commit(self.repo, "docs/b.md", "moved\n")
        result = self.run_plan(Plan("fan", [NodeSpec("na", ["docs/a.md"])]), StubRunner({"na": {}}), base=old[:12])
        self.assertEqual(result.base_sha, old)

    def test_add_worktree_refuses_unresolved_revs(self):
        sha = fixture_git(self.repo, "rev-parse", "HEAD").stdout.strip()
        for rev in ["HEAD", "main", sha[:12], "refs/heads/main"]:
            with self.subTest(rev=rev):
                with self.assertRaises(WorktreeError):
                    add_worktree(self.repo, self.tmp.name + "/wt-" + rev.replace("/", "_"), rev)
        porcelain = fixture_git(self.repo, "worktree", "list", "--porcelain").stdout
        self.assertEqual([l for l in porcelain.splitlines() if l.startswith("worktree ")],
                         [f"worktree {self.repo.resolve()}"])

    def test_existing_run_dir_refused(self):
        (self.state / "graph" / "run-p2").mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            self.run_plan(Plan("fan", [NodeSpec("na", ["docs/a.md"])]), StubRunner({"na": {}}))


VIOLATIONS = [
    ("new untracked file", {"src/rogue.txt": "r\n"}, "src/rogue.txt"),
    ("modified tracked file", {"docs/b.md": "changed\n"}, "docs/b.md"),
    ("deleted tracked file", {"src/x.txt": None}, "src/x.txt"),
    ("gitignored file", {"build.log": "noise\n"}, "build.log"),
    ("nested new directory", {"docs/sub/deep.md": "d\n"}, "docs/sub/deep.md"),
]


class ScopeViolationTest(FixtureCase):
    def test_out_of_scope_write_fails_node(self):
        for i, (label, rogue, path) in enumerate(VIOLATIONS):
            with self.subTest(label):
                writes = {"docs/a.md": "in scope\n", **rogue}
                run_id = f"viol-{i}"
                plan = Plan("fan", [NodeSpec("na", ["docs/a.md"]), NodeSpec("nb", ["src/y.txt"])])
                result = self.run_plan(plan, StubRunner({"na": writes, "nb": {"src/y.txt": "Y\n"}}), run_id=run_id)
                self.assertFalse(result.ok)
                self.assertEqual(result.nodes["na"].failure_kind, "scope_violation")
                self.assertIn(path, result.nodes["na"].out_of_scope)
                self.assertNotIn("docs/a.md", result.nodes["na"].out_of_scope)
                self.assertTrue(result.nodes["nb"].ok, "a sibling's violation must not fail the sibling")
                recs = records(result.run_dir)
                na = [r["event"] for r in events_for(recs, "na")]
                self.assertEqual(na, ["spawn", "enter", "fail", "exit"])
                fail = next(r for r in recs if r["node"]["id"] == "na" and r["event"] == "fail")
                self.assertEqual(fail["failure_kind"], "scope_violation")
                self.assertIn(path, fail["detail"])
                self.assertEqual(recs[-1]["node"]["id"], "fan")
                self.assertEqual(recs[-1]["event"], "exit")
                route = next(r for r in recs if r["event"] == "route")
                self.assertEqual(route["decision"]["edge_taken"], "escalate")
                self.loglint(result.run_dir)

    def test_runner_failure_closes_bracket(self):
        plan = Plan("fan", [NodeSpec("na", ["docs/a.md"])])
        result = self.run_plan(plan, StubRunner({"na": {"docs/a.md": "x\n"}}, exit_codes={"na": 3}))
        self.assertEqual(result.nodes["na"].failure_kind, "runner_failure")
        na = [r["event"] for r in events_for(records(result.run_dir), "na")]
        self.assertEqual(na, ["spawn", "enter", "fail", "exit"])
        self.loglint(result.run_dir)

    def test_fanout_log_passes_loglint_and_spawns_carry_writes(self):
        plan = Plan("fan", [NodeSpec("na", ["docs/a.md", "docs/*.txt"], reads=["src/"]),
                            NodeSpec("nb", ["src/"])])
        result = self.run_plan(plan, StubRunner({"na": {"docs/a.md": "A\n"}, "nb": {"src/z.txt": "z\n"}}))
        self.assertTrue(result.ok)
        recs = records(result.run_dir)
        spawns = {r["node"]["id"]: r for r in recs if r["event"] == "spawn"}
        self.assertEqual(spawns["na"]["scope"]["writes"], ["docs/a.md", "docs/*.txt"])
        self.assertEqual(spawns["nb"]["scope"]["writes"], ["src/"])
        self.assertEqual({r["parent_node_id"] for r in spawns.values()}, {"fan"})
        self.assertTrue(all("stub" in r.get("detail", "") for r in recs if r["event"] == "enter"),
                        "every enter names the stub runner")
        out = self.loglint(result.run_dir)
        self.assertIn(f"{len(recs)} records", out)


class FenceTest(unittest.TestCase):
    def test_this_repository_carries_no_marker(self):
        self.assertFalse((ROOT / MARKER).exists())

    def test_helpers_refuse_this_repository(self):
        before = (listing(ROOT / ".agent" / "graph"), git_state(ROOT))
        refusals = {
            "require_fixture": lambda: require_fixture(ROOT),
            "fixture_git": lambda: fixture_git(ROOT, "status"),
            "fixture_commit": lambda: fixture_commit(ROOT, "notes.md", "x"),
            "stub runner": lambda: StubRunner({"na": {}}).check(ROOT),
        }
        for label, fn in refusals.items():
            with self.subTest(label):
                with self.assertRaises(FenceError):
                    fn()
        with tempfile.TemporaryDirectory() as tmp, self.subTest("run_fanout with stub runner"):
            with self.assertRaises(FenceError):
                run_fanout(ROOT, Plan("fan", [NodeSpec("na", ["notes.md"])]), base="HEAD", run_id="fence",
                           state_dir=Path(tmp) / "state", runner=StubRunner({"na": {}}))
            self.assertFalse((Path(tmp) / "state").exists())
        self.assertEqual((listing(ROOT / ".agent" / "graph"), git_state(ROOT)), before)

    def test_fixture_helper_refuses_parent_inside_checkout(self):
        with self.assertRaises(RuntimeError):
            make_fixture_repo(ROOT / ".agent")


if __name__ == "__main__":
    unittest.main()
