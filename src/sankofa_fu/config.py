"""Per-index configuration. JSON round-trip is used to snapshot the
config into the index's meta table so query-time normalisation always
matches index-time (spec §4.3)."""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class IndexConfig:
    name: str
    code_column: str
    id_column: str | None = None
    scheme: str = "archival"
    description_columns: tuple[str, ...] = ()
    abbreviations: dict[str, str] = field(default_factory=dict)
    interchangeable_delimiters: list[str] = field(
        default_factory=lambda: [".", "/", "-", " "])
    numeric_padding: str = "strip"          # "strip" | "pad:N"
    numeric_gate: str = "veto"              # "veto" | "penalty:N"
    weights: dict[str, float] = field(
        default_factory=lambda: {"prefix": 2.0, "alpha": 1.0})
    ocr_confusables: bool = True

    def __post_init__(self):
        object.__setattr__(self, "description_columns",
                           tuple(self.description_columns))

    @classmethod
    def from_dict(cls, d: dict) -> "IndexConfig":
        flat = {k: v for k, v in d.items() if k not in ("normalise", "scoring")}
        flat |= d.get("normalise", {}) | d.get("scoring", {})
        names = {f.name for f in dataclasses.fields(cls)}
        unknown = set(flat) - names
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        return cls(**flat)

    @classmethod
    def from_yaml(cls, path: Path | str) -> "IndexConfig":
        return cls.from_dict(yaml.safe_load(Path(path).read_text()))

    def to_json(self) -> str:
        d = dataclasses.asdict(self)
        d["description_columns"] = list(self.description_columns)
        return json.dumps(d, sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> "IndexConfig":
        return cls(**json.loads(s))
