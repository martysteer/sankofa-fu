import textwrap
from sankofa_fu.config import IndexConfig

YAML = textwrap.dedent("""\
    name: "RM manuscripts"
    code_column: shelfmark
    scheme: archival
    description_columns: [title, date]
    normalise:
      abbreviations: {"ms": "MS"}
      interchangeable_delimiters: [".", "/", "-", " "]
      numeric_padding: strip
    scoring:
      numeric_gate: veto
      weights: {prefix: 2.0, alpha: 1.0}
""")

def test_load_yaml(tmp_path):
    p = tmp_path / "repo.yaml"
    p.write_text(YAML)
    cfg = IndexConfig.from_yaml(p)
    assert cfg.name == "RM manuscripts"
    assert cfg.code_column == "shelfmark"
    assert cfg.scheme == "archival"
    assert cfg.id_column is None          # default: row number
    assert cfg.abbreviations == {"ms": "MS"}
    assert cfg.interchangeable_delimiters == [".", "/", "-", " "]
    assert cfg.numeric_padding == "strip"
    assert cfg.numeric_gate == "veto"
    assert cfg.weights == {"prefix": 2.0, "alpha": 1.0}

def test_roundtrip_json():
    cfg = IndexConfig(name="x", code_column="c")
    assert IndexConfig.from_json(cfg.to_json()) == cfg

def test_defaults():
    cfg = IndexConfig(name="x", code_column="c")
    assert cfg.scheme == "archival"
    assert cfg.numeric_gate == "veto"
    assert cfg.ocr_confusables is True
