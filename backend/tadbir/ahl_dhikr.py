"""Ahl al-Dhikr (أهل الذكر): when MIZAN does not know, it asks those who know.

"Ask the people of knowledge if you do not know" (Quran 16:43). An answer in
the language model's own words carries claims that nothing MIZAN holds
supports (da'if in the Isnad ledger). When the question asks about the world
(Qasd's ``fact`` facet), MIZAN asks its sources about those claims before the
answer is shown:

1. what it settled before from a source (the ``ilm`` it keeps per user);
2. the references it can read: Wikipedia in the answer's language and in
   English, and a web search, read as untrusted data. Which of these is asked
   first is learned: each has a Beta posterior of settling a claim when asked,
   and the order is a Thompson sample.

A source's sentences are ranked by BM25 against the claim, and a multilingual
NLI model (``MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli``, MIT, run with
ONNX Runtime on the CPU) reads the best of them against the claim. The verdict
is the most probable label of the most decisive sentence: entailment
(supported), contradiction, or neither, which leaves the claim unknown. There is
no threshold. A supported claim becomes hasan with its source; a contradicted
one is shown with what the source says, next to it; with no source it stays the
model's word, and the answer says so.

What a source settled is kept with its sentence, title, link and date, so the
same claim is answered from memory the next time, and the next answer is given
it before it is written. Deleting the chat (Mahw) deletes what it taught.

``MIZAN_AHL_DHIKR``: ``on`` (default) or ``off``. The model is downloaded once,
at a pinned revision, into ``$MIZAN_DATA_DIR/models/nli`` and let go after ten
idle minutes; without it every claim stays unknown and nothing is guessed.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import re
import threading
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from core.adaptive import BetaEstimator, bm25_scores, tokenize

from . import amanah, isnad, qamus, qasd
from .taallum import content_words

logger = logging.getLogger("mizan.ahl_dhikr")

REPO = "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli"
REVISION = "0a71e92a985b6e1ad1828cf67ce9c459639c1dca"
WEIGHTS = "onnx/model.onnx"
VOCABULARY = "onnx/tokenizer.json"
LABELS = ("entailment", "neutral", "contradiction")  # the model's id2label order
IDLE_SECONDS = 600
CANDIDATES = 3  # sentences per claim that the NLI model reads
MAX_KEPT = 300  # settled claims kept per user, the most recently used first
BUDGET_SECONDS = 20.0  # all sources together, so an answer is never held long
# Wikimedia's policy asks every client to name itself and how to reach its
# operator; MIZAN_CONTACT lets the owner give their own address.
PROJECT_URL = "https://github.com/CodeWithJuber/mizan"
# Wikipedia editions for MIZAN's languages (Roman Hindi/Urdu reads English).
WIKIPEDIA = {"en": "en", "ar": "ar", "ur": "ur", "hi": "hi", "hi-latn": "en"}
EXTERNAL = ("wikipedia", "web")
_SENTENCE = re.compile(r"(?<=[.!?۔؟।])\s+|\n+")
_PRIOR = {"alpha": 1.0, "beta": 1.0, "prior_alpha": 1.0, "prior_beta": 1.0, "forgetting": 0.99}


def enabled() -> bool:
    return os.getenv("MIZAN_AHL_DHIKR", "on").strip().lower() != "off"


@dataclass
class Passage:
    text: str
    title: str
    url: str
    source: str  # "ilm", "wikipedia" or "web"
    at: str = ""


@dataclass
class Finding:
    claim: str
    verdict: str  # "supported", "contradicted" or "unknown"
    probability: float = 0.0
    passage: Passage | None = None

    def to_dict(self) -> dict:
        found: dict[str, Any] = {
            "claim": self.claim,
            "verdict": self.verdict,
            "p": round(self.probability, 3),
        }
        if self.passage is not None:
            found.update(
                says=self.passage.text[:400],
                title=self.passage.title,
                url=self.passage.url,
                source=self.passage.source,
            )
            if self.passage.at:
                found["checked"] = self.passage.at
        return found


# ── the NLI model ──────────────────────────────────────────────────────────

_model: Any = None
_model_lock = threading.Lock()
_last_used = 0.0


def _root() -> Path:
    return Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "models" / "nli"


def _load_model() -> Any:
    global _model
    with _model_lock:
        if _model is None:
            import onnxruntime
            from huggingface_hub import hf_hub_download
            from tokenizers import Tokenizer

            root = str(_root())
            weights = hf_hub_download(REPO, WEIGHTS, revision=REVISION, cache_dir=root)
            vocabulary = hf_hub_download(REPO, VOCABULARY, revision=REVISION, cache_dir=root)
            tokenizer = Tokenizer.from_file(vocabulary)
            tokenizer.enable_truncation(512)
            options = onnxruntime.SessionOptions()
            options.intra_op_num_threads = int(os.getenv("MIZAN_NLI_THREADS", "2") or 2)
            session = onnxruntime.InferenceSession(
                weights, options, providers=["CPUExecutionProvider"]
            )
            _model = (tokenizer, session)
        return _model


def _let_go_when_idle() -> None:
    global _model
    if time.monotonic() - _last_used < IDLE_SECONDS:
        return
    with _model_lock:
        _model = None


def _infer(pairs: list[tuple[str, str]]) -> list[dict[str, float]]:
    """P(entailment, neutral, contradiction) of each (premise, hypothesis)."""
    global _last_used
    import numpy as np

    tokenizer, session = _load_model()
    found = []
    for premise, hypothesis in pairs:
        encoded = tokenizer.encode(premise, hypothesis)
        logits = session.run(
            None,
            {
                "input_ids": np.array([encoded.ids], dtype=np.int64),
                "attention_mask": np.array([encoded.attention_mask], dtype=np.int64),
            },
        )[0][0]
        exp = np.exp(logits - logits.max())
        probabilities = exp / exp.sum()
        found.append({label: float(p) for label, p in zip(LABELS, probabilities, strict=True)})
    _last_used = time.monotonic()
    timer = threading.Timer(IDLE_SECONDS + 1, _let_go_when_idle)
    timer.daemon = True
    timer.start()
    return found


async def nli(pairs: list[tuple[str, str]]) -> list[dict[str, float]] | None:
    """The NLI model's reading of each pair, or None when it cannot run here."""
    if not pairs:
        return []
    try:
        return await asyncio.to_thread(_infer, pairs)
    except Exception:  # noqa: BLE001 - no model: every claim stays unknown
        logger.warning("Ahl al-Dhikr: the NLI model is unavailable", exc_info=True)
        return None


