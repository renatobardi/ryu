"""Testes do ciclo 1 do domínio issues: attachments, subscribers, properties,
reactions, resolve, pins, batch, filtros avançados, busca e metadata KV."""
from __future__ import annotations

import httpx
from .conftest import login


async def _setup(client: httpx.AsyncClient, email: str = "cycle1@ryu.dev"):
    data = await login(client, email)
    ws = data["workspaces"][0]
    return data["user"], ws


async def _create_issue(client, ws_id, title="Issue base", **kw):
    r = await client.post("/api/issues", json={"workspace_id": ws_id, "title": title, **kw})
    assert r.status_code == 201, r.text
    return r.json()


# ── Subscribers ───────────────────────────────────────────────────────
async def test_subscribers_auto_and_manual(client):
    user, ws = await _setup(client)
    issue = await _create_issue(client, ws["id"], "Sub issue")

    r = await client.get(f"/api/issues/{issue['id']}/subscribers")
    assert r.status_code == 200
    subs = r.json()
    assert any(s["user_id"] == user["id"] and s["reason"] == "creator" for s in subs)

    # comentar → commenter (já é subscriber como creator; idempotente)
    r = await client.post(f"/api/issues/{issue['id']}/comments", json={"body": "olá"})
    assert r.status_code == 201

    # unsubscribe / subscribe manual
    r = await client.post(f"/api/issues/{issue['id']}/unsubscribe")
    assert r.status_code == 204
    r = await client.get(f"/api/issues/{issue['id']}/subscribers")
    assert not any(s["user_id"] == user["id"] for s in r.json())
    r = await client.post(f"/api/issues/{issue['id']}/subscribe")
    assert r.status_code == 201
    r = await client.get(f"/api/issues/{issue['id']}/subscribers")
    assert any(s["user_id"] == user["id"] and s["reason"] == "manual" for s in r.json())


async def test_mention_autosubscribe(client):
    user, ws = await _setup(client, "cycle1-mention@ryu.dev")
    # menção ao próprio localpart do email em issue nova criada por "outro" caminho:
    # criador já é subscriber; o que validamos é que o parser roda sem erro e
    # que a menção por localpart resolve o member.
    r = await client.post(
        "/api/issues",
        json={
            "workspace_id": ws["id"],
            "title": "Mention",
            "description": "cc @cycle1-mention e @ninguem_desconhecido",
        },
    )
    assert r.status_code == 201, r.text
    issue = r.json()
    subs = (await client.get(f"/api/issues/{issue['id']}/subscribers")).json()
    assert any(s["user_id"] == user["id"] for s in subs)
    # comentário com menção também roda o parser sem quebrar
    r = await client.post(f"/api/issues/{issue['id']}/comments", json={"body": "olha isso @cycle1-mention"})
    assert r.status_code == 201


# ── Metadata KV ───────────────────────────────────────────────────────
async def test_metadata_limits(client):
    user, ws = await _setup(client)
    issue = await _create_issue(client, ws["id"], "Meta issue")

    r = await client.put(f"/api/issues/{issue['id']}/metadata/pr_number", json={"value": 42})
    assert r.status_code == 200
    assert r.json()["metadata"]["pr_number"] == 42

    # chave inválida
    r = await client.put(f"/api/issues/{issue['id']}/metadata/1bad", json={"value": "x"})
    assert r.status_code == 400
    # valor não-primitivo
    r = await client.put(f"/api/issues/{issue['id']}/metadata/obj", json={"value": {"a": 1}})
    assert r.status_code == 400
    r = await client.put(f"/api/issues/{issue['id']}/metadata/arr", json={"value": [1, 2]})
    assert r.status_code == 400

    # cap de 50 chaves
    for i in range(49):
        r = await client.put(f"/api/issues/{issue['id']}/metadata/k{i}", json={"value": i})
        assert r.status_code == 200, r.text
    r = await client.put(f"/api/issues/{issue['id']}/metadata/overflow", json={"value": 1})
    assert r.status_code == 400

    # delete
    r = await client.delete(f"/api/issues/{issue['id']}/metadata/pr_number")
    assert r.status_code == 200
    assert "pr_number" not in r.json()["metadata"]

    r = await client.get(f"/api/issues/{issue['id']}/metadata")
    assert r.status_code == 200


