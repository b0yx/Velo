from job_store import JobStore


def test_jobs_are_persisted_and_retryable(tmp_path):
    store = JobStore(tmp_path / "jobs.sqlite3")
    job = store.create("https://example.com/video", {"quality": "720p"}, batch_id="batch-a")

    store.update(job["id"], status="running", progress=42)
    # Opening the database after a simulated restart requeues running work.
    restored = JobStore(tmp_path / "jobs.sqlite3")
    assert restored.pending()[0]["progress"] == 42

    restored.update(job["id"], status="failed", error="network")
    retried = restored.retry_failed("batch-a")
    assert retried[0]["status"] == "queued"
    assert retried[0]["error"] == ""


def test_job_state_is_scoped_to_batch(tmp_path):
    store = JobStore(tmp_path / "jobs.sqlite3")
    first = store.create("https://example.com/1", {}, batch_id="first")
    second = store.create("https://example.com/2", {}, batch_id="second")
    store.update(first["id"], status="completed", progress=100)
    store.update(second["id"], status="failed", error="failed")

    assert store.state(batch_id="first")["completed"] == 1
    assert store.state(batch_id="first")["failed"] == 0
    assert store.state(batch_id="second")["failed"] == 1
