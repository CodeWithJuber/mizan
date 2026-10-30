"""The Ruh reader: MIZAN's own byte-level language model as a second opinion
beside Lughah, used only once it beats Lughah on held-out seeds."""

import json
import math

import pytest

from memory import stateless
from tadbir import lughah, ruh_reader

TINY = {"d_model": 32, "layers": 1, "heads": 2, "d_ff": 64, "context": 64, "dropout": 0.0}


@pytest.fixture
def reader_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MIZAN_TALIM", "off")
    ruh_reader.reset()
    yield tmp_path / "models" / "ruh_reader"
    ruh_reader.reset()


@pytest.fixture
def few_seeds(monkeypatch):
    """Every 15th seed, so a reader is built in seconds."""
    rows = ruh_reader.seeds()[::15]
    monkeypatch.setattr(ruh_reader, "seeds", lambda: list(rows))
    return rows


# ── without torch: the maths, the gate, the settings, consent ────────────


def test_off_or_missing_weights_leave_lughah_unchanged(reader_home, monkeypatch):
    for mode in ("off", "shadow", "on"):
        monkeypatch.setenv("MIZAN_RUH_READER", mode)
        for text in ("kya haal hai bhai", "What is the time?", "آپ کیسے ہیں"):
            assert lughah.posterior(text) == lughah.naive_posterior(text)
    assert ruh_reader.status()["present"] is False


def test_an_unknown_mode_reads_as_shadow(monkeypatch):
    monkeypatch.setenv("MIZAN_RUH_READER", "loud")
    assert ruh_reader.mode() == "shadow"
    monkeypatch.delenv("MIZAN_RUH_READER")
    assert ruh_reader.mode() == "shadow"


def test_b_is_zero_and_the_factor_one_when_the_reader_adds_nothing():
    lughah_rows = [[math.log(0.7), math.log(0.2), math.log(0.1)]] * 20
    uniform = [[-math.log(3)] * 3] * 20
    b, before, after = ruh_reader.fit_b(lughah_rows, uniform, [0] * 20)
    assert b == 0.0 and before == after
    assert ruh_reader.combined_log_posterior(lughah_rows[0], uniform[0], 0.0) == pytest.approx(
        lughah_rows[0]
    )


def test_the_reader_never_claims_more_than_its_own_likelihoods():
    # A dev set the reader never gets wrong would push κ without end.
    lm = [[-10.0, -40.0], [-50.0, -12.0]] * 30
    kappa, gamma, _loss = ruh_reader.fit_reader(lm, [20, 20] * 30, [0, 1] * 30, ref=20.0)
    assert kappa <= 1.0
    row = ruh_reader.reader_log_posterior([-10.0, -40.0], 2, kappa, 1.0, 20.0)
    assert row == pytest.approx(ruh_reader.reader_log_posterior([-10.0, -40.0], 2, 1.0, 0.0, 1.0))


def _rows(right: bool) -> list[float]:
    return [math.log(0.9), math.log(0.1)] if right else [math.log(0.1), math.log(0.9)]


def test_the_gate_refuses_a_reader_that_does_not_beat_lughah():
    truths = [0] * 200
    groups = [f"g{i}" for i in range(200)]
    lughah_rows = [_rows(i % 50 != 0) for i in range(200)]  # four mistakes
    # The same decisions, less sure: no better in accuracy, worse in log-loss.
    after = [[math.log(0.6), math.log(0.4)] if i % 50 else _rows(False) for i in range(200)]
    verdict = ruh_reader.gate(truths, groups, lughah_rows, after)
    assert verdict["adopted"] is False and verdict["wins"] == 0
    # Fixing a few mistakes is not yet more than chance at α = 0.05.
    fixed = [_rows(i not in (0, 50)) for i in range(200)]
    assert ruh_reader.gate(truths, groups, lughah_rows, fixed)["adopted"] is False


