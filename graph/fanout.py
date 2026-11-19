"""One fan-out of worktree-isolated nodes with disjoint write scopes.

Order of operations (each step before anything stateful):
  1. validate_plan  - ids, scope syntax, pairwise-disjoint sibling writes (G7)
  2. runner.check   - the runner's own precondition (the stub requires a fixture)
  3. resolve base   - to a 40-hex SHA, once; every worktree uses that SHA
  4. run directory  - <state-dir>/graph/<run-id>/, refused if it already exists
Only then are worktrees created, under <run-dir>/worktrees/<node-id>.

A node fails on runner error/non-zero exit (runner_failure) or on any change
outside its scope.writes (scope_violation), detected from the worktree's
actual changes against the base SHA. Every failure closes its bracket via
RoutingLog.fail_and_exit. Join is all-of; nodes run sequentially, so there
are no stragglers.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

from graph.routing_log import RoutingLog, utc_now
from graph.scope import ScopeError, covers, first_overlap, parse_entry
from graph.worktree import add_worktree, changed_paths, resolve_sha

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class PlanError(ValueError):
    """`rule` is 'G7' (overlapping sibling writes), 'scope' (malformed entry) or 'plan'."""

    def __init__(self, rule, message):
        super().__init__(f"{rule}: {message}")
        self.rule = rule


@dataclass
class NodeSpec:
    id: str
    writes: list
    reads: list = field(default_factory=list)


@dataclass
class Plan:
    fanout_id: str
    nodes: list


@dataclass
class NodeResult:
    id: str
    ok: bool
    failure_kind: str = None
    detail: str = ""
    changed: list = field(default_factory=list)
    out_of_scope: list = field(default_factory=list)


@dataclass
class RunResult:
    run_id: str
    run_dir: Path
    base_sha: str
    ok: bool
    nodes: dict


def validate_plan(plan):
    if not plan.nodes:
        raise PlanError("plan", "a fan-out needs at least one node")
    ids = [plan.fanout_id] + [n.id for n in plan.nodes]
    for nid in ids:
        if not isinstance(nid, str) or not SAFE_ID.match(nid):
            raise PlanError("plan", f"node id {nid!r} must match {SAFE_ID.pattern}")
    if len(set(ids)) != len(ids):
        raise PlanError("plan", f"node ids must be unique, including the fan-out id: {ids}")
    for node in plan.nodes:
        for kind, entries in (("writes", node.writes), ("reads", node.reads)):
            if len(set(entries)) != len(entries):
                raise PlanError("scope", f"{node.id}.{kind} has duplicate entries")
            for entry in entries:
                try:
                    parse_entry(entry)
                except ScopeError as e:
                    raise PlanError("scope", f"{node.id}.{kind}: {e}") from None
    for i, a in enumerate(plan.nodes):
        for b in plan.nodes[i + 1:]:
            clash = first_overlap(a.writes, b.writes)
            if clash:
                raise PlanError("G7", f"siblings '{a.id}' and '{b.id}' have overlapping writes "
                                      f"{clash[0]!r} and {clash[1]!r}; serialize them or split the scope")


def _scope(node):
    scope = {"writes": list(node.writes)}
    if node.reads:
        scope["reads"] = list(node.reads)
    return scope


def _short(paths, limit=10):
    shown = ", ".join(paths[:limit])
    return shown + (f" (+{len(paths) - limit} more)" if len(paths) > limit else "")


def _run_node(log, repo, run_dir, node, base_sha, runner):
    checkpoint = {"id": "base", "git_ref": base_sha}
    log.append(node.id, "model", "enter", role="producer", checkpoint=checkpoint, scope=_scope(node),
               detail=f"runner: {runner.identity}")
    try:
        worktree = add_worktree(repo, run_dir / "worktrees" / node.id, base_sha)
    except Exception as e:  # noqa: BLE001
        detail = f"worktree: {e}"
        log.fail_and_exit(node.id, "model", detail, failure_kind="infra")
        return NodeResult(node.id, False, "infra", detail)
    try:
        code, said = runner.run(node, worktree)
    except Exception as e:  # noqa: BLE001
        code, said = None, f"{type(e).__name__}: {e}"
    if code != 0:
        detail = f"runner exited {code}: {said}"
        log.fail_and_exit(node.id, "model", detail, failure_kind="runner_failure")
        return NodeResult(node.id, False, "runner_failure", detail)
    changed = changed_paths(worktree, base_sha)
    outside = [p for p in changed if not covers(node.writes, p)]
    if outside:
        detail = f"wrote outside scope.writes {node.writes}: {_short(outside)}"
        log.fail_and_exit(node.id, "model", detail, failure_kind="scope_violation")
        return NodeResult(node.id, False, "scope_violation", detail, changed, outside)
    detail = f"ok: {len(changed)} path(s) changed within scope: {_short(changed)}"
    log.append(node.id, "model", "exit", detail=detail[:1000])
    return NodeResult(node.id, True, None, detail, changed)


def run_fanout(repo, plan, *, base, run_id, state_dir, runner, clock=utc_now):
    validate_plan(plan)
    if not isinstance(run_id, str) or not SAFE_ID.match(run_id):
        raise PlanError("plan", f"run id {run_id!r} must match {SAFE_ID.pattern}")
    identity = getattr(runner, "identity", None)
    if not isinstance(identity, str) or not identity:
        raise PlanError("plan", "runner must self-identify with a non-empty `identity`")
    check = getattr(runner, "check", None)
    if check is not None:
        check(repo)
    repo = Path(repo)
    base_sha = resolve_sha(repo, base)
    run_dir = Path(state_dir) / "graph" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    fan = plan.fanout_id
    results = {}
    with RoutingLog(run_dir / "routing.jsonl", run_id, clock=clock) as log:
        log.append(fan, "fanout", "enter", checkpoint={"id": "base", "git_ref": base_sha},
                   detail=f"fan-out of {len(plan.nodes)} node(s), join all-of; runner: {identity}")
        try:
            for node in plan.nodes:
                log.append(node.id, "model", "spawn", parent_node_id=fan, scope=_scope(node))
            for node in plan.nodes:
                results[node.id] = _run_node(log, repo, run_dir, node, base_sha, runner)
            failed = [r for r in results.values() if not r.ok]
            ok = not failed
            log.append(f"{fan}-join", "join", "join",
                       detail=f"all-of: {len(results) - len(failed)} of {len(results)} node(s) succeeded")
            reason = "all nodes succeeded within scope" if ok else \
                "; ".join(f"{r.id} {r.failure_kind}" for r in failed)
            log.append(fan, "fanout", "route", decision={
                "edge_taken": "integrate" if ok else "escalate", "reason": reason[:500],
                "alternatives": ["escalate" if ok else "integrate"]})
            if not ok:
                log.append("operator", "human", "escalate", failure_kind=failed[0].failure_kind,
                           detail=f"run {run_id} escalated: {reason}"[:1000])
            log.append(fan, "fanout", "exit",
                       detail=("run ok" if ok else f"run failed: {reason}")[:1000])
        except BaseException as e:
            if fan in log.open_nodes:
                for nid in sorted(log.open_nodes - {fan}):
                    log.fail_and_exit(nid, "model", f"aborted: {type(e).__name__}", failure_kind="infra")
                log.fail_and_exit(fan, "fanout", f"{type(e).__name__}: {e}", failure_kind="infra")
            raise
    return RunResult(run_id, run_dir, base_sha, ok, results)
