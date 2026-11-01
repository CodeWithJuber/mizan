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


def test_a_language_taught_on_one_server_keeps_its_share_and_is_not_the_readers(
    reader_home, monkeypatch
):
    """Production taught Lughah Tamil (Ta'lim, MASSIVE): the reader's corpus is
    still the shipped seeds, so weights trained elsewhere are found, and Tamil's
    probability is left as Lughah gives it while the reader weighs the rest."""
    pytest.importorskip("torch")
    from tadbir import talim

    before = ruh_reader.corpus_digest(ruh_reader.seeds())
    monkeypatch.setattr(
        talim, "rows", lambda model: [("நான் நாளை வருகிறேன்", "ta", "b1")] if model == "lughah" else []
    )
    assert ("நான் நாளை வருகிறேன்", "ta") in lughah.corpus()
    assert ruh_reader.corpus_digest(ruh_reader.seeds()) == before
    languages = tuple(dict.fromkeys(label for _t, label in ruh_reader.seeds()))
    ruh_reader.install(_tiny_reader(languages, b=1.0, adopted=True))
    assert ruh_reader.load() is not None
    found = {code: 0.6 / len(languages) for code in languages} | {"ta": 0.4}
    monkeypatch.setenv("MIZAN_RUH_READER", "on")
    weighed = ruh_reader.weigh(found, "kal milte hain")
    assert weighed["ta"] == found["ta"]
    assert sum(weighed.values()) == pytest.approx(1.0)
    assert sum(weighed[code] for code in languages) == pytest.approx(0.6)
    assert weighed != found
    monkeypatch.setenv("MIZAN_RUH_READER", "shadow")
    assert ruh_reader.weigh(found, "kal milte hain") == found


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
    assert sources["hinglish-1m"]["trained_on"] is False  # GPT-4o-mini wrote it: measured only
    assert sources["tatoeba-eng"]["licence"].startswith("CC BY 2.0 FR")
    assert all(len(item["sha256"]) == 64 for item in sources.values())
    assert manifest["seeds_sha256"] == ruh_reader.corpus_digest(ruh_reader.seeds())
    rows = (out / "train.tsv").read_text(encoding="utf-8").splitlines()
    assert rows and all(row.split(":")[0] in {"tatoeba", "massive"} for row in rows)
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


def test_trained_weights_are_kept_before_reading_and_found_again(
    reader_home, few_seeds, tmp_path, monkeypatch
):
    torch = pytest.importorskip("torch")
    from tadbir.ruh_reader import net

    kept = tmp_path / "weights"
    settings = {
        "config": TINY,
        "plan": {"epochs": 1, "seconds": 30, "batch": 8},
        "calibrate": False,
    }

    def stopped(*_args, **_kwargs):  # the container restarts while the reader reads
        raise KeyboardInterrupt

    with monkeypatch.context() as patched:
        patched.setattr(ruh_reader, "score_reads", stopped)
        with pytest.raises(KeyboardInterrupt):
            ruh_reader.build(0, trained=kept, log=lambda _line: None, **settings)
    marker = json.loads((kept / "seed0.trained").read_text(encoding="utf-8"))
    assert (kept / marker["weights"]).exists() and marker["report"]["steps"] > 0
    first = net.load(kept / marker["weights"]).state_dict()

    def no_training(*_args, **_kwargs):
        raise AssertionError("trained again")

    monkeypatch.setattr(net, "train", no_training)
    lines: list[str] = []
    built = ruh_reader.build(0, trained=kept, log=lines.append, **settings)
    assert any("already trained" in line for line in lines)
    assert built.manifest["training"]["steps"] == marker["report"]["steps"]
    assert all(torch.equal(first[k], v) for k, v in built.model.state_dict().items())
    assert "held_out_bpb" in built.manifest

    # Another seed, other settings or damaged weights are another run's: not used.
    model = net.Reader(net.Config(**TINY))
    assert ruh_reader.load_trained(kept, 1, marker["key"], model) is None
    assert ruh_reader.load_trained(kept, 0, "0" * 64, model) is None
    (kept / marker["weights"]).write_bytes(b"not the weights")
    assert ruh_reader.load_trained(kept, 0, marker["key"], model) is None


def test_the_trained_key_changes_with_what_training_depends_on():
    lines, dev = [("hello there", 0)], [("kya haal hai", 1)]
    key = ruh_reader.trained_key(0, TINY, {"epochs": 1}, lines, dev)
    assert key == ruh_reader.trained_key(0, dict(TINY), {"epochs": 1}, list(lines), list(dev))
    assert key != ruh_reader.trained_key(1, TINY, {"epochs": 1}, lines, dev)
    assert key != ruh_reader.trained_key(0, TINY, {"epochs": 2}, lines, dev)
    assert key != ruh_reader.trained_key(0, TINY, {"epochs": 1}, [("hello there", 1)], dev)
    assert key != ruh_reader.trained_key(0, TINY, {"epochs": 1}, lines, [])


# ── v1.1: calibrated on one half of real short messages, gated on the other ─