# ── judging a claim against a source ──────────────────────────────────────


def sentences(passages: Sequence[Passage]) -> list[Passage]:
    """Each passage split into its sentences, each keeping its source."""
    found = []
    for passage in passages:
        for sentence in _SENTENCE.split(passage.text):
            sentence = sentence.strip()
            if len(tokenize(sentence)) >= 3:
                found.append(
                    Passage(sentence[:600], passage.title, passage.url, passage.source, passage.at)
                )
    return found


@lru_cache(maxsize=1)
def _background() -> tuple[dict[str, int], int]:
    """How many sentences of general language (Lughah's corpora, five
    languages) each word appears in: common words carry little information."""
    from . import lughah

    counts: dict[str, int] = {}
    sentences_read = 0
    for label in lughah.LANGUAGES:
        for line in (lughah.CORPUS / f"{label}.tsv").read_text(encoding="utf-8").splitlines():
            words = set(tokenize(line.partition("\t")[2]))
            if words:
                sentences_read += 1
                for word in words:
                    counts[word] = counts.get(word, 0) + 1
    return counts, sentences_read


def information(word: str) -> float:
    """A word's inverse document frequency in general language."""
    counts, total = _background()
    return math.log((total + 1) / (counts.get(word, 0) + 1))


@lru_cache(maxsize=1)
def average_information() -> float:
    """The information of an average running word of general language: a word
    carrying less is a function word ("and", "the", "with", "hai")."""
    counts, _total = _background()
    occurrences = sum(counts.values()) or 1
    return sum(count * information(word) for word, count in counts.items()) / occurrences