def test_the_gate_adopts_only_a_clear_held_out_gain():
    truths = [0] * 400
    groups = [f"g{i}" for i in range(400)]
    before = [_rows(i % 10 != 0) for i in range(400)]  # 40 mistakes
    after = [_rows(i % 100 != 0) for i in range(400)]  # 4 left, none new
    verdict = ruh_reader.gate(truths, groups, before, after)
    assert verdict["adopted"] is True and verdict["wins"] == 36 and verdict["losses"] == 0
    # The k-th test of one reader needs k(k+1)/α.
    assert ruh_reader.gate(truths, groups, before, after, test=3)["needed"] == pytest.approx(240)


def test_a_message_and_its_first_words_count_as_one_group():
    truths = [0, 0, 0]
    before = [_rows(False), _rows(False), _rows(True)]
    after = [_rows(True), _rows(True), _rows(True)]
    verdict = ruh_reader.gate(truths, ["g", "g", "g"], before, after)
    assert verdict["groups"] == 1 and verdict["wins"] == 1


def test_short_messages_are_cut_from_whole_ones():
    assert ruh_reader.variants("one two three four") == [
        ("whole", "one two three four"),
        ("2w", "one two"),
        ("3w", "one two three"),
    ]
    assert ruh_reader.variants("one two") == [("whole", "one two")]


def test_splits_are_by_group_and_fixed():
    parts = {ruh_reader.part(ruh_reader.group_of(text)) for text, _ in ruh_reader.seeds()}
    assert parts == {"train", "dev", "held_out"}
    # The same words, written differently, are one group in one split.
    assert ruh_reader.group_of("Hello, World!") == ruh_reader.group_of("hello world")


def _quote() -> str:
    line = (lughah.CORPUS / "quote.tsv").read_text(encoding="utf-8").splitlines()[5]
    return line.partition("\t")[2]


def test_scripture_is_set_aside_before_training():
    quote = _quote()
    rows = [(quote, "ar"), (f"my favourite ayah is {quote}", "en"), ("the cat sat", "en")]
    lines, dropped = ruh_reader.training_lines(rows, ["en", "ar"])
    assert dropped == 2 and lines == [("the cat sat", 0)]
    # A Quranic phrase in an otherwise ordinary line (18:24, in the seeds).
    assert ruh_reader.scripture("اذْكُر رَّبَّكَ إِذَا نَسِيتَ.")


def test_no_learning_without_consent(reader_home):
    texts = ["Mujhe kal ka mausam batao"]
    # Training is opt-in: with no choice bound, nothing is learned.
    assert ruh_reader.learn(texts, seconds=5)["status"] == "no consent"
    with stateless.allow_training("training: on"), stateless.no_learning("learning: off"):
        assert ruh_reader.learn(texts, seconds=5)["status"] == "no consent"
    with stateless.allow_training("training: on"), stateless.bind():
        assert ruh_reader.learn(texts, seconds=5)["status"] == "no consent"
    with stateless.allow_training("training: on"), stateless.no_training("whatsapp"):
        assert ruh_reader.learn(texts, seconds=5)["status"] == "no consent"
    with stateless.allow_training("training: on"):
        assert ruh_reader.learn(texts, seconds=5)["status"] in {"no reader", "no torch"}


async def test_the_night_needs_the_reader_on_and_consent(reader_home, monkeypatch):
    monkeypatch.setenv("MIZAN_RUH_READER", "off")
    assert (await ruh_reader.rest("u1"))["status"] == "off"
    monkeypatch.setenv("MIZAN_RUH_READER", "shadow")
    assert (await ruh_reader.rest("u1"))["status"] == "no consent"
    with stateless.allow_training("training: on"):
        assert (await ruh_reader.rest("u1"))["status"] == "skipped"  # no weights yet


def _fake_version(home, name: str, learned: list[str]) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / f"{name}.pt").write_bytes(b"weights of " + name.encode())
    (home / f"{name}.json").write_text(json.dumps({"learned": learned, "name": name}))
    (home / f"{name}.reads.json").write_text("{}")


