"""Generate a toy routing log with the stub runner (no real agent sessions).

Usage: python3 -m graph.toy [--run-id ID] [--state-dir .agent]
Writes <state-dir>/graph/<run-id>/routing.jsonl and prints its path.
"""
import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from graph.routing_log import RoutingLog


def build(path, run_id, git_ref):
    """Two-way fan-out: demoa succeeds, demob's stub runner fails and the run escalates."""
    with RoutingLog(path, run_id) as log:
        checkpoint = {"id": "base", "git_ref": git_ref}
        log.append("graph-root", "fanout", "enter", checkpoint=checkpoint, detail="toy run start (stub runner)")
        log.append("demoa", "model", "spawn", parent_node_id="graph-root",
                   scope={"writes": ["graph/toy-scratch-a.md"]})
        log.append("demob", "model", "spawn", parent_node_id="graph-root",
                   scope={"writes": ["graph/toy-scratch-b.md"]})
        with log.node("demoa", "model", checkpoint=checkpoint, role="producer",
                      scope={"reads": ["index.html"], "writes": ["graph/toy-scratch-a.md"]}):
            pass
        log.append("demob", "model", "enter", checkpoint=checkpoint, role="producer",
                   scope={"reads": ["index.html"], "writes": ["graph/toy-scratch-b.md"]})
        log.fail_and_exit("demob", "model", "stub runner exited 1", failure_kind="runner_failure")
        log.append("join-root", "join", "join", detail="all-of: 1 of 2 succeeded; join fails")
        log.append("graph-root", "fanout", "route",
                   decision={"edge_taken": "escalate", "reason": "demob runner_failure; all-of join unsatisfied",
                             "alternatives": ["integrate"]})
        log.append("operator", "human", "escalate", failure_kind="runner_failure",
                   detail="toy run escalated to operator")
        log.append("graph-root", "fanout", "exit", detail="run failed: demob runner_failure")
    return Path(path)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("toy-%Y%m%d-%H%M%S"))
    ap.add_argument("--state-dir", default=".agent")
    args = ap.parse_args(argv)
    git_ref = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    path = Path(args.state_dir) / "graph" / args.run_id / "routing.jsonl"
    print(build(path, args.run_id, git_ref))
    return 0


if __name__ == "__main__":
    sys.exit(main())