def about(claim: str, sentence: str) -> bool:
    """The sentence speaks of what the claim speaks of.

    The claim's distinctive words are those carrying more information than its
    average word (names, numbers, terms: never "is", "the", "hai"). The sentence
    is about the claim when it holds most (> ½) of their information. A sentence
    that shares only common words with a claim is not evidence for or against
    it, however an NLI model reads the pair (such models often call two
    unrelated sentences a contradiction).

    A distinctive word written in another script than the sentence (a claim in
    Hindi or Urdu, an English Wikipedia sentence) is also present when one of
    its translations in MIZAN's own lexicon (Qāmūs) is a word of the sentence
    that is not a function word: a translation such as "the" or "is" is in
    nearly every sentence, so finding it is no evidence. As a word found as it
    is stands for itself, a word of the sentence stands for one claim word at
    most (``docs/qamus.md``)."""
    weights = {word: information(word) for word in set(tokenize(claim))}
    if not weights:
        return False
    mean = sum(weights.values()) / len(weights)
    distinctive = {word: weight for word, weight in weights.items() if weight > mean} or weights
    present = set(tokenize(sentence))
    covered = sum(weight for word, weight in distinctive.items() if word in present)
    total = sum(distinctive.values())
    if 2 * covered <= total:
        missing = sorted(
            (word for word in distinctive if word not in present),
            key=lambda word: (-distinctive[word], word),
        )
        floor = average_information()
        translated = qamus.found_in(missing, sentence, lambda word: information(word) > floor)
        covered += sum(distinctive[word] for word in translated)
    return 2 * covered > total


def joint_premise(claim: str, pool: Sequence[Passage], scores: Sequence[float]) -> Passage | None:
    """One page's best sentences for the claim, joined in the page's order.

    A model's sentence often joins what a source says in several ("commissioned
    by Shah Jahan in memory of Mumtaz Mahal" against "It was built by Shah
    Jahan…" and "…for his wife, Mumtaz Mahal"), so no single sentence holds
    most of its information and none could be read against it. The page whose
    best ``CANDIDATES`` sentences match the claim most (summed BM25) gives
    them, in their order, as one premise, when together they are about the
    claim. Measured on 30 teacher answers (``scripts/ahl_coverage.py``):
    supported claims 5 → 17 of 66 against Simple English Wikipedia and 13 → 15
    against web snippets, every new one right on audit; none of 20 false
    claims supported (``docs/ahl-dhikr.md``)."""
    by_page: dict[str, list[int]] = {}
    for position, passage in enumerate(pool):
        if scores[position] > 0:
            by_page.setdefault(passage.url, []).append(position)
    if not by_page:
        return None

    def strength(url: str) -> float:
        return sum(sorted((scores[i] for i in by_page[url]), reverse=True)[:CANDIDATES])

    best = sorted(by_page[max(by_page, key=strength)], key=lambda i: -scores[i])[:CANDIDATES]
    if len(best) < 2:
        return None
    text = " ".join(pool[i].text for i in sorted(best))
    if not about(claim, text):
        return None
    first = pool[best[0]]
    return Passage(text, first.title, first.url, first.source, first.at)


def searched(claim: str) -> str:
    """The words a claim's sentences are searched by: its own, and their
    English translations in MIZAN's lexicon (Qāmūs), so a Hindi or Urdu claim
    finds the English source sentences about it. Whether a found sentence is
    about the claim is still decided by ``about`` on the claim itself.
    Measured on 30 teacher answers in Hindi and 30 in Urdu against Simple
    English Wikipedia: supported 2 → 5 of 119 and 1 → 2 of 120 claims, none
    read against another question's article (``docs/qamus.md``)."""
    bridged = qamus.bridge(claim, "en")
    return claim + " " + " ".join(bridged) if bridged else claim


