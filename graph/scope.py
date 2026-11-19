"""Write-scope entries and the overlap relation that defines fan-out independence (G7).

Syntax (repo-relative POSIX paths):
  docs/a.md     exact file
  docs/         directory prefix: everything below it (trailing slash)
  docs/*.md     glob: `*` and `?` stay within one segment; a `**` segment spans
                zero or more segments. `[...]` classes are not supported.

Overlap is decided exactly for exact/exact, exact/prefix, prefix/prefix and
exact/glob. For glob/prefix and glob/glob it is decided on the literal text
before the first wildcard: if neither literal is a prefix of the other, no
path can match both (disjoint); otherwise they are treated as overlapping,
which is the conservative reading. Overlap compares case-folded text, since
two entries differing only in case name one file on a case-insensitive
filesystem. Runtime membership (`covers`) is case-exact, so a write that
differs from its scope only in case is out of scope - also conservative.
"""
import re
from dataclasses import dataclass

WILD = "*?"


class ScopeError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    text: str
    kind: str      # "exact" | "prefix" | "glob"
    literal: str   # text before the first wildcard (whole text for exact/prefix)


def parse_entry(text):
    if not isinstance(text, str) or not text:
        raise ScopeError(f"empty scope entry {text!r}")
    if "\\" in text or text.startswith("/") or "[" in text or "]" in text:
        raise ScopeError(f"scope entry {text!r}: use repo-relative POSIX paths without [] classes")
    body = text[:-1] if text.endswith("/") else text
    segments = body.split("/")
    for seg in segments:
        if seg in ("", ".", ".."):
            raise ScopeError(f"scope entry {text!r}: empty, '.' or '..' segment")
        if "**" in seg and seg != "**":
            raise ScopeError(f"scope entry {text!r}: '**' must be a whole segment")
    wild = [i for i, ch in enumerate(text) if ch in WILD]
    if wild:
        if text.endswith("/"):
            raise ScopeError(f"scope entry {text!r}: a glob may not end in '/'")
        return Entry(text, "glob", text[:wild[0]])
    return Entry(text, "prefix" if text.endswith("/") else "exact", text)


def _glob_regex(text, flags=0):
    out, segments = [], text.split("/")
    for i, seg in enumerate(segments):
        last = i == len(segments) - 1
        if seg == "**":
            out.append(".*" if last else "(?:[^/]+/)*")
            continue
        out.append("".join("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c) for c in seg))
        if not last:
            out.append("/")
    return re.compile("".join(out), flags)


def _match(entry, path, fold):
    if entry.kind == "exact":
        return entry.text.casefold() == path.casefold() if fold else entry.text == path
    if entry.kind == "prefix":
        return path.casefold().startswith(entry.text.casefold()) if fold else path.startswith(entry.text)
    return _glob_regex(entry.text, re.IGNORECASE if fold else 0).fullmatch(path) is not None


def overlaps(a, b):
    if a.kind == "exact":
        return _match(b, a.text, fold=True)
    if b.kind == "exact":
        return _match(a, b.text, fold=True)
    la, lb = a.literal.casefold(), b.literal.casefold()
    return la.startswith(lb) or lb.startswith(la)


def covers(writes, path):
    return any(_match(parse_entry(w), path, fold=False) for w in writes)


def first_overlap(writes_a, writes_b):
    for wa in writes_a:
        for wb in writes_b:
            if overlaps(parse_entry(wa), parse_entry(wb)):
                return wa, wb
    return None
