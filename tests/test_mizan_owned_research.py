import hashlib
import json
import zipfile
from dataclasses import asdict
from pathlib import Path

import pytest

from mizan_owned import research
from mizan_owned.provider import OwnedProvider


def test_pinned_runtime_sources_are_unmodified():
    root = Path(__file__).resolve().parents[1]
    sources = json.loads((root / "research/registry/runtime_sources.json").read_text())
    assert len(sources) == 12
    for row in sources:
        assert hashlib.sha256((root / row["path"]).read_bytes()).hexdigest() == row["sha256"]


def test_import_and_local_source_search(tmp_path, monkeypatch):
    bundle = tmp_path / "fixture.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(
            "history/note.md", "Historical root experiment: unresolved metric inconsistency."
        )
        archive.writestr("data.bin", b"\x00\xff")
    monkeypatch.setattr(research, "BUNDLE_SHA256", hashlib.sha256(bundle.read_bytes()).hexdigest())
    output = tmp_path / "imported"
    result = research.import_bundle(bundle, output)
    assert result["archive_members"] == 2 and result["indexed_text_files"] == 1
    assert (output / "data.bin").read_bytes() == b"\x00\xff"
    matches = research.search("metric inconsistency", output)
    assert matches[0]["path"] == "history/note.md"
    assert matches[0]["verified_claim"] is False
    assert research.search('" OR sql: *', output) == []
    with pytest.raises(ValueError, match="never overwritten"):
        research.import_bundle(bundle, output)


def test_import_rejects_mismatch_and_traversal(tmp_path, monkeypatch):
    bundle = tmp_path / "bad.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("../escape", "do not write")
    with pytest.raises(ValueError, match="SHA256"):
        research.import_bundle(bundle, tmp_path / "wronghash")
    monkeypatch.setattr(research, "BUNDLE_SHA256", hashlib.sha256(bundle.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="Unsafe"):
        research.import_bundle(bundle, tmp_path / "unsafe")
    assert not (tmp_path / "escape").exists()


def test_mem0_cannot_send_background_model_requests_in_owned_mode(monkeypatch):
    from memory import mem0_store

    monkeypatch.setenv("MEM0_ENABLED", "true")
    monkeypatch.setenv("MIZAN_OWNED_ONLY", "true")
    monkeypatch.setattr(mem0_store, "_store", object())
    assert mem0_store.enabled() is False
    assert mem0_store.get_store() is None


def test_adapter_loads_real_own_checkpoint_and_decodes(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    from mizan_reply.checkpoint import FORMAT, atomic_save, capture_rng
    from mizan_reply.data import encode_prompt
    from mizan_reply.generation import generate
    from mizan_reply.model import MizanReplyModel, ModelConfig
    from mizan_reply.train import TrainingConfig

    torch.set_num_threads(1)
    torch.manual_seed(17)
    model = MizanReplyModel(ModelConfig(dim=8, layers=8, max_seq_len=256, root_dim=3))
    path = tmp_path / "fixture.pt"
    atomic_save(
        path,
        dict(
            format=FORMAT,
            checkpoint_boundary="complete_epoch",
            model_config=model.config.to_dict(),
            training_config=asdict(TrainingConfig(device="cpu")),
            model_state=model.state_dict(),
            optimizer_state={},
            scaler_state={},
            data_manifest={},
            epoch_completed=0,
            optimizer_steps=0,
            world_size=1,
            runtime={},
            rng_by_rank=[capture_rng()],
        ),
    )
    monkeypatch.setenv("MIZAN_REPLY_CHECKPOINT", str(path))
    monkeypatch.setenv("MIZAN_OWNED_DB", str(tmp_path / "owned.db"))
    request = {"system": "fixture", "messages": [{"role": "user", "content": "u"}]}
    provider = OwnedProvider()
    actual = provider._decode(request, 8)
    prompt = encode_prompt(
        [{"role": "system", "content": "fixture"}, *request["messages"]], [], None, 256
    )
    expected = generate(model, prompt["input_ids"], roots=prompt["roots"], max_new_tokens=8)
    assert actual == (expected.text, expected.eos)
    assert provider._sha == hashlib.sha256(path.read_bytes()).hexdigest()


def test_explicit_existential_context_preserves_unknowns():
    from mizan_owned.schemas import ContextRequest, resolve_context

    request = ContextRequest(
        mode="episodic_exists",
        ontology={"place": ["river", "city"]},
        senses=["shore", "finance"],
        language="en",
        symbol="bank",
        context={},
        observations=[{"id": "episode", "context": {}, "sense": "shore", "source": "fixture"}],
    )
    answer = resolve_context(request)
    assert answer["status"] == "AMBIGUOUS_FINITE_MEANING"
    assert answer["answered"] is False
    assert set(answer["possible_senses"]) == {"shore", "finance"}