def test_forgetting_a_chat_drops_every_version_that_learned_from_it(reader_home):
    said = "Mujhe kal ka mausam batao"
    _fake_version(reader_home, "base", [])
    _fake_version(reader_home, "previous", [])
    _fake_version(reader_home, "current", [ruh_reader.text_digest(said)])
    assert ruh_reader.forget(["something else"]) == 0
    assert ruh_reader.forget([said]) == 1
    assert ruh_reader.manifest("current")["name"] == "previous"
    assert ruh_reader.manifest("previous") is None
    # When the previous version learned from it too, the base (seeds only) is used.
    _fake_version(reader_home, "previous", [ruh_reader.text_digest(said)])
    _fake_version(reader_home, "current", [ruh_reader.text_digest(said)])
    assert ruh_reader.forget([f"  {said} "]) == 2
    assert ruh_reader.manifest("current")["name"] == "base"


def test_rollback_restores_the_previous_version(reader_home):
    assert ruh_reader.rollback() is False
    _fake_version(reader_home, "previous", [])
    _fake_version(reader_home, "current", ["x"])
    assert ruh_reader.rollback() is True
    assert ruh_reader.manifest("current")["name"] == "previous"


# ── with torch: the network, training, shadow and on ─────────────────────


def test_every_language_is_scored_in_one_batch_and_padding_changes_nothing():
    torch = pytest.importorskip("torch")
    from tadbir.ruh_reader import net

    torch.manual_seed(0)
    model = net.Reader(net.Config(**TINY))
    texts = ["hi", "kya haal hai", "آپ کیسے ہیں"]
    scores, tokens = net.score(model, texts, [0, 1, 2, 3, 4])
    assert len(scores) == 3 and all(len(row) == 5 for row in scores)
    assert tokens == [2, 12, len("آپ کیسے ہیں".encode())]  # bytes; the end is not scored
    with_end, counted = net.score(model, texts, [0, 1, 2, 3, 4], ends=True)
    assert counted == [3, 13, tokens[2] + 1] and with_end[0][0] < scores[0][0]
    alone, _ = net.score(model, [texts[1]], [0, 1, 2, 3, 4])
    assert alone[0] == pytest.approx(scores[1], abs=1e-4)
    assert all(value < 0 for row in scores for value in row)


def test_decoding_with_the_cache_matches_a_full_forward_pass():
    torch = pytest.importorskip("torch")
    from tadbir.ruh_reader import net

    torch.manual_seed(1)
    model = net.Reader(net.Config(**TINY)).eval()
    tokens = torch.tensor([[net.lang_token(2), *b"salaam dost"]])
    full, _ = model(tokens)
    first, cache = model(tokens[:, :4])
    steps = [first]
    for position in range(4, tokens.shape[1]):
        logits, cache = model(tokens[:, position : position + 1], cache)
        steps.append(logits)
    assert torch.allclose(full, torch.cat(steps, dim=1), atol=1e-5)
    made = net.generate(model, 2, "salaam", 5)
    assert isinstance(made, bytes) and len(made) <= 5


def test_int8_scores_stay_close_to_fp32():
    torch = pytest.importorskip("torch")
    from tadbir.ruh_reader import net

    torch.manual_seed(2)
    model = net.Reader(net.Config(**TINY)).eval()
    small = net.quantized(model)
    fp32, _ = net.score(model, ["what is the time"], [0, 1])
    int8, _ = net.score(small, ["what is the time"], [0, 1])
    assert int8[0] == pytest.approx(fp32[0], rel=0.05)


def _train_split(text: str) -> str:
    """A variant of ``text`` whose group falls in the training split."""
    for n in range(200):
        candidate = f"{text} {'x' * n}" if n else text
        if ruh_reader.part(ruh_reader.group_of(candidate)) == "train":
            return candidate
    raise AssertionError("no variant in the training split")


