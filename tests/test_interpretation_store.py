from api.interpretation_store import InterpretationStore


def test_store_start_and_finish_job():
    store = InterpretationStore()
    token = store.start("entry_oracle")

    assert token == 0
    assert "entry_oracle" in store.queue
    assert store.is_current("entry_oracle", token)

    store.finish("entry_oracle", token)

    assert "entry_oracle" not in store.queue


def test_cancel_invalidates_existing_worker():
    store = InterpretationStore()
    token = store.start("entry_oracle")

    assert store.cancel("entry_oracle") is True
    assert store.is_current("entry_oracle", token) is False
    assert "entry_oracle" not in store.queue


def test_expire_moves_job_to_error_state():
    store = InterpretationStore()
    store.start("entry_oracle")
    store.expire("entry_oracle", "timed out")

    assert store.errors["entry_oracle"] == "timed out"
    assert "entry_oracle" not in store.queue