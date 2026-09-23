import json

from api.semantic_store import SemanticStore


def test_semantic_store_loads_and_snapshots_groups(tmp_path):
    path = tmp_path / "semantic_groups.json"
    path.write_text(json.dumps({"tag_to_group": {"eau": "Nature"}}))
    store = SemanticStore(path)

    store.ensure_loaded()

    assert store.groups() == ["Nature"]
    assert store.snapshot() == ({"eau": "Nature"}, set())


def test_semantic_store_generation_invalidates_pending_work(tmp_path):
    store = SemanticStore(tmp_path / "semantic_groups.json")
    generation = store.begin_tag("eau")

    store.reset()

    assert generation == 0
    assert store.current_generation() == 1
    assert store.assign("eau", "Nature", generation) is False
    assert store.snapshot() == ({}, set())


def test_semantic_store_persists_assignments_and_clears_pending(tmp_path):
    path = tmp_path / "semantic_groups.json"
    store = SemanticStore(path)
    generation = store.begin_tag("eau")

    assert store.assign("eau", "Nature", generation) is True
    store.finish_tag("eau")
    store.save()

    loaded = SemanticStore(path)
    loaded.ensure_loaded()
    assert loaded.snapshot() == ({"eau": "Nature"}, set())