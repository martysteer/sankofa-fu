"""ISBN/ISSN: validate + canonicalise (spec §3.3). ID components compare
exact-only in scoring: kind 'ID' is not ALPHA and not NUM, so any
mismatch is a kind/value mismatch -> no fuzzing."""
from __future__ import annotations

import re


def _digits(s: str) -> str:
    return re.sub(r"[\s\-]", "", s).upper()


def canonical_isbn(raw: str) -> str:
    d = _digits(raw)
    if len(d) == 10:
        total = sum((10 - i) * (10 if ch == "X" else int(ch))
                    for i, ch in enumerate(d))
        if total % 11 != 0:
            raise ValueError(f"ISBN-10 check digit invalid: {raw!r}")
        core = "978" + d[:9]
        return core + _ean13_check(core)
    if len(d) == 13 and d.isdigit():
        if _ean13_check(d[:12]) != d[12]:
            raise ValueError(f"ISBN-13 check digit invalid: {raw!r}")
        return d
    raise ValueError(f"not an ISBN: {raw!r}")


def _ean13_check(first12: str) -> str:
    s = sum(int(ch) * (1 if i % 2 == 0 else 3)
            for i, ch in enumerate(first12))
    return str((10 - s % 10) % 10)


def canonical_issn(raw: str) -> str:
    d = _digits(raw)
    if len(d) != 8:
        raise ValueError(f"not an ISSN: {raw!r}")
    total = sum((8 - i) * (10 if ch == "X" else int(ch))
                for i, ch in enumerate(d))
    if total % 11 != 0:
        raise ValueError(f"ISSN check digit invalid: {raw!r}")
    return f"{d[:4]}-{d[4:]}"


class _IsbnScheme:
    canonicalise = staticmethod(canonical_isbn)

    @staticmethod
    def tokenise(canonical):
        from ..grammar import Component
        return [Component("ID", canonical)]


class _IssnScheme(_IsbnScheme):
    canonicalise = staticmethod(canonical_issn)