# ── Propriedades customizadas ─────────────────────────────────────────
async def test_properties_catalog_and_values(client):
    user, ws = await _setup(client)
    issue = await _create_issue(client, ws["id"], "Prop issue")

    r = await client.post(
        "/api/properties",
        json={
            "workspace_id": ws["id"],
            "name": "Ambiente",
            "type": "select",
            "config": {"options": [{"name": "prod"}, {"name": "staging"}]},
        },
    )
    assert r.status_code == 201, r.text
    prop = r.json()
    opt_id = prop["config"]["options"][0]["id"]

    # tipo inválido
    r = await client.post(
        "/api/properties", json={"workspace_id": ws["id"], "name": "X", "type": "banana"}
    )
    assert r.status_code == 400

    # set valor válido / inválido
    r = await client.put(f"/api/issues/{issue['id']}/properties/{prop['id']}", json={"value": opt_id})
    assert r.status_code == 200
    assert r.json()["properties"][prop["id"]] == opt_id
    r = await client.put(f"/api/issues/{issue['id']}/properties/{prop['id']}", json={"value": "nope"})
    assert r.status_code == 400

    # number property
    r = await client.post(
        "/api/properties", json={"workspace_id": ws["id"], "name": "Pontos", "type": "number"}
    )
    num_prop = r.json()
    r = await client.put(f"/api/issues/{issue['id']}/properties/{num_prop['id']}", json={"value": "3"})
    assert r.status_code == 400
    r = await client.put(f"/api/issues/{issue['id']}/properties/{num_prop['id']}", json={"value": 3})
    assert r.status_code == 200

    # listagem / get / archive (nunca deleta)
    r = await client.get("/api/properties", params={"workspace_id": ws["id"]})
    assert len(r.json()) == 2
    r = await client.patch(f"/api/properties/{prop['id']}", json={"archived": True})
    assert r.status_code == 200 and r.json()["archived_at"]
    r = await client.get("/api/properties", params={"workspace_id": ws["id"]})
    assert len(r.json()) == 1
    r = await client.get("/api/properties", params={"workspace_id": ws["id"], "include_archived": "true"})
    assert len(r.json()) == 2
    # propriedade arquivada não aceita valor
    r = await client.put(f"/api/issues/{issue['id']}/properties/{prop['id']}", json={"value": opt_id})
    assert r.status_code == 400

    # delete do valor
    r = await client.delete(f"/api/issues/{issue['id']}/properties/{num_prop['id']}")
    assert r.status_code == 200
    assert num_prop["id"] not in r.json()["properties"]


# ── Reactions ─────────────────────────────────────────────────────────
async def test_reactions_issue_and_comment(client):
    user, ws = await _setup(client)
    issue = await _create_issue(client, ws["id"], "React issue")

    r = await client.post(f"/api/issues/{issue['id']}/reactions", json={"emoji": "🔥"})
    assert r.status_code == 200
    r = await client.post(f"/api/issues/{issue['id']}/reactions", json={"emoji": "🔥"})  # dedup
    reactions = r.json()["reactions"]
    assert len(reactions) == 1 and reactions[0]["count"] == 1

    r = await client.get(f"/api/issues/{issue['id']}")
    assert r.json()["reactions"][0]["emoji"] == "🔥"

    r = await client.delete(f"/api/issues/{issue['id']}/reactions", params={"emoji": "🔥"})
    assert r.json()["reactions"] == []

    # comment reactions
    c = (await client.post(f"/api/issues/{issue['id']}/comments", json={"body": "reagível"})).json()
    r = await client.post(f"/api/issues/comments/{c['id']}/reactions", json={"emoji": "👍"})
    assert r.status_code == 200 and r.json()["reactions"][0]["count"] == 1
    r = await client.get(f"/api/issues/{issue['id']}/comments")
    assert r.json()[0]["reactions"][0]["emoji"] == "👍"
    r = await client.delete(f"/api/issues/comments/{c['id']}/reactions", params={"emoji": "👍"})
    assert r.json()["reactions"] == []


