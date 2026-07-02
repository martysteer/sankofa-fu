"""Scheme registry. A scheme provides tokenise() and may override
per-component scoring rules (spec §3.3). Future: dewey, lc, lccn, oclc."""
from . import archival
from .isbn import _IsbnScheme, _IssnScheme


class _Raw:
    @staticmethod
    def tokenise(canonical):
        from ..grammar import Component
        return [Component("RAW", canonical)]


SCHEMES = {"archival": archival, "raw": _Raw,
           "isbn": _IsbnScheme, "issn": _IssnScheme}
