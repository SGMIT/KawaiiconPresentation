"""Append-only routing log (JSONL) with a single writer assigning seq.

Enforced at append time, not by convention (routing-log grammar 0.1):
  G1  seq is writer-assigned, dense from 0; a reopened log with a gap is refused.
  G2  `at` is writer-assigned from a tz-aware clock and never decreases.
  G3  brackets balance: no exit without enter, no re-enter while open, no double close.
  G4  once the root (first-entered) node exits, the log is concluded.
Every record is validated against the pinned routing-record schema before it
is written. A rejected append writes nothing and consumes no seq.
"""
import contextlib
import fcntl
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_VERSION = "0.4.0"
SCHEMA_ID = f"urn:taniko:schema:routing-record:{SCHEMA_VERSION}"
WRITER_FIELDS = ("schema_version", "run_id", "seq", "at")


class RoutingLogError(ValueError):
    """An append or reopen that would break the log's contract. `rule` is the
    grammar rule (G1..G4), 'schema', 'writer', or 'single-writer'."""

    def __init__(self, rule, message):
        super().__init__(f"{rule}: {message}")
        self.rule = rule


def default_suite_dir():
    env = os.environ.get("TANIKO_DIR")
    return Path(env) if env else Path(__file__).resolve().parents[1].parent / "taniko"


def load_validator(suite_dir=None):
    path = Path(suite_dir or default_suite_dir()) / "schemas" / "routing-record.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    if schema.get("$id") != SCHEMA_ID:
        raise RoutingLogError("schema", f"{path} has $id {schema.get('$id')!r}, expected {SCHEMA_ID!r}")
    return Draft202012Validator(schema, format_checker=FormatChecker())


def utc_now():
    return datetime.now(timezone.utc)


def format_at(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


class RoutingLog:
    """The single writer for one run's routing.jsonl. Holds an exclusive lock
    on the file for its lifetime; a second writer is refused."""

    def __init__(self, path, run_id, clock=utc_now, suite_dir=None):
        self.path = Path(path)
        self.run_id = run_id
        self._clock = clock
        self._validator = load_validator(suite_dir)
        self._mutex = threading.RLock()
        self._seq = 0
        self._last_at = None
        self._open = {}
        self._root = None
        self._concluded = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._file.close()
            raise RoutingLogError("single-writer", f"{self.path} is held by another writer") from None
        try:
            self._replay()
        except Exception:
            self.close()
            raise

    @property
    def next_seq(self):
        return self._seq

    @property
    def open_nodes(self):
        return set(self._open)

    def _replay(self):
        self._file.seek(0)
        for lineno, line in enumerate(self._file.read().splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                raise RoutingLogError("schema", f"line {lineno} is not JSON: {e}") from None
            if record.get("run_id") != self.run_id:
                raise RoutingLogError("writer", f"line {lineno} belongs to run {record.get('run_id')!r}, not {self.run_id!r}")
            if record.get("seq") != self._seq:
                raise RoutingLogError("G1", f"line {lineno} has seq {record.get('seq')!r}, expected {self._seq}")
            self._check(record)
            self._commit(record, parse_at(record["at"]))

    def _check(self, record):
        errors = sorted(self._validator.iter_errors(record), key=lambda e: list(e.path))
        if errors:
            raise RoutingLogError("schema", "; ".join(e.message for e in errors[:3]))
        if self._concluded:
            raise RoutingLogError("G4", f"root '{self._root}' has exited; the log is concluded")
        moment = parse_at(record["at"])
        if self._last_at is not None and moment < self._last_at:
            raise RoutingLogError("G2", f"at {record['at']} precedes previous {format_at(self._last_at)}")
        nid, event = record["node"]["id"], record["event"]
        if event == "enter" and nid in self._open:
            raise RoutingLogError("G3", f"re-enter of '{nid}' while open since seq {self._open[nid]}")
        if event == "exit" and nid not in self._open:
            raise RoutingLogError("G3", f"exit of '{nid}' without an open enter (double close or never entered)")

    def _commit(self, record, moment):
        nid, event = record["node"]["id"], record["event"]
        if event == "enter":
            self._open[nid] = record["seq"]
            if self._root is None:
                self._root = nid
        elif event == "exit":
            del self._open[nid]
            if nid == self._root:
                self._concluded = True
        self._seq += 1
        self._last_at = moment

    def append(self, node_id, node_type, event, role=None, **fields):
        supplied = [f for f in WRITER_FIELDS if f in fields]
        if supplied:
            rule = "G1" if supplied == ["seq"] else "writer"
            raise RoutingLogError(rule, f"{', '.join(supplied)} are assigned by the writer, not the caller")
        node = {"id": node_id, "type": node_type}
        if role is not None:
            node["role"] = role
        with self._mutex:
            if self._file.closed:
                raise RoutingLogError("writer", "log is closed")
            moment = self._clock()
            if not isinstance(moment, datetime) or moment.tzinfo is None:
                raise RoutingLogError("G2", f"clock returned {moment!r}; a tz-aware datetime is required")
            record = {"schema_version": SCHEMA_VERSION, "run_id": self.run_id, "seq": self._seq,
                      "at": format_at(moment), "node": node, "event": event, **fields}
            self._check(record)
            self._file.seek(0, os.SEEK_END)
            self._file.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
            self._file.flush()
            os.fsync(self._file.fileno())
            self._commit(record, moment)
            return record

    def fail_and_exit(self, node_id, node_type, detail, failure_kind="other", **fields):
        """Terminal failure: record the fail, then close the bracket."""
        detail = str(detail)[:1000]
        with self._mutex:
            if node_id not in self._open:
                raise RoutingLogError("G3", f"cannot fail '{node_id}': no open enter")
            self.append(node_id, node_type, "fail", failure_kind=failure_kind, detail=detail, **fields)
            return self.append(node_id, node_type, "exit", detail=f"failed: {detail}"[:1000])

    @contextlib.contextmanager
    def node(self, node_id, node_type, failure_kind="other", **enter_fields):
        """Bracket a node; an exception still closes it (fail, then exit) and re-raises."""
        self.append(node_id, node_type, "enter", **enter_fields)
        try:
            yield self
        except BaseException as e:
            self.fail_and_exit(node_id, node_type, f"{type(e).__name__}: {e}", failure_kind=failure_kind)
            raise
        self.append(node_id, node_type, "exit")

    def close(self):
        if not self._file.closed:
            fcntl.flock(self._file, fcntl.LOCK_UN)
            self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
