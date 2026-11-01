# Diagrams

Two kinds of diagram describe MIZAN. Both are drawn from the code at commit `5cc11dc` (28 October 2026). Change them when the architecture changes.

## Interactive diagrams (Archify)

Each is one self-contained HTML file. You can click a node to open its source lines on GitHub at the pinned commit, trace a route or the reach of a node, switch between light and dark, and export to PNG or SVG. To view one, download the file and open it in a browser; it needs no network except for the source links.

| File | Type | Shows |
| --- | --- | --- |
| [`runtime.html`](runtime.html) | architecture | The runtime: channels, API gate, `BaseAgent.execute`, Tadbir, Fahm, the tool gate, the sandbox runner, memory, Sakk receipts, Lisan and the answer checks |
| [`chat-turn.html`](chat-turn.html) | sequence | One recognised request (write, run and check a program), from `POST /api/chat/stream` to `chat_complete` |
| [`learning.html`](learning.html) | dataflow | What is learned from verified outcomes (Qasd, Ta'allum, Hifz, Tajriba, Ahl al-Dhikr), where it is kept, what uses it next, and how Mahw erases it |
| [`approval.html`](approval.html) | lifecycle | A tool call that changes something: checked, asked, held for an unattended run, refused, declined or expired |
| [`imtihan.html`](imtihan.html) | workflow | The AGI test: stateless runs, the base and MIZAN arms, scoring by rule, the report, the faculty profile and the human panel |

The typed sources are in [`src/`](src). Every component cites the files and line ranges it stands for (`sources`), and `meta.repository` pins the commit. They are rendered and checked with [Archify](https://github.com/tt-a1i/archify) 3.2.0 (Apache-2.0):

```bash
git clone --depth 1 https://github.com/tt-a1i/archify /path/to/archify
export ARCHIFY_CHROME=/path/to/chrome            # for the browser gate
node /path/to/archify/archify/bin/archify.mjs finalize architecture \
  docs/diagrams/src/runtime.architecture.json docs/diagrams/runtime.html \
  --repo-root . --quality showcase --out-dir /tmp/archify-runtime --json
```

Use the same command for the other files: the diagram type is the second part of the source's file name (`chat-turn.sequence.json` → `sequence`). `finalize` passes only when four gates pass:

- validation of the schema and layout, which with `--repo-root` also checks every cited source against the pinned commit;
- delivery, an atomic write;
- the strict provenance check of the artifact;
- a real-browser check of readability and overflow.

The delivery receipts (`*.delivery.json`) hold local paths and are not committed.

When the code moves, update the cited line ranges and `meta.repository.revision` to a commit that is on GitHub, then finalize again.

## Static figures (diagram-design)

The README embeds SVGs, because GitHub shows images but runs no scripts:

| Figure | Type |
| --- | --- |
| [`overview.svg`](overview.svg) | architecture |
| [`trust-layers.svg`](trust-layers.svg) | layer stack |
| [`learning-loop.svg`](learning-loop.svg) | loop |

Each has a `-dark` variant, chosen with `<picture>` and `prefers-color-scheme`.

They follow the [diagram-design](https://github.com/cathrynlavery/diagram-design) method (MIT):

- at most 9 nodes, with one or two focal elements;
- orthogonal connectors and masked labels;
- a legend strip at the bottom;
- an accessible `<svg>` with a `<title>` and a `<desc>`.

The skin uses MIZAN's own tokens from `frontend/src/index.css`: navy paper, gold accent, Space Grotesk, DM Sans and IBM Plex Mono, falling back to system fonts. Every text colour clears 4.5:1 against its paper.

[`design/build_static.py`](design/build_static.py) writes each figure's HTML in both skins. diagram-design's own tools then check and export it:

```bash
python docs/diagrams/design/build_static.py
DD=/path/to/diagram-design            # git clone https://github.com/cathrynlavery/diagram-design
for f in docs/diagrams/design/*.html; do
  python3 -I $DD/skills/diagram-design/scripts/self_check.py --offline "$f"
  python3 -I $DD/scripts/verify-geometry.py "$f"
done
python3 -I $DD/skills/diagram-design/scripts/export_svg.py \
  docs/diagrams/design/overview.html docs/diagrams/overview.svg --system-fonts
```

`self_check.py` checks the accessible-SVG contract, single-file safety and that the content stays inside the viewBox. `verify-geometry.py` checks the connector rules, for example no diagonal connectors and no label mask covered by a node. A loop's radial spokes are marked `class="spoke"`, the documented exception.

## Older diagrams

[`../architecture-2026-10-25.md`](../architecture-2026-10-25.md) and [`../ruh-runtime-2026-10-25.svg`](../ruh-runtime-2026-10-25.svg) record the 25 October 2026 repair of the owned Ruh runtime. They are kept as dated records, not as the current architecture.
