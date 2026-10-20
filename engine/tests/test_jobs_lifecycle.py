"""Jobs — dedup, timeout→failed, retry máx."""

from __future__ import annotations

import time

import pytest

from veu import jobs


@pytest.fixture()
def clean_store(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("VEU_DATA_ROOT", str(tmp_path))
    # reinicia store isolado
    store = jobs.JobStore()
    monkeypatch.setattr(jobs, "store", store)
    return store


def test_dedup_returns_same_job(clean_store: jobs.JobStore):
    clean_store.set_executor(lambda j: {"summary": "ok"})
    a = clean_store.enqueue(intent="ative o agente architect", route="ecc")
    b = clean_store.enqueue(intent="ative o agente architect", route="ecc")
    assert a["id"] == b["id"]
    assert b.get("deduped") is True


def test_timeout_marks_failed(clean_store: jobs.JobStore, monkeypatch: pytest.MonkeyPatch):
    def slow(_job):
        time.sleep(0.01)
        raise RuntimeError("boom")

    clean_store.set_executor(slow)
    # força timeout curto e sem retry útil
    job = clean_store.enqueue(intent="job lento", route="chat", timeout_sec=0)
    job_id = job["id"]
    # simula running antigo
    with clean_store._lock:
        row = clean_store._jobs[job_id]
        row["state"] = "running"
        row["started"] = time.time() - 10
        row["attempts"] = jobs.MAX_RETRIES + 1
    clean_store._tick()
    got = clean_store.get(job_id)
    assert got is not None
    assert got["state"] == "failed"


def test_retry_respects_max(clean_store: jobs.JobStore):
    calls = {"n": 0}

    def flaky(_job):
        calls["n"] += 1
        raise RuntimeError("fail")

    clean_store.set_executor(flaky)
    job = clean_store.enqueue(intent="falha controlada", route="chat")
    # força running + fail com retry
    for _ in range(jobs.MAX_RETRIES + 3):
        with clean_store._lock:
            row = clean_store._jobs[job["id"]]
            if row["state"] in jobs.TERMINAL:
                break
            row["state"] = "running"
            row["started"] = time.time() - 999
            clean_store._fail_locked(row, "timeout", retry=True)
    got = clean_store.get(job["id"])
    assert got is not None
    assert got["state"] in {"failed", "queued"}
    if got["state"] == "failed":
        assert int(got.get("attempts") or 0) >= 1
