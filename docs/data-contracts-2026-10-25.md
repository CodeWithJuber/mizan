# Data and training contracts

No new training dataset is fabricated by this patch. The JSON below is a schema
illustration with placeholders, not real Quran/Hadith text or gold labels.

## Links and verification scope

| Resource | Use and scope |
|---|---|
| [mizan-corpus-v2](https://huggingface.co/datasets/Zubairshaikh/mizan-corpus-v2) | User's programmatic corpus; the private MiniMind model card (available on request) pins revision `3b2521c64cd7861a138e185da4810ed20ada2950`. This patch did not recount all shards. |
| mizan-full-sft (private, available on request) | Completed MiniMind release; code/tokenizer/final checkpoint were authenticated, downloaded and checked in this repair. |
| Pinned filtered/training data in mizan-full-sft at revision `2ecc917266a626db919fd6af154f9f0d3a286bcf` (private, available on request) | Card reports 1,325,484 supported SFT train rows; teacher-forced loss is not QA accuracy. Counts are card-reported here. |
| [Q-CSMP v2](https://huggingface.co/datasets/Zubairshaikh/qcsmp-v2) | Historical root/sense data underlying the packaged WSD artifacts; preserve annotation provenance and known label limitations. |
| [quran-datasets-v2](https://huggingface.co/datasets/Zubairshaikh/quran-datasets-v2) | Earlier collection; contents not re-audited in this patch. |
| [Qwen3 S4](https://huggingface.co/Zubairshaikh/qwen3-0.6b-quran-s4) | Earlier separate model; neither Ruh nor MiniMind weights. Not rerun here. |
| [Quranic Arabic Corpus](https://corpus.quran.com/) | Candidate primary morphology resource; ingestion/license/annotation review needed for new experiments. No fresh corpus verification claimed here. |
| [Tanzil downloads](https://tanzil.net/download/) | Candidate exact Quran text source. Preserve edition, terms, verse IDs and original bytes; no invented quotations. |

## Ruh v2 sequence training input

One UTF-8 JSON object per line. Existing `ruh_model.train_sequence` accepts text
records or plain-text conversation records. Put related translations, variants,
windows and turns under the same stable `group_id` **before** splitting.

```json
{"group_id":"source:document-or-conversation-id","lang":"ar","text":"<unchanged source text>"}
{"group_id":"source:conversation-id","lang":"en","messages":[{"role":"user","content":"<source question>"},{"role":"assistant","content":"<reviewed source answer>"}]}
```

Supported roles in Ruh's serializer are `system`, `user`, `assistant`, `tool`;
content must be a string. A tool-message string does not create a trained tool
decoder. Conversation targets cover assistant content; role/user prefixes are
masked. Long records are windowed without manufacturing EOS at cut boundaries.
The CLI performs a deterministic train/validation split; it does **not** implement
a separate locked test-set lifecycle. Keep locked test data outside its input.

Keep a sidecar keyed by immutable `group_id` or row hash:

```json
{
  "group_id":"source:document-or-conversation-id",
  "source_url":"<publisher URL>",
  "source_revision":"<immutable revision>",
  "source_sha256":"<original file hash>",
  "locator":"<surah:ayah or book/chapter/hadith identifier>",
  "edition":"<edition and translation identity>",
  "license":"<source-specific reuse terms>",
  "annotation_origin":"human-reviewed or programmatic",
  "reviewer_id":"<reviewer identity when actually reviewed>"
}
```

For Hadith, add separately attributed grading authority, collection/edition and
grading disagreements. A book's fame or a generated `sahih` string is not evidence
of authentication. A generic behavioral example must be labelled as an authored
application and linked to evidence; it must not be presented as the source's exact
wording. Distinguish verse text, translation, tafsir, commentary and model output.

## MiniMind input and compatibility

Use the **pinned private trainer's** (available on request) data loader/chat template when continuing
MiniMind training. Its worker uses Hugging Face `apply_chat_template`, not Ruh's
`role: content` serializer. Its final checkpoint has a 2048-token serving limit.
Ruh byte windows and MiniMind subword token counts are different units.

The inference provider accepts `messages` with `system/user/assistant` text and a
final `user` message; it sends `max_new_tokens`, `do_sample`, `temperature` to the
queue worker. Images, tool-result blocks and unsupported roles are rejected.
This integration does not implement LoRA, DPO or GRPO for the custom Ruh model.

## Bounded own-model training command

This existing command starts a **new** Bayan-v2 candidate, preserving the custom
Ruh architecture. Run it only after supplying your reviewed real data. It is a
single-device CLI; do not prepend `torchrun` and assume it becomes distributed.

```bash
python -m ruh_model.train_sequence \
  --data /workspace/reviewed-training.jsonl \
  --source-metadata /workspace/sources.json \
  --output /workspace/candidate-new-run \
  --production-architecture --device cuda --precision bfloat16 \
  --seq-len 384 --batch-size 2 --steps 1000 --max-seconds 600 \
  --checkpoint-every-seconds 120
```

The sequence length is in Bayan-v2 byte tokens, not words. Batch size is an initial
operating choice, not a validated universal fit for every GPU. `--max-seconds`
bounds the training loop, not initialization, downloads, evaluation or cloud
billing. Use a separate provider-side budget watchdog. Training is not launched
by these documentation commands. Multi-GPU performance/parity is unverified here.

## Data still needed before a conversational-quality claim

- Real reviewed dialogue turns in the target languages, including greetings,
  identity, clarification, follow-ups, refusal to invent evidence and uncertainty.
- Independent contextual root/sense labels across many roots, nouns and verbs;
  root labels must not be provided only for event tokens.
- Negation, multiple events, coreference, time, quantities, quotation vs assertion,
  conflicting sources, unseen roots and ambiguous vowel-less forms.
- A locked, source-disjoint human-reviewed evaluation set. Hash and freeze it
  before model selection; report abstention/coverage and accuracy separately.
- A minimum useful gain and baseline comparisons declared before testing.
  Include root-ID/no-root/letter-order arms for root-theory experiments.

No finite unit suite establishes that every possible sentence is understood.
Additional examples are required because current generation failed, not because
an arbitrary row-count target guarantees intelligence.