# ── Resolve/unresolve de thread ───────────────────────────────────────
async def test_comment_resolve(client):
    user, ws = await _setup(client)
    issue = await _create_issue(client, ws["id"], "Thread issue")
    root = (await client.post(f"/api/issues/{issue['id']}/comments", json={"body": "raiz"})).json()
    child = (
        await client.post(
            f"/api/issues/{issue['id']}/comments",
            json={"body": "resposta", "parent_comment_id": root["id"]},
        )
    ).json()

    r = await client.post(f"/api/issues/comments/{child['id']}/resolve")
    assert r.status_code == 400  # só raiz

    r = await client.post(f"/api/issues/comments/{root['id']}/resolve")
    assert r.status_code == 200 and r.json()["resolved_at"]
    r = await client.delete(f"/api/issues/comments/{root['id']}/resolve")
    assert r.status_code == 200 and r.json()["resolved_at"] is None


# ── Attachments ───────────────────────────────────────────────────────
async def test_attachments_upload_flow(client):
    user, ws = await _setup(client)
    issue = await _create_issue(client, ws["id"], "Attach issue")

    r = await client.post(
        "/api/upload-file",
        data={"workspace_id": ws["id"], "issue_id": issue["id"]},
        files={"file": ("notes.txt", b"conteudo de teste", "text/plain")},
    )
    assert r.status_code == 201, r.text
    att = r.json()
    assert att["filename"] == "notes.txt" and att["size_bytes"] == 17

    r = await client.get(f"/api/issues/{issue['id']}/attachments")
    assert len(r.json()) == 1

    r = await client.get(f"/api/attachments/{att['id']}")
    assert r.status_code == 200

    r = await client.get(f"/api/attachments/{att['id']}/content")
    assert r.status_code == 200 and r.content == b"conteudo de teste"

    r = await client.get(f"/api/attachments/{att['id']}/download")
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")

    # serve local /uploads/*
    r = await client.get(att["url"])
    assert r.status_code == 200 and r.content == b"conteudo de teste"

    # GC junto com o delete da issue
    r = await client.delete(f"/api/issues/{issue['id']}")
    assert r.status_code == 204
    r = await client.get(f"/api/attachments/{att['id']}")
    assert r.status_code == 404
    r = await client.get(att["url"])
    assert r.status_code == 404


async def test_attachment_delete_endpoint(client):
    user, ws = await _setup(client)
    issue = await _create_issue(client, ws["id"], "Attach del")
    att = (
        await client.post(
            "/api/upload-file",
            data={"workspace_id": ws["id"], "issue_id": issue["id"]},
            files={"file": ("x.bin", b"\x00\x01", "application/octet-stream")},
        )
    ).json()
    r = await client.delete(f"/api/attachments/{att['id']}")
    assert r.status_code == 204
    r = await client.get(f"/api/issues/{issue['id']}/attachments")
    assert r.json() == []


