"""Sidq (صدق): the Truth Gate. No claim MIZAN can prove false reaches the user.

Muhasaba reviews answers once a day; Sidq checks each answer before it is
shown, with the same proofs and no model call:

- **arithmetic** stated as ``expression = value``: recomputed exactly; a wrong
  value is replaced by the right one
- **Quran and hadith quoted with a reference**: compared with the text MIZAN
  reads from its authentic source, word for word and vowel for vowel; an
  altered quote is replaced by the source text. An Arabic passage given with
  no reference that is mostly an ayah (``muhasaba.scripture``) is checked
  against that ayah the same way
- **the mushaf's script**: Arabic written with marks only the mushaf writes
  that is not the Quran's text (``muhasaba.mushaf_script``) is marked, never
  rewritten
- **fabricated claims** (mawdu' in the Isnad ledger): an action that has no
  receipt ("I ran the code") is removed, a citation to a source that does not
  exist loses its marker
- **links MIZAN never found**: opened (public addresses only); a link that
  does not open is removed
- **a hadith cited to the wrong book**: a quote given as Bukhari or Muslim that
  none of their narrations says, while another of the six books does
  (``hadith_index``), is reported with where it is

``MIZAN_TRUTH_GATE``: ``strict`` (default) corrects and removes, ``flag``
keeps the text and marks each problem, ``off`` skips the gate. What the gate
did is returned as a report, shown under the answer.
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

from . import hadith_index, muhasaba, muqabala
from .express import phrase

MODES = ("strict", "flag", "off")
MAX_LINKS = 5
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)|(https?://[^\s<>)\]]+)")
_CITE = re.compile(r"\s?\[(\d{1,2})\]")
_SENTENCE_END = re.compile(r"(?<=[.!?۔؟])\s+")


def mode() -> str:
    value = os.getenv("MIZAN_TRUTH_GATE", "strict").strip().lower()
    return value if value in MODES else "strict"


async def gate(
    text: str,
    ledger: list[dict] | None = None,
    *,
    language: str = "en",
    max_citation: int = 0,
    check_links: bool = True,
) -> tuple[str, dict]:
    """The answer after the gate, and what the gate did."""
    current = mode()
    if current == "off" or not isinstance(text, str) or not text.strip():
        return text, {}
    strict = current == "strict"
    report: dict[str, Any] = {"mode": current, "corrected": [], "removed": [], "flagged": []}

    for finding in muhasaba.arithmetic(text):
        changed = _fix_arithmetic(text, finding) if strict else text
        item = f"{finding['expression']} = {finding['correct']} (not {finding['claimed']})"
        if changed != text:
            text = changed
            report["corrected"].append({"kind": "arithmetic", "detail": item})
        else:
            report["flagged"].append({"kind": "arithmetic", "detail": item})

    with muhasaba.sources():  # each source text read once for this answer
        # Last quote first, so replacing one never moves the lines of another.
        quotes = await muhasaba.scripture(text)
        for finding in sorted(quotes, key=lambda found: -min(found.get("lines") or [0])):
            detail = f"{finding['reference']}: the quoted text differs from MIZAN's source"
            if finding.get("unreferenced"):
                detail += " (given as the Quran without a reference)"
            if strict:
                text = _replace_quote(
                    text, finding["source"], finding["reference"], language, finding.get("lines")
                )
                report["corrected"].append({"kind": "quote", "detail": detail})
            else:
                report["flagged"].append({"kind": "quote", "detail": detail})

        # Arabic written with the mushaf's marks that is not the Quran's text:
        # marked under the answer, never rewritten. A quote already reported is
        # not read again (in strict mode it is now the source's own text).
        reported = [] if strict else [line for found in quotes for line in found.get("lines") or []]
        for finding in await muhasaba.mushaf_script(text, reported):
            report["flagged"].append(
                {
                    "kind": "mushaf_script",
                    "detail": f"“{finding['text']}” is written in the mushaf's script "
                    "but is not the Quran's text",
                }
            )

    # A hadith quoted under books whose narrations do not say it, while another
    # of the six books does: reported with where it is (never rewritten).
    for finding in await hadith_index.check(text):
        cited = " and ".join(finding["cited"])
        found = ", ".join(item["reference"] for item in finding["found"])
        report["flagged"].append(
            {
                "kind": "hadith_source",
                "detail": f"\u201c{finding['quote']}\u201d is found in {found}, not in {cited}",
                "found": finding["found"],
            }
        )

    unchecked: list[str] = []
    for unit in ledger or []:
        if unit.get("grade") != "mawdu":
            continue
        reasons = " ".join(str(reason) for reason in unit.get("support", []))
        sentence = str(unit.get("text", ""))
        if "action that has no receipt" in reasons:
            if strict and sentence and sentence in text:
                text = _drop(text, sentence)
                report["removed"].append({"kind": "action", "detail": sentence[:200]})
            else:
                report["flagged"].append({"kind": "action", "detail": sentence[:200]})
        if "does not exist" in reasons:
            text, dropped = _drop_citations(text, max_citation) if strict else (text, 0)
            if dropped:
                report["removed"].append({"kind": "citation", "detail": f"{dropped} marker(s)"})
            else:
                report["flagged"].append({"kind": "citation", "detail": sentence[:200]})
        if "did not find" in reasons:
            unchecked += [m[1] or m[2] for m in _LINK.findall(sentence)]

    if check_links and unchecked:
        dead = await dead_links(list(dict.fromkeys(url.rstrip(").,") for url in unchecked)))
        report["links"] = {"checked": min(len(unchecked), MAX_LINKS), "dead": dead}
        for url in dead:
            if strict:
                text = _unlink(text, url)
                report["removed"].append({"kind": "link", "detail": url})
            else:
                report["flagged"].append({"kind": "link", "detail": url})

    if not (report["corrected"] or report["removed"] or report["flagged"]):
        return text, {"mode": current, "passed": True}
    note_key = "sidq_corrected" if report["corrected"] or report["removed"] else "sidq_flagged"
    count = len(report["corrected"]) + len(report["removed"]) + len(report["flagged"])
    # Shown under the answer (usage.sidq), never added to its text; a channel
    # with no notes view puts it on its own line.
    report["note"] = phrase(note_key, language, count=count)
    return text, report


def _fix_arithmetic(text: str, finding: dict) -> str:
    expression, claimed = str(finding["expression"]), str(finding["claimed"])
    number = ",?".join(re.escape(char) for char in claimed)
    pattern = re.compile(re.escape(expression) + r"(\s*=\s*\**\s*)" + number + r"(?!\d|\.\d)")
    return pattern.sub(lambda m: f"{expression}{m.group(1)}{finding['correct']}", text, 1)


def _replace_quote(
    text: str, source: str, reference: str, language: str, only: list[int] | None = None
) -> str:
    """The quoted Arabic lines (those given under this reference, when known)
    become MIZAN's source text."""
    lines = text.splitlines()
    run: list[int] = []
    for index, line in enumerate(lines):
        if only is not None and index not in only:
            if run:
                break
            continue
        arabic = len(muqabala.fold_arabic(line))
        latin = len(re.findall(r"[A-Za-z]{2,}", line))
        if arabic >= 3 and arabic >= latin:
            if run and index != run[-1] + 1:
                break
            run.append(index)
        elif run:
            break
    quoted = [f"> {line}" for line in source.splitlines() if line.strip()]
    quoted.append(f"_{phrase('sidq_quote', language, reference=reference)}_")
    if not run:
        return f"{text.rstrip()}\n\n" + "\n".join(quoted)
    return "\n".join(lines[: run[0]] + quoted + lines[run[-1] + 1 :])