async def judge(claims: list[str], pool: list[Passage]) -> list[Finding]:
    """Each claim's verdict from the sentences of one source that are about it,
    one by one and, joined, the page's best of them (``joint_premise``)."""
    if not pool:
        return [Finding(claim, "unknown") for claim in claims]
    pairs: list[tuple[str, str]] = []
    owners: list[tuple[int, Passage]] = []
    texts = [passage.text for passage in pool]
    for index, claim in enumerate(claims):
        scores = bm25_scores(searched(claim), texts)
        ranked = sorted(range(len(pool)), key=lambda i: -scores[i])
        related = [i for i in ranked if scores[i] > 0 and about(claim, texts[i])]
        for position in related[:CANDIDATES]:
            pairs.append((pool[position].text, claim))
            owners.append((index, pool[position]))
        joint = joint_premise(claim, pool, scores)
        if joint is not None:
            pairs.append((joint.text, claim))
            owners.append((index, joint))
    readings = await nli(pairs)
    if readings is None:
        return [Finding(claim, "unknown") for claim in claims]
    best: dict[int, tuple[float, str, Passage]] = {}
    for (index, passage), reading in zip(owners, readings, strict=True):
        # The most decisive sentence speaks for the source: the one whose
        # strongest of entailment and contradiction is highest.
        decisive = max(reading["entailment"], reading["contradiction"])
        if index not in best or decisive > best[index][0]:
            label = max(reading, key=reading.__getitem__)
            best[index] = (decisive, label, passage)
    # Contradiction is symmetric: if the source contradicts the claim, the claim
    # contradicts the source. A one-way reading is the NLI model misreading a
    # pair (an agreeing page read as "says otherwise"), so it settles nothing.
    disputed = [index for index, (_, label, _) in best.items() if label == "contradiction"]
    reverse = await nli([(claims[index], best[index][2].text) for index in disputed])
    for index, reading in zip(disputed, reverse or [], strict=False):
        if max(reading, key=reading.__getitem__) != "contradiction":
            best[index] = (best[index][0], "neutral", best[index][2])
    if disputed and reverse is None:
        for index in disputed:
            best[index] = (best[index][0], "neutral", best[index][2])
    findings = []
    for index, claim in enumerate(claims):
        if index not in best or best[index][1] == "neutral":
            findings.append(Finding(claim, "unknown"))
            continue
        probability, label, passage = best[index]
        verdict = "supported" if label == "entailment" else "contradicted"
        findings.append(Finding(claim, verdict, probability, passage))
    return findings


# ── the sources ───────────────────────────────────────────────────────────


def user_agent() -> str:
    contact = os.getenv("MIZAN_CONTACT", "").strip()[:200]
    reach = f"{PROJECT_URL}; {contact}" if contact else PROJECT_URL
    return f"MIZAN/3.0 ({reach}) httpx/{httpx.__version__}"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=10.0, follow_redirects=False, headers={"User-Agent": user_agent()}
    )


class _Refused(Exception):
    """Wikimedia refused this client (403, its robot policy): every one of its
    sites answers the same, so asking again in this call only spends time."""


def _retry_after(response: httpx.Response) -> float | None:
    """Seconds the server asked to wait (``Retry-After``: seconds or a date)."""
    value = response.headers.get("retry-after", "").strip()
    if not value:
        return None
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


async def _ask(
    client: httpx.AsyncClient, url: str, params: dict | None, deadline: float
) -> httpx.Response:
    """A GET that honours Wikimedia's robot policy: on 429 or 503 it waits as
    long as ``Retry-After`` says and asks once more, if that wait is at most
    half the time left (the other half is the retried request's and the other
    sources'); on 403 it stops asking (``_Refused``)."""
    response = await client.get(url, params=params)
    if response.status_code == 403:
        raise _Refused
    if response.status_code in (429, 503):
        wait = _retry_after(response)
        if wait is not None and wait <= (deadline - time.monotonic()) / 2:
            await asyncio.sleep(wait)
            response = await client.get(url, params=params)
            if response.status_code == 403:
                raise _Refused
    return response


async def _article(client: httpx.AsyncClient, base: str, title: str, deadline: float) -> str:
    """An article's plain text from the Action API; when that does not answer,
    its lead section from the REST API (a separate, cached service)."""
    try:
        response = await _ask(
            client,
            f"{base}/w/api.php",
            {
                "action": "query",
                "prop": "extracts",
                "explaintext": 1,
                "titles": title,
                "format": "json",
                "formatversion": 2,
            },
            deadline,
        )
        items = response.json().get("query", {}).get("pages", []) if response.is_success else []
        text = str((items[0] if items else {}).get("extract", ""))
    except (httpx.HTTPError, ValueError):
        text = ""
    if text:
        return text
    try:
        page = quote(title.replace(" ", "_"), safe="")
        summary = await _ask(client, f"{base}/api/rest_v1/page/summary/{page}", None, deadline)
        return str(summary.json().get("extract", "")) if summary.is_success else ""
    except (httpx.HTTPError, ValueError):
        return ""