# ── Pins ──────────────────────────────────────────────────────────────
async def test_pins_crud_and_reorder(client):
    user, ws = await _setup(client)
    i1 = await _create_issue(client, ws["id"], "Pin A")
    i2 = await _create_issue(client, ws["id"], "Pin B")

    for i in (i1, i2):
        r = await client.post(
            "/api/pins", json={"workspace_id": ws["id"], "item_type": "issue", "item_id": i["id"]}
        )
        assert r.status_code == 201, r.text

    r = await client.get("/api/pins", params={"workspace_id": ws["id"]})
    pins = r.json()
    assert [p["item_id"] for p in pins] == [i1["id"], i2["id"]]
    assert pins[0]["item"]["key"] == i1["key"]

    r = await client.put(
        "/api/pins/reorder",
        json={
            "workspace_id": ws["id"],
            "items": [
                {"item_type": "issue", "item_id": i2["id"]},
                {"item_type": "issue", "item_id": i1["id"]},
            ],
        },
    )
    assert [p["item_id"] for p in r.json()] == [i2["id"], i1["id"]]

    r = await client.delete(f"/api/pins/issue/{i1['id']}", params={"workspace_id": ws["id"]})
    assert r.status_code == 204
    r = await client.get("/api/pins", params={"workspace_id": ws["id"]})
    assert len(r.json()) == 1

    # tipo inválido
    r = await client.post(
        "/api/pins", json={"workspace_id": ws["id"], "item_type": "banana", "item_id": i2["id"]}
    )
    assert r.status_code == 400


