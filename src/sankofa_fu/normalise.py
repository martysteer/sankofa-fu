"""Canonicalisation pipeline (spec §3.1). Order matters:
NFKC → upper → whitespace → delimiters → abbreviations → padding."""
from __future__ import annotations

import re
import unicodedata

from .config import IndexConfig

_WS = re.compile(r"\s+")


def normalise(text: str, cfg: IndexConfig) -> str:
    s = unicodedata.normalize("NFKC", text)
    s = s.upper()                                   # single case; upper keeps Ó
    s = s.replace("\u00a0", " ")
    # interchangeable delimiters -> single space (canonical separator)
    for d in cfg.interchangeable_delimiters:
        if d != " ":
            s = s.replace(d, " ")
    s = _WS.sub(" ", s).strip()
    # abbreviations on word boundaries (keys matched case-insensitively;
    # a trailing "." in input already became a space above)
    for src, dst in cfg.abbreviations.items():
        s = re.sub(rf"\b{re.escape(src.upper())}\b", dst.upper(), s)
    # numeric padding policy on every digit-run
    if cfg.numeric_padding == "strip":
        s = re.sub(r"\b0+(\d)", r"\1", s)
    elif cfg.numeric_padding.startswith("pad:"):
        width = int(cfg.numeric_padding.split(":", 1)[1])
        s = re.sub(r"\d+", lambda m: m.group().zfill(width), s)
    else:
        raise ValueError(f"bad numeric_padding: {cfg.numeric_padding!r}")
    return s
