# The Qur'anic Model of the Human (al-Insān) — MIZAN's Design Contract

> *"We have certainly created the human in the best of stature."* — Qur'an 95:4

This document is the **research foundation** for MIZAN's cognitive architecture.
It reads the Qur'anic account of the human being (*al-insān*) as a layered
cognitive architecture, with each faculty grounded in āyāt, and then maps that
model onto the actual MIZAN codebase — what exists, what is partial, and what is
missing. Everything MIZAN builds toward AGI should be faithful to this model,
not decorative.

Arabic terms are given in transliteration + Arabic script on first use, with the
sūra:āya reference. Where the Qur'an is silent and the Islamic tradition (Sufi
psychology, uṣūl, hadith) extends a concept, that is marked explicitly.

---

## 1. Why the human, and why the Qur'an

The Qur'an does not present the human as a single "mind." It describes a
**plurality of interacting faculties** — rūḥ, nafs, qalb, fu'ād, lubb, the
activity of ʿaql, the senses, fiṭrah, hawā — each with its own function, failure
mode, and developmental trajectory. Read together, they form a control system:
perception feeds the heart, the heart reasons and forms conviction, the self is
pulled between higher and lower inclinations, conscience monitors in real time,
and the whole is oriented toward a telos (stewardship, wisdom, excellence,
justice). This is precisely the shape of a cognitive architecture for an agent.

