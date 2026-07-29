from pathlib import Path
from akili_runtime import AkiliStore


def test_scope_isolation(tmp_path: Path):
    store = AkiliStore(tmp_path / "akili.db")
    store.remember(scope="repo:a", family="style", content="Use UTC", source="issue-1")
    store.remember(scope="repo:b", family="style", content="Use local time", source="issue-2")
    assert [m.content for m in store.retrieve(scope="repo:a")] == ["Use UTC"]
    assert [m.content for m in store.retrieve(scope="repo:b")] == ["Use local time"]


def test_supersession(tmp_path: Path):
    store = AkiliStore(tmp_path / "akili.db")
    first = store.remember(scope="repo:a", family="style", content="Use UTC", source="issue-1")
    second = store.remember(scope="repo:a", family="style", content="Use RFC3339 Z", source="review-2")
    active = store.retrieve(scope="repo:a")
    assert len(active) == 1
    assert active[0].id == second.id
    assert active[0].supersedes_id == first.id


def test_audit_chain(tmp_path: Path):
    store = AkiliStore(tmp_path / "akili.db")
    store.remember(scope="repo:a", family="style", content="Use UTC", source="issue-1")
    store.retrieve(scope="repo:a")
    assert store.validate_audit_chain()


def test_context_bundle(tmp_path: Path):
    store = AkiliStore(tmp_path / "akili.db")
    store.remember(scope="repo:a", family="style", content="Use UTC", source="issue-1")
    bundle = store.context_bundle(scope="repo:a", task="Add timestamp")
    assert bundle["active_memories"][0]["content"] == "Use UTC"
    assert "source=issue-1" in bundle["memory_prompt"]
