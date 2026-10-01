"""Explicit conversation serialization shared by training and inference.

Legacy checkpoints are root generators; preserving context does not establish
instruction-following ability. Version 2 training can retain the protocol exactly.
"""

import json


def serialize_messages(messages: list[dict], system: str = "", *, assistant_prefix=True) -> str:
    records = []
    if system:
        records.append(f"system: {system}")
    for message in messages or []:
        role = message.get("role", "user")
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("Unsupported message role")
        content = message.get("content", "")
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    parts.append(
                        block.get("text", "")
                        if block.get("type") == "text"
                        else json.dumps(block, ensure_ascii=False)
                    )
                else:
                    parts.append(
                        block.text
                        if getattr(block, "type", None) == "text"
                        else json.dumps(vars(block), ensure_ascii=False)
                    )
            content = "\n".join(parts)
        records.append(f"{role}: {content}")
    if assistant_prefix:
        records.append("assistant:")
    return "\n".join(records)