def test_no_quranic_span_reaches_the_loss(reader_home, few_seeds):
    pytest.importorskip("torch")
    quote = _quote()
    quoted = [
        (_train_split(quote), "ar"),
        (_train_split(f"my favourite ayah is {quote}"), "en"),
        (_train_split("اذْكُر رَّبَّكَ إِذَا نَسِيتَ"), "ar"),
    ]
    seen: list[bytes] = []

    def hook(labels, mask):
        for row, keep in zip(labels.tolist(), mask.tolist(), strict=True):
            seen.append(bytes(t for t, k in zip(row, keep, strict=True) if k and t < 256))

    built = ruh_reader.build(
        0,
        config=TINY,
        plan={"epochs": 2, "seconds": 60, "batch": 8},
        rows=[*few_seeds, *quoted],
        loss_hook=hook,
        calibrate=False,
        log=lambda _line: None,
    )
    assert seen and built.manifest["scripture_set_aside"] >= 3
    stream = b"\n".join(seen)
    words = ruh_reader.reading(quote).split()
    assert len(words) >= 3
    for start in range(len(words) - 2):  # no run of three of the ayah's words
        assert " ".join(words[start : start + 3]).encode() not in stream
    assert ruh_reader.reading("رَّبَّكَ إِذَا نَسِيتَ").encode() not in stream


def _tiny_reader(languages, b: float, adopted: bool):
    import torch

    from tadbir.ruh_reader import net

    torch.manual_seed(3)
    model = net.Reader(net.Config(**TINY)).eval()
    manifest = {
        "corpus_sha256": ruh_reader.corpus_digest(ruh_reader.seeds()),
        "languages": list(languages),
        "config": model.config.to_dict(),
        "fit": {"kappa": 1.0, "gamma": 0.0, "ref": 20.0, "b": b},
        "adopted": adopted,
        "learned": [],
        "tests": 1,
    }
    return ruh_reader.Built(model, manifest, [], [], None)


def test_shadow_computes_the_reader_but_never_changes_the_decision(reader_home, monkeypatch):
    pytest.importorskip("torch")
    languages = tuple(dict.fromkeys(label for _t, label in ruh_reader.seeds()))
    ruh_reader.install(_tiny_reader(languages, b=1.0, adopted=True))
    assert ruh_reader.load() is not None
    text = "kal milte hain"
    monkeypatch.setenv("MIZAN_RUH_READER", "shadow")
    read_before = ruh_reader.status()["shadow"]["read"]
    assert lughah.posterior(text) == lughah.naive_posterior(text)
    assert ruh_reader.status()["shadow"]["read"] == read_before + 1
    monkeypatch.setenv("MIZAN_RUH_READER", "on")
    weighed = lughah.posterior(text)
    assert weighed != lughah.naive_posterior(text)
    assert sum(weighed.values()) == pytest.approx(1.0)


def test_on_without_a_passed_gate_is_factor_one(reader_home, monkeypatch):
    pytest.importorskip("torch")
    languages = tuple(dict.fromkeys(label for _t, label in ruh_reader.seeds()))
    ruh_reader.install(_tiny_reader(languages, b=1.0, adopted=False))
    assert ruh_reader.load() is not None
    monkeypatch.setenv("MIZAN_RUH_READER", "on")
    assert lughah.posterior("kal milte hain") == lughah.naive_posterior("kal milte hain")


def test_a_reader_of_another_corpus_is_not_loaded(reader_home):
    pytest.importorskip("torch")
    built = _tiny_reader(("en", "ar"), b=1.0, adopted=True)
    built.manifest["corpus_sha256"] = "0" * 64
    ruh_reader.install(built)
    assert ruh_reader.load() is None


def test_a_reader_that_does_not_beat_lughah_is_not_adopted(reader_home, few_seeds):
    pytest.importorskip("torch")
    built = ruh_reader.build(
        0,
        config=TINY,
        plan={"epochs": 1, "seconds": 30, "batch": 8},
        calibrate=False,
        log=lambda _line: None,
    )
    assert built.manifest["adopted"] is False
    assert built.manifest["gate"]["adopted"] is False
    assert set(built.manifest["held_out_bpb"]) <= set(built.manifest["languages"])