def test_kappa_alone_is_calibrated_when_gamma_is_held():
    # Sure of itself and wrong twice in twenty: a smaller κ is better calibrated.
    lm = [[-10.0, -30.0]] * 18 + [[-30.0, -10.0]] * 2
    truths, tokens = [0] * 20, [40] * 20

    def loss(kappa: float) -> float:
        rows = [
            ruh_reader.reader_log_posterior(r, m, kappa, 0.5, 20.0)
            for r, m in zip(lm, tokens, strict=True)
        ]
        return ruh_reader.log_loss(rows, truths)

    kappa, gamma, fitted = ruh_reader.fit_reader(lm, tokens, truths, ref=20.0, gamma=0.5)
    assert gamma == 0.5 and kappa < 1.0
    best = min((math.exp(x / 200) for x in range(-1381, 1)), key=loss)
    assert kappa == pytest.approx(best, rel=0.01) and fitted == pytest.approx(loss(kappa))
    reads = [
        ruh_reader.Read(
            text="x",
            truth=t,
            group=f"g{i}",
            own="x",
            lughah=[math.log(0.6), math.log(0.4)],
            lm=row,
            tokens=m,
        )
        for i, (row, m, t) in enumerate(zip(lm, tokens, truths, strict=True))
    ]
    fit = ruh_reader.fit_on(reads, 20.0, gamma=0.5)
    assert (fit.gamma, fit.ref) == (0.5, 20.0) and fit.kappa == pytest.approx(kappa)


def test_the_validation_slices_are_fresh_and_their_halves_fixed():
    from tadbir.ruh_reader import corpus

    seen = "set an alarm for six tomorrow"
    dev = [
        corpus.Line(f"massive:en-US:{n}", "en", f"please play the song {_word(n)} now", "dev")
        for n in range(60)
    ]
    dev += [
        corpus.Line(f"massive:hi-IN:{n}", "hi", f"गाना {_word(n)} चलाओ अभी", "dev")
        for n in range(60)
    ]
    dev += [
        corpus.Line("massive:en-US:900", "en", seen.title(), "dev"),  # words already seen
        corpus.Line("massive:en-US:901", "en", "stop", "dev"),  # not 3 to 8 words
        corpus.Line("massive:ar-SA:902", "ar", "reggae music please now", "dev"),  # not Arabic
        corpus.Line("massive:en-US:903", "en", f"please play the song {_word(1)} now!", "dev"),
    ]
    roman = [
        corpus.Line(f"hinglish-1m:{n}:{column}", "hi-latn", f"{column} kal milte hain {_word(n)}")
        for n in range(600)
        for column in ("input", "output")
    ]
    excluded = {ruh_reader.group_of(seen)}
    chosen = corpus.pick_validation(dev, roman, excluded)
    assert chosen == corpus.pick_validation(list(reversed(dev)), list(reversed(roman)), excluded)
    texts = {line.text for line, _group, _half in chosen}
    assert not texts & {seen.title(), "stop", "reggae music please now"}
    twice = {f"please play the song {_word(1)} now", f"please play the song {_word(1)} now!"}
    assert len(texts & twice) == 1  # the same words are one message
    massive = [(line, group, where) for line, group, where in chosen if line.label != "hi-latn"]
    for line, group, where in massive:
        request = line.source.rsplit(":", 1)[1]
        assert group == f"massive:{request}" and where == corpus.half(group)
    assert {where for _l, _g, where in massive} == set(corpus.HALVES)
    fresh = [(line, group, where) for line, group, where in chosen if line.label == "hi-latn"]
    assert fresh
    for line, group, where in fresh:
        assert not corpus._kept(line.source, corpus.KEEP["hinglish-1m"])  # v1 never read it
        assert ruh_reader.part(group) == "held_out" and group == ruh_reader.group_of(line.text)
        assert where == corpus.half(line.source.rsplit(":", 1)[0])  # the conversation's half
    for name in corpus.HALVES:  # Roman Hindi/Urdu weighs as one language of the half
        per_language = [
            sum(1 for line, _g, h in massive if h == name and line.label == label)
            for label in ("en", "hi")
        ]
        assert sum(1 for _l, _g, h in fresh if h == name) == round(sum(per_language) / 2)


def test_validation_slices_are_built_beside_the_corpus_and_checked(tmp_path, monkeypatch):
    from tadbir.ruh_reader import corpus

    monkeypatch.setenv("MIZAN_TALIM", "off")
    measured = "wake me up at seven tomorrow"
    paths = _fake_sources(
        tmp_path,
        tatoeba={"eng": [("900000010", "The library opens early on weekdays.")]},
        massive={
            "en-US": [
                {"id": "1", "partition": "train", "utt": "set an alarm for six please"},
                {"id": "2", "partition": "test", "utt": measured},
                {"id": "3", "partition": "dev", "utt": "what is on my calendar today"},
                {"id": "4", "partition": "dev", "utt": "Set an alarm for six, please!"},
                {"id": "5", "partition": "dev", "utt": measured.upper()},
            ],
        },
        hinglish=[
            (f"kal milte hain {_word(n)}", f"haan yaar zaroor {_word(n)}") for n in range(400)
        ],
    )
    out = tmp_path / "corpus"

    def built(count: int) -> None:
        corpus.build(
            paths=paths,
            out=out,
            scripture=ruh_reader.scripture,
            hinglish_count=count,
            log=lambda _line: None,
        )

    built(20)
    made = corpus.build_validation(out, paths=paths, log=lambda _line: None)
    assert made["settings"]["hinglish_read_share"] == corpus.KEEP["hinglish-1m"]
    assert made["dropped"]["massive: other partitions"] == 2
    assert made["dropped"]["massive: seen words"] == 2  # trained on, or measured in v1
    rows = corpus.load_validation(out)
    assert rows is not None and len(rows) == made["lines"]
    english = [(text, group) for text, label, group, _half in rows if label == "en"]
    assert english == [("what is on my calendar today", "massive:3")]
    found = corpus.load(out)
    assert found is not None
    trained = {ruh_reader.group_of(text) for text, _label in found.train}
    short = {ruh_reader.group_of(text) for text, _label, _group in found.short}
    assert not {ruh_reader.group_of(text) for text, *_ in rows} & (trained | short)
    assert all(name in corpus.HALVES for *_, name in rows)
    # A file changed since, or a corpus rebuilt under it, and the slices are not used.
    body = (out / "validation.tsv").read_text(encoding="utf-8")
    (out / "validation.tsv").write_text(body.replace("calendar", "diary"), encoding="utf-8")
    assert corpus.load_validation(out) is None
    (out / "validation.tsv").write_text(body, encoding="utf-8")
    assert corpus.load_validation(out) is not None
    built(5)
    assert corpus.load_validation(out) is None


