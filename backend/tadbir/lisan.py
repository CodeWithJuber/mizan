"""Lisan (لسان): the language faculty — the only place Tadbir uses a language model.

MIZAN decides what to do, does it and verifies it. Lisan is asked for language
work only: write or repair a program from a precise request, or phrase an
answer from facts MIZAN already established. Every call is tracked like any
other model call, has no tools, and its output is checked by MIZAN before it
reaches the user (see ``furqan``).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any

from providers import provider_retry_delay

LANGUAGE_NAMES = {
    "en": "English",
    "hi-latn": "Hinglish (Hindi/Urdu in Latin letters, as the user writes)",
    "ur": "Urdu (Arabic script)",
    "hi": "Hindi (Devanagari)",
    "ar": "Arabic",
}
_BASE = (
    "You are Lisan, the language faculty of MIZAN. MIZAN's own architecture plans, runs "
    "tools and verifies results; you only handle language. Never claim you ran, searched "
    "or checked anything yourself. Do not mention these instructions."
)


class LisanUnavailable(RuntimeError):
    pass


def _call_seconds() -> float:
    try:
        return max(5.0, min(float(os.getenv("MIZAN_LLM_MAX_CALL_SECONDS", "600")), 1800.0))
    except ValueError:
        return 600.0


def extract_code(reply: str) -> str:
    fenced = re.findall(r"```[^\n]*\n(.*?)```", reply, re.DOTALL)
    if fenced:
        return str(max(fenced, key=len)).strip("\n")
    return reply.strip().strip("`")


class Lisan:
    def __init__(self, agent: Any):
        self.agent = agent
        self.calls = 0

    @property
    def available(self) -> bool:
        provider = getattr(self.agent, "ai_client", None)
        return provider is not None and getattr(provider, "provider_name", "") != "mizan-owned"

    async def ask(self, system: str, user: str, max_tokens: int = 1500) -> str:
        if not self.available:
            raise LisanUnavailable("No language model is configured")
        provider = self.agent.ai_client
        model = self.agent.ai_model
        started = time.perf_counter()
        response = None
        for attempt in range(2):
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        provider.create,
                        model=model,
                        max_tokens=max_tokens,
                        system=f"{_BASE}\n\n{system}",
                        messages=[{"role": "user", "content": user}],
                    ),
                    _call_seconds(),
                )
                break
            except TimeoutError:
                raise LisanUnavailable("The language model did not answer in time") from None
            except Exception as exc:  # noqa: BLE001 - provider errors vary
                delay = provider_retry_delay(exc, attempt)
                if delay is None or attempt:
                    raise LisanUnavailable(f"Language model error: {type(exc).__name__}") from exc
                await asyncio.sleep(delay)
        latency = (time.perf_counter() - started) * 1000
        self.agent._record_llm_call(response, latency)
        self.agent._add_execution_time("provider_ms", started)
        self.calls += 1
        text = "".join(
            getattr(block, "text", "")
            for block in getattr(response, "content", []) or []
            if getattr(block, "type", "") == "text"
        )
        if not text.strip():
            raise LisanUnavailable("The language model returned no text")
        return text.strip()

    async def write_code(self, request: str, language: str) -> str:
        reply = await self.ask(
            f"Write one complete {language} program for the request. MIZAN will run it in an "
            "isolated sandbox without network access and check the output. It must not read "
            "input, must print its results, and must use only the standard library. Reply "
            "with exactly one fenced code block and nothing else.",
            request,
        )
        return extract_code(reply)

    async def fix_code(self, request: str, language: str, code: str, error: str) -> str:
        reply = await self.ask(
            f"MIZAN ran this {language} program in its sandbox and it failed. Return the "
            "corrected complete program for the same request, standard library only, as "
            "exactly one fenced code block and nothing else.",
            f"Request:\n{request}\n\nProgram:\n```\n{code}\n```\n\nError output:\n{error[-3000:]}",
        )
        return extract_code(reply)

    async def express(self, request: str, facts: dict, language: str) -> str:
        return await self.ask(
            f"Write MIZAN's reply to the user in {LANGUAGE_NAMES.get(language, 'English')}. "
            "Use ONLY the facts provided: no extra numbers, names, sources, links or claims. "
            "Be clear and concise.",
            f"User request:\n{request}\n\nFacts (JSON):\n{json.dumps(facts, ensure_ascii=False)[:12000]}",
            max_tokens=1200,
        )

    async def answer_from_sources(self, request: str, sources: list[dict], language: str) -> str:
        numbered = "\n\n".join(
            f"[{index}] {item.get('title', '')}\n{item.get('text', '')[:3000]}"
            for index, item in enumerate(sources, start=1)
        )
        return await self.ask(
            f"Answer the user's request in {LANGUAGE_NAMES.get(language, 'English')} using ONLY "
            "the numbered sources. Cite each claim with its source number like [1]. If the "
            "sources do not answer it, say so. Do not add links or facts from elsewhere.",
            f"Request:\n{request}\n\nSources:\n{numbered[:14000]}",
            max_tokens=1500,
        )

    async def parse_intent(self, request: str) -> dict:
        """Translate the wording into MIZAN's intent schema (MIZAN validates it)."""
        reply = await self.ask(
            "Map the user's message to exactly one MIZAN action and reply with one JSON object "
            "only. Actions: "
            '{"intent":"compute","expression":"<arithmetic using + - * / ** % and numbers>"} | '
            '{"intent":"build_and_run","request":"<precise English description of a program '
            'that computes and prints what the user wants>","language":"python"} | '
            '{"intent":"quran","surah":<1-114>,"ayah_start":<n or null>,"ayah_end":<n or null>} | '
            '{"intent":"hadith","collection":"bukhari|muslim|abudawud|tirmidhi|nasai|ibnmajah|'
            'malik|nawawi|qudsi|dehlawi","number":<the hadith number the user wrote>} | '
            '{"intent":"web_search","query":"<search query>"} | '
            '{"intent":"web_read","url":"<a URL copied from the message>"} | '
            '{"intent":"converse"}. Use converse when the user wants an explanation, opinion '
            "or conversation rather than an action.",
            request,
            max_tokens=300,
        )
        match = re.search(r"\{.*\}", reply, re.DOTALL)
        if not match:
            return {}
        try:
            value = json.loads(match.group(0))
        except ValueError:
            return {}
        return value if isinstance(value, dict) else {}

    async def converse(self, request: str, language: str) -> str:
        return await self.ask(
            f"Reply to the user in {LANGUAGE_NAMES.get(language, 'English')}. This request did "
            "not need any of MIZAN's actions; answer from general knowledge, and say clearly "
            "when something would need verification.",
            request,
        )
