"""Generic archival grammar: split on spaces, parens, and
letter/digit boundaries; digit runs become integer NUM components."""
from __future__ import annotations

import re

_PART = re.compile(r"[A-Z\u00C0-\u024F]+|\d+")


def tokenise(canonical: str):
    from ..grammar import Component
    out = []
    for m in _PART.finditer(canonical):
        tok = m.group()
        if tok.isdigit():
            out.append(Component("NUM", int(tok)))
        else:
            out.append(Component("ALPHA", tok))
    return out