@pytest.fixture
def tiny_installed(reader_home, few_seeds):
    pytest.importorskip("torch")
    built = ruh_reader.build(
        0,
        config=TINY,
        plan={"epochs": 1, "seconds": 30, "batch": 8},
        calibrate=False,
        log=lambda _line: None,
    )
    ruh_reader.install(built)
    return built


NIGHT_WORDS = ["the weather is nice today", "please remind me after lunch"]


def _both_agree(monkeypatch):
    """Lughah and the reader read each text alike (a tiny untrained reader would not)."""

    def agreed(text, model, fit, languages):
        posterior = lughah.naive_posterior(text)
        return list(languages).index(max(posterior, key=posterior.__getitem__))

    monkeypatch.setattr(ruh_reader, "agreed_language", agreed)


def test_a_night_that_is_not_better_keeps_the_current_version(tiny_installed, monkeypatch):
    _both_agree(monkeypatch)
    monkeypatch.setattr(ruh_reader, "no_worse", lambda old, new, truths: (False, 1.0, 0.1, 0.2))
    before = ruh_reader.manifest("current")
    with stateless.allow_training("training: on"):
        report = ruh_reader.learn(NIGHT_WORDS, seconds=30)
    assert report["status"] == "kept" and report["learned"] == 0 and report["steps"] > 0
    assert ruh_reader.manifest("current") == before and ruh_reader.manifest("previous") is None


def test_a_promoted_night_keeps_the_previous_and_is_forgotten_with_the_chat(
    tiny_installed, monkeypatch
):
    _both_agree(monkeypatch)
    monkeypatch.setattr(ruh_reader, "no_worse", lambda old, new, truths: (True, 0.0, 0.2, 0.1))
    with stateless.allow_training("training: on"):
        report = ruh_reader.learn([*NIGHT_WORDS, _quote()], seconds=30)
        assert report["status"] == "promoted" and report["learned"] == 2
        assert report["scripture"] == 1  # the ayah is never learned
        again = ruh_reader.learn(NIGHT_WORDS, seconds=30)
    assert again["status"] == "nothing new" and again["seen"] == 2
    current = ruh_reader.manifest("current")
    assert {ruh_reader.text_digest(text) for text in NIGHT_WORDS} == set(current["learned"])
    assert current["tests"] == 2 and ruh_reader.manifest("previous")["learned"] == []
    assert ruh_reader.forget([NIGHT_WORDS[0]]) == 1
    assert ruh_reader.manifest("current")["learned"] == []
    assert ruh_reader.rollback() is False  # the previous one became current


def test_the_night_learns_only_reviewed_words_of_consenting_people(reader_home, tmp_path):
    import sqlite3

    from learner.review_contract import content_hash
    from memory.mahw import private_dir

    folder = private_dir("u1")
    folder.mkdir(parents=True)
    conn = sqlite3.connect(folder / "learner.sqlite3")
    conn.execute(
        "CREATE TABLE interactions (id INTEGER PRIMARY KEY, prompt TEXT, response TEXT, "
        "provider TEXT, model TEXT, review_status TEXT, reviewed_content_hash TEXT)"
    )
    rows = [
        ("accepted words", "a", "p", "m", "accepted"),
        ("unreviewed words", "a", "p", "m", "unreviewed"),
        ("rejected words", "a", "p", "m", "rejected"),
        ("changed after review", "a", "p", "m", "accepted"),
    ]
    for prompt, response, provider, model, status in rows:
        digest = content_hash(prompt, response, provider, model)
        if prompt.startswith("changed"):
            digest = content_hash("what was reviewed", response, provider, model)
        conn.execute(
            "INSERT INTO interactions (prompt, response, provider, model, review_status, "
            "reviewed_content_hash) VALUES (?, ?, ?, ?, ?, ?)",
            (prompt, response, provider, model, status, digest),
        )
    conn.commit()
    conn.close()
    assert ruh_reader.reviewed_words("u1") == ["accepted words"]
    assert ruh_reader.reviewed_words("someone else") == []


