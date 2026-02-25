"""
Context Manager (Siyaq - سِيَاق — Context)
=============================================

"And We have not revealed to you the Book except for you to make clear to them
that wherein they have differed, and as guidance and mercy" — Quran 16:64

Manages the conversation context window efficiently.
Implements compaction when approaching token limits.
Preserves the most important context.
"""

import json
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger("mizan.context")


class ContextManager:
    """
    Manages conversation context window.
    Prevents token overflow while preserving important information.
    """

    # Rough estimate: 1 token ≈ 4 characters
    CHARS_PER_TOKEN = 4

    def __init__(self, max_tokens: int = 100000):
        self.max_tokens = max_tokens

    def estimate_tokens(self, messages: List[Dict]) -> int:
        """Rough token estimate for a message list"""
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        total_chars += len(json.dumps(block))
        return total_chars // self.CHARS_PER_TOKEN

    def needs_compaction(self, messages: List[Dict]) -> bool:
        """Check if messages need compaction"""
        return self.estimate_tokens(messages) > (self.max_tokens * 0.75)

    def compact(self, messages: List[Dict], agent=None) -> List[Dict]:
        """
        Compact messages to fit within context window.

        Strategy:
        1. Always keep the first message (original task)
        2. Always keep the last 5 messages (recent context)
        3. Summarize middle messages if we have an AI client
        4. Otherwise, truncate middle messages
        """
        if not self.needs_compaction(messages):
            return messages

        # Keep first and last N messages
        keep_last = min(5, len(messages))

        if len(messages) <= keep_last + 1:
            return messages

        first = messages[0]
        recent = messages[-keep_last:]
        middle = messages[1:-keep_last]

        # Create a summary of middle messages
        summary_parts = []
        for msg in middle:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, str):
                summary_parts.append(f"[{role}]: {content[:200]}")
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        summary_parts.append(f"[{role}]: {block.get('text', '')[:200]}")

        summary_text = "\n".join(summary_parts[:10])

        # Build compacted messages
        compacted = [first]
        if summary_text:
            compacted.append({
                "role": "user",
                "content": f"[Previous conversation summary]\n{summary_text}\n[End summary]",
            })
        compacted.extend(recent)

        logger.info(
            f"[SIYAQ] Compacted {len(messages)} messages to {len(compacted)} "
            f"(~{self.estimate_tokens(compacted)} tokens)"
        )

        return compacted

    def inject_memory(self, messages: List[Dict],
                      memories: List[Dict]) -> List[Dict]:
        """
        Inject relevant memories into the context.
        Adds a system-like context block with important memories.
        """
        if not memories:
            return messages

        memory_text = "Relevant knowledge from memory:\n"
        for mem in memories[:5]:
            memory_text += f"- [{mem.get('type', 'general')}] {str(mem.get('content', ''))[:200]}\n"

        # Insert after the first message
        enhanced = [messages[0]]
        enhanced.append({
            "role": "user",
            "content": f"[Context from Dhikr memory]\n{memory_text}",
        })
        enhanced.extend(messages[1:])

        return enhanced
