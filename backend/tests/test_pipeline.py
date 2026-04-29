"""Pipeline: link, move, unlink, board, history.

Keystone invariant under test:
    Stage history is permanent. Unlinking a candidate from a job removes the
    candidate_jobs row but the stage_transitions trail stays.
"""

ADMIN = {"email": "admin@example.com", "password": "admin-pass-12345"}


def _login(client, **creds):
    r = client.post("/auth/login", json=creds)
    assert r.status_code == 200, r.text


def _setup_job(client) -> tuple[int, list[dict]]:
    """Create a client + job and return (job_id, stages)."""
    cid = client.post("/clients", json={"name": "BoardCo"}).json()["id"]
    job = client.post(
        "/jobs", json={"client_id": cid, "title": "Senior Backend Engineer"}
    ).json()
    return job["id"], job["stages"]


def test_link_candidate_places_at_first_stage(client):
    _login(client, **ADMIN)
    job_id, stages = _setup_job(client)
    cand_id = client.post("/candidates", json={"full_name": "Asha"}).json()["id"]

    r = client.post(f"/jobs/{job_id}/candidates", json={"candidate_id": cand_id})
    assert r.status_code == 201, r.text
    assert r.json()["current_stage_id"] == stages[0]["id"]


def test_cannot_link_same_candidate_twice(client):
    _login(client, **ADMIN)
    job_id, _ = _setup_job(client)
    cand_id = client.post("/candidates", json={"full_name": "Asha"}).json()["id"]

    client.post(f"/jobs/{job_id}/candidates", json={"candidate_id": cand_id})
    r = client.post(f"/jobs/{job_id}/candidates", json={"candidate_id": cand_id})
    assert r.status_code == 409


def test_cannot_link_soft_deleted_candidate(client):
    _login(client, **ADMIN)
    job_id, _ = _setup_job(client)
    cand_id = client.post("/candidates", json={"full_name": "Ghost"}).json()["id"]
    client.delete(f"/candidates/{cand_id}")
    r = client.post(f"/jobs/{job_id}/candidates", json={"candidate_id": cand_id})
    assert r.status_code == 404


def test_initial_link_writes_a_transition_with_null_from(client):
    _login(client, **ADMIN)
    job_id, stages = _setup_job(client)
    cand_id = client.post("/candidates", json={"full_name": "Asha"}).json()["id"]
    link = client.post(
        f"/jobs/{job_id}/candidates", json={"candidate_id": cand_id}
    ).json()

    history = client.get(f"/candidate-jobs/{link['id']}/transitions").json()
    assert len(history) == 1
    assert history[0]["from_stage_id"] is None
    assert history[0]["to_stage_id"] == stages[0]["id"]


def test_move_to_stage_writes_transition_and_updates_current(client):
    _login(client, **ADMIN)
    job_id, stages = _setup_job(client)
    cand_id = client.post("/candidates", json={"full_name": "Asha"}).json()["id"]
    link = client.post(
        f"/jobs/{job_id}/candidates", json={"candidate_id": cand_id}
    ).json()

    target = stages[3]["id"]  # arbitrary later stage
    r = client.patch(f"/candidate-jobs/{link['id']}", json={"stage_id": target})
    assert r.status_code == 200, r.text
    assert r.json()["current_stage_id"] == target

    history = client.get(f"/candidate-jobs/{link['id']}/transitions").json()
    assert len(history) == 2
    assert history[1]["from_stage_id"] == stages[0]["id"]
    assert history[1]["to_stage_id"] == target


def test_move_to_same_stage_is_a_noop(client):
    _login(client, **ADMIN)
    job_id, stages = _setup_job(client)
    cand_id = client.post("/candidates", json={"full_name": "X"}).json()["id"]
    link = client.post(
        f"/jobs/{job_id}/candidates", json={"candidate_id": cand_id}
    ).json()

    r = client.patch(f"/candidate-jobs/{link['id']}", json={"stage_id": stages[0]["id"]})
    assert r.status_code == 200
    history = client.get(f"/candidate-jobs/{link['id']}/transitions").json()
    assert len(history) == 1  # no extra row written


def test_move_to_a_stage_from_a_different_job_rejected(client):
    _login(client, **ADMIN)
    job_id, _ = _setup_job(client)
    cand_id = client.post("/candidates", json={"full_name": "X"}).json()["id"]
    link = client.post(
        f"/jobs/{job_id}/candidates", json={"candidate_id": cand_id}
    ).json()

    other_job_id, other_stages = _setup_job(client)
    r = client.patch(
        f"/candidate-jobs/{link['id']}", json={"stage_id": other_stages[2]["id"]}
    )
    assert r.status_code == 400


def test_unlink_preserves_transition_history(client):
    """The keystone audit invariant."""
    _login(client, **ADMIN)
    job_id, stages = _setup_job(client)
    cand_id = client.post("/candidates", json={"full_name": "Audit"}).json()["id"]
    link = client.post(
        f"/jobs/{job_id}/candidates", json={"candidate_id": cand_id}
    ).json()
    client.patch(f"/candidate-jobs/{link['id']}", json={"stage_id": stages[2]["id"]})

    # Before unlink: 2 transitions
    before = client.get(f"/candidate-jobs/{link['id']}/transitions").json()
    assert len(before) == 2

    # Unlink
    r = client.delete(f"/candidate-jobs/{link['id']}")
    assert r.status_code == 204

    # After unlink: link is gone but the transitions persist (read directly
    # from the DB since the link-scoped endpoint is now 404)
    assert client.get(f"/candidate-jobs/{link['id']}/transitions").status_code == 404

    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models.pipeline import StageTransition

    with SessionLocal() as s:
        rows = list(
            s.scalars(
                select(StageTransition)
                .where(
                    StageTransition.candidate_id == cand_id,
                    StageTransition.job_id == job_id,
                )
                .order_by(StageTransition.at)
            ).all()
        )
    # 2 from before + 1 leaving (to=None) = 3
    assert len(rows) == 3
    assert rows[-1].to_stage_id is None  # explicit "left the pipeline" marker


