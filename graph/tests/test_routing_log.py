import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from graph.routing_log import RoutingLog, RoutingLogError, default_suite_dir
from graph import toy

ROOT = Path(__file__).resolve().parents[2]
SHA = "0123456789abcdef0123456789abcdef01234567"


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 11, 20, 0, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        self.now += timedelta(seconds=1)
        return self.now


def lines(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


class RoutingLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "run" / "routing.jsonl"
        self.clock = FakeClock()
        self.log = RoutingLog(self.path, "run-test", clock=self.clock)

    def tearDown(self):
        self.log.close()
        self.tmp.cleanup()

    def enter_root(self):
        return self.log.append("root", "fanout", "enter", checkpoint={"id": "base", "git_ref": SHA})

    def assertRejected(self, rule, fn, *args, **kwargs):
        before = self.path.read_bytes() if self.path.exists() else b""
        seq = self.log.next_seq
        with self.assertRaises(RoutingLogError) as cm:
            fn(*args, **kwargs)
        self.assertEqual(cm.exception.rule, rule, str(cm.exception))
        after = self.path.read_bytes() if self.path.exists() else b""
        self.assertEqual(before, after, "a rejected append must write nothing")
        self.assertEqual(seq, self.log.next_seq, "a rejected append must not consume a seq")

    def test_writer_assigns_dense_seq_and_records_match_file(self):
        self.enter_root()
        self.log.append("a", "code", "enter")
        self.log.append("a", "code", "exit")
        self.log.append("root", "fanout", "exit")
        recs = lines(self.path)
        self.assertEqual([r["seq"] for r in recs], [0, 1, 2, 3])
        self.assertTrue(all(r["run_id"] == "run-test" and r["schema_version"] == "0.4.0" for r in recs))

    def test_rejects_double_close(self):
        self.enter_root()
        self.log.append("a", "code", "enter")
        self.log.append("a", "code", "exit")
        self.assertRejected("G3", self.log.append, "a", "code", "exit")

    def test_rejects_reenter_while_open(self):
        self.enter_root()
        self.log.append("a", "code", "enter")
        self.assertRejected("G3", self.log.append, "a", "code", "enter")

    def test_rejects_exit_without_enter(self):
        self.enter_root()
        self.assertRejected("G3", self.log.append, "never-entered", "code", "exit")

    def test_rejects_caller_supplied_seq(self):
        self.enter_root()
        self.assertRejected("G1", self.log.append, "a", "code", "enter", seq=5)

    def test_rejects_caller_supplied_writer_fields(self):
        self.enter_root()
        for field, value in (("at", "2026-01-01T00:00:00Z"), ("run_id", "other"), ("schema_version", "9.9.9")):
            with self.subTest(field=field):
                self.assertRejected("writer", self.log.append, "a", "code", "enter", **{field: value})

    def test_reopen_rejects_seq_gap(self):
        self.enter_root()
        self.log.close()
        rec = lines(self.path)[0]
        rec["seq"] = 2
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        with self.assertRaises(RoutingLogError) as cm:
            RoutingLog(self.path, "run-test", clock=self.clock)
        self.assertEqual(cm.exception.rule, "G1")

    def test_reopen_continues_seq_and_bracket_state(self):
        self.enter_root()
        self.log.append("a", "code", "enter")
        self.log.close()
        self.log = RoutingLog(self.path, "run-test", clock=self.clock)
        self.assertEqual(self.log.next_seq, 2)
        self.assertEqual(self.log.open_nodes, {"root", "a"})
        self.assertRejected("G3", self.log.append, "a", "code", "enter")
        self.assertEqual(self.log.append("a", "code", "exit")["seq"], 2)

    def test_rejects_time_going_backwards(self):
        self.enter_root()
        self.clock.now -= timedelta(seconds=10)
        self.assertRejected("G2", self.log.append, "a", "code", "enter")

    def test_rejects_naive_clock(self):
        log_path = Path(self.tmp.name) / "naive" / "routing.jsonl"
        with RoutingLog(log_path, "run-naive", clock=lambda: datetime(2026, 11, 20)) as log:
            with self.assertRaises(RoutingLogError) as cm:
                log.append("root", "fanout", "enter", checkpoint={"id": "base", "git_ref": SHA})
            self.assertEqual(cm.exception.rule, "G2")
        self.assertFalse(log_path.exists() and log_path.read_text())

    def test_rejects_schema_invalid_records(self):
        self.enter_root()
        cases = [
            (("a", "wizard", "enter"), {}),
            (("a", "code", "teleport"), {}),
            (("root", "fanout", "route"), {}),
            (("a", "code", "retry"), {}),
            (("a", "model", "spawn"), {}),
            (("a", "model", "enter"), {"checkpoint": {"id": "c", "git_ref": "HEAD"}}),
            (("a", "code", "enter"), {"bogus": 1}),
        ]
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs):
                self.assertRejected("schema", self.log.append, *args, **kwargs)

    def test_append_after_root_exit_rejected(self):
        self.enter_root()
        self.log.append("root", "fanout", "exit")
        self.assertRejected("G4", self.log.append, "late", "code", "enter")

    def test_failure_inside_node_still_closes_bracket(self):
        self.enter_root()
        with self.assertRaises(RuntimeError):
            with self.log.node("a", "code"):
                raise RuntimeError("boom")
        recs = lines(self.path)
        self.assertEqual([(r["node"]["id"], r["event"]) for r in recs[1:]],
                         [("a", "enter"), ("a", "fail"), ("a", "exit")])
        self.assertEqual(recs[2]["failure_kind"], "other")
        self.assertIn("boom", recs[3]["detail"])
        self.assertEqual(self.log.open_nodes, {"root"})

    def test_fail_and_exit_closes_bracket(self):
        self.enter_root()
        self.log.append("a", "code", "enter")
        self.log.fail_and_exit("a", "code", "runner timed out", failure_kind="runner_timeout")
        recs = lines(self.path)
        self.assertEqual([r["event"] for r in recs[-2:]], ["fail", "exit"])
        self.assertEqual(recs[-2]["failure_kind"], "runner_timeout")
        self.assertNotIn("a", self.log.open_nodes)

    def test_fail_and_exit_requires_open_bracket(self):
        self.enter_root()
        self.assertRejected("G3", self.log.fail_and_exit, "ghost", "code", "x")

    def test_second_writer_rejected(self):
        self.enter_root()
        with self.assertRaises(RoutingLogError) as cm:
            RoutingLog(self.path, "run-test", clock=self.clock)
        self.assertEqual(cm.exception.rule, "single-writer")

    def test_reopen_rejects_other_run_id(self):
        self.enter_root()
        self.log.close()
        with self.assertRaises(RoutingLogError) as cm:
            RoutingLog(self.path, "run-other", clock=self.clock)
        self.assertEqual(cm.exception.rule, "writer")


class ToyLogTest(unittest.TestCase):
    def test_toy_log_passes_loglint(self):
        loglint = default_suite_dir() / "conformance" / "loglint.py"
        self.assertTrue(loglint.is_file(), f"pinned suite not found at {loglint}")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "routing.jsonl"
            toy.build(path, "run-toy", SHA)
            recs = lines(path)
            self.assertGreaterEqual(len(recs), 10)
            self.assertIn("fail", [r["event"] for r in recs])
            proc = subprocess.run([sys.executable, str(loglint), str(path)],
                                  capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn(f"LOGLINT PASS (grammar 0.1): {len(recs)} records", proc.stdout)


if __name__ == "__main__":
    unittest.main()
