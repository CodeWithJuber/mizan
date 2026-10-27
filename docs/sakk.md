# Sakk (صَكّ): signed receipts for everything MIZAN does

A *sakk* is a written deed. Every action MIZAN takes or holds for you is written as a receipt in **your own chain**, and the chains are signed once a day. Nobody can change, remove or reorder a receipt later, not even an administrator with the database, without the chain showing it.

Code: `backend/security/sakk.py`, the `/api/sakk*` and `/api/public/*` routes in `backend/api/main.py`, `scripts/verify_sakk.py`, `frontend/src/components/SakkPanel.tsx`.

## What is written

| Receipt | When |
|---|---|
| `tool` | every tool call through `_execute_tool_safe`, whatever happened: done, held, declined, error or raised |
| `held_decision` | you allowed or denied a held action |
| `approval` | you answered a live approval prompt |
| `erase` | you deleted a chat (Mahw), with how much was removed and how many traces were found |
| `scorecard` | an administrator published an AGI-test result (owner `system`) |

**What a receipt holds:**
- **Every receipt:** version, owner, sequence number, time, kind, and `prev` (the previous receipt's hash).
- **Tool receipts also:** the tool name, the outcome, and **HMAC-SHA256 digests** of the parameters and the result.

Its `hash` is SHA-256 over the receipt's RFC 8785 canonical JSON ([`rfc8785`](https://github.com/trailofbits/rfc8785.py), Apache-2.0).

**No content is kept.** The digests use a key of your own, sealed with the data key, so:
- you can export the key and show that a receipt matches what you hold;
- nobody else can test a guess against a receipt.

Deleting a chat (Mahw) leaves its receipts: they say which tools ran and how they ended, with no words from the chat. The Mahw receipt says so under *kept*.

The short display line ("bash · held") is outside the hashed fields.

## Checking

**What the chain catches.** Each receipt names the hash of the one before it. Each of these is caught at the first receipt it affects:
- changing a receipt changes its hash;
- removing or reordering one breaks the sequence;
- rewriting one and recomputing its hash breaks the next receipt's link.

`GET /api/sakk/verify` (Settings → Receipts → **Verify my chain**) recomputes the whole chain and names the first receipt that fails.

**The daily signature.** Once a day (UTC) MIZAN signs, with an Ed25519 key of its own, the Merkle root of every chain's latest receipt:
- leaves and nodes are hashed as in RFC 6962;
- a leaf names its owner only as a SHA-256 digest;
- the roots and the public key are public: `/api/public/sakk`, and the reliability page.

A history therefore cannot be rewritten after it was signed, even by recomputing every hash, without the signed root changing.

**Checking it yourself, offline.** **Export to check elsewhere** gives you `mizan-sakk.json`: your chain, your digest key, MIZAN's public key and the Merkle proof of your chain in the latest signed root. Then:

```
pip install rfc8785 cryptography
python scripts/verify_sakk.py mizan-sakk.json --public-key <key from the reliability page>
```

It recomputes every hash and link, checks your chain's head is in the signed root, and checks the signature.

## Public reliability page

`/reliability` needs no sign-in. It shows:
- the latest published AGI-test result ([Imtihan](imtihan.md)), with the same aggregate charts as the admin page: per-block pass rates with 95% Wilson intervals, the weighted index, agentic dimensions, games, Isnad support, calibration, consistency and work done;
- the published history;
- the signed Sakk roots and the public key.

**What is never published:** prompts, answers and per-task rows. The locked evaluation appears only as its block score.

**Publishing:** an administrator publishes a finished run from Developer → AGI Test (**Publish on the public page**), and can remove it again. Publishing writes the report's SHA-256 into a `scorecard` receipt (`backend/imtihan/scorecard.py`).

## API

| Route | |
|---|---|
| `GET /api/sakk?limit=&before=` | your receipts, newest first |
| `GET /api/sakk/verify` | your chain checked: `{ok, receipts, head}` or `{ok: false, broken_at, problem}` |
| `GET /api/sakk/export` | your chain with your digest key and the signed proof |
| `GET /api/sakk/verify/all` | admin: every chain checked |
| `POST`/`DELETE /api/imtihan/runs/{id}/publish` | admin: publish or remove a run |
| `GET /api/public/reliability`, `/api/public/reliability/{run_id}` | public, rate-limited |
| `GET /api/public/sakk` | public key and the last 30 signed roots |

Back up `sakk.db` with the data volume. Its signing key is sealed with the data key, like connector secrets.