def test_can_relink_after_unlinking(client):
    _login(client, **ADMIN)
    job_id, _ = _setup_job(client)
    cand_id = client.post("/candidates", json={"full_name": "Comeback"}).json()["id"]
    link1 = client.post(
        f"/jobs/{job_id}/candidates", json={"candidate_id": cand_id}
    ).json()
    client.delete(f"/candidate-jobs/{link1['id']}")

    r = client.post(f"/jobs/{job_id}/candidates", json={"candidate_id": cand_id})
    assert r.status_code == 201
    # Whether the new row reuses the old PK is a backend impl detail; what
    # matters is that the relink succeeds and lands at the first stage.
    new_link = r.json()
    assert new_link["candidate_id"] == cand_id
    assert new_link["job_id"] == job_id


def test_board_groups_links_by_stage_and_excludes_soft_deleted(client):
    _login(client, **ADMIN)
    job_id, stages = _setup_job(client)

    a = client.post("/candidates", json={"full_name": "A"}).json()["id"]
    b = client.post("/candidates", json={"full_name": "B"}).json()["id"]
    c = client.post("/candidates", json={"full_name": "C"}).json()["id"]

    la = client.post(f"/jobs/{job_id}/candidates", json={"candidate_id": a}).json()
    lb = client.post(f"/jobs/{job_id}/candidates", json={"candidate_id": b}).json()
    lc = client.post(f"/jobs/{job_id}/candidates", json={"candidate_id": c}).json()

    # Move b to stage 2; c to stage 4
    client.patch(f"/candidate-jobs/{lb['id']}", json={"stage_id": stages[2]["id"]})
    client.patch(f"/candidate-jobs/{lc['id']}", json={"stage_id": stages[4]["id"]})

    # Soft-delete c
    client.delete(f"/candidates/{c}")

    board = client.get(f"/jobs/{job_id}/board").json()
    assert [col["stage"]["id"] for col in board] == [s["id"] for s in stages]

    by_stage = {col["stage"]["id"]: col["links"] for col in board}
    assert [l["id"] for l in by_stage[stages[0]["id"]]] == [la["id"]]
    assert [l["id"] for l in by_stage[stages[2]["id"]]] == [lb["id"]]
    assert by_stage[stages[4]["id"]] == []  # c was soft-deleted


def test_link_scoped_note(client):
    _login(client, **ADMIN)
    job_id, _ = _setup_job(client)
    cand_id = client.post("/candidates", json={"full_name": "X"}).json()["id"]
    link = client.post(
        f"/jobs/{job_id}/candidates", json={"candidate_id": cand_id}
    ).json()

    # Add a candidate-global note and a link-scoped note.
    g = client.post(f"/candidates/{cand_id}/notes", json={"body": "global"}).json()
    s = client.post(
        f"/candidate-jobs/{link['id']}/notes", json={"body": "link-scoped"}
    ).json()
    assert s["candidate_job_id"] == link["id"]
    assert g["candidate_job_id"] is None

    # Candidate-scoped list returns BOTH; link-scoped list returns only the link's.
    all_notes = client.get(f"/candidates/{cand_id}/notes").json()
    assert {n["id"] for n in all_notes} == {g["id"], s["id"]}

    link_notes = client.get(f"/candidate-jobs/{link['id']}/notes").json()
    assert [n["id"] for n in link_notes] == [s["id"]]


def test_board_includes_last_transition_with_actor_name(client):
    _login(client, **ADMIN)
    me = client.get("/auth/me").json()
    job_id, stages = _setup_job(client)
    cand_id = client.post(
        "/candidates", json={"full_name": "Asha"}
    ).json()["id"]
    link = client.post(
        f"/jobs/{job_id}/candidates", json={"candidate_id": cand_id}
    ).json()
    # Move once so the latest transition is the move (not the initial link).
    client.patch(
        f"/candidate-jobs/{link['id']}", json={"stage_id": stages[2]["id"]}
    )

    board = client.get(f"/jobs/{job_id}/board").json()
    moved_link = next(
        l for col in board for l in col["links"] if l["id"] == link["id"]
    )
    lt = moved_link["last_transition"]
    assert lt is not None
    assert lt["by_user_id"] == me["id"]
    assert lt["by_user_name"] == me["name"]
    assert lt["from_stage_id"] == stages[0]["id"]
    assert lt["to_stage_id"] == stages[2]["id"]


def test_board_last_transition_is_initial_link_when_no_moves(client):
    _login(client, **ADMIN)
    job_id, stages = _setup_job(client)
    cand_id = client.post(
        "/candidates", json={"full_name": "Just Linked"}
    ).json()["id"]
    link = client.post(
        f"/jobs/{job_id}/candidates", json={"candidate_id": cand_id}
    ).json()

    board = client.get(f"/jobs/{job_id}/board").json()
    only_link = next(
        l for col in board for l in col["links"] if l["id"] == link["id"]
    )
    lt = only_link["last_transition"]
    assert lt is not None
    assert lt["from_stage_id"] is None  # initial link rows have null from
    assert lt["to_stage_id"] == stages[0]["id"]