def _drop(text: str, sentence: str) -> str:
    out = text.replace(sentence, "", 1)
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", out)).strip()


def _drop_citations(text: str, max_citation: int) -> tuple[str, int]:
    dropped = 0

    def keep(match: re.Match[str]) -> str:
        nonlocal dropped
        if 1 <= int(match.group(1)) <= max_citation:
            return match.group(0)
        dropped += 1
        return ""

    return _CITE.sub(keep, text), dropped


def _unlink(text: str, url: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\(" + re.escape(url) + r"\)", r"\1", text)
    return text.replace(url, "")


MAX_HOPS = 5  # redirects followed per link, each one checked and pinned


async def dead_links(urls: list[str], timeout: float = 4.0) -> list[str]:
    """The links that do not exist: the page is gone (404/410) or the host does not.

    Only public addresses are opened, and every redirect hop is checked and
    pinned to the address that was checked (no DNS rebinding); a hop to a
    private address is not followed and the link is not judged. When MIZAN
    cannot reach the network at all, nothing is judged dead.
    """
    import httpx

    from connectors.net_guard import BlockedDestination, check_url, pinned_destination

    async def online() -> bool:
        try:
            await check_url("https://quran.com/")
            return True
        except BlockedDestination:
            return False

    async def status(client: httpx.AsyncClient, url: str) -> tuple[int, str | None]:
        """The page's status code, and where it redirects (if it does)."""
        destination, host, tls_name = await pinned_destination(url)
        headers = {"User-Agent": "MIZAN-Sidq/1.0", "Host": host}
        extensions = {"sni_hostname": tls_name}
        response = await client.head(destination, headers=headers, extensions=extensions)
        if response.status_code in (403, 405, 501):
            async with client.stream(
                "GET", destination, headers=headers, extensions=extensions
            ) as streamed:  # the status only; the body is never read
                response = streamed
        location = response.headers.get("location") if response.is_redirect else None
        return response.status_code, location

    async def missing(client: httpx.AsyncClient, url: str, reachable: bool) -> bool:
        try:
            await check_url(url)
        except BlockedDestination as exc:
            return reachable and "Cannot resolve" in str(exc)  # a host that does not exist
        current = url
        for _hop in range(MAX_HOPS + 1):
            try:
                code, location = await status(client, current)
            except (ValueError, OSError, httpx.HTTPError):
                return False  # unreachable or not public: not proof it never existed
            if location is None:
                return code in (404, 410)
            current = str(httpx.URL(current).join(location))
        return False  # too many redirects: not judged

    reachable = await online()
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=False, trust_env=False
    ) as client:
        results = await asyncio.gather(
            *(missing(client, url, reachable) for url in urls[:MAX_LINKS])
        )
    return [url for url, gone in zip(urls[:MAX_LINKS], results, strict=True) if gone]
