"""Explicit teacher drafting; never imported by the owned inference provider."""

import os

from mizan_owned.store import ReviewStore
from providers import OpenAICompatibleProvider


def draft_support(owner: str, request: dict, store: ReviewStore, teacher=None) -> dict:
    model = os.getenv("MIZAN_SUPPORT_MODEL", "")
    if teacher is None:
        key = os.getenv("OPENROUTER_API_KEY", "")
        if not key or not model:
            raise ValueError("OPENROUTER_API_KEY and MIZAN_SUPPORT_MODEL are required")
        teacher = OpenAICompatibleProvider(
            api_key=key, base_url="https://openrouter.ai/api/v1", provider_name="openrouter"
        )
    response = teacher.create(
        model=model,
        max_tokens=1024,
        system="Provide a training/support draft only. Do not execute tools or claim verification.\n"
        + request["system"],
        messages=request["messages"],
        tools=None,
        temperature=0,
    )
    if any(block.type != "text" for block in response.content):
        raise ValueError("Teacher tool calls are prohibited")
    answer = "\n".join(block.text for block in response.content)
    row = store.save(
        owner, request, answer, "openrouter:" + model, response.stop_reason == "end_turn"
    )
    return {
        "proposal": row,
        "status": "draft",
        "used_as_final_answer": False,
        "used_for_weight_training": False,
    }
