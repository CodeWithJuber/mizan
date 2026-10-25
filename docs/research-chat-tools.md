# Research tools in administrator chat

The built-in `research_archive` skill is discovered by the existing skill registry.
It adds two read-only tools to normal administrator chat when the selected provider
supports tools and the existing agent/tool gates permit them. Chats bound to a
coding workspace retain their narrower workspace tool policy. Both research tools
also check the bound authenticated administrator when invoked directly; model
arguments and skill context cannot supply identity or grant a role.

| Tool | Executes | Evidence boundary |
| --- | --- | --- |
| `mizan_research_search(query)` | Existing local SQLite FTS search after a pinned archive import | Returns original paths, hashes and source excerpts. Historical statements remain unverified; archived programs are never executed. Missing/broken imports return `unavailable`. |
| `mizan_context_resolve(...)` | Existing bounded finite or existential context resolver with strict `ContextRequest` validation | Uses only the caller's declared ontology, senses, observations and retractions. Preserves ambiguity and conflicts; it does not derive trusted labels from natural language. |

The resolver is stateless. Supply all observations on every call. A retraction
applies only to that call's supplied evidence; it does not delete persistent
knowledge. Source labels identify the supplied observation's origin, not independent
verification. Neither tool updates neural weights, accepts training gold or promotes
a checkpoint. Neither tool makes a model/network call.

Search does not download or import the archive automatically. Follow
`OWN_ARCHITECTURE_INTEGRATION.md` to import the consolidated bundle with the required
SHA256 into `MIZAN_RESEARCH_DIR`. The original uploaded archive with the same display
filename has different bytes and cannot substitute for the consolidated pinned
artifact. Repository manifests alone do not establish a production import.

These tools connect existing research mechanisms to the normal agent tool loop.
The text-only `mizan-owned` provider still cannot select or invoke tools. Tool access,
source preservation and conditional symbolic results do not demonstrate an
independently capable general language model.

## Bounded owned-model prompt

Normal owned chat now supplies an explicit host-created prompt projection instead
of sending the full diagnostic system boilerplate to a 2,048-byte-context model.
The original full system remains the exact review/replay identity. The projection
keeps the owned capability policy, exact custom role text, guidance and attributed
evidence; all supplied conversation messages, user preferences and current input
are preserved. Arbitrary system strings are never automatically shortened.

`owned_prompt` response metadata reports the rendering contract, UTF-8/framing
token counts and allocated output budget. If the irreducible input cannot fit
while reserving up to 64 output tokens, the provider abstains with
`owned_reason=context_budget_exceeded`; it does not drop instructions or fall back
to OpenRouter. A locally loaded checkpoint and successful transport still do not
establish useful conversational accuracy. General-chat readiness remains false.
