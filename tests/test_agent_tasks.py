"""The agent-task queue: enqueue -> claim (single winner) -> complete / fail."""

from __future__ import annotations

from pathlib import Path

from matchbox.agent_tasks import repo
from matchbox.core.db import connect
from matchbox.core.migrations import migrate


def _db(tmp_path: Path):  # noqa: ANN202 - test helper
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    return conn


def test_enqueue_then_drain(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    tid = repo.enqueue(conn, "prep", payload={"stage": "onsite"})

    pending = repo.list_tasks(conn, state="pending")
    assert [t["id"] for t in pending] == [tid]
    assert pending[0]["kind"] == "prep"
    assert pending[0]["payload"] == {"stage": "onsite"}

    claimed = repo.claim(conn, tid)
    assert claimed is not None
    assert claimed["state"] == "claimed"
    assert claimed["claimedAt"] is not None
    assert repo.list_tasks(conn, state="pending") == []

    done = repo.complete(conn, tid, result={"artifactId": 9})
    assert done is not None
    assert done["state"] == "done"
    assert done["result"] == {"artifactId": 9}
    assert done["doneAt"] is not None
    conn.close()


def test_claim_is_single_winner(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    tid = repo.enqueue(conn, "tailor")
    first = repo.claim(conn, tid)
    assert first is not None and first["state"] == "claimed"
    # A second claim must not re-claim: state and timestamp stay put.
    again = repo.claim(conn, tid)
    assert again is not None
    assert again["state"] == "claimed"
    assert again["claimedAt"] == first["claimedAt"]
    conn.close()


def test_fail_records_error(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    tid = repo.enqueue(conn, "extract_reqs")
    repo.claim(conn, tid)
    failed = repo.fail(conn, tid, "no jd_text")
    assert failed is not None
    assert failed["state"] == "failed"
    assert failed["error"] == "no jd_text"
    conn.close()


def test_list_filters_by_kind(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    repo.enqueue(conn, "prep")
    t2 = repo.enqueue(conn, "tailor")
    only_tailor = repo.list_tasks(conn, state="pending", kind="tailor")
    assert [t["id"] for t in only_tailor] == [t2]
    conn.close()