async def wikipedia(question: str, language: str, deadline: float | None = None) -> list[Passage]:
    """The articles Wikipedia's own search finds for the question, as plain text.

    Requests are made one at a time, as Wikimedia asks of a client that does
    not log in (Action API: one concurrent request)."""
    found: list[Passage] = []
    deadline = deadline or time.monotonic() + BUDGET_SECONDS
    editions = list(dict.fromkeys([WIKIPEDIA.get(language, "en"), "en"]))
    async with _client() as client:
        try:
            for edition in editions:
                base = f"https://{edition}.wikipedia.org"
                try:
                    search = await _ask(
                        client,
                        f"{base}/w/api.php",
                        {
                            "action": "query",
                            "list": "search",
                            "srsearch": question[:300],
                            "srlimit": 2,
                            "format": "json",
                            "formatversion": 2,
                        },
                        deadline,
                    )
                    pages = (
                        search.json().get("query", {}).get("search", [])
                        if search.is_success
                        else []
                    )
                except (httpx.HTTPError, ValueError):
                    continue
                for page in pages[:2]:
                    title = str(page.get("title", ""))
                    text = (await _article(client, base, title, deadline))[:30000]
                    if text:
                        link = f"{base}/wiki/{quote(title.replace(' ', '_'))}"
                        found.append(Passage(text, title, link, "wikipedia"))
                if found:
                    break
        except _Refused:
            logger.info("Ahl al-Dhikr: Wikipedia refused this client (403)")
    return found


def web_from(results: Any) -> list[Passage]:
    """A web search's results, as untrusted snippets with their links."""
    found = []
    for item in (results or {}).get("results", [])[:8] if isinstance(results, dict) else []:
        snippet = str(item.get("snippet") or "")
        if snippet:
            clean, _findings = amanah.neutralize(snippet)
            found.append(
                Passage(clean, str(item.get("title") or ""), str(item.get("url") or ""), "web")
            )
    return found


# ── what was settled before (ilm), per user ──────────────────────────────


def _key(user_id: str) -> str:
    return "ilm:" + hashlib.sha256((user_id or "anonymous").encode()).hexdigest()[:24]


def _load(store: Any, user_id: str) -> list[dict]:
    try:
        data = store.get(_key(user_id)) or {}
    except Exception:  # noqa: BLE001 - no store: nothing kept
        return []
    return [item for item in data.get("facts", []) if isinstance(item, dict)]


def _save(store: Any, user_id: str, items: list[dict]) -> None:
    kept = sorted(items, key=lambda item: item.get("used", ""), reverse=True)[:MAX_KEPT]
    try:
        store.put(_key(user_id), {"facts": kept})
    except Exception:  # noqa: BLE001 - keeping is best effort
        pass


def _settled(item: dict) -> bool:
    """A kept verdict whose sentence is about its claim. Verdicts kept before
    the relevance gate existed may pair a claim with an unrelated sentence;
    those are not knowledge and are dropped."""
    return bool(item.get("says") and item.get("url")) and about(
        str(item.get("claim", "")), str(item["says"])
    )


def known(store: Any, user_id: str) -> list[Passage]:
    """Every sentence a source settled for this user before."""
    return [
        Passage(item["says"], item["title"], item["url"], "ilm", item.get("checked", ""))
        for item in _load(store, user_id)
        if _settled(item)
    ]


