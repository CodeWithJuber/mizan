# Satr (ستر): covering secrets in what tools return

"Whoever covers a Muslim, Allah will cover him in this world and the next"
(Muslim 2699).

A tool's output goes to the model, the chat history, the live activity events and the
signed Sakk receipt. A key, token or password in it (a `cat .env`, a log line, a
connector's answer) would travel to all of them. Satr (`backend/security/satr.py`,
ported from ForgeKit's `src/secrets.js`) covers each secret-shaped value with
`[redacted:<kind>]` and leaves the rest of the text as it was. It is always on.

## Where it applies

- **Every tool result**, in one place: `BaseAgent._execute_tool_safe`, which every tool
  call passes, covers the result before it is returned and before its receipt is
  written. `satr.cover` walks strings, dicts, lists and tuples.
- **Memory writes**: `Dhikr.remember` (every note, fact and "remember this") and a
  Daftar edit store the text covered; Talaqqi does not keep an answer that holds a
  secret at all (it would hand out the placeholder when it answers again).
- **Connector logs** (`connectors.manager.redact`) use the same patterns.
- **Live activity events** (`agents.events.bounded`: tool starts, approval prompts,
  results): a value under a key that mentions a secret word is shown as `[redacted]`, and
  every string value is covered too, so `curl -H "Authorization: Bearer …"` inside a
  `bash` command never reaches the browser whole. The person still approves the exact
  parameters (an approval is bound to their SHA-256), only the display is covered.

## What is covered

| Kind | Shape |
|---|---|
| `private_key` | a PEM block (`-----BEGIN … -----END …-----`) |
| `github_token`, `gitlab_token` | `ghp_…`, `gho_…`, `ghu_…`, `ghs_…`, `ghr_…`, `github_pat_…`, `glpat-…` |
| `api_key` | `sk-…` (Anthropic, OpenAI and others), TypeSafe `apikey_…` |
| `stripe_key`, `npm_token` | `sk_live_…`, `rk_live_…`, `pk_live_…`; `npm_` + 36 characters |
| `slack_token`, `google_key`, `google_token`, `jwt`, `aws_key` | `xox[baprs]-…`, `AIza…`, `ya29.…`, `eyJ….eyJ…`, `AKIA…`/`ASIA…` (exact case) |
| `url_password` | the password in `scheme://user:PASSWORD@host` |
| `authorization` | an `Authorization: Bearer|Basic|Token …` header, a bearer token with a digit in it |
| `assigned` | a value assigned to a key whose last word is a credential word (`token`, `secret`, `password`, `passwd`, `apikey`, or `key` after `api`/`secret`/`private`/`access`/`signing`): `DB_PASSWORD=…`, `api_key: "…"`, `token = 'abcd…'`, `password: hunter2hunter2`. The env form (`KEY=value`, no spaces) covers the whole shell word; with any other separator the value must be a quoted literal of 4+ characters or a bare run of 8+ that is not code (below) |
| `key` | a structured value under a key ending in `password`, `secret`, `api_key`, `token`, `authorization`, `cookie` (a cursor such as `next_page_token` is not one) |
| `high_entropy` | a token of 20+ characters with lower case, upper case and three or more separate digit runs, at 3.9 bits per character or more |

## What is never covered

Precision comes first, so what MIZAN itself prints is never mangled:

- hex digests (SHA-256 receipts and parameter digests, git SHAs) and UUIDs: no mixed
  case, and a 64-hex digest is not a secret;
- lockfile and SRI digests (`sha512-…`, `h1:…`) and the fixed XMP packet id;
- code that assigns an expression: `token = jwt.sign(payload, key)`,
  `secret_key = settings.SECRET_KEY`, `password = getpass()`, and a bare value that is
  a number, or an identifier or dotted name with no digit or with `_`/`.` in it
  (`api_key = config_value_loaded`); a bare word with a digit and no `_` or `.`
  (`hunter2hunter2`) is still covered;
- keys that name where a secret is or how many, not the secret: their last word is not
  a credential word (`token_url`, `secret_name`, `password_file`, `api_key_path`,
  `max_tokens`, `tokens`, `token_count`);
- an identifier of words joined by `_` (`ClassName_getUser2Name3Value4Handler5Impl`) is
  not scored for entropy. Random tokens rarely decompose so: measured, under 1% of
  20-character urlsafe tokens that hold a `_`, 0.07% at 43 characters; a token with no
  `_` is always scored;
- a `data:` image (base64 is random by nature) and the path of a link (a document id in
  a URL is part of the address; a `?token=…` in it is still covered);
- Quran and hadith text, prose that mentions passwords or tokens, camelCase identifiers,
  file paths.

## A covered secret is never written back

A file read through Satr shows the placeholder where its secret was. A
`workspace_write` that puts a placeholder into an existing file holding a secret, with
that secret no longer in the new content, is refused with the reason (writing the
covered view back would replace the secret itself); so is a `workspace_edit` whose
`old_string` holds a secret that its `new_string` replaces with a placeholder. A
placeholder written into a new file (a README, a fixture), into a file that holds no
secret, or beside a secret that is kept, is ordinary text and is written.

## Limits

Detection is by shape: a short password with no key name next to it, or a credential in
a format nobody documents and below the entropy bar, passes. The patterns are bounded, so
the scan is linear in the length of the output.
