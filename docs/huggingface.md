# Hugging Face in MIZAN

MIZAN's code sandbox has **no network**, by design: a program MIZAN runs cannot download anything, so it cannot be used to send your data out. That is why "download this dataset in Python" fails inside the sandbox ("DNS resolution failed").

MIZAN reads Hugging Face **itself, on the server**, and puts what is needed into your project, where the program then works offline (`backend/knowledge/hf_hub.py`, tools in `skills/builtin/huggingface_hub.py`):

| Ask | What MIZAN does |
|---|---|
| `https://huggingface.co/<you>/` or "mere huggingface datasets dikhao" | Lists the account's datasets and models (with "training", models too) |
| `https://huggingface.co/datasets/<owner>/<name>` | Lists its files and sizes, and shows the first rows (the Hub's dataset viewer) |
| "`…/<name>` se `file.jsonl` project me lao", or a `/blob/main/<file>` link | Imports the file into the selected project (or Scratch) as `hf/<name>/<file>`, with its SHA-256 and source link |

- **Large files:** a project file is limited (1 MiB by default, `MIZAN_WORKSPACE_MAX_FILE_BYTES`). A larger text file (`.jsonl`, `.json`, `.csv`, …) is imported as its first whole rows (`file.sample.jsonl`) and the reply says so; a large binary file is refused.
- **Only Hugging Face is contacted:** `huggingface.co` and its file servers (`*.hf.co`); every redirect is checked, and the token is never sent to a file server.
- **Read-only:** nothing in MIZAN writes to the Hub.

## The token (vault)

Set **System settings → API keys → Hugging Face token** (`HF_TOKEN`). It is stored sealed in `$MIZAN_DATA_DIR/runtime_settings.json` (encrypted with the connectors key, never shown again) and used **only for administrators**: a user's request reads public repositories only and can never reach the owner's private ones. A fine-grained read-only token is enough.

## The locked evaluation set

The owner's published, hash-locked evaluation set (`Zubairshaikh/mizan-eval-v1`, 300 items, SHA-256 `14844d6f…`) is an AGI Test block (**Your locked eval**). MIZAN downloads it once into `$MIZAN_DATA_DIR/imtihan/` and uses it only when the hash matches; it is never copied into this repository or into training data, as its lock requires. See [imtihan.md](imtihan.md).
