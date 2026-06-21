# 03 — Semantics, Polysemy, and the Classical *Wujūh* Sciences

This is where the project meets a thousand-year-old Islamic science head-on: **wujūh
wa-naẓāʾir** — the study of a single Quranic word carrying several distinct "faces" (senses)
across its occurrences. We first build distributional meaning vectors, then test how far an
automatic method can recover the classical sense-analysis, and finally show context resolving a
genuine hard case.

---

## 3.1 Root embeddings

**Method.** Build a root × root co-occurrence matrix from verse co-membership, weight by PPMI
(positive pointwise mutual information), reduce by SVD (k = 100 for roots; k = 50 in later
experiments). Each root becomes a dense meaning vector. See `embeddings_map.png`,
`top_roots.png`, `root_network.png`.

**Result, with an honest negative** `[Established]`. The embeddings recover real semantic
neighbourhoods — but **نور (light) and نار (fire) collapse together** when working at the root
level, because they share consonantal material and co-occurrence company. Moving to **lemma**
embeddings (citation forms, `lemma_embeddings_map.png`) **separates نُور from نار** correctly.

`[Inference]` Lesson: the level of representation (root vs lemma) changes what the geometry can
resolve. Root level is good for broad fields; lemma level is needed for fine sense contrasts.

![Embeddings map](embeddings_map.png)

---

## 3.2 A worked semantic family: praise

To ground the method in lexicography, the cluster of "praise" words was examined: **madḥ,
shukr, ḥamd, thanāʾ**. Their distinctions are exactly those drawn classically by
**al-Rāghib al-Iṣfahānī** in *al-Mufradāt fī Gharīb al-Qurʾān* (d. 502 AH). See
`praise_family.png`, `egonet_Hmd.png`. `[Established]` (the lexical distinctions are
transmission, not a model output — the model is shown to be *consistent* with them).

---

## 3.3 The *wujūh wa-naẓāʾir* science (provenance)

All claims here are sourced to the classical tradition, verified during the work:

- The science is old: the earliest dedicated treatment is ascribed to **Muqātil ibn Sulaymān**
  (d. 150 AH). It is codified later in **al-Zarkashī's** *al-Burhān fī ʿUlūm al-Qurʾān* and
  **al-Suyūṭī's** *al-Itqān*.
- The companion science of fine synonym-distinctions, *al-Furūq al-Lughawiyya*, is associated
  with **Abū Hilāl al-ʿAskarī**.
- The interpretive principle used to resolve the hard case below — **tafsīr al-Qurʾān
  bi'l-Qurʾān** (explaining the Quran by the Quran) — is given its first explicit
  methodological statement by **Ibn Taymiyya** in *Muqaddima fī Uṣūl al-Tafsīr* (d. 728 AH).

`[Established]` These are historical/bibliographic facts, verified, not model outputs.

---

## 3.4 Polysemy by clustering — *dīn* and *ummah*

**Question.** Can an unsupervised method rediscover the classical "faces" of a polysemous word?

**Method.** For a target word, take all its occurrences, embed each by its local context, and
cluster (KMeans). See `wujuh_deen.png`, `wujuh_ummah.png`.

**Results** `[Established]`:

- **dīn** (92 occurrences) clusters into interpretable faces: **RECOMPENSE / OBEDIENCE /
  RELIGION**, plus a small "huzuwan" (mockery-context) group. This matches the classical
  multi-face analysis of *dīn* well.
- **ummah** clusters into four groups, but the split is driven more by the **immediate
  neighbour word** than by the classical wujūh of *ummah* (community / period of time / leader
  / way) — i.e. raw clustering picks up surface collocation, not always the intended sense.

`[Inference]` Clustering is a decent first pass but conflates "what word sits next to it" with
"which sense it is." That motivated a more targeted tool.

![Wujuh of deen](wujuh_deen.png)

---

## 3.5 The wajh-detector (rule-based, governing-neighbour → classical face)

**Method.** Instead of blind clustering, a rule maps each occurrence to a classical face using
its **governing neighbour** (the word that grammatically governs it). Validated against the
famous, scholar-agreed occurrences.

**Results** `[Established]` (rule-based, hand-validated):

| Word | Coverage (occurrences confidently tagged) | Accuracy on famous occurrences |
|---|---|---|
| **dīn** | 77% tagged | 25/26 = **96%** |
| **ummah** | 12% tagged | 12/12 = **100%** |

`[Inference]` The detector deliberately abstains when the governing cue is weak (hence modest
coverage), buying very high precision where it does fire. It beat blind clustering on specific
known cases (e.g. 95:7 and 107:1 for *dīn*). Outputs: `wajh_detector.png`,
`wajh_deen_tagged.csv`, `wajh_ummah_tagged.csv`.

![Wajh detector](wajh_detector.png)

---

## 3.6 Resolving a hard case: *dīn* in 98:5 via *tafsīr al-Qurʾān bi'l-Qurʾān*

**The problem.** One occurrence (98:5, "mukhliṣīna lahu **al-dīn**") resisted the detector's
neighbour rule — a genuine apparent miss.

**The resolution** `[Established]`. Using the classical principle of explaining the Quran by the
Quran, the **naẓāʾir family** — the set of verses sharing the phrase "mukhliṣan / mukhliṣīna
lahu al-dīn" (11 members) — fixes the face: here *dīn* = **sincere, obedient worship (ikhlāṣ
al-dīn)**, i.e. the OBEDIENCE face, not "religion-as-system" and not "recompense". The method
that resolves it is exactly Ibn Taymiyya's, applied mechanically. Output: `nazair_deen.png`,
`nazair_deen.json`.

`[Inference]` This is the project's cleanest demonstration that **context genuinely
disambiguates** a specific polysemous word — a point that matters when, in Phase 2, an
*aggregate* context signal turns out not to help (the two are not in conflict; see
`06_compositional_meaning.md`).

![Nazair of deen](nazair_deen.png)