# ── the reader's own corpus (sources, licences, what is never trained on) ─


def _seed_in(split: str) -> str:
    """A seed of five words or more whose group falls in ``split``."""
    for text, _label in ruh_reader.seeds():
        if len(text.split()) >= 5 and ruh_reader.part(ruh_reader.group_of(text)) == split:
            return text
    raise AssertionError(split)


def _word(n: int) -> str:
    return "z" + "".join(chr(97 + int(digit)) for digit in str(n))


def _said_with_quote() -> str:
    """A line that is not a seed but holds eight words of an ayah."""
    return "قال " + " ".join(_quote().split()[:8])


def _fake_sources(tmp_path, tatoeba: dict, massive: dict, hinglish: list) -> dict:
    import bz2
    import csv
    import io
    import tarfile

    folder = tmp_path / "downloads"
    folder.mkdir()
    paths = {}
    for code, rows in tatoeba.items():
        path = folder / f"{code}_sentences.tsv.bz2"
        with bz2.open(path, "wt", encoding="utf-8") as handle:
            handle.writelines(f"{number}\t{code}\t{text}\n" for number, text in rows)
        paths[f"tatoeba-{code}"] = path
    paths["massive"] = folder / "massive.tar.gz"
    with tarfile.open(paths["massive"], "w:gz") as archive:
        for locale, rows in massive.items():
            body = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode()
            info = tarfile.TarInfo(f"1.1/data/{locale}.jsonl")
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
    paths["hinglish-1m"] = folder / "hinglish.csv"
    with paths["hinglish-1m"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["input", "output"])
        writer.writerows(hinglish)
    return paths