def keep(store: Any, user_id: str, question: str, findings: list[Finding]) -> int:
    """Keep what an outside source settled, tied to the question that asked it,
    with the host it came from; a host gains or loses trust as other, independent
    hosts agree or disagree with it on the same claim."""
    now = datetime.now(UTC).isoformat(timespec="seconds")
    stored = _load(store, user_id)
    items = [item for item in stored if _settled(item)]
    seen = {(item.get("claim"), item.get("url")) for item in items}
    added = 0
    for finding in findings:
        passage = finding.passage
        if finding.verdict == "unknown" or passage is None:
            continue
        # A claim MIZAN's ilm settled in new words is kept under those words
        # too, with the site that said it: that site is its first witness.
        if (finding.claim, passage.url) in seen:
            continue
        host = host_of(passage.url)
        others = {
            item["host"]: item["verdict"]
            for item in items
            if item.get("claim") == finding.claim and item.get("host") and item["host"] != host
        }
        items.append(
            {
                "claim": finding.claim,
                "verdict": finding.verdict,
                "p": round(float(finding.probability or 0.0), 3),
                "says": passage.text,
                "title": passage.title,
                "url": passage.url,
                "host": host,
                "source": passage.source,
                "checked": now,
                "used": now,
                # Mahw drops what a deleted chat's requests taught.
                "tokens": content_words(question),
            }
        )
        seen.add((finding.claim, passage.url))
        for other, verdict in others.items():
            agreed = verdict == finding.verdict
            credit(store, host, agreed)
            credit(store, other, agreed)
        added += 1
    if added or len(items) < len(stored):
        _save(store, user_id, items)
    return added


# ── two witnesses: corroboration and source trust (Isnad) ────────────────
#
# "And bring to witness two witnesses from among your men ... so that if one of
# them [i.e., the women] errs, then the other can remind her" (2:282); "if there
# comes to you a disobedient one with information, investigate" (49:6), from
# which, Ibn Kathir notes, the scholars of hadith refuse narrators whose
# reliability is unknown. So a claim one source settled is shown with that
# source but is not yet knowledge; it becomes knowledge (given to Lisan before it
# answers) when a second, independent source agrees and none disagrees. Each
# host's reliability is a Beta posterior, credited when an independent host
# agrees with it and debited when one disagrees; the sources are weighed
# together in log-odds:
#
#     logit P(true) = Σ_h  s_h · p_h · logit(t̄_h)
#
# with s_h = +1 when host h supports the claim and −1 when it contradicts it,
# p_h its NLI probability and t̄_h its posterior mean reliability. Copies of one
# site count once (a host is one witness however many pages it has).

_TRUST = {"alpha": 2.0, "beta": 1.0, "prior_alpha": 2.0, "prior_beta": 1.0, "forgetting": 1.0}


def host_of(url: str) -> str:
    """The witness behind a link: its host, without "www." (a site counts once)."""
    host = urlparse(url or "").netloc.lower().split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _hosts_key() -> str:
    return "ilm:hosts"


def trust(store: Any) -> dict[str, BetaEstimator]:
    try:
        data = store.get(_hosts_key()) or {}
    except Exception:  # noqa: BLE001
        data = {}
    return {host: BetaEstimator.from_dict(value, **_TRUST) for host, value in data.items()}


def credit(store: Any, host: str, agreed: bool) -> None:
    if not host:
        return
    try:
        data = store.get(_hosts_key()) or {}
        data[host] = BetaEstimator.from_dict(data.get(host), **_TRUST).update(agreed).to_dict()
        store.put(_hosts_key(), data)
    except Exception:  # noqa: BLE001 - trust is learned best effort
        pass


def witnesses(store: Any, user_id: str) -> dict[str, dict]:
    """Per kept claim: its independent hosts, what each said, the sources weighed
    together, and its grade: "sahih" (two or more hosts agree, none disagrees),
    "hasan" (one host) or "mudtarib" (hosts disagree)."""
    trusted = trust(store)
    by_claim: dict[str, dict[str, dict]] = {}
    for item in _load(store, user_id):
        if not _settled(item):
            continue
        host = item.get("host") or host_of(str(item.get("url", "")))
        by_claim.setdefault(str(item.get("claim", "")), {}).setdefault(host, item)
    found: dict[str, dict] = {}
    for claim, hosts in by_claim.items():
        logit = 0.0
        for host, item in hosts.items():
            sign = 1.0 if item.get("verdict") == "supported" else -1.0
            reliability = trusted.get(host) or BetaEstimator(**_TRUST)
            mean = min(max(float(reliability.mean), 1e-6), 1 - 1e-6)
            weight = float(item.get("p") or 0.5)
            logit += sign * weight * math.log(mean / (1.0 - mean))
        verdicts = {item.get("verdict") for item in hosts.values()}
        grade = "mudtarib" if len(verdicts) > 1 else "sahih" if len(hosts) >= 2 else "hasan"
        found[claim] = {
            "hosts": sorted(hosts),
            "grade": grade,
            "p_true": round(1.0 / (1.0 + math.exp(-logit)), 3),
            "items": list(hosts.values()),
        }
    return found


