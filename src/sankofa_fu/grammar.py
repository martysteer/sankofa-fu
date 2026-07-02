"""Typed-component tokeniser + scheme registry (spec §3.2–3.3).
Components serialise to JSON arrays like [["ALPHA","RM"],["NUM",801]]
for storage in records.components."""
from __future__ import annotations

import json
from dataclasses import dataclass

from .schemes import SCHEMES


@dataclass(frozen=True)
class Component:
    kind: str          # "ALPHA" | "NUM" | "RAW" | "ID"
    value: str | int


def tokenise(canonical: str, scheme: str) -> list[Component]:
    return SCHEMES[scheme].tokenise(canonical)


def to_json(components: list[Component]) -> str:
    return json.dumps([[c.kind, c.value] for c in components])


def from_json(s: str) -> list[Component]:
    return [Component(k, v) for k, v in json.loads(s)]
