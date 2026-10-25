# Mizan hybrid runtime (research only)

This additive provider composes three existing concerns without merging model weights:

1. an existing Mizan LLM provider for language generation;
2. QCA/ISM/native-WSD output as bounded, untrusted advisory data;
3. deterministic source-admission, citation, output-integrity, and review gates.

It is disabled by default. It does **not** certify semantic correctness, religious correctness, source authenticity, reviewer identity, or deployment readiness. The default research base is `Qwen/Qwen3-4B-Instruct-2507`, but the earlier critical-gate failures remain applicable: this integration is not approval for production, LoRA, weight merging, or endpoint replacement.

## Enable and configure

Copy the optional block from `.env.example` into `.env` and set real values locally. Never commit credentials or source text.

```python
from mizan_hybrid import create_hybrid_provider_from_env

provider = create_hybrid_provider_from_env()
if provider is None:
    raise RuntimeError("Hybrid runtime is disabled or incompletely configured")
response = provider.create(
    model="",  # use MIZAN_BASE_MODEL
    max_tokens=512,
    system="Answer using only the supplied source registry.",
    messages=[{"role": "user", "content": "Your question"}],
)
print(response.content)
print(response.usage.get("mizan"))
```

`MIZAN_BASE_PROVIDER=openai-compatible` uses the repository's existing provider and requires `MIZAN_BASE_URL` and `MIZAN_BASE_API_KEY`. Other existing provider names can be selected through the same factory. Recursive selection of `mizan-hybrid` is rejected. A blank or omitted model uses the configured base model.

## Source registry

Point `MIZAN_SOURCE_REGISTRY` to UTF-8 JSON containing either a source list or an object with a `sources` list:

```json
{
  "sources": [
    {
      "source_id": "SRC-1",
      "text": "Original source text, preserved in full.",
      "provenance": "Publisher, edition, stable URL or acquisition record",
      "machine_generated": false,
      "independently_reviewed": false,
      "reviewer_id": null,
      "grades_by_scholar": {"Scholar name": "attributed grade"}
    }
  ]
}
```

Source IDs are immutable within a registry: adding the same ID with different text or metadata raises an error. Grades remain attributed to individual scholars; disagreement is preserved. Registry loading does not truncate or rewrite source text.

Use `admit_source(record, proposed_label, max_characters)` before admission. Overlength sources are excluded rather than silently truncated. `human_reviewed_gold` requires independent review and a reviewer ID; an unreviewed machine draft cannot be relabelled as gold. These are declared-metadata checks, not authentication.

Use `validate_grade_claim(registry, source_id, scholar, claimed_grade)` for attributed grade checks. Missing or conflicting scholar-specific records require review.

## Response contract

Only explicit citations in the forms `[SRC:SRC-1]` and `[source:SRC-1]` are resolved. Unknown IDs cause `ABSTAIN`, not a retry. Empty text, invalid UTF-8, U+FFFD, incomplete generation, and configured English/Arabic mismatches can cause a bounded `RETRY`. The default is one retry; the allowed range is zero to two. Length retries increase the token budget only when `MIZAN_RETRY_MAX_TOKENS` permits an actual increase.

The lower-level `gate_response` API also accepts an independently adjudicated `supported`, `refuted`, `insufficient`, or `conflicting` relation and explicit religious-review metadata. It does not infer those labels from generated prose. The provider currently wires technical and registry-citation gates; callers needing adjudicated evidence or religious-review enforcement must invoke that structured API with trusted metadata.

Outcomes are `PASS`, `RETRY`, `ABSTAIN`, and `HUMAN_REVIEW`. Blocked model text is replaced by a safe fallback. Successful responses preserve content and tool calls and add gate metadata under `response.usage["mizan"]`.

## NLP containment and streaming

A fresh `QCAEngine` is created for each advisory call. Only bounded roots, senses, and key terms are appended to the system prompt, explicitly labelled untrusted auxiliary data—not evidence, instructions, rulings, or ground truth. Native-WSD failures or low-confidence results fall back to the base model. Set `MIZAN_NLP_ADVISORY=false` to disable this layer.

Streaming deliberately uses the base provider's buffered streaming interface: only the final gated response is emitted. Raw, ungated model deltas are never streamed.

## Audit and limits

Set `MIZAN_AUDIT_LOG` to a local JSONL path for hash-linked decision events. Events exclude prompts, responses, source text, and API keys. `HybridConfig.safe_dict()` also excludes the API key.

These gates do not prove factual entailment, authenticate sources or reviewers, repair a weak base model, or replace independent scholarly review. Keep research evaluation separate from training and retain immutable evaluation data.