def test_the_corpus_records_its_sources_and_never_holds_what_is_held_out(tmp_path, monkeypatch):
    from tadbir.ruh_reader import corpus

    monkeypatch.setenv("MIZAN_TALIM", "off")
    monkeypatch.setattr(corpus, "KEEP", {})  # every line of the small fake sources
    first = (lughah.CORPUS / "en.tsv").read_text(encoding="utf-8").splitlines()[0]
    seed_id = first.partition("\t")[0].split(":")[1]
    held, dev = _seed_in("held_out"), _seed_in("dev")
    request = "wake me up at seven tomorrow"
    ordinary = [
        "The library opens early on weekdays.",
        "We walked along the river after dinner.",
        "Her garden is full of tomatoes this year.",
    ]
    paths = _fake_sources(
        tmp_path,
        tatoeba={
            "eng": [
                (seed_id, "A sentence the seeds already hold by its id."),
                ("900000001", held.upper() + "!!"),
                ("900000002", dev),
                *((str(900000010 + i), text) for i, text in enumerate(ordinary)),
            ],
            "ara": [("900000020", _said_with_quote()), ("900000021", "ذهبنا إلى السوق صباحا")],
        },
        massive={
            "en-US": [
                {"id": "1", "partition": "train", "utt": "set an alarm for six"},
                {"id": "2", "partition": "train", "utt": request.title()},
                {"id": "2", "partition": "test", "utt": request},
                {"id": "3", "partition": "test", "utt": "stop"},
                {"id": "4", "partition": "dev", "utt": "what is on my calendar"},
            ],
            "ar-SA": [
                {"id": "5", "partition": "train", "utt": "reggae music"},
                {"id": "6", "partition": "train", "utt": "شغل الموسيقى في المطبخ"},
                {"id": "2", "partition": "test", "utt": "صحيني الساعة سبعة بكرة"},
            ],
        },
        hinglish=[
            (f"kal milte hain {_word(n)}", f"haan yaar zaroor {_word(n)}") for n in range(40)
        ],
    )
    out = tmp_path / "corpus"
    manifest = corpus.build(
        paths=paths,
        out=out,
        scripture=ruh_reader.scripture,
        bytes_per_language=10**6,
        hinglish_count=100,
        log=lambda _line: None,
    )
    sources = {item["name"]: item for item in manifest["sources"]}
    assert set(sources) == {"tatoeba-eng", "tatoeba-ara", "massive", "hinglish-1m"}
    assert sources["massive"]["licence"].startswith("CC BY 4.0")
    assert sources["hinglish-1m"]["licence"].startswith("MIT")
    assert sources["tatoeba-eng"]["licence"].startswith("CC BY 2.0 FR")
    assert all(len(item["sha256"]) == 64 for item in sources.values())
    assert manifest["seeds_sha256"] == ruh_reader.corpus_digest(ruh_reader.seeds())
    rows = (out / "train.tsv").read_text(encoding="utf-8").splitlines()
    assert rows and all(row.split(":")[0] in {"tatoeba", "massive", "hinglish-1m"} for row in rows)
    found = corpus.load(out)
    assert found is not None
    texts = {text for text, _label in found.train}
    assert {"set an alarm for six", "شغل الموسيقى في المطبخ", *ordinary} <= texts
    trained = {ruh_reader.group_of(text) for text in texts}
    guarded = {
        ruh_reader.group_of(text)
        for text, _label in ruh_reader.seeds()
        if ruh_reader.part(ruh_reader.group_of(text)) != "train"
    }
    assert not trained & guarded  # no held-out or development seed's words
    assert not trained & {ruh_reader.group_of(text) for text, _l, _g in found.short}
    assert not any("reggae" in text or "قال" in text for text in texts)
    dropped = manifest["dropped"]
    assert dropped["tatoeba-eng"]["seed id"] == 1 and dropped["tatoeba-eng"]["seed words"] == 2
    assert dropped["tatoeba-ara"]["scripture"] == 1
    assert dropped["massive"]["held out here"] == 1 and dropped["massive"]["script"] == 1
    assert dropped["massive"]["partition dev"] == 1
    short = {(label, group): text for text, label, group in found.short}
    assert short[("en", "massive:2")] == request  # one request in two languages, one group
    assert short[("ar", "massive:2")] == "صحيني الساعة سبعة بكرة"
    assert ("en", "massive:3") not in short  # a single word is not a 3-8 word message
    roman = [group for _text, label, group in found.short if label == "hi-latn"]
    assert roman and all(ruh_reader.part(group) == "held_out" for group in roman)
    # A corpus that changed on disk, or was built against other seeds, is not used.
    (out / "train.tsv").write_text("\n".join(rows[1:]) + "\n", encoding="utf-8")
    assert corpus.load(out) is None
    corpus.build(paths=paths, out=out, scripture=ruh_reader.scripture, log=lambda _line: None)
    stale = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    stale["seeds_sha256"] = "0" * 64
    (out / "manifest.json").write_text(json.dumps(stale), encoding="utf-8")
    assert corpus.load(out) is None


def test_a_line_is_kept_only_in_its_languages_script():
    from tadbir.ruh_reader import corpus

    assert not corpus.own_script("reggae music", "ar")
    assert corpus.own_script("سلام olly قفل اللمبه لو سمحت", "ar")
    assert corpus.own_script("kal milte hain", "hi-latn")
    assert not corpus.own_script("कल मिलते हैं", "hi-latn")
    assert corpus.own_script("कल मिलते हैं", "hi")
    assert not corpus.own_script("ok", "en")  # too few letters to say


def test_a_pinned_source_that_changed_is_refused(tmp_path):
    import dataclasses
    import hashlib

    import httpx

    from tadbir.ruh_reader import corpus

    body = b"input,output\nkal milte hain,haan\n"
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, content=body))
    )
    pinned = corpus.Source(
        "x", "https://example.org/x.csv", "MIT", "x.csv", hashlib.sha256(b"pinned").hexdigest()
    )
    with pytest.raises(corpus.Mismatch):
        corpus.download(pinned, tmp_path / "x", client)
    assert list((tmp_path / "x").iterdir()) == []
    same = dataclasses.replace(pinned, sha256=hashlib.sha256(body).hexdigest())
    assert corpus.download(same, tmp_path / "x", client)["sha256"] == same.sha256
    assert (tmp_path / "x" / "x.csv").read_bytes() == body
    assert corpus.download(same, tmp_path / "x", client)["cached"] is True