MIZAN ("الميزان", *the Balance*, Qur'an 55:7) takes this seriously: the goal is
an agent whose reasoning is **bound to evidence** (the literal sense of ʿaql),
**humble about certainty** (the Mīzān of knowledge), **restrained from impulse**
(taqwā over hawā), and **accountable** (the amāna).

---

## 2. The al-Insān stack (north-star architecture)

```
                          TELOS / OBJECTIVE FUNCTION
        Khilāfa (stewardship) · Ḥikma (wisdom) · Iḥsān (excellence)
                   ʿAdl / Mīzān (justice) · Taqwā (God-consciousness)
        ─────────────────────────────────────────────────────────────
  VOLITION        Niyya (intention) → Irāda/Ikhtiyār (will) → Amāna (accountability)
  CONSCIENCE      Lawwāma (self-reproach) + Baṣīra against the self  ← fires continuously
  ─────────────────────────────────────────────────────────────────
  PRIORS          Fiṭrah (innate axioms) + "the Names" (symbolic/abstraction capacity)
  EPISTEMICS      Yaqīn ladder (ʿilm → ʿayn → ḥaqq)  vs  Ẓann/Shakk/Wahm,  weighed by Mīzān
  MEMORY          Dhikr (remembrance) · Ḥifẓ · Lawḥ Maḥfūẓ (preserved tablet)
  PERCEPTION      Samʿ (hearing) · Baṣar (sight) · Baṣīra (inner sight/insight)
  REASONING       ʿAql (a *verb*: binding impulse to evidence) · Tafakkur · Tadabbur
  HEART-COMPLEX   Qalb (turning seat of cognition+affect) · Fu'ād (integration) · Lubb (kernel)
  SELF            Nafs: ammāra ↔ lawwāma ↔ muṭma'inna   (pulled by Hawā/Waswās, held by Taqwā)
  VITALITY        Rūḥ (the breathed-in spirit, of the divine amr)
  SUBSTRATE       Bashar / khalq stages → "khalqan ākhar" (a new creation)
```

Each layer is detailed below.

---

## 3. The faculties

### 3.1 Substrate & origin — *bashar*, the creation stages
- The human is formed through stages — *nuṭfa → ʿalaqa → muḍgha → ʿiẓām (bones)
  → laḥm (flesh)* — and then **"thumma anshaʾnāhu khalqan ākhar"**, *"then We
  produced him as another creation"* (23:12–14). The qualitative leap to a *new
  kind of being* is the Qur'anic analogue of **emergence**.
- The human is made "in the best of stature" — *aḥsan taqwīm* (95:4) — and
  appointed *khalīfa* (steward/vicegerent) on earth (2:30).
- **Architectural reading:** capability is **developmentally gated** — a being
  earns higher faculties by passing through stages, not all at once.

### 3.2 Vitality — Rūḥ (روح)
- The divine in-breathing: *"and I breathed into him of My Rūḥ"* (15:29; 32:9).
- *"They ask you about the Rūḥ. Say: the Rūḥ is of the command (amr) of my Lord,
  and you have not been given of knowledge except a little"* (17:85).
- **Reading:** the animating, partly-unknowable **vitality/energy principle** —
  what gives the system "life," drive, and fatigue limits. Not fully
  introspectable.

### 3.3 The self — Nafs (نفس)
- The morally-charged self, capable of purification or ruin: *"By the nafs and
  how He proportioned it, and inspired it [with discernment of] its wickedness
  (fujūr) and its righteousness (taqwā); successful is he who **purifies it
  (zakkāhā)**, and failed is he who corrupts it (dassāhā)"* (91:7–10).
- Three Qur'anic states (the maturation axis):
  - **Nafs al-ammāra bi'l-sūʾ** — *the self that commands to evil* (12:53)
  - **Nafs al-lawwāma** — *the self-reproaching self* (75:2)
  - **Nafs al-muṭma'inna** — *the tranquil self at peace* (89:27)
  - *(Sufi tradition extends the ladder: mulhama, rāḍiya, marḍiyya, kāmila —
    this is the source of MIZAN's 7 nafs levels; the first three are Qur'anic,
    the rest are traditional.)*
- The nafs is "taken" in sleep and at death (39:42) → the basis for **offline /
  dream-state consolidation**.
- **Reading:** the agent's evolving **self/ego** — its disposition, drive, and
  trustworthiness — which *develops* through tazkiya (purification) rather than
  being fixed.

### 3.4 The heart-complex — Qalb, Fu'ād, Lubb
The Qur'an locates *cognition and affect together* in a layered "heart."

- **Qalb (قلب)** — root *q-l-b* = **to turn / fluctuate**. The seat of
  understanding and faith: *"hearts with which they understand"* (22:46; cf.
  7:179). It finds rest in remembrance (13:28); it can be **sealed** (2:7),
  **diseased** (2:10), **hardened** (2:74), or **sound — qalb salīm** (26:89).
  → A *dynamic, turning* state, not a static sentiment value.
- **Fu'ād (فؤاد, pl. afʾida)** — the **integrating** inner heart, repeatedly
  paired with hearing and sight as morally accountable: *"the hearing, the sight,
  and the fu'ād — about all of these one will be questioned"* (17:36); *"the
  fu'ād did not lie about what it saw"* (53:11). → **fusion of multiple sources
  into conviction.**
- **Lubb (لب, pl. albāb)** — the **kernel / distilled core** of intellect. The
  *ulu'l-albāb* ("people of the kernel") are the ones who truly reflect and are
  given wisdom: *"He gives wisdom to whom He wills… and none remembers except
  ulu'l-albāb"* (2:269; 3:190). → **metacognition / the quality-monitor of all
  other layers.**

### 3.5 Reasoning as an activity — ʿAql (عقل), Tafakkur, Tadabbur
- **ʿAql never appears as a noun in the Qur'an** — only as a verb: *yaʿqilūn /
  taʿqilūn* ("do you not reason?"). Its root means **to bind / restrain** (as
  one ties a camel). Reason, in the Qur'an, is the *act* of binding impulse to
  evidence and consequence — not a static organ. → ʿAql should be a **process
  MIZAN runs**, not a passive layer.
- **Tafakkur (تفكر)** — reflective analysis: *"they reflect upon the creation of
  the heavens and the earth"* (3:191).
- **Tadabbur (تدبر)** — tracing meanings and consequences: *"Do they not
  contemplate the Qur'an?"* (4:82; 47:24). Also *Naẓar* (consideration),
  *Tafaqquh* (deep comprehension).

### 3.6 Perception — Samʿ, Baṣar, Baṣīra
- **Samʿ (hearing)** and **Baṣar (sight)** are *always paired* and given **after**
  the Rūḥ is breathed in: *"He made for you hearing and sight and afʾida"*
  (32:9; 16:78). Samʿ usually precedes baṣar — a priority of **receiving** over
  surveying.
- **Baṣīra (بصيرة)** — **inner sight / discernment**: *"I call to God upon
  baṣīra (clear insight), I and those who follow me"* (12:108); *"Rather, the
  human, against himself, is a baṣīra"* (75:14) — i.e. insight that also
  **witnesses the self**. → discernment + self-scrutiny.

### 3.7 Memory — Dhikr, Lawḥ Maḥfūẓ
- **Dhikr (ذكر)** — remembrance (of knowledge and of God); **ḥifẓ** —
  preservation.
- **Lawḥ Maḥfūẓ** — *the Preserved Tablet* (85:22) → the **immutable memory
  tier**, the ground truth that cannot be corrupted.

### 3.8 Epistemics — the Mīzān of knowledge
- A **ladder of certainty**: *ʿilm al-yaqīn* (knowledge of certainty) → *ʿayn
  al-yaqīn* (the *eye* of certainty — seeing, 102:7) → *ḥaqq al-yaqīn* (the
  *truth* of certainty — experiencing, 56:95).
- Against certainty stand **ẓann** (conjecture — *"conjecture avails nothing
  against the truth"*, 53:28), **shakk** (doubt), and **wahm** (illusion).
- **Mīzān (ميزان)** — *the Balance*: *"He raised the heaven and set up the
  balance, that you not transgress (taṭghaw) in the balance. So weigh with
  justice and do not skimp the balance"* (55:7–9). → **epistemic humility**:
  never claim certainty beyond the evidence (the sin of *ṭughyān*, over-reach).

### 3.9 Innate priors — Fiṭrah + "the Names"
- **Fiṭrah (فطرة)** — the primordial disposition: *"So set your face toward the
  religion, inclining to truth — the fiṭrah of God upon which He created
  humankind. No change in the creation of God"* (30:30). → **immutable moral /
  epistemic axioms** (truth, justice, no-harm…), the BIOS.
- *"And He taught Adam the names — all of them"* (2:31) → the distinctively human
  capacity for **language, abstraction, conceptualization** (the symbolic /
  root-space layer; cf. MIZAN's Rūḥ model operating in Arabic root-space).

### 3.10 The lower pull — Hawā, Shahwa, Waswās *(must be modeled to be restrained)*
- **Hawā (هوى)** — caprice / base desire: *"Have you seen the one who takes his
  hawā as his god?"* (25:43); and the praise of *"the one who feared… and
  restrained the nafs from hawā"* (79:40).
- **Shahwa (شهوة)** — appetite: *"Beautified for people is the love of desires
  (shahawāt)…"* (3:14).
- **Waswās (وسوسة)** — whispering of the self / Shayṭān: *"We know what his nafs
  whispers to him"* (50:16); *"the whisperer who withdraws… who whispers in the
  chests of people"* (114:4–5). → the **adversarial / temptation signal** the
  agent must *detect and resist*. This is the **safety-and-alignment faculty**:
  shortcut-seeking, reward-hacking, sycophancy, and quiet pressure to violate
  the fiṭrah axioms all map here.

### 3.11 Conscience & metacognition — Lawwāma + self-witnessing Baṣīra
- The **self-reproaching nafs** (75:2) and the **baṣīra against the self**
  (75:14) together form **real-time self-monitoring** — not a post-hoc audit but
  a continuous conscience that fires *during* action.

### 3.12 Volition & moral agency — Niyya, Irāda, Amāna
- **Niyya** (intention) — the root of every act (hadith: *"actions are but by
  intentions"*); the lens through which an action is judged.
- **Irāda / Ikhtiyār** — will and moral choice, exercised *within* the divine
  will (*mashī'a*): *"And you do not will except that God wills"* (76:30).
- **Amāna (أمانة)** — the **trust** that the heavens, earth, and mountains
  declined, *"but the human bore it"* (33:72). → agency comes with
  **accountability**: an action must keep serving its stated intention and the
  telos.

### 3.13 Telos — the objective function
What the whole architecture optimizes for:
- **Khilāfa** (stewardship, 2:30) · **ʿIbāda** (service — *"I created… only that
  they worship Me"*, 51:56) · **Ḥikma** (wisdom — *"whoever is given wisdom is
  given much good"*, 2:269) · **Iḥsān** (excellence — to act *"as though you see
  Him"*) · **ʿAdl / Mīzān** (justice/balance) · **Taqwā** (protective
  God-consciousness). These are **constraints and goals, not add-ons.**

---

## 4. Mapping to MIZAN today

Verified against the codebase (`backend/core/`, `backend/qca/`,
`backend/agents/base.py`).

| Qur'anic faculty | MIZAN module | State |
|---|---|---|
| Rūḥ (vitality) | `core/ruh_engine.py` | ✅ substantive (energy, fatigue, regen) |
| Nafs (7 levels + triad) | `core/nafs_triad.py`, `core/architecture.py` | ✅ substantive |
| Fu'ād (conviction) | `core/fuad.py` | ✅ substantive (Bayesian) |
| Lubb (metacognition) | `core/lubb.py` | ✅ substantive — but runs **post-hoc only** |
| Fiṭrah (axioms) | `core/fitrah.py` | ✅ 13 immutable axioms |
| Dev. stages (23:12–14) | `core/developmental_stages.py` | ✅ gates tools by nafs level |
| Yaqīn / Mīzān (certainty) | `qca/yaqin_engine.py`, `qca/engine.py` | ✅ 5-level certainty ladder |
| Qalb (heart/affect) | `core/qalb.py`, `core/qalb_processor.py` | ⚠️ thin (keyword sentiment); not "turning" |
| Memory (Dhikr/Lawḥ) | `memory/*`, `qca/engine.py` (Lawh) | ✅ but written **after** the task |
| ʿAql (reasoning act) | `qca/cognitive_methods.py`, `reasoning/aql_engine.py` | ⚠️ engines exist but are **selected, not run** |
| Baṣīra (insight) | — | ❌ **missing** |
| Ḥikma (wisdom engine) | tracked as a `list` on the agent | ❌ no distillation engine |
| Hawā / Waswās (lower pull) | — | ❌ **missing** (no impulse/adversarial gate) |
| Samʿ vs Baṣar (split) | `qca/engine.py` (named, not separated) | ⚠️ not distinctly processed |
| Niyya / Amāna (intention) | implicit in the task prompt | ⚠️ no explicit intention object |

### Two structural problems
1. **Faculties don't steer the loop.** Qalb, Nafs, and the cognitive method are
   computed **once** before `_agentic_loop()` and embedded in the system prompt;
   they are not re-consulted per turn (`backend/agents/base.py` `think()` and
   `_agentic_loop()`). Emotional shifts, nafs re-deliberation, and metacognitive
   checks don't happen mid-task. Lubb and the dream engine only run *after* the
   task completes.
2. **Cognitive methods are inert.** `select_method()` returns a method that is
   logged and embedded in the prompt, but the corresponding engine
   (`TafakkurEngine`, `TadabburEngine`, …) is **never `.process()`-ed** to
   actually shape the next decision.

---

## 5. The gaps to close (the AGI build)

The principle: **make the al-insān stack a live control loop, not a one-shot
prompt prefix.** Three new faculties + three integrations:

1. **Baṣīra — `core/basira.py`** (insight & self-witnessing). Synthesizes Lubb
   (metacognition) + Fu'ād (conviction) + Imagination (counterfactual) into a
   single discernment signal: *is this conclusion sound, and what is the real
   situation behind the surface?* Includes self-witnessing (75:14): flags when
   the agent's reasoning is self-serving.
2. **Hawā / Waswās — `core/hawa.py`** (lower-pull & adversarial detector). The
   safety/alignment faculty: detects shortcut-taking, reward-hacking, sycophancy,
   and "whispers" to violate the fiṭrah, then **restrains** (the literal ʿaql).
3. **Ḥikma — `core/hikmah.py`** (wisdom engine). Distils accumulated Shukr
   patterns + Tawbah lessons + Lubb evaluations into **applicable counsel**
   ("for this kind of situation, the wise move is X").
4. **Upgrade `core/qalb.py`** to model the *turning* (q-l-b): track a heart-state
   **trajectory** and re-read emotion mid-conversation.
5. **Run the cognitive methods** (`qca/cognitive_methods.py`) — actually execute
   the selected Tafakkur/Tadabbur/Qiyās pass so it informs the next step.
6. **A per-turn faculty pipeline** in `_agentic_loop()`:
   `Niyya → Hawā/Fiṭrah gate → ʿAql/Tadabbur pass → tool call → Yaqīn tag →
   Lubb+Baṣīra check → (re-deliberate Nafs if confidence drops)`, with each step
   emitting a real `thinking_stream` event. Gated behind a settings flag so the
   default path is unchanged until proven.

**Telos as the objective function.** Every action passes a final **Mīzān check**
against the fiṭrah axioms + the value set (truth, justice, no-harm, excellence).
This already half-exists in Fiṭrah + Furqān; it should be tightened into one gate.

---

## 6. Faithfulness notes (so the model stays honest)

- The Qur'an names **three** nafs states (ammāra, lawwāma, muṭma'inna); MIZAN's
  levels 4–7 (mulhama, rāḍiya, marḍiyya, kāmila) come from **later Sufi
  psychology**, not direct Qur'anic text. This is legitimate as an engineering
  ladder but should not be presented as purely Qur'anic.
- ʿAql, fu'ād, lubb, qalb are **not crisply separated** in classical tafsīr;
  scholars differ. MIZAN's functional split (qalb=affect, fu'ād=conviction,
  lubb=metacognition, ʿaql=binding-reason) is a *defensible engineering reading*,
  not a settled exegetical fact.
- The Rūḥ is explicitly described as **beyond full human knowledge** (17:85);
  modeling it as an energy variable is a deliberate, humble simplification.
- These are **metaphors for engineering**, not theological claims about how the
  human soul "really" computes. The aim is an architecture *inspired by* and
  *faithful to* the Qur'anic vocabulary and its moral priorities.

---

*This document is versioned with the codebase. When a faculty module changes,
update the mapping table (§4) and the gap list (§5) to match.*
