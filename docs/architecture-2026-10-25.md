# Actual runtime and training boundaries

> Dated record (25 October 2026). It describes the code as it was then; the current architecture is in [architecture.md](architecture.md) and its [diagrams](diagrams/README.md).

![Actual own Ruh generator](ruh-runtime-2026-10-25.svg)

The arrows below describe implemented code paths, not claims about consciousness
or universal semantic understanding. QCA and WSD supply auxiliary data; the
selected generator produces reply tokens. The hybrid path checks declared output
contracts, not whether arbitrary propositions are true.

```mermaid
flowchart TD
    U["User + conversation history"] --> A["BaseAgent"]
    A --> Q["QCA: lexical root candidates"]
    A --> W["WSD: observed Arabic tokens"]
    Q --> P["Messages + advisory context"]
    W --> P
    A --> P
    P --> R{"Selected provider"}
    R --> H["Optional hybrid wrapper"]
    R --> G["Direct provider"]
    H --> B["Configured base generator"]
    B --> K["Output gates + bounded retries"]
    K --> O["Reply + technical metadata"]
    G --> O
```

```mermaid
flowchart TD
    S["Reviewed source records + provenance"] --> D["Source-group split + leakage checks"]
    D --> T{"Checkpoint family"}
    T --> M["MiniMind tokenizer + chat template"]
    T --> V["Ruh Bayan v2 UTF-8 surface tokens"]
    M --> MC["MiniMind causal Transformer"]
    V --> RC["Ruh: ISM embedding, causal Sam/Basar + Qalb, FFN/MoE"]
    MC --> L["Assistant-masked next-token loss"]
    RC --> L
    L --> C["Separate candidate checkpoints"]
    C --> E["Generation + held-out task evaluation"]
    E --> F{"Promotion evidence sufficient?"}
    F -->|No| X["Keep candidate; record failures"]
    F -->|Yes| Y["Versioned deployment + rollback"]
```

The two tokenizer/weight families are incompatible. Sharing a JSONL conversation
format does not permit swapping their token IDs or state dictionaries. No dataset
was generated, new checkpoint trained or candidate promoted during this repair.

For `hi`, the observed trace is: user text → no Arabic WSD occurrence → selected
MiniMind worker serializes the exact training chat template → original checkpoint
generates tokens → adapter reads `response`, usage and finish status → UI receives
text. The raw checkpoint answered `فَأَنتَ` in the CPU probe. No greeting template
was inserted to hide this failure. In hybrid mode an EOS reply can pass technical
gates while remaining irrelevant: technical completion is not semantic correctness.