def evidence_for(store: Any, user_id: str, question: str, limit: int = 4) -> list[dict]:
    """Sentences two independent sources agree on that bear on a question, given
    to Lisan before it answers. One source's word is shown under an answer but is
    not given as knowledge until a second witness agrees (2:282, 49:6)."""
    corroborated = [
        item
        for entry in witnesses(store, user_id).values()
        if entry["grade"] == "sahih"
        for item in entry["items"]
    ]
    if not corroborated:
        return []
    scores = bm25_scores(question, [str(item["says"]) for item in corroborated])
    ranked = sorted(range(len(corroborated)), key=lambda i: -scores[i])
    chosen: list[dict] = []
    for index in ranked:
        item = corroborated[index]
        if scores[index] <= 0 or not about(question, str(item["says"])):
            continue
        if any(entry["says"] == item["says"] for entry in chosen):
            continue
        chosen.append({"says": item["says"], "source": item["title"], "url": item["url"]})
    return chosen[:limit]


def single_witness(store: Any, user_id: str) -> set[str]:
    """Claims only one host has settled: MIZAN still seeks a second witness."""
    return {
        claim for claim, entry in witnesses(store, user_id).items() if entry["grade"] == "hasan"
    }


# ── which outside source to ask first (learned) ──────────────────────────


def _trust_key() -> str:
    return "ilm:sources"


def order(store: Any) -> list[str]:
    """Outside sources by a Thompson sample of how often each settled a claim."""
    try:
        data = store.get(_trust_key()) or {}
    except Exception:  # noqa: BLE001
        data = {}
    samples = {
        name: BetaEstimator.from_dict(data.get(name), **_PRIOR).sample() for name in EXTERNAL
    }
    return sorted(EXTERNAL, key=lambda name: -samples[name])


def record(store: Any, source: str, asked: int, settled: int) -> None:
    try:
        data = store.get(_trust_key()) or {}
        estimator = BetaEstimator.from_dict(data.get(source), **_PRIOR)
        for index in range(asked):
            estimator.update(index < settled)
        data[source] = estimator.to_dict()
        store.put(_trust_key(), data)
    except Exception:  # noqa: BLE001 - learning the order is best effort
        pass


# ── asking ────────────────────────────────────────────────────────────────


def factual(question: str) -> bool:
    """The question asks about the world, so its answer's claims can be checked."""
    return qasd.facet("fact", question or "")


def ruling(question: str) -> bool:
    """The question asks for a religious ruling, which a scholar gives."""
    return qasd.facet("ruling", question or "")


def cites_scripture(text: str) -> bool:
    """The text gives a Quran or hadith reference on one of its lines."""
    from . import hadith, quran

    return any(
        quran.parse_reference(line) is not None or hadith.parse_reference(line) is not None
        for line in (text or "").splitlines()[:200]
        if line.strip()
    )


def religious(question: str, answer: str = "") -> bool:
    """The question is about the deen (the Quran, a hadith, belief, a ruling),
    or the answer cites the Quran or a hadith: its claims are not asked of
    Wikipedia or a web search. MIZAN quotes the Quran and hadith from their own
    sources, and a ruling is a scholar's."""
    return qasd.facet("deen", question or "") or ruling(question) or cites_scripture(answer)


