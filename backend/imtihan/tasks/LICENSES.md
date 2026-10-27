# Sources and licences of the Imtihan tasks

Each task names its source in its `source` field. Tasks without a `source` were
written for MIZAN.

| File | Source | Licence |
|---|---|---|
| `arc.jsonl` | 8 tasks from the ARC-AGI-2 public evaluation set, <https://github.com/arcprize/ARC-AGI-2> (ARC Prize Foundation). Only the first test input of each task is used. | Apache License 2.0 |
| `knowledge.jsonl` | 8 questions from TruthfulQA, as binary choices between each question's Best Answer and Best Incorrect Answer. Lin, Hilton and Evans, "TruthfulQA: Measuring How Models Mimic Human Falsehoods" (2022), <https://github.com/sylinrl/TruthfulQA>. The Religion category is left out. | Apache License 2.0 |
| `safety.jsonl` | 6 prompts from XSTest. Röttger et al., "XSTest: A Test Suite for Identifying Exaggerated Safety Behaviours in Large Language Models" (NAACL 2024), <https://github.com/paul-rottger/xstest>. The prompts are used unchanged. | CC BY 4.0 |
| All other files | Written for MIZAN | Same licence as MIZAN |

Humanity's Last Exam and GAIA forbid redistribution, so their tasks are not
included.
