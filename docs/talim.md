# Ta'lim (تعليم): teaching MIZAN new examples

MIZAN understands messages by evidence (Tamyiz, `backend/core/tamyiz.py`), not by word lists:

- **Qasd** reads what a message asks for (its intent).
- Its **facets** answer yes/no questions about it (a ruling question, about the deen, about a word's root, …).
- **Lughah** reads its language.

Each is a naive Bayes model fitted on seed examples shipped in `backend/tadbir/data/`. Ta'lim (`backend/tadbir/talim.py`) lets an administrator add examples, and a language Lughah did not know (Tamil, Bengali, …), without changing code.

## Where

**Developer → Teach MIZAN** (administrators only):

1. **Pick a model:** `qasd`, `lughah`, or a facet `qasd.<name>`. The labels it takes are listed.
2. **Type examples,** one per line: `label | text` (or a tab between them).
3. **Or import from Hugging Face:** give the dataset, config, split, rows (up to 5,000), the text and label columns, and a label map (`dataset label = MIZAN label`, one per line; rows whose label is not mapped are left out). Rows are read on the server through the dataset viewer (`knowledge/hf_hub.rows`).
4. **Teaching a new language:** pick `lughah`, use a new code as the label (`ta`), and give the language's name (Tamil).

## When a batch is kept

A batch is kept only if it does not make MIZAN worse at what it already knew. Nothing else decides; there is no hand-set accuracy floor.

1. The model is fitted with and without the batch.
2. Every known seed is re-read by exact leave-one-out, before and after. Up to 1,500 seeds are read: every k-th.
3. A paired bootstrap over those seeds gives P(after < before). It uses 2,000 resamples and a fixed seed, so the verdict is reproducible.
4. The batch is **refused when P(worse) ≥ 0.95**, the same standard Tajdid uses to replace an incumbent. Otherwise it is **kept**.

Each batch is listed with:

- its source and licence;
- the accuracy on what MIZAN knew, before and after;
- how well the refitted model reads the new examples themselves;
- each class whose accuracy changed.

A kept batch is a Sakk receipt, and **Undo** removes it. Batches live in `$MIZAN_DATA_DIR/talim.db`. The kept ones join each model's corpus, so the fit follows them; fits are cached by the corpus SHA-256.

## API

| Route | What it does |
|---|---|
| `GET /api/tadbir/talim` | The teachable models and their labels, the languages taught, and every batch |
| `POST /api/tadbir/talim` | `{model, examples: [{text, label}], source?, licence?, language_name?}`: judge a batch and keep it if it passes |
| `POST /api/tadbir/talim/import` | `{model, dataset, config, split, revision?, text_column, label_column, label_map?, limit, licence?, language_name?}`: the same, from a Hugging Face dataset |
| `DELETE /api/tadbir/talim/{batch}` | Undo a kept batch |

## Setting

`MIZAN_TALIM` is `on` by default, in Settings → System settings. When `off`, taught batches are kept but set aside, and MIZAN reads messages with its shipped seeds only. A change applies on restart.

The shipped fit (`core/data/tamyiz.json`, `cd backend && python -m core.tamyiz_cache`) is always computed with Ta'lim off. Production's taught batches therefore never leak into the repository's seeds.