def test_a_reader_trained_on_the_corpus_never_sees_held_out_words(reader_home, few_seeds):
    pytest.importorskip("torch")
    from tadbir.ruh_reader import corpus

    held, label = next(
        (text, found)
        for text, found in few_seeds
        if len(text.split()) >= 5 and ruh_reader.part(ruh_reader.group_of(text)) == "held_out"
    )
    short = [
        ("wake me up at seven tomorrow", "en", "massive:2"),
        ("kal subah jaldi uthana hai", "hi-latn", "g"),
    ]
    fresh = "the river runs past the old mill"
    extra = corpus.Corpus(
        train=[
            (fresh, "en"),
            (held + "!", label),  # a held-out seed's words
            ("Wake me up at seven tomorrow!", "en"),  # a held-out short message
            (_said_with_quote(), "ar"),  # the Quran's words
        ],
        short=short,
        manifest={
            "train": {"sha256": "t"},
            "short": {"sha256": "s"},
            "scripture": {"iqtibas": True},
            "sources": [{"name": "massive", "licence": "CC BY 4.0", "sha256": "x"}],
        },
    )
    rows: set[bytes] = set()

    def hook(labels, mask):
        for row, keep in zip(labels.tolist(), mask.tolist(), strict=True):
            rows.add(bytes(t for t, k in zip(row, keep, strict=True) if k and t < 256))

    built = ruh_reader.build(
        0,
        config=TINY,
        plan={"epochs": 1, "seconds": 30, "batch": 8, "checks": 3},
        corpus=extra,
        loss_hook=hook,
        calibrate=False,
        log=lambda _line: None,
    )
    report = built.manifest["corpus"]
    assert report["lines"] == 1 and report["held_out_dropped"] == 2
    assert report["scripture_set_aside"] == 1 and report["sources"][0]["licence"] == "CC BY 4.0"
    context = TINY["context"]
    assert ruh_reader.reading(fresh).encode()[:context] in rows
    for text in (held, "wake me up at seven tomorrow"):
        assert ruh_reader.reading(text).encode()[:context] not in rows
    assert [read.group for read in built.short] == ["massive:2", "g"]
    assert built.manifest["short"]["n"] == 2
    assert built.manifest["short"]["check"]["n"] == 2  # reported; the gate is the seeds'
    assert built.manifest["gate"]["n"] == len(built.held_out)


def test_reading_in_smaller_passes_changes_nothing():
    torch = pytest.importorskip("torch")
    from tadbir.ruh_reader import net

    torch.manual_seed(5)
    model = net.Reader(net.Config(**TINY))
    texts = [f"message {_word(n)} " * (1 + n % 4) for n in range(40)]
    one, counts = net.score(model, texts, [0, 1, 2])
    small, again = net.score(model, texts, [0, 1, 2], tokens_per_pass=200)
    assert counts == again
    for a, b in zip(one, small, strict=True):
        assert a == pytest.approx(b, abs=1e-4)


def test_dev_checks_can_be_spread_over_one_long_pass():
    torch = pytest.importorskip("torch")
    from tadbir.ruh_reader import net

    torch.manual_seed(4)
    model = net.Reader(net.Config(**TINY))
    lines = [(f"line number {_word(n)}", n % 2) for n in range(64)]
    plan = net.Plan(seconds=60, epochs=1, batch=8, warmup=2, checks=4)
    report = net.train(model, lines, plan, dev=lines[:8])
    assert report["steps"] == 8
    assert [item["step"] for item in report["history"]] == [2, 4, 6, 8]