# ── Batch ─────────────────────────────────────────────────────────────
async def test_batch_update_and_delete(client):
    user, ws = await _setup(client)
    issues = [await _create_issue(client, ws["id"], f"Batch {i}") for i in range(3)]
    ids = [i["id"] for i in issues]

    r = await client.post(
        "/api/issues/batch-update",
        json={"workspace_id": ws["id"], "issue_ids": ids, "status": "todo", "priority": "high"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 3
    for item in r.json()["items"]:
        assert item["status"] == "todo" and item["priority"] == "high"

    r = await client.post(
        "/api/issues/batch-delete", json={"workspace_id": ws["id"], "issue_ids": ids[:2]}
    )
    assert r.json()["deleted"] == 2
    r = await client.get(f"/api/issues/{ids[0]}")
    assert r.status_code == 404
    r = await client.get(f"/api/issues/{ids[2]}")
    assert r.status_code == 200


# ── Filtros avançados / paginação / query ─────────────────────────────
async def test_advanced_filters_and_pagination(client):
    user, ws = await _setup(client, "cycle1-filters@ryu.dev")
    a = await _create_issue(client, ws["id"], "Alpha", status="todo", priority="high")
    b = await _create_issue(client, ws["id"], "Beta", status="in_progress", priority="low")
    c = await _create_issue(client, ws["id"], "Gamma", status="done", priority="high")

    # multi-status
    r = await client.get(
        "/api/issues",
        params=[("workspace_id", ws["id"]), ("statuses", "todo"), ("statuses", "in_progress")],
    )
    body = r.json()
    items = body["items"] if isinstance(body, dict) else body
    assert {i["title"] for i in items} == {"Alpha", "Beta"}

    # priorities + open_only
    r = await client.get(
        "/api/issues",
        params=[("workspace_id", ws["id"]), ("priorities", "high"), ("open_only", "true"), ("limit", "10")],
    )
    body = r.json()
    assert [i["title"] for i in body["items"]] == ["Alpha"] and body["total"] == 1

    # sort + paginação
    r = await client.get(
        "/api/issues",
        params=[("workspace_id", ws["id"]), ("sort", "created"), ("direction", "asc"), ("limit", "2"), ("offset", "1")],
    )
    body = r.json()
    assert body["total"] == 3 and [i["title"] for i in body["items"]] == ["Beta", "Gamma"]

    # involves (comentou)
    await client.post(f"/api/issues/{b['id']}/comments", json={"body": "meu envolvimento"})
    r = await client.post(
        "/api/issues/query",
        json={"workspace_id": ws["id"], "involves_user_id": user["id"], "sort": "created"},
    )
    assert r.status_code == 200
    assert {i["title"] for i in r.json()["items"]} == {"Alpha", "Beta", "Gamma"}  # criador de todas

    # POST /query com ids
    r = await client.post(
        "/api/issues/query", json={"workspace_id": ws["id"], "ids": [a["id"], c["id"]]}
    )
    assert {i["id"] for i in r.json()["items"]} == {a["id"], c["id"]}

    # sort por prioridade (urgent→none) e por due_date
    r = await client.get(
        "/api/issues", params=[("workspace_id", ws["id"]), ("sort", "priority"), ("limit", "10")]
    )
    assert [i["priority"] for i in r.json()["items"]] == ["high", "high", "low"]
    r = await client.get(
        "/api/issues", params=[("workspace_id", ws["id"]), ("sort", "due_date"), ("limit", "10")]
    )
    assert r.status_code == 200

    # filtro por metadata
    await client.put(f"/api/issues/{a['id']}/metadata/env", json={"value": "prod"})
    r = await client.get(
        "/api/issues", params=[("workspace_id", ws["id"]), ("metadata", '{"env": "prod"}')]
    )
    body = r.json()
    items = body["items"] if isinstance(body, dict) else body
    assert [i["id"] for i in items] == [a["id"]]


# ── Grouped / table / facets ──────────────────────────────────────────
async def test_grouped_and_facets(client):
    user, ws = await _setup(client, "cycle1-groups@ryu.dev")
    await _create_issue(client, ws["id"], "G1", status="todo", priority="high")
    await _create_issue(client, ws["id"], "G2", status="todo", priority="low")
    await _create_issue(client, ws["id"], "G3", status="done")

    r = await client.get("/api/issues/grouped", params={"workspace_id": ws["id"], "group_by": "status"})
    groups = {g["key"]: g for g in r.json()["groups"]}
    assert groups["todo"]["count"] == 2 and len(groups["todo"]["issues"]) == 2
    assert groups["done"]["count"] == 1

    r = await client.get("/api/issues/grouped", params={"workspace_id": ws["id"], "group_by": "priority"})
    groups = {g["key"]: g for g in r.json()["groups"]}
    assert groups["high"]["count"] == 1 and groups["none"]["count"] == 1

    r = await client.post("/api/issues/table/groups", json={"workspace_id": ws["id"], "group_by": "status"})
    assert {g["key"]: g["count"] for g in r.json()["groups"]} == {"todo": 2, "done": 1}

    r = await client.post(
        "/api/issues/table/rows",
        json={"workspace_id": ws["id"], "group_by": "status", "group_key": "todo", "limit": 1},
    )
    assert r.json()["total"] == 2 and len(r.json()["items"]) == 1

    r = await client.post("/api/issues/table/facets", json={"workspace_id": ws["id"]})
    facets = r.json()["facets"]
    assert {f["value"]: f["count"] for f in facets["status"]} == {"todo": 2, "done": 1}
    assert any(f["value"] == "unassigned" for f in facets["assignee"])


# ── Busca ─────────────────────────────────────────────────────────────
async def test_search_title_description_comments(client):
    user, ws = await _setup(client, "cycle1-search@ryu.dev")
    t = await _create_issue(client, ws["id"], "Pagamento com xurupita")
    d = await _create_issue(client, ws["id"], "Outra", description="detalhe xurupita profundo")
    c = await _create_issue(client, ws["id"], "Sem nada")
    await client.post(f"/api/issues/{c['id']}/comments", json={"body": "mencionando xurupita aqui"})

    r = await client.get("/api/issues/search", params={"workspace_id": ws["id"], "q": "xurupita"})
    results = r.json()["results"]
    by_id = {res["issue"]["id"]: res for res in results}
    assert set(by_id) == {t["id"], d["id"], c["id"]}
    assert by_id[t["id"]]["match"] == "title"
    assert by_id[d["id"]]["match"] == "description"
    assert by_id[c["id"]]["match"] == "comment"
    assert "xurupita" in by_id[d["id"]]["snippet"]