def _eval_script():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "ruh_reader_eval.py"
    spec = importlib.util.spec_from_file_location("ruh_reader_eval", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v11_fits_on_the_calibration_half_and_gates_on_the_other(reader_home, few_seeds):
    pytest.importorskip("torch")
    evaluation = _eval_script()
    built = ruh_reader.build(
        0,
        config=TINY,
        plan={"epochs": 1, "seconds": 30, "batch": 8},
        calibrate=False,
        log=lambda _line: None,
    )
    languages = built.manifest["languages"]
    rows = [
        ("kal subah jaldi uthana hai", "hi-latn", "r1", "calibration"),
        ("wake me up at seven", "en", "massive:1", "calibration"),
        ("مجھے سات بجے جگا دو", "ur", "massive:1", "calibration"),
        ("please turn the lights off", "en", "massive:2", "gate"),
        ("mujhe kal yaad dila dena", "hi-latn", "r2", "gate"),
        ("बत्ती बंद कर दो", "hi", "massive:2", "gate"),
    ]
    halves = evaluation.validation_reads(built, rows, languages)
    assert [len(halves[name]) for name in ("calibration", "gate")] == [3, 3]
    development = ruh_reader.Fit(**built.manifest["fit"])
    found = evaluation.validate(built, halves, languages)
    expected = ruh_reader.fit_on(halves["calibration"], development.ref, gamma=development.gamma)
    assert found["fit"] == expected.to_dict()  # the calibration half only, γ and ñ held
    assert found["test"] == 2 and found["gate"]["needed"] == pytest.approx(120)
    assert found["gate"]["n"] == 3 and found["gate"]["groups"] == 2  # the gate half only
    assert found["groups"] == {"calibration": 2, "gate": 2}
    assert found["adopted"] == (found["gate"]["adopted"] and found["fit"]["b"] > 0)
    assert found["held_out_seeds"]["check"]["n"] == len(built.held_out)
    again = evaluation.validate(built, halves, languages, test=3)
    assert again["gate"]["needed"] == pytest.approx(240)
    assert any(line.startswith("GATE") for line in evaluation.validation_table(found))


# ── test 3: the Roman rule, near copies, the fresh slices ────────────────


def test_a_near_copy_is_two_edits_or_one_word_away():
    from tadbir.ruh_reader import corpus

    seen = corpus.Near(["Set an alarm for six, please!", "play some jazz music now"])
    assert "set an alarm for six please" in seen  # the same words
    assert "set an alarm for sixx please" in seen  # one edit
    assert "set an alarm for six" in seen  # one word fewer
    assert "please play some jazz music now" in seen  # one word more
    assert "play some rock music now" not in seen  # another word: four edits
    assert "set an alarm for seven please" not in seen
    assert corpus.within("kitten", "sitting", 3) and not corpus.within("kitten", "sitting", 2)


def test_the_near_index_finds_what_comparing_every_pair_finds():
    import random

    from tadbir.ruh_reader import corpus

    def distance(a: str, b: str) -> int:
        previous = list(range(len(b) + 1))
        for i, x in enumerate(a, 1):
            current = [i]
            for j, y in enumerate(b, 1):
                current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
            previous = current
        return previous[-1]

    def one_more(a: tuple, b: tuple) -> bool:
        return len(a) == len(b) + 1 and any(a[:i] + a[i + 1 :] == b for i in range(len(a)))

    rng = random.Random(0)
    vocabulary = ["set", "an", "alarm", "for", "six", "play", "jazz", "kal", "milte", "hain"]

    def sentence() -> str:
        return " ".join(rng.choice(vocabulary) for _ in range(rng.randint(1, 10)))

    def changed(text: str) -> str:
        letters = list(text)
        for _ in range(rng.randint(0, 3)):
            at = rng.randrange(len(letters) + 1)
            if rng.random() < 0.5 or at == len(letters):
                letters.insert(at, rng.choice("abcde "))
            else:
                letters[at] = rng.choice("abcde ")
        return "".join(letters)

    seen = [sentence() for _ in range(150)]
    index = corpus.Near(seen)
    checked = 0
    for _ in range(600):
        text = changed(rng.choice(seen)) if rng.random() < 0.7 else sentence()
        said = ruh_reader.reading(text)
        if not 3 <= len(said.split()) <= 8:
            continue
        words = tuple(said.split())
        expected = any(
            distance(said, ruh_reader.reading(other)) <= 2
            or one_more(words, tuple(ruh_reader.reading(other).split()))
            or one_more(tuple(ruh_reader.reading(other).split()), words)
            for other in seen
        )
        assert (text in index) == expected, text
        checked += 1
    assert checked > 200


def test_a_roman_row_counts_only_where_qamus_reads_a_hindi_word():
    from tadbir.ruh_reader import corpus

    assert corpus.roman_words("kya haal hai bhai") and corpus.roman_words("kal milte hain")
    assert not corpus.roman_words("what are you doing tonight?")
    assert not corpus.roman_words("i have a question about inheritance law.")


def _letters(n: int) -> str:
    """Eight letters fixed by n, far (in edits) from those of other n."""
    import hashlib

    digest = hashlib.sha256(str(n).encode()).hexdigest()
    return "".join(chr(97 + int(digit, 16) % 26) for digit in digest[:8])


def test_fresh_slices_hold_nothing_seen_or_near_and_the_rule_picks_their_roman_rows(
    tmp_path, monkeypatch
):
    from tadbir.ruh_reader import corpus

    monkeypatch.setenv("MIZAN_TALIM", "off")
    monkeypatch.setattr(corpus, "LABELLED", 5)
    paths = _fake_sources(
        tmp_path,
        tatoeba={"eng": [("900000010", "The library opens early on weekdays.")]},
        massive={
            "en-US": [
                {"id": "1", "partition": "train", "utt": "set an alarm for six please"},
                {"id": "2", "partition": "test", "utt": "wake me up at seven tomorrow"},
                {"id": "3", "partition": "dev", "utt": "what is on my calendar today"},
            ],
        },
        hinglish=[  # rows far apart: a near copy of a trained row is not fresh
            (f"kal {_letters(2 * n)} milte {_letters(2 * n + 1)}", f"see {_letters(-n)} there")
            for n in range(1500)
        ],
    )
    fresh = [f"how do i say {_letters(10**6 + n)} in french" for n in range(6)]
    paths["clinc150"] = tmp_path / "downloads" / "data_full.json"
    splits = {
        "train": [[text, "translate"] for text in fresh[:4]]
        + [
            ["Set an alarm for six, please!", "alarm"],  # a MASSIVE utterance's words
            ["please wake me up at seven tomorrow", "alarm"],  # one word more: near
            ["what is on my calender today", "calendar"],  # one edit: near
            ["balance", "balance"],  # not 3 to 8 words
        ],
        "oos_test": [[text, "oos"] for text in fresh[4:]] + [[fresh[0] + "!", "oos"]],
    }
    paths["clinc150"].write_text(json.dumps(splits), encoding="utf-8")
    out = tmp_path / "corpus"
    corpus.build(paths=paths, out=out, scripture=ruh_reader.scripture, log=lambda _line: None)
    corpus.build_validation(out, paths=paths, log=lambda _line: None)

    def rule(text: str) -> bool:
        return text.startswith("kal")

    first = corpus.build_fresh(out, paths=paths, labels_only=True, log=lambda _line: None)
    labels = (out / "labels.tsv").read_text(encoding="utf-8").splitlines()
    assert first["labels"] == len(labels) == 5 and not (out / "fresh.tsv").exists()
    made = corpus.build_fresh(out, paths=paths, rule=rule, log=lambda _line: None)
    assert made["labels_sha256"] == first["labels_sha256"]  # the same rows, drawn again
    rows = corpus.load_fresh(out)
    assert rows is not None and len(rows) == made["lines"]
    english = sorted(ruh_reader.reading(text) for text, label, _g, _p in rows if label == "en")
    assert english == sorted(map(ruh_reader.reading, fresh))  # nothing seen, near, short, twice
    assert made["clinc150"]["exact_massive_copies"] == 1
    roman = [text for text, label, _g, part in rows if label == "hi-latn" and part == "gate"]
    assert len(roman) == len(english) and all(rule(text) for text in roman)
    assert all(not rule(text) for text, _l, _g, part in rows if part == "rule")
    labelled = {row.split("\t", 1)[1] for row in labels}
    assert not labelled & {text for text, *_rest in rows}  # the hand-labelled rows are not measured
    found = corpus.load(out)
    validation = corpus.load_validation(out)
    assert found is not None and validation is not None
    seen = {ruh_reader.group_of(text) for text, _label in found.train}
    seen |= {ruh_reader.group_of(text) for text, *_rest in validation}
    for text, _label, group, _part in rows:
        assert group == ruh_reader.group_of(text) and group not in seen
    # Changed since, or built beside another validation file, and they are not used.
    body = (out / "fresh.tsv").read_text(encoding="utf-8")
    (out / "fresh.tsv").write_text(body.replace("french", "german"), encoding="utf-8")
    assert corpus.load_fresh(out) is None
    (out / "fresh.tsv").write_text(body, encoding="utf-8")
    assert corpus.load_fresh(out) is not None
    with (out / "validation.tsv").open("a", encoding="utf-8") as handle:
        handle.write("x\ten\tg\tgate\tone two three\n")
    assert corpus.load_fresh(out) is None


def test_test3_calibrates_with_the_rule_and_gates_on_the_fresh_slice(
    reader_home, few_seeds, monkeypatch
):
    pytest.importorskip("torch")
    from tadbir.ruh_reader import corpus

    evaluation = _eval_script()
    built = ruh_reader.build(
        0,
        config=TINY,
        plan={"epochs": 1, "seconds": 30, "batch": 8},
        calibrate=False,
        log=lambda _line: None,
    )
    languages = built.manifest["languages"]
    monkeypatch.setattr(corpus, "roman_words", lambda text: "kal" in text.split())
    validation = [
        ("kal subah jaldi uthana hai", "hi-latn", "r1", "calibration"),
        ("see you at the party tonight", "hi-latn", "r2", "calibration"),  # left out by the rule
        ("wake me up at seven", "en", "massive:1", "calibration"),
        ("please turn the lights off", "en", "massive:2", "gate"),
        ("बत्ती बंद कर दो", "hi", "massive:2", "gate"),
    ]
    fresh_rows = [
        ("how do i say hello in french", "en", "c1", "gate"),
        ("kal milna hai yaar", "hi-latn", "c2", "gate"),
        ("what time is it there", "hi-latn", "c3", "rule"),
    ]
    halves = evaluation.validation_reads(built, validation, languages)
    fresh = evaluation.fresh_reads(built, fresh_rows, languages)
    assert [len(fresh[name]) for name in ("gate", "rule")] == [2, 1]
    development = ruh_reader.Fit(**built.manifest["fit"])
    found = evaluation.test3(built, halves, fresh, languages, test=3)
    kept = [r for r in halves["calibration"] if r.text != "see you at the party tonight"]
    expected = ruh_reader.fit_on(kept, development.ref, gamma=development.gamma)
    assert found["fit"] == expected.to_dict() and found["calibration_left_out_by_rule"] == 1
    assert found["gate"]["n"] == 2 and found["gate"]["needed"] == pytest.approx(240)
    unfiltered = ruh_reader.fit_on(halves["calibration"], development.ref, gamma=development.gamma)
    assert found["gate_v11_fit"]["fit"] == unfiltered.to_dict()
    assert found["left_out_by_rule"]["slices"]["left out by the rule"]["lughah"]["n"] == 1
    assert found["v11_gate_half"]["check"]["n"] == 2
    assert found["adopted"] == (found["gate"]["adopted"] and found["fit"]["b"] > 0)
    assert any(line.startswith("GATE") for line in evaluation.validation_table(found))


# ── v2: no model-written text; FineWeb-2 Roman Hindi/Urdu ────────────────


def test_model_written_text_is_never_a_training_source():
    from tadbir.ruh_reader import corpus, speaker

    names = {source.name for source in corpus.SOURCES}
    assert "hinglish-1m" not in names and corpus.MODEL_WRITTEN == {"hinglish-1m"}
    assert corpus.HINGLISH_1M in corpus.MEASURED and "GPT-4o-mini" in corpus.HINGLISH_1M.licence
    assert any("Hinglish" in name for name in speaker.REJECTED)
    assert {"fineweb-2-hin_Latn", "fineweb-2-urd_Latn"} <= names
    pinned = {item.name: item.files[0][1] for item in speaker.SOURCES if item.kind == "parquet"}
    for name in corpus.FINEWEB_LATIN:  # pinned in one place: where the speaker pins them
        source = next(item for item in corpus.SOURCES if item.name == name)
        assert source.sha256 == pinned[name] and speaker.FINEWEB_2 in source.url
    assert corpus.model_written("hinglish-1m:12:input")
    assert not corpus.model_written("fineweb-2-hin_Latn:<urn:uuid:1>:0")
    written = ruh_reader.written_by_a_model()
    roman = (lughah.CORPUS / "hi-latn.tsv").read_text(encoding="utf-8").splitlines()
    from_model = [row.partition("\t")[2] for row in roman if row.startswith("hinglish-1m:")]
    assert from_model and all(ruh_reader.group_of(text) in written for text in from_model)
    kept = ruh_reader.trainable([(row.partition("\t")[2], "hi-latn") for row in roman])
    assert kept and all(ruh_reader.group_of(text) not in written for text, _label in kept)


def test_model_written_seeds_never_reach_the_loss_nor_the_development_set(reader_home, few_seeds):
    pytest.importorskip("torch")
    written = ruh_reader.written_by_a_model()
    assert any(ruh_reader.group_of(text) in written for text, _l in few_seeds)
    rows: set[bytes] = set()

    def hook(labels, mask):
        for row, keep in zip(labels.tolist(), mask.tolist(), strict=True):
            rows.add(bytes(t for t, k in zip(row, keep, strict=True) if k and t < 256))

    built = ruh_reader.build(
        0,
        config=TINY,
        plan={"epochs": 1, "seconds": 30, "batch": 8},
        loss_hook=hook,
        calibrate=False,
        log=lambda _line: None,
    )
    context = TINY["context"]
    for text, _label in few_seeds:
        if ruh_reader.group_of(text) in written:
            assert ruh_reader.reading(text).encode()[:context] not in rows
    assert built.manifest["model_written_left_out"]["train"] > 0
    assert not any(read.group in written for read in built.dev)
    assert any(read.group in written for read in built.held_out)  # measured, reported only


def test_an_older_corpus_never_trains_its_model_written_lines(tmp_path):
    import hashlib

    from tadbir.ruh_reader import corpus

    train = (
        "tatoeba:1\ten\tThe river runs past the old mill.\n"
        "hinglish-1m:5:input\thi-latn\tkal milte hain yaar\n"
    )
    short = "massive:en-US:2\ten\tmassive:2\twake me up at seven\n"
    manifest = {
        "seeds_sha256": ruh_reader.corpus_digest(ruh_reader.seeds()),
        "train": {"sha256": hashlib.sha256(train.encode()).hexdigest()},
        "short": {"sha256": hashlib.sha256(short.encode()).hexdigest()},
    }
    (tmp_path / "train.tsv").write_text(train, encoding="utf-8")
    (tmp_path / "short.tsv").write_text(short, encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    found = corpus.load(tmp_path)
    assert found is not None
    assert found.train == [("The river runs past the old mill.", "en")]
    assert found.written == [("kal milte hain yaar", "hi-latn")]


def test_a_web_document_is_cut_into_short_lines():
    from tadbir.ruh_reader import corpus

    long = " ".join(f"shabd{n}" for n in range(80))
    found = corpus.lines_of(f"Yeh pehli line hai. Aur doosri?\n\n  \n{long}")
    assert found[:2] == ["Yeh pehli line hai.", "Aur doosri?"]
    rest = found[2:]
    assert len(rest) > 1 and " ".join(rest) == long
    assert all(len(ruh_reader.reading(line).encode()) <= corpus.MAX_BYTES for line in rest)
    sizes = [len(line.split()) for line in rest]
    assert max(sizes) - min(sizes) <= 1  # the fewest equal runs


def _fineweb_rows(texts: dict[str, str], held: bool) -> list[tuple[str, str]]:
    """(id, text) rows whose documents are (or are not) held out by v2's rule."""
    from tadbir.ruh_reader import corpus

    rows, n = [], 0
    for text in texts.values():
        while True:
            n += 1
            identifier = f"<urn:uuid:{n}>"
            if corpus.held_document(f"fineweb-2-hin_Latn:{identifier}") == held:
                rows.append((identifier, text))
                break
    return rows


def test_fineweb_lines_pass_every_rule_the_other_sources_pass(tmp_path, monkeypatch):
    from tadbir.ruh_reader import corpus

    monkeypatch.setenv("MIZAN_TALIM", "off")
    monkeypatch.setattr(corpus, "KEEP", {})  # every document of the small fake files
    seed = next(t for t, label in ruh_reader.seeds() if label == "hi-latn" and len(t.split()) > 3)
    measured = "kal subah saat baje uthana hai"
    documents = {
        "ordinary": "Aaj mausam bahut accha hai.\nHum kal bazaar jayenge.\nYeh lamba din tha.",
        "with a seed": f"Pehli baat yeh hai.\n{seed}",
        "with the quran": "Yeh ek dua hai.\n" + _quote() + "\nIska matlab samjho.",
        "measured": f"{measured.upper()}!\nkal subah saat baje uthana hain\nBaaki sab theek hai.",
        "other script": "Hindi mein likha hai.\nयह देवनागरी में लिखा है।",
        "long": "\n".join(f"line number {_word(n)} hai" for n in range(40)),
        "twice": "Aaj mausam bahut accha hai.\nNaya din hai yaar.",
    }
    trained = _fineweb_rows(documents, held=False)
    held = _fineweb_rows({"held": "Yeh document kabhi seekha nahi jayega."}, held=True)
    paths = _fake_sources(
        tmp_path,
        tatoeba={"eng": [("900000010", "The library opens early on weekdays.")]},
        massive={"en-US": [{"id": "1", "partition": "train", "utt": "set an alarm for six"}]},
        hinglish=[(f"kal milte hain {_word(n)}", f"haan yaar {_word(n)}") for n in range(30)],
    )
    paths["fineweb-2-hin_Latn"] = tmp_path / "fineweb.parquet"  # read through rows_of
    paths["fineweb-2-hin_Latn"].write_bytes(b"")
    out = tmp_path / "corpus"
    manifest = corpus.build(
        paths=paths,
        out=out,
        scripture=ruh_reader.scripture,
        measured=[measured],
        rows_of=lambda _path: [*trained, *held],
        hinglish_count=10,
        log=lambda _line: None,
    )
    found = corpus.load(out)
    assert found is not None and not found.written
    assert "hinglish-1m" not in (out / "train.tsv").read_text(encoding="utf-8")
    texts = {text for text, label in found.train if label == "hi-latn"}
    assert {"Aaj mausam bahut accha hai.", "Hum kal bazaar jayenge.", "Naya din hai yaar."} <= texts
    assert not any("kabhi seekha" in text for text in texts)  # a held-out document
    assert not any("dua" in text or "matlab" in text for text in texts)  # the Quran's document
    assert seed not in texts and "Pehli baat yeh hai." in texts
    assert not any("saat baje" in text for text in texts)  # measured, and near it
    assert "Baaki sab theek hai." in texts
    assert "Hindi mein likha hai." in texts and not any("देवनागरी" in t for t in texts)
    assert sum(1 for text in texts if text.startswith("line number")) == corpus.PER_DOCUMENT
    dropped = manifest["dropped"]["fineweb-2-hin_Latn"]
    assert dropped["duplicate"] == 1 and dropped["seed words"] == 1
    assert dropped["held out here"] == 1 and dropped["near a measured message"] == 1
    # The ayah's own line is not Latin (the script rule), yet its document is
    # read whole for scripture: the lines around it are never trained on.
    assert dropped["script"] >= 2 and dropped["document holds scripture or hadith"] == 2
    roman_short = [text for text, label, _group in found.short if label == "hi-latn"]
    assert roman_short and all(text.startswith(("kal", "haan")) for text in roman_short)
    assert manifest["measured"]["messages"] == 1


def test_a_document_holding_hadith_gives_no_line(tmp_path, monkeypatch):
    from tadbir.ruh_reader import corpus, speaker

    monkeypatch.setenv("MIZAN_TALIM", "off")
    monkeypatch.setattr(corpus, "KEEP", {})
    narration = "actions are judged by intentions and every person will get what they intended"
    documents = {
        "narrated": "Yeh ek kahani hai.\nPeople say " + narration + " always.",
        "ordinary": "Aaj mausam bahut accha hai.",
    }
    paths = _fake_sources(
        tmp_path,
        tatoeba={"eng": [("900000010", "The library opens early on weekdays.")]},
        massive={"en-US": [{"id": "1", "partition": "train", "utt": "set an alarm for six"}]},
        hinglish=[],
    )
    paths["fineweb-2-hin_Latn"] = tmp_path / "fineweb.parquet"
    paths["fineweb-2-hin_Latn"].write_bytes(b"")
    corpus.build(
        paths=paths,
        out=tmp_path / "corpus",
        scripture=ruh_reader.scripture,
        hadith=speaker.Hadith(english=[narration]),
        rows_of=lambda _path: _fineweb_rows(documents, held=False),
        log=lambda _line: None,
    )
    found = corpus.load(tmp_path / "corpus")
    assert found is not None
    assert {text for text, label in found.train if label == "hi-latn"} == {
        "Aaj mausam bahut accha hai."
    }


def _v2_rule(text: str) -> bool:
    return "kya" in text or "ghar" in text


def test_v2_slices_take_a_third_of_each_half_from_each_roman_source():
    from tadbir.ruh_reader import corpus

    english = [
        corpus.Line(f"banking77:train:{n}", "en", f"where is my new card {_word(n)}", "train")
        for n in range(90)
    ]
    roman = {
        "dakshina": [
            corpus.Line(f"dakshina:hi:dev:{n}", "hi-latn", f"yah ek gaon hai {_word(n)}", "dev")
            for n in range(80)
        ],
        "phinc": [
            corpus.Line(
                f"phinc:{n}", "hi-latn", f"{'kya baat' if n % 2 else 'so true'} {_word(n)}", "t"
            )
            for n in range(80)
        ],
        "fineweb-2": [
            corpus.Line(
                f"fineweb-2-hin_Latn:<d{n // 5}>:{n % 5}",
                "hi-latn",
                f"mera ghar {_word(n)}",
                "held",
            )
            for n in range(200)
        ],
    }
    labelled = [roman["phinc"][1], roman["fineweb-2"][0]]
    seen = {ruh_reader.group_of(english[0].text)}
    rows = corpus.pick_v2(english, roman, seen, (), labelled, rule=_v2_rule)
    again = corpus.pick_v2(list(reversed(english)), roman, seen, (), labelled, rule=_v2_rule)
    assert [(line.source, part) for line, _g, _w, part in rows] == [
        (line.source, part) for line, _g, _w, part in again
    ]
    counted = [(line, group, where) for line, group, where, part in rows if part == "in"]
    english_rows = [item for item in counted if item[0].label == "en"]
    assert len(english_rows) == 89  # the seen query is left out
    for name in corpus.HALVES:
        cap = -(-sum(1 for _l, _g, w in english_rows if w == name) // 3)
        for source in ("dakshina", "phinc", "fineweb-2"):
            have = [
                line for line, _g, w in counted if w == name and corpus._source_of(line) == source
            ]
            assert 0 < len(have) <= cap
    for line, group, where, part in rows:
        assert group == corpus.unit_of(line) and where == corpus.v2_half(group)
        if corpus._source_of(line) == "phinc":
            assert (part == "in") == ("kya" in line.text)
    documents = [group for _line, group, _w, _p in rows if group.startswith("fineweb")]
    assert max(documents.count(name) for name in set(documents)) <= corpus.V2_PER_DOCUMENT
    left_out = {corpus.unit_of(line) for line in labelled}
    assert not left_out & {group for _l, group, _w, _p in rows}
    sample = corpus.v2_label_sample(roman, seen, ())
    assert {line.origin for line in sample} <= {"phinc", "fineweb-2-hin_Latn"}
    assert len({corpus.unit_of(line) for line in sample}) == len(sample)


def test_v2_calibrates_on_one_half_and_gates_on_the_other(reader_home, few_seeds):
    pytest.importorskip("torch")
    evaluation = _eval_script()
    built = ruh_reader.build(
        0,
        config=TINY,
        plan={"epochs": 1, "seconds": 30, "batch": 8},
        calibrate=False,
        log=lambda _line: None,
    )
    languages = built.manifest["languages"]

    def row(text, label, group, source):
        return {"text": text, "label": label, "group": group, "source": source}

    calibration = [
        row("where is my new card", "en", "banking77:train:1", "banking77"),
        row("kal subah jaldi uthana hai", "hi-latn", "phinc:1", "phinc"),
        row("yah ek chhota gaon hai", "hi-latn", "dakshina:hi:dev:1", "dakshina"),
    ]
    gate = [
        row("how do i top up my card", "en", "banking77:test:2", "banking77"),
        row(
            "mera ghar yahan se door hai",
            "hi-latn",
            "fineweb-2-hin_Latn:<d1>",
            "fineweb-2-hin_Latn",
        ),
        row(
            "woh bahut accha aadmi hai", "hi-latn", "fineweb-2-hin_Latn:<d1>", "fineweb-2-hin_Latn"
        ),
    ]
    sets = {
        "calibration in": evaluation.read_rows(built, calibration, languages),
        "gate in": evaluation.read_rows(built, gate, languages),
        "gate rule": evaluation.read_rows(
            built, [row("did you watch the match", "hi-latn", "phinc:9", "phinc")], languages
        ),
        "seeds held out": (built.held_out, ["seeds"] * len(built.held_out)),
    }
    assert sets["gate in"][1] == ["banking77", "fineweb-2", "fineweb-2"]
    development = ruh_reader.Fit(**built.manifest["fit"])
    found = evaluation.measure_v2(built.model, development, sets, languages, test=1)
    expected = ruh_reader.fit_on(sets["calibration in"][0], development.ref, development.gamma)
    assert found["fit"] == expected.to_dict()
    assert found["gate"]["n"] == 3 and found["gate"]["groups"] == 2  # a document is one group
    assert found["gate"]["needed"] == pytest.approx(40)
    assert set(found["gate_parts"]) == {"banking77", "fineweb-2", "Roman Hindi/Urdu"}
    assert found["reported"]["gate rule"]["check"]["n"] == 1
    assert len(found.pop("gate_combined")) == 3
    assert any(line.startswith("GATE") for line in evaluation.v2_table(found, "v2"))


def test_the_v2_rule_asks_two_hindi_or_urdu_words(monkeypatch):
    from tadbir import qamus
    from tadbir.ruh_reader import corpus

    monkeypatch.setattr(qamus, "read_roman", lambda word: word in {"kya", "hai", "yaar"})
    assert corpus.roman_words("kya baat hai")
    assert corpus.roman_words("kya baat hai", corpus.V2_LEAST)
    assert corpus.roman_words("my bank kya", 1)
    assert not corpus.roman_words("my bank kya", corpus.V2_LEAST)
    assert not corpus.roman_words("kya kya kya", corpus.V2_LEAST)  # distinct words


# ── installing a version trained and gated elsewhere ─────────────────────


def _report(languages, digest, fit, gate):
    return {
        "seed 0": {
            "manifest": {
                "created": "2026-10-31T06:16:27+00:00",
                "corpus_sha256": digest,
                "languages": list(languages),
                "fit": {"kappa": 1.0, "gamma": 0.0, "ref": 20.0, "b": 1.0},
                "gate": {"adopted": False},  # the seeds' gate, under the development fit
                "adopted": False,
                "learned": [],
                "tests": 1,
            },
            "v2": {"fit": fit, "gate": gate, "adopted": gate["adopted"]},
        }
    }


def test_a_reader_gated_elsewhere_installs_with_its_gate_and_is_read(
    reader_home, few_seeds, tmp_path, monkeypatch
):
    torch = pytest.importorskip("torch")
    from tadbir.ruh_reader import net

    monkeypatch.setenv("MIZAN_RUH_READER", "shadow")
    languages = list(dict.fromkeys(label for _text, label in few_seeds))
    torch.manual_seed(5)
    weights = tmp_path / "reader-seed0.pt"
    net.save(net.Reader(net.Config(**TINY)).eval(), weights)
    fit = {"kappa": 0.4, "gamma": 0.0, "ref": 47.0, "b": 0.67}
    report = _report(languages, ruh_reader.corpus_digest(few_seeds), fit, {"adopted": True})
    found = ruh_reader.install_trained(weights, report, {"repo": "owner/reader"})
    assert found["fit"] == fit and found["adopted"] is True
    assert found["dev"] > 0 and found["held_out"] > 0
    current = ruh_reader.manifest("current")
    assert current["fit"] == fit and current["gate"] == {"adopted": True}
    assert current["installed"]["repo"] == "owner/reader"
    assert ruh_reader.manifest("base")["installed"] == current["installed"]
    assert (reader_home / "current.reads.json").exists()  # what a night compares against
    loaded = ruh_reader.load()
    assert loaded is not None and loaded.fit.b == pytest.approx(0.67)


def test_a_reader_trained_on_other_seeds_is_not_installed(reader_home, few_seeds, tmp_path):
    torch = pytest.importorskip("torch")
    from tadbir.ruh_reader import net

    languages = list(dict.fromkeys(label for _text, label in few_seeds))
    torch.manual_seed(5)
    weights = tmp_path / "reader-seed0.pt"
    net.save(net.Reader(net.Config(**TINY)).eval(), weights)
    fit = {"kappa": 1.0, "gamma": 0.0, "ref": 20.0, "b": 0.5}
    with pytest.raises(ValueError, match="other seeds"):
        ruh_reader.install_trained(weights, _report(languages, "0" * 64, fit, {"adopted": True}))
    with pytest.raises(ValueError, match="other languages"):
        ruh_reader.install_trained(
            weights,
            _report(languages[::-1], ruh_reader.corpus_digest(few_seeds), fit, {"adopted": True}),
        )
    assert ruh_reader.manifest("current") is None


def test_only_an_administrator_installs_a_reader_and_only_the_weights_pinned(
    reader_home, monkeypatch
):
    import hashlib

    from fastapi.testclient import TestClient

    import api.main as main
    from knowledge import hf_hub

    pytest.importorskip("torch")
    blob = b"weights"
    served = {"reader-seed0.pt": blob, "seed0.json": json.dumps({"seed 0": {}}).encode()}

    async def fetch(repo, path, kind="datasets", revision="main", max_bytes=0):
        assert kind == "models" and revision == "a" * 40
        return {"bytes": served[path], "sampled": False}

    installed: list = []

    def install(weights, report, source):
        installed.append((weights.read_bytes(), report, source))
        return {"fit": {"b": 0.67}, "adopted": True}

    monkeypatch.setattr(hf_hub, "fetch", fetch)
    monkeypatch.setattr(ruh_reader, "install_trained", install)
    body = {"repo": "owner/reader", "revision": "a" * 40, "sha256": "0" * 64}
    client = TestClient(main.app)
    member = main.auth.create_token(main.auth.create_user("readeruser", "pw", roles=["user"]))
    denied = client.post(
        "/api/tadrib/reader", json=body, headers={"Authorization": f"Bearer {member}"}
    )
    assert denied.status_code == 403 and not installed
    admin = main.auth.create_token(main.auth.create_user("readeradmin", "pw", roles=["admin"]))
    headers = {"Authorization": f"Bearer {admin}"}
    wrong = client.post("/api/tadrib/reader", json=body, headers=headers)
    assert wrong.status_code == 422 and not installed  # not the weights pinned
    body["sha256"] = hashlib.sha256(blob).hexdigest()
    done = client.post("/api/tadrib/reader", json=body, headers=headers)
    assert done.status_code == 200 and done.json()["adopted"] is True
    assert installed[0][0] == blob and installed[0][2]["repo"] == "owner/reader"
    assert not list(reader_home.glob("incoming-*"))  # the download is not left behind
