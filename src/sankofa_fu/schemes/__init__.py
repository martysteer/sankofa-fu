"""Scheme registry. A scheme provides tokenise() and may override
per-component scoring rules (spec §3.3). Future: dewey, lc, lccn, oclc."""
from . import archival


class _Raw:
    @staticmethod
    def tokenise(canonical):
        from ..grammar import Component
        return [Component("RAW", canonical)]


SCHEMES = {"archival": archival, "raw": _Raw}