async def consult(
    question: str,
    ledger: list[dict],
    *,
    store: Any,
    user_id: str,
    language: str,
    web: Callable[[str], Awaitable[Any]] | None = None,
    answer: str = "",
) -> tuple[list[Finding], list[str]]:
    """Every da'if claim's verdict, asking MIZAN's own ilm first and then its
    outside sources in their learned order, until each claim is settled; and
    which sources answered at all. A religious question or answer is asked of
    MIZAN's own ilm only."""
    # A claim is held to the same unit as a source sentence (``sentences``):
    # two words relate nothing a source could support or contradict.
    # An equation is settled by computing it (Sidq), never by a source.
    from . import muhasaba

    claims = [
        unit["text"]
        for unit in ledger
        if unit.get("grade") == "daif"
        and unit.get("kind", "sentence") == "sentence"
        and len(tokenize(unit["text"])) >= 3
        and not muhasaba.computable(unit["text"])
    ]
    if not claims:
        return [], []
    verdicts = {claim: Finding(claim, "unknown") for claim in claims}
    heard: list[str] = []
    # Claims MIZAN's ilm settled from one host only: a second, independent
    # witness is sought (2:282) and kept beside the first.
    lone = single_witness(store, user_id)
    seeking: dict[str, str] = {}
    seconds: list[Finding] = []

    async def ask(pool: list[Passage]) -> int:
        if pool:
            heard.append(pool[0].source)
        open_claims = [
            claim
            for claim, found in verdicts.items()
            if found.verdict == "unknown" or claim in seeking
        ]
        settled = 0
        for finding in await judge(open_claims, sentences(pool)):
            if finding.verdict == "unknown" or finding.passage is None:
                continue
            claim = finding.claim
            if claim in seeking:
                if host_of(finding.passage.url) != seeking[claim]:
                    seconds.append(finding)
                    del seeking[claim]
                    settled += 1
                continue
            verdicts[claim] = finding
            settled += 1
            if finding.passage.source == "ilm" and any(
                about(claim, other) and about(other, claim) for other in lone
            ):
                seeking[claim] = host_of(finding.passage.url)
        return settled

    deadline = time.monotonic() + BUDGET_SECONDS
    await ask(known(store, user_id))
    outside = [] if religious(question, answer) else order(store)
    for source in outside:
        unknown = sum(1 for found in verdicts.values() if found.verdict == "unknown")
        remaining = unknown + len(seeking)
        if not remaining or time.monotonic() > deadline:
            break
        if (
            not unknown
            and source == "wikipedia"
            and all(host.endswith("wikipedia.org") for host in seeking.values())
        ):
            continue  # a site is never its own second witness
        try:
            async with asyncio.timeout(max(1.0, deadline - time.monotonic())):
                if source == "wikipedia":
                    pool = await wikipedia(question, language, deadline)
                elif web is not None:
                    pool = web_from(await web(question[:300]))
                else:
                    continue
        except (TimeoutError, httpx.HTTPError):
            continue
        record(store, source, remaining, await ask(pool))
    findings = list(verdicts.values())
    keep(store, user_id, question, findings + seconds)
    return findings, heard


# ── showing what the sources said ─────────────────────────────────────────


def regrade(ledger: list[dict], findings: list[Finding]) -> list[dict]:
    """The Isnad ledger with what the sources settled: supported claims are
    hasan with their source; contradicted ones stay da'if, with the source."""
    by_claim = {finding.claim: finding for finding in findings if finding.passage is not None}
    graded = []
    for unit in ledger:
        finding = by_claim.get(unit.get("text", ""))
        if finding is None or unit.get("grade") != "daif":
            graded.append(unit)
            continue
        passage = finding.passage
        assert passage is not None
        where = f"{passage.title} ({passage.source})"
        if finding.verdict == "supported":
            graded.append({**unit, "grade": "hasan", "support": [f"{where} says so"]})
        else:
            graded.append({**unit, "support": [f"{where} says otherwise"]})
    return graded


def report(
    findings: list[Finding], heard: Sequence[str] = (), *, ruling_question: bool = False
) -> dict:
    supported = [f.to_dict() for f in findings if f.verdict == "supported"]
    contradicted = [f.to_dict() for f in findings if f.verdict == "contradicted"]
    found: dict[str, Any] = {
        "checked": len(findings),
        "supported": supported,
        "contradicted": contradicted,
        "unknown": sum(1 for f in findings if f.verdict == "unknown"),
        "answered": list(dict.fromkeys(heard)),
    }
    if ruling_question:
        found["ruling"] = True
    return found


def summary_of(graded: list[dict]) -> dict:
    return isnad.summary(graded)
