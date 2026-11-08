"""The Ruh speaker pilot: shards that hold no scripture, a sieve that never
lets past what the reader's filter flags, training that resumes exactly, and
a launcher that spends nothing unless told how much."""

import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from tadbir import iqtibas, lughah, ruh_reader
from tadbir.ruh_reader import speaker

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "scripts" / "runpod_speaker.py"
NARRATION = (
    "actions are judged by intentions and every person will get what they intended "
    "so whoever emigrated for worldly benefits"
)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MIZAN_TALIM", "off")
    return tmp_path


def _uthmani() -> str:
    for row in (lughah.CORPUS / "quote.tsv").read_text(encoding="utf-8").splitlines():
        _source, _, text = row.partition("\t")
        if len(text.split()) >= 8:
            return text.strip()
    raise AssertionError("no long quote in the seeds")


def _documents() -> list[speaker.Document]:
    """Documents of several seed lines each (so no document is a seed's
    words), and the ones every rule must drop."""
    by_label: dict[str, list[str]] = {}
    for text, label in ruh_reader.seeds():
        by_label.setdefault(label, []).append(text)
    found = []
    for label, texts in sorted(by_label.items()):
        for number in range(30):
            body = "\n".join(texts[number * 4 : number * 4 + 4])
            found.append(speaker.Document(f"test:{label}:{number}", label, body))
    seed_text, seed_label = ruh_reader.seeds()[0]
    found += [
        speaker.Document("bad:quran", "ar", f"{by_label['ar'][200]}\n{_uthmani()}"),
        speaker.Document(
            "bad:hadith", "en", f"{by_label['en'][200]} The Prophet said: {NARRATION}."
        ),
        speaker.Document("bad:seed", seed_label, seed_text),
        speaker.Document("bad:script", "ar", "This is plainly an English sentence, not Arabic."),
        speaker.Document("bad:copy", "en", next(d.text for d in found if d.label == "en")),
    ]
    return found


@pytest.fixture
def shards(home, monkeypatch):
    monkeypatch.setattr(speaker, "HELD_OUT", 4)  # some of every language held out
    out = home / "shards"
    manifest = speaker.prepare(
        out,
        _documents(),
        plan="tiny",
        budgets=dict.fromkeys(speaker.LANGUAGES, 0),
        scripture=ruh_reader.scripture,
        hadith=speaker.Hadith(english=[NARRATION]),
        log=lambda _line: None,
    )
    return out, manifest


# ── without torch ────────────────────────────────────────────────────────


def test_importing_the_speaker_needs_no_torch():
    found = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import tadbir.ruh_reader.speaker; print('torch' in sys.modules)",
        ],
        cwd=ROOT / "backend",
        capture_output=True,
        text=True,
        check=True,
    )
    assert found.stdout.strip() == "False"


def test_pieces_hold_every_span_of_half_their_length():
    words = [f"word{i}" for i in range(200)]
    found = speaker.pieces(" ".join(words) + "\nsecond line")
    assert found[-1] == "second line"
    assert all(len(iqtibas.tokens(piece)) <= iqtibas.MAX_WORDS for piece in found)
    for start in range(len(words) - 32):
        span = " ".join(words[start : start + 32])
        assert any(span in piece for piece in found)


def _tiny_quran(monkeypatch):
    rows = {
        "ar": [
            (1, 2, "الحمد لله رب العالمين"),
            (1, 5, "إياك نعبد وإياك نستعين"),
            (112, 1, "قل هو الله أحد"),
        ],
        "tr": [
            (1, 2, "Alhamdu lillahi rabbi alAAalameena"),
            (1, 5, "Iyyaka naAAbudu waiyyaka nastaAAeenu"),
            (112, 1, "Qul huwa Allahu ahadun"),
        ],
        "en": [
            (1, 2, "All praise is due to Allah, Lord of the worlds"),
            (1, 5, "It is You we worship and You we ask for help"),
            (112, 1, "Say, He is Allah, who is One"),
        ],
        "ur": [
            (1, 2, "سب طرح کی تعریف خدا ہی کو سزاوار ہے جو تمام مخلوقات کا پروردگار ہے"),
            (1, 5, "اے پروردگار ہم تیری ہی عبادت کرتے ہیں اور تجھ ہی سے مدد مانگتے ہیں"),
            (112, 1, "کہو کہ وہ اللہ ایک ہے"),
        ],
        "hi": [
            (1, 2, "प्रशंसा अल्लाह ही के लिए है जो सारे संसार का रब है"),
            (1, 5, "हम तेरी ही बन्दगी करते हैं और तुझी से मदद माँगते हैं"),
            (112, 1, "कहो वह अल्लाह यकता है"),
        ],
    }
    quotes = iqtibas.build(rows)
    monkeypatch.setattr(iqtibas, "_quotes", quotes)
    return quotes


