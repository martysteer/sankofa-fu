"""Datasette plugin: W3C Reconciliation API 0.2 over a sankofa-fu index.
One endpoint per database: /{db}/-/sankofa-fu/reconcile
Protocol layer only — matching lives in sankofa_fu.engine."""
from __future__ import annotations

import json

from datasette import hookimpl
from datasette.utils.asgi import Response

from sankofa_fu.engine import Engine

MAX_BATCH = 50
_engines: dict[str, Engine] = {}


def _engine(datasette, db_name: str) -> Engine:
    if db_name not in _engines:
        db = datasette.get_database(db_name)
        _engines[db_name] = Engine(db.path)
    return _engines[db_name]


def _json(body, status=200):
    return Response.json(body, status=status,
                         headers={"Access-Control-Allow-Origin": "*"})


def _describe(candidate) -> str:
    return " · ".join(
        f"{e.query}→{e.candidate}: {e.detail} ({e.similarity})"
        for e in candidate.evidence) or "exact canonical match"


async def reconcile(request, datasette):
    db_name = request.url_vars["db_name"]
    try:
        engine = _engine(datasette, db_name)
    except ValueError as e:                   # not a sankofa-fu index
        return _json({"error": str(e)}, status=400)

    post = await request.post_vars()
    queries = post.get("queries") or request.args.get("queries")
    extend = post.get("extend") or request.args.get("extend")

    if queries:
        qs = json.loads(queries)
        if len(qs) > MAX_BATCH:
            return _json({"error": f"max {MAX_BATCH} queries per batch"}, 400)
        out = {}
        for qid, q in qs.items():
            limit = min(int(q.get("limit", 5)), 25)
            out[qid] = {"result": [
                {"id": c.id, "name": c.name, "score": c.score,
                 "match": c.match, "description": _describe(c),
                 "type": [{"id": "record", "name": "Catalogue record"}]}
                for c in engine.match(q["query"], limit=limit)]}
        return _json(out)

    if extend:
        return _json(_extend(engine, json.loads(extend)))

    return _json(_manifest(datasette, db_name, engine))


def _extend(engine, payload):
    ids = payload["ids"]
    props = [p["id"] for p in payload["properties"]]
    rows = {}
    ph = ",".join("?" * len(ids))
    for rid, extra in engine.blocker.db.execute(
            f"select id, extra from records where id in ({ph})", ids):
        data = json.loads(extra)
        rows[rid] = {p: [{"str": str(data.get(p, ""))}] for p in props}
    return {"meta": [{"id": p, "name": p} for p in props], "rows": rows}


def _manifest(datasette, db_name, engine):
    base = datasette.setting("base_url").rstrip("/")
    service = f"{base}/{db_name}/-/sankofa-fu/reconcile"
    return {
        "versions": ["0.1", "0.2"],
        "name": engine.cfg.name,
        "identifierSpace": f"{service}/entity/",
        "schemaSpace": f"{service}/schema/",
        "defaultTypes": [{"id": "record", "name": "Catalogue record"}],
        "view": {"url": f"{base}/{db_name}/records/{{{{id}}}}"},
        "suggest": {"entity": {
            "service_url": "", "service_path":
            f"{service}/suggest/entity"}},
        "extend": {"propose_properties": {
            "service_url": "", "service_path":
            f"{service}/properties"}},
    }


async def suggest_entity(request, datasette):
    db_name = request.url_vars["db_name"]
    engine = _engine(datasette, db_name)
    prefix = request.args.get("prefix", "")
    rows = engine.blocker.db.execute(
        "select id, raw_code from records where canonical like ? limit 10",
        (f"{prefix.upper()}%",))
    return _json({"result": [{"id": r[0], "name": r[1]} for r in rows]})


async def properties(request, datasette):
    db_name = request.url_vars["db_name"]
    engine = _engine(datasette, db_name)
    return _json({"properties": [
        {"id": c, "name": c} for c in engine.cfg.description_columns]})


@hookimpl
def register_routes():
    return [
        (r"^/(?P<db_name>[^/]+)/-/sankofa-fu/reconcile$", reconcile),
        (r"^/(?P<db_name>[^/]+)/-/sankofa-fu/reconcile/suggest/entity$",
         suggest_entity),
        (r"^/(?P<db_name>[^/]+)/-/sankofa-fu/reconcile/properties$",
         properties),
    ]
