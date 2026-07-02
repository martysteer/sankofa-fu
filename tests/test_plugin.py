import json
from pathlib import Path
import pytest
from datasette.app import Datasette
from sankofa_fu.config import IndexConfig
from sankofa_fu.index import build_index

FIX = Path(__file__).parent / "fixtures" / "catalogue.csv"
CFG = IndexConfig(name="RM test", code_column="shelfmark",
                  id_column="record_id", description_columns=("title", "date"))

@pytest.fixture
def ds(tmp_path):
    db = tmp_path / "authority.db"
    build_index(FIX, CFG, db)
    return Datasette([str(db)])

@pytest.mark.asyncio
async def test_manifest(ds):
    r = await ds.client.get("/authority/-/sankofa-fu/reconcile")
    assert r.status_code == 200
    m = r.json()
    assert "0.2" in m["versions"]
    assert m["name"] == "RM test"
    assert r.headers["access-control-allow-origin"] == "*"

@pytest.mark.asyncio
async def test_reconcile_exact(ds):
    queries = json.dumps({"q0": {"query": "rm c.801.k.5"}})
    r = await ds.client.post("/authority/-/sankofa-fu/reconcile",
                             data={"queries": queries})
    result = r.json()["q0"]["result"]
    assert result[0]["id"] == "r1"
    assert result[0]["score"] == 100
    assert result[0]["match"] is True

@pytest.mark.asyncio
async def test_reconcile_fuzzy_not_automatch(ds):
    queries = json.dumps({"q0": {"query": "Egetron 3025"}})
    r = await ds.client.post("/authority/-/sankofa-fu/reconcile",
                             data={"queries": queries})
    result = r.json()["q0"]["result"]
    assert result[0]["id"] == "r7"
    assert result[0]["match"] is False
    assert "description" in result[0]        # evidence surfaced

@pytest.mark.asyncio
async def test_batch(ds):
    queries = json.dumps({"q0": {"query": "MS 12345"},
                          "q1": {"query": "MS 12346"}})
    r = await ds.client.post("/authority/-/sankofa-fu/reconcile",
                             data={"queries": queries})
    body = r.json()
    assert body["q0"]["result"][0]["id"] == "r5"
    assert body["q1"]["result"][0]["id"] == "r6"

@pytest.mark.asyncio
async def test_extend(ds):
    payload = json.dumps({"ids": ["r1", "r7"],
                          "properties": [{"id": "title"}]})
    r = await ds.client.post("/authority/-/sankofa-fu/reconcile",
                             data={"extend": payload})
    rows = r.json()["rows"]
    assert rows["r1"]["title"] == [{"str": "Letters of X"}]
    assert rows["r7"]["title"] == [{"str": "Charter"}]

@pytest.mark.asyncio
async def test_suggest_entity(ds):
    r = await ds.client.get(
        "/authority/-/sankofa-fu/reconcile/suggest/entity?prefix=RM C 801")
    names = [e["name"] for e in r.json()["result"]]
    assert any("801.k.5" in n for n in names)