def test_the_sieve_never_lets_past_what_scripture_flags(monkeypatch):
    quotes = _tiny_quran(monkeypatch)
    sieve = speaker.Sieve(quotes)
    quoted = [
        "my favourite verse: It is You we worship and You we ask for help. amazing",
        "he recited All praise is due to Allah, Lord of the worlds before eating",
        "qul huwa allahu ahadun is what she read",
        "الحمد لله رب العالمين على كل حال",
        "हम तेरी ही बन्दगी करते हैं और तुझी से मदद माँगते हैं यह पढ़ो",
        _uthmani(),
    ]
    ordinary = [text for text, _label in lughah.corpus() if _label not in lughah.NEUTRAL]
    random.Random(7).shuffle(ordinary)
    flagged = passed = 0
    for text in quoted + ordinary[:400]:
        for piece in speaker.pieces(text):
            holy = ruh_reader.scripture(piece)
            may = sieve.may_hold(piece)
            assert may or not holy, piece  # never skips what scripture flags
            flagged += holy
            passed += not may
    assert flagged >= 4
    assert passed >= 300  # and most ordinary text is never read again


def test_hadith_runs_are_found_in_either_script():
    books = speaker.Hadith(
        arabic=["إنما الأعمال بالنيات وإنما لكل امرئ ما نوى فمن كانت هجرته إلى دنيا يصيبها"],
        english=[NARRATION],
    )
    assert books("He said that " + " ".join(NARRATION.split()[:9]) + " and left.")
    assert books("قال إنما الأعمال بالنيات وإنما لكل امرئ ما نوى")
    assert not books("actions are judged by their results in the market")
    assert not speaker.Hadith()("anything at all")


def test_prepare_drops_every_rule_and_writes_checked_shards(shards):
    out, manifest = shards
    dropped = manifest["dropped"]
    assert dropped["bad"] == {
        "scripture": 1,
        "hadith": 1,
        "seed words": 1,
        "script": 1,
        "duplicate": 1,
    }
    assert set(manifest["kept"]["test"]) <= {"train", "held"}
    assert {item["language"] for item in manifest["train"]} == set(speaker.LANGUAGES)
    assert speaker.verify_shards(out)["plan"] == "tiny"
    stream = b"".join((out / item["file"]).read_bytes() for item in manifest["train"])
    # uint16 tokens: the bytes of the text sit in the low byte of each token
    text = bytes(low for low, high in zip(stream[0::2], stream[1::2], strict=True) if high == 0)
    words = ruh_reader.reading(_uthmani()).split()
    for start in range(len(words) - 2):
        assert " ".join(words[start : start + 3]).encode() not in text
    assert NARRATION.split()[3].encode() + b" by intentions" not in text
    # a shard that changes is refused
    path = out / manifest["train"][0]["file"]
    data = bytearray(path.read_bytes())
    data[0] ^= 1
    path.write_bytes(bytes(data))
    with pytest.raises(speaker.Mismatch):
        speaker.verify_shards(out)


def test_held_out_documents_are_never_trained_on(shards):
    out, _manifest = shards
    rows = {
        split: [
            json.loads(row)["group"]
            for path in (out / "text").glob(f"*.{split}.jsonl")
            for row in path.read_text(encoding="utf-8").splitlines()
        ]
        for split in ("train", "held")
    }
    assert rows["held"] and rows["train"]
    assert not set(rows["held"]) & set(rows["train"])
    assert all(speaker.held_out(group) for group in rows["held"])


def test_the_pilot_is_what_the_doc_says():
    budgets = speaker.pilot_budgets()
    assert budgets == {
        "en": 4_500_000_000,
        "hi": 4_000_000_000,
        "ur": 3_000_000_000,
        "ar": 3_000_000_000,
        "hi-latn": 0,
    }
    plan = speaker.PLANS["pilot"]
    per_step = plan["batch"] * plan["accumulate"] * speaker.CONFIGS["pilot"]["context"]
    assert per_step == 262_144
    for source in speaker.SOURCES:
        assert "NC" not in source.licence and "SA" not in source.licence
        assert all(len(digest) == 64 for _name, digest in source.files)
    assert any("GPT-4o-mini" in reason for reason in speaker.REJECTED.values())


def test_bpe_specials_come_first_and_text_round_trips(tmp_path):
    pytest.importorskip("tokenizers")
    texts = [text for text, _label in ruh_reader.seeds()]
    codec = speaker.train_bpe(texts, 700, tmp_path / "tokenizer.json")
    assert codec.tokenizer.token_to_id("<end>") == codec.end == 0
    assert codec.tokenizer.token_to_id("<lang:3>") == codec.lang(3)
    for text in ("नमस्ते, आप कैसे हैं?", "آپ کیسے ہیں؟", "kya haal hai", "مرحبا بالعالم", "Hi!"):
        assert codec.decode(codec.encode([text])[0]) == text


# ── with torch ───────────────────────────────────────────────────────────


def _state(folder: Path):
    import torch

    return torch.load(folder / "final" / "model.pt", map_location="cpu", weights_only=True)["state"]


def test_training_resumed_from_a_checkpoint_matches_one_run(shards, home):
    torch = pytest.importorskip("torch")
    from tadbir.ruh_reader import speaker_net

    out, _manifest = shards
    config, plan = speaker.CONFIGS["tiny"], speaker.PLANS["tiny"]
    quiet = {"log": lambda _line: None, "device": "cpu"}
    whole = speaker_net.train(out, home / "whole", config, plan, steps=4, **quiet)
    speaker_net.train(out, home / "parts", config, plan, steps=2, **quiet)
    parts = speaker_net.train(out, home / "parts", config, plan, steps=2, **quiet)
    assert whole["step"] == parts["step"] == 4 and parts["calls"] == 2
    one, two = _state(home / "whole"), _state(home / "parts")
    assert all(torch.equal(one[name], two[name]) for name in one)
    for language, item in parts["held_out"].items():
        assert language in speaker.LANGUAGES and 0 < item["bpb"] < 16
    model, codec = speaker_net.load_final(home / "parts" / "final")
    assert codec.kind == "bytes" and model.parameters_count() == parts["parameters"]


def test_fewer_rows_per_pass_train_the_same_run(shards, home, monkeypatch):
    # A 64 GB Mac cannot hold the pilot's 32 rows in one pass; splitting each
    # micro-batch must not change the data, the gradient or the run's identity.
    torch = pytest.importorskip("torch")
    from tadbir.ruh_reader import speaker_net

    out, _manifest = shards
    config, plan = speaker.CONFIGS["tiny"], speaker.PLANS["tiny"]
    quiet = {"log": lambda _line: None, "device": "cpu"}
    whole = speaker_net.train(out, home / "whole", config, plan, steps=3, **quiet)
    passes: list[int] = []
    forward = speaker_net.Speaker.forward

    def counted(self, tokens, *args, **kwargs):
        passes.append(len(tokens))
        return forward(self, tokens, *args, **kwargs)

    monkeypatch.setattr(speaker_net.Speaker, "forward", counted)
    split = speaker_net.train(out, home / "split", config, plan, steps=2, rows=1, **quiet)
    assert passes[: plan["batch"]] == [1] * plan["batch"]  # one window a pass
    split = speaker_net.train(out, home / "split", config, plan, steps=1, rows=2, **quiet)
    assert split["step"] == whole["step"] == 3 and split["calls"] == 2  # resumed, same run
    one, two = _state(home / "whole"), _state(home / "split")
    assert all(torch.allclose(one[name], two[name], atol=1e-5) for name in one)
    with pytest.raises(ValueError, match="rows"):
        speaker_net.train(out, home / "bad", config, plan, steps=1, rows=3, **quiet)


def test_a_checkpoint_that_does_not_match_its_sha256_is_not_resumed(shards, home):
    pytest.importorskip("torch")
    from tadbir.ruh_reader import speaker_net

    out, _manifest = shards
    config, plan = speaker.CONFIGS["tiny"], speaker.PLANS["tiny"]
    run = home / "run"
    speaker_net.train(out, run, config, plan, steps=3, log=lambda _line: None, device="cpu")
    pointer = json.loads((run / "latest.json").read_text())
    (run / pointer["path"] / "model.pt").write_bytes(b"not the weights")
    seen: list[str] = []
    report = speaker_net.train(out, run, config, plan, steps=0, log=seen.append, device="cpu")
    assert report["step"] == 2  # the one before, whole
    assert any("does not match" in line for line in seen)
    other = dict(plan, lr=1e-4)  # another run's checkpoints are never continued
    report = speaker_net.train(out, run, config, other, steps=0, log=seen.append, device="cpu")
    assert report["step"] == 0


def test_cached_decoding_matches_a_full_forward_pass():
    torch = pytest.importorskip("torch")
    from tadbir.ruh_reader import speaker_net

    torch.manual_seed(0)
    model = speaker_net.Speaker(speaker_net.Config.of(speaker.CONFIGS["tiny"])).eval()
    tokens = torch.tensor([[258, *b"salaam dunya"]])
    full, _ = model(tokens)
    logits, cache = model(tokens[:, :5])
    steps = [logits[:, -1]]
    for position in range(5, tokens.shape[1]):
        logits, cache = model(tokens[:, position : position + 1], cache)
        steps.append(logits[:, -1])
    assert torch.allclose(torch.stack(steps[:-1], 1), full[:, 4:-1], atol=1e-5)
    codec = speaker.ByteCodec()
    assert isinstance(speaker_net.generate(model, codec, 1, "hello", 5), str)


def test_the_speaker_can_stand_in_for_the_reader_at_the_gate():
    torch = pytest.importorskip("torch")
    from tadbir.ruh_reader import speaker_net

    torch.manual_seed(0)
    model = speaker_net.Speaker(speaker_net.Config.of(speaker.CONFIGS["tiny"])).eval()
    rows = [
        (text, label, f"g{number // 2}", ("calibration", "gate")[number % 2])
        for number, (text, label) in enumerate(ruh_reader.seeds()[::40])
    ]
    found = speaker_net.gate_on_validation(model, speaker.ByteCodec(), rows, speaker.LANGUAGES)
    assert found["test"] == 1 and found["gate"]["needed"] == pytest.approx(40)
    assert found["adopted"] is False  # an untrained speaker earns nothing
    assert set(found["gate_bpb"]) <= set(speaker.LANGUAGES)


def test_the_pilot_has_about_125m_parameters():
    pytest.importorskip("torch")
    from tadbir.ruh_reader import speaker_net

    config = speaker_net.Config.of(speaker.CONFIGS["pilot"])
    model = speaker_net.Speaker(config)
    assert model.parameters_count() == 124_278_528
    per_token = speaker_net.flops_per_token(config, model.parameters_count())
    assert round(per_token * 2.5e9 / 1e18, 2) == 2.03


# ── the launcher ─────────────────────────────────────────────────────────


def _launch(*args, key="rpa_THIS_IS_A_TEST_KEY_123"):
    env = {k: v for k, v in os.environ.items() if k not in {"RUNPOD_API_KEY", "HF_TOKEN"}}
    env["RUNPOD_API_KEY"] = key
    env["HF_TOKEN"] = "hf_THIS_IS_A_TEST_TOKEN_456"
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args], capture_output=True, text=True, env=env, cwd=ROOT
    )


REVISION = "da9c7b64087f410bf742faffddfd3b0e43c9361b"


def test_the_launcher_refuses_without_a_confirmed_budget():
    found = _launch("--revision", REVISION, "--return", "volume", "--network-volume", "vol123")
    assert found.returncode != 0 and "--confirm-budget" in found.stderr
    found = _launch(
        "--revision",
        REVISION,
        "--confirm-budget",
        "30",
        "--return",
        "volume",
        "--network-volume",
        "vol123",
    )
    assert found.returncode != 0 and "25" in found.stderr


def test_the_dry_run_shows_the_request_and_never_the_keys():
    found = _launch(
        "--revision",
        REVISION,
        "--confirm-budget",
        "25",
        "--return",
        "hf",
        "--hf-repo",
        "owner/ruh-speaker-pilot",
    )
    assert found.returncode == 0, found.stderr
    shown = found.stdout + found.stderr
    assert "rpa_THIS_IS_A_TEST_KEY_123" not in shown and "hf_THIS_IS_A_TEST_TOKEN_456" not in shown
    plan = json.loads(found.stdout)
    assert plan["dry_run"] is True
    create = next(r for r in plan["requests"] if r["method"] == "POST")
    assert create["url"] == "https://api.runpod.io/v2/pods"
    assert create["headers"]["Authorization"] == "Bearer <redacted>"
    assert create["body"]["env"]["HF_TOKEN"] == "<redacted>"
    assert create["body"]["image"].startswith("pytorch/pytorch@sha256:")
    budget = plan["budget"]
    assert budget["usd"] == 25 and budget["worst_case_usd"] <= 25
    assert any(r["method"] == "DELETE" for r in plan["requests"])


def test_the_pod_commands_are_valid_python_and_carry_no_key():
    sys.path.insert(0, str(LAUNCHER.parent))
    try:
        import runpod_speaker
    finally:
        sys.path.remove(str(LAUNCHER.parent))
    for source in (runpod_speaker.BOOTSTRAP, runpod_speaker.SMOKE):
        compile(source, "pod", "exec")
        assert "RUNPOD_API_KEY" in source  # the pod-scoped key RunPod gives the pod
    assert "end()" in runpod_speaker.SMOKE and "execv" not in runpod_speaker.SMOKE
    budget = runpod_speaker.lifetime(25, 1.79)
    assert (1.79 + runpod_speaker.disk_hourly()) * budget / 3600 <= 25 - runpod_speaker.safety(25)


def test_training_picks_cuda_then_apples_gpu_then_the_cpu(monkeypatch):
    torch = pytest.importorskip("torch")
    from tadbir.ruh_reader import speaker_net

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: True)
    assert speaker_net.default_device() == "mps"
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)
    assert speaker_net.default_device() == "cpu"
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    assert speaker_net.default_device() == "cuda"
