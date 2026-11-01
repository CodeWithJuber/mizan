"""Static figures for the README and the Markdown docs, drawn to the
diagram-design method (github.com/cathrynlavery/diagram-design, MIT): one
self-contained HTML + inline SVG per figure and skin, MIZAN's own tokens
(frontend/src/index.css) as the skin, system fonts so an exported SVG renders
the same inside GitHub's <img>.

    python docs/diagrams/design/build_static.py          # writes the HTML here
    python <skill>/scripts/self_check.py --offline <html>
    python <repo>/scripts/verify-geometry.py <html>
    python <skill>/scripts/export_svg.py <html> docs/diagrams/<name>.svg --system-fonts

Every node, label and arrow below states a fact of the current code; the
interactive diagrams in docs/diagrams/*.html carry the source lines.
"""

from __future__ import annotations

import math
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent

SKINS = {
    "light": {
        "paper": "#f8fafc",
        "paper2": "#eef2f7",
        "ink": "#0f172a",
        "muted": "#475569",
        "soft": "#64748b",
        "rule": "rgba(15,23,42,0.12)",
        "accent": "#8a5a0e",
        "accent_tint": "rgba(212,175,55,0.14)",
        "link": "#1d4ed8",
        "white": "#ffffff",
        "ink_rgb": "15,23,42",
        "dots": "rgba(15,23,42,0.10)",
    },
    "dark": {
        "paper": "#0f172a",
        "paper2": "#1e293b",
        "ink": "#f1f5f9",
        "muted": "#cbd5e1",
        "soft": "#94a3b8",
        "rule": "rgba(241,245,249,0.12)",
        "accent": "#d4af37",
        "accent_tint": "rgba(212,175,55,0.14)",
        "link": "#93c5fd",
        "white": "#1e293b",
        "ink_rgb": "241,245,249",
        "dots": "rgba(241,245,249,0.08)",
    },
}

TITLE_FONT = "'Space Grotesk', system-ui, sans-serif"
SANS = "'DM Sans', system-ui, sans-serif"
MONO = "'IBM Plex Mono', ui-monospace, monospace"


def label_width(text: str, size: float = 8, tracking: float = 0.08) -> int:
    """Mono label plate: 0.62em per character plus tracking, 6px padding a side."""
    width = len(text) * size * (0.62 + tracking) + 12
    return int(math.ceil(width / 4) * 4)


class Figure:
    def __init__(self, slug: str, skin: str, width: int, height: int):
        self.slug = slug
        self.skin = skin
        self.c = SKINS[skin]
        self.width = width
        self.height = height
        self.zones: list[str] = []
        self.arrows: list[str] = []
        self.labels: list[str] = []
        self.nodes: list[str] = []
        self.extra: list[str] = []

    def ink(self, alpha: float) -> str:
        return f"rgba({self.c['ink_rgb']},{alpha})"

    # ── primitives ───────────────────────────────────────────────────────

    def zone(self, x: int, y: int, w: int, h: int, label: str) -> None:
        lw = label_width(label, 7, 0.14)
        self.zones.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{self.ink(0.02)}" '
            f'stroke="{self.ink(0.10)}" stroke-width="0.8"/>'
            f'<rect x="{x + 12}" y="{y + 4}" width="{lw}" height="12" rx="2" fill="{self.c["paper"]}"/>'
            f'<text x="{x + 12 + lw / 2}" y="{y + 13}" fill="{self.c["soft"]}" font-size="7" '
            f'font-family="{MONO}" text-anchor="middle" letter-spacing="0.14em">{escape(label)}</text>'
        )

    def arrow(self, d: str, kind: str = "muted", dashed: bool = False) -> None:
        color = {"muted": self.c["muted"], "accent": self.c["accent"], "link": self.c["link"]}[kind]
        marker = {"muted": "arrow", "accent": "arrow-accent", "link": "arrow-link"}[kind]
        width = "1.4" if kind == "accent" else ("1" if dashed else "1.2")
        dash = ' stroke-dasharray="4,3"' if dashed else ""
        self.arrows.append(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{dash} '
            f'marker-end="url(#{marker})"/>'
        )

    def label(self, cx: float, cy: float, text: str, kind: str = "muted") -> None:
        """A plate centred on (cx, cy); callers keep it 6-10px clear of its stroke."""
        color = {
            "muted": self.c["muted"],
            "accent": self.c["accent"],
            "link": self.c["link"],
            "soft": self.c["soft"],
        }[kind]
        w = label_width(text)
        self.labels.append(
            f'<rect x="{cx - w / 2:g}" y="{cy - 6:g}" width="{w}" height="12" rx="2" fill="{self.c["paper"]}"/>'
            f'<text x="{cx:g}" y="{cy + 3:g}" fill="{color}" font-size="8" font-family="{MONO}" '
            f'text-anchor="middle" letter-spacing="0.08em">{escape(text)}</text>'
        )

    def node(
        self, x: int, y: int, w: int, h: int, kind: str, tag: str, name: str, sub: str
    ) -> None:
        c = self.c
        fill, stroke, dash, tag_color = {
            "focal": (c["accent_tint"], c["accent"], "", c["accent"]),
            "backend": (c["white"], c["ink"], "", c["ink"]),
            "store": (self.ink(0.05), c["muted"], "", c["muted"]),
            "external": (self.ink(0.03), self.ink(0.30), "", c["soft"]),
            "input": (
                "rgba(71,85,105,0.10)" if self.skin == "light" else "rgba(203,213,225,0.10)",
                c["soft"],
                "",
                c["soft"],
            ),
            "security": (
                "rgba(212,175,55,0.05)",
                c["accent"],
                ' stroke-dasharray="4,4"',
                c["accent"],
            ),
        }[kind]
        tw = label_width(tag, 7)
        self.nodes.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{c["paper"]}"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="1"{dash}/>'
            f'<rect x="{x + 8}" y="{y + 8}" width="{tw}" height="12" rx="2" fill="transparent" '
            f'stroke="{stroke}" stroke-opacity="0.5" stroke-width="0.8"/>'
            f'<text x="{x + 8 + tw / 2}" y="{y + 17}" fill="{tag_color}" font-size="7" font-family="{MONO}" '
            f'text-anchor="middle" letter-spacing="0.08em">{escape(tag)}</text>'
            f'<text x="{x + w / 2}" y="{y + h / 2 + 8}" fill="{c["ink"]}" font-size="12" font-weight="600" '
            f'font-family="{SANS}" text-anchor="middle">{escape(name)}</text>'
            f'<text x="{x + w / 2}" y="{y + h / 2 + 22}" fill="{c["muted"]}" font-size="9" '
            f'font-family="{MONO}" text-anchor="middle">{escape(sub)}</text>'
        )

    def legend(self, y: int, entries: list[tuple[str, str]]) -> None:
        """Bottom strip: (swatch kind, text) pairs."""
        c = self.c
        out = [
            f'<line x1="40" y1="{y}" x2="{self.width - 40}" y2="{y}" stroke="{c["rule"]}" stroke-width="0.8"/>',
            f'<text x="40" y="{y + 16}" fill="{c["muted"]}" font-size="8" font-family="{MONO}" '
            f'letter-spacing="0.18em">LEGEND</text>',
        ]
        x = 40
        for kind, text in entries:
            sy = y + 30
            if kind.startswith("arrow"):
                style = kind.split(":")[1]
                color = {"accent": c["accent"], "link": c["link"], "muted": c["muted"]}[
                    style.replace("-dashed", "")
                ]
                marker = {"accent": "arrow-accent", "link": "arrow-link", "muted": "arrow"}[
                    style.replace("-dashed", "")
                ]
                dash = ' stroke-dasharray="4,3"' if style.endswith("dashed") else ""
                out.append(
                    f'<line x1="{x}" y1="{sy + 5}" x2="{x + 28}" y2="{sy + 5}" stroke="{color}" '
                    f'stroke-width="1.2"{dash} marker-end="url(#{marker})"/>'
                )
                tx = x + 36
            else:
                fill, stroke, dash = {
                    "focal": (c["accent_tint"], c["accent"], ""),
                    "backend": (c["white"], c["ink"], ""),
                    "store": (self.ink(0.05), c["muted"], ""),
                    "external": (self.ink(0.03), self.ink(0.30), ""),
                    "security": ("rgba(212,175,55,0.05)", c["accent"], ' stroke-dasharray="3,2"'),
                }[kind]
                out.append(
                    f'<rect x="{x}" y="{sy}" width="14" height="10" rx="2" fill="{fill}" stroke="{stroke}" '
                    f'stroke-width="1"{dash}/>'
                )
                tx = x + 20
            out.append(
                f'<text x="{tx}" y="{sy + 8}" fill="{c["muted"]}" font-size="8.5" font-family="{SANS}">'
                f"{escape(text)}</text>"
            )
            x = tx + int(len(text) * 4.6) + 28
        self.extra.extend(out)

    # ── document ─────────────────────────────────────────────────────────

    def svg(self, title: str, desc: str) -> str:
        c = self.c
        ident = f"{self.slug}{'-dark' if self.skin == 'dark' else ''}"
        markers = "".join(
            f'<marker id="{mid}" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">'
            f'<polygon points="0 0, 8 3, 0 6" fill="{color}"/></marker>'
            for mid, color in (
                ("arrow", c["muted"]),
                ("arrow-accent", c["accent"]),
                ("arrow-link", c["link"]),
                ("arrow-soft", c["soft"]),
            )
        )
        body = "\n".join(self.zones + self.arrows + self.labels + self.nodes + self.extra)
        return (
            f'<svg viewBox="0 0 {self.width} {self.height}" xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-labelledby="{ident}-title {ident}-desc">\n'
            f'<title id="{ident}-title">{escape(title)}</title>\n'
            f'<desc id="{ident}-desc">{escape(desc)}</desc>\n'
            f'<defs><pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
            f'<circle cx="1" cy="1" r="0.9" fill="{c["dots"]}"/></pattern>{markers}</defs>\n'
            f'<rect width="100%" height="100%" fill="{c["paper"]}"/>\n'
            f'<rect width="100%" height="100%" fill="url(#dots)" opacity="0.55"/>\n'
            f"{body}\n</svg>"
        )

    def html(self, eyebrow: str, title: str, desc: str) -> str:
        c = self.c
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(title)}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: {SANS}; background: {c["paper"]}; color: {c["ink"]}; min-height: 100vh;
      display: flex; align-items: center; justify-content: center; padding: 3rem 2rem; }}
    .frame {{ max-width: 1200px; width: 100%; }}
    .eyebrow {{ font-family: {MONO}; font-size: 0.66rem; font-weight: 500; letter-spacing: 0.18em;
      text-transform: uppercase; color: {c["muted"]}; margin-bottom: 0.5rem; }}
    h1 {{ font-family: {TITLE_FONT}; font-size: clamp(1.5rem, 2.4vw + 0.75rem, 2rem); font-weight: 500;
      letter-spacing: -0.02em; line-height: 1.15; color: {c["ink"]}; margin-bottom: 1.5rem; }}
    .diagram-container {{ width: 100%; overflow-x: auto; }}
    svg {{ width: 100%; min-width: {self.width}px; display: block; }}
  </style>
</head>
<body>
  <div class="frame">
    <p class="eyebrow">{escape(eyebrow)}</p>
    <h1>{escape(title)}</h1>
    <div class="diagram-container">
{self.svg(title, desc)}
    </div>
  </div>
</body>
</html>
"""


# ── 1. Overview: MIZAN directs, the model speaks (Architecture) ──────────


def overview(skin: str) -> Figure:
    f = Figure("overview", skin, 1000, 500)
    f.zone(196, 48, 612, 368, "MIZAN BACKEND")
    # Arrows first: main row at y=232, Person <-> Channels on two offset lines.
    f.arrow("M 160,224 H 216", "link")
    f.arrow("M 216,240 H 160", dashed=True)
    f.arrow("M 360,232 H 424")
    f.arrow("M 584,232 H 648", "accent")
    f.arrow("M 792,232 H 856")
    f.arrow("M 480,200 V 136")
    f.arrow("M 560,200 V 112 Q 560,104 568,104 H 856")
    f.arrow("M 720,264 V 328")
    f.arrow("M 504,264 V 328")
    f.arrow("M 424,360 H 296 Q 288,360 288,352 V 264")
    f.label(188, 210, "HTTPS", "link")
    f.label(188, 254, "REPLY")
    f.label(392, 218, "REQUEST")
    f.label(616, 218, "TOOLS", "accent")
    f.label(824, 218, "RUN")
    f.label(436, 168, "UNDERSTAND")
    f.label(712, 90, "WORDS, CODE ONLY")
    f.label(756, 296, "RECALL")
    f.label(468, 296, "ANSWER")
    f.label(360, 346, "SSE STREAM")
    f.node(40, 200, 120, 64, "external", "EXT", "Person", "owner, linked")
    f.node(216, 200, 144, 64, "security", "GATE", "Channels", "web, Telegram, mail")
    f.node(424, 72, 112, 64, "backend", "FAHM", "Fahm", "intent by MAP")
    f.node(424, 200, 160, 64, "focal", "DIRECTS", "Tadbir", "plan, act, verify")
    f.node(648, 200, 144, 64, "security", "GATE", "Tool gate", "Izn, approvals, Sakk")
    f.node(856, 72, 112, 64, "external", "LISAN", "Language model", "Wazn, Iqtisad")
    f.node(856, 200, 112, 64, "external", "RUN", "Sandbox", "isolated runner")
    f.node(424, 328, 160, 64, "security", "CHECK", "Answer checks", "Sidq, Isnad, Ahl")
    f.node(648, 328, 144, 64, "store", "DB", "Memory", "Dhikr, Daftar")
    f.legend(
        436,
        [
            ("focal", "MIZAN decides"),
            ("backend", "MIZAN faculty"),
            ("security", "Gate / check"),
            ("store", "Store"),
            ("external", "Outside MIZAN"),
            ("arrow:accent", "Every action"),
            ("arrow:link", "HTTP"),
            ("arrow:muted-dashed", "Return"),
        ],
    )
    return f


# ── 2. Trust layers a request passes (Layer stack) ───────────────────────


LAYERS = [
    ("L1", "Amanah", "outside text is data: scan, fence, taint", False),
    ("L2", "Fahm", "intent and language by evidence, no word lists", False),
    ("L3", "Tool gate", "Izn, approvals, Hudud; a Sakk receipt either way", True),
    ("L4", "Tathabbut, Furqan", "a second program agrees; wording held to facts", False),
    ("L5", "Sidq, Isnad", "arithmetic, quotes, links fixed; each claim graded", False),
    ("L6", "Ahl al-Dhikr", "sources asked (16:43); reported under the answer", False),
]


def layers(skin: str) -> Figure:
    f = Figure("trust-layers", skin, 1000, 540)
    c = f.c
    top, h = 64, 64
    out = [
        f'<text x="40" y="{top - 12}" fill="{c["muted"]}" font-size="8" font-family="{MONO}" '
        f'letter-spacing="0.18em">REQUEST</text>',
        f'<line x1="80" y1="{top}" x2="80" y2="{top + h * len(LAYERS) - 8}" stroke="{f.ink(0.30)}" stroke-width="1"/>',
        f'<polygon points="76,{top + h * len(LAYERS) - 8} 84,{top + h * len(LAYERS) - 8} 80,{top + h * len(LAYERS)}" '
        f'fill="{c["muted"]}"/>',
        f'<text x="40" y="{top + h * len(LAYERS) + 20}" fill="{c["muted"]}" font-size="8" font-family="{MONO}" '
        f'letter-spacing="0.18em">ANSWER</text>',
        f'<line x1="120" y1="{top}" x2="960" y2="{top}" stroke="{c["rule"]}" stroke-width="1"/>',
    ]
    for index, (tag, name, note, focal) in enumerate(LAYERS):
        y = top + index * h
        fill = c["accent_tint"] if focal else (c["white"] if index % 2 == 0 else c["paper2"])
        out.append(f'<rect x="120" y="{y}" width="840" height="{h}" fill="{fill}"/>')
        if focal:
            out.append(
                f'<rect x="120" y="{y}" width="840" height="{h}" fill="none" stroke="{c["accent"]}" stroke-width="1"/>'
            )
        else:
            out.append(
                f'<line x1="120" y1="{y + h}" x2="960" y2="{y + h}" stroke="{c["rule"]}" stroke-width="1"/>'
            )
        tone = c["accent"] if focal else c["muted"]
        weight = ' font-weight="600"' if focal else ""
        out.append(
            f'<text x="140" y="{y + 36}" fill="{tone}" font-size="8" font-family="{MONO}" letter-spacing="0.14em"'
            f"{weight}>{tag}</text>"
            f'<text x="200" y="{y + 38}" fill="{c["ink"]}" font-size="16" font-weight="600" font-family="{SANS}">'
            f"{escape(name)}</text>"
            f'<text x="940" y="{y + 38}" fill="{tone}" font-size="10" font-family="{MONO}" text-anchor="end" '
            f'letter-spacing="0.04em">{escape(note)}</text>'
        )
    bottom = top + h * len(LAYERS)
    out.append(
        f'<text x="120" y="{bottom + 48}" fill="{c["muted"]}" font-size="8" font-family="{MONO}" '
        f'letter-spacing="0.18em">FOCAL LAYER</text>'
        f'<text x="220" y="{bottom + 48}" fill="{c["muted"]}" font-size="9" font-family="{SANS}" font-style="italic">'
        "The model never holds a tool: every action passes one gate, and every outcome leaves a receipt.</text>"
    )
    f.extra.extend(out)
    return f


# ── 3. Learning loop (Loop) ──────────────────────────────────────────────


STATIONS = [
    ("Understand", "Fahm + user overlay", None, False),
    ("Act", "recipe runs tools", None, False),
    ("Verify", "Tathabbut, Sidq", None, True),
    ("Keep", "Hifz, Qasd, Tajriba", "VERIFIED ONLY", False),
    ("Reuse", "no model call", "RECORD", False),
    ("Re-check", "Muhasaba, daily", None, False),
]


def _box_hits(
    cx: float, cy: float, r: float, bx: float, by: float, w: float, h: float
) -> list[tuple[float, float]]:
    points = []
    for xe in (bx, bx + w):
        d = r * r - (xe - cx) ** 2
        if d >= 0:
            for s in (-1, 1):
                y = cy + s * math.sqrt(d)
                if by <= y <= by + h:
                    points.append((xe, y))
    for ye in (by, by + h):
        d = r * r - (ye - cy) ** 2
        if d >= 0:
            for s in (-1, 1):
                x = cx + s * math.sqrt(d)
                if bx <= x <= bx + w:
                    points.append((x, ye))
    return points


def loop(skin: str) -> Figure:
    width, height = 1040, 760
    cx, cy, r = 520, 360, 240
    sw, sh, hw, hh = 160, 64, 200, 104
    f = Figure("learning-loop", skin, width, height)
    c = f.c
    n = len(STATIONS)
    boxes = []
    for k in range(n):
        theta = math.radians(-90 + k * 360 / n)
        px, py = cx + r * math.cos(theta), cy + r * math.sin(theta)
        bx, by = round((px - sw / 2) / 4) * 4, round((py - sh / 2) / 4) * 4
        boxes.append((theta, px, py, bx, by))

    def polar(point: tuple[float, float]) -> float:
        return math.atan2(point[1] - cy, point[0] - cx)

    def norm(a: float) -> float:
        return a % (2 * math.pi)

    for k in range(n):
        j = (k + 1) % n
        theta_k, _, _, bx, by = boxes[k]
        theta_j, _, _, jx, jy = boxes[j]
        exits = [
            p for p in _box_hits(cx, cy, r, bx, by, sw, sh) if norm(polar(p) - theta_k) < math.pi
        ]
        entries = [
            p for p in _box_hits(cx, cy, r, jx, jy, sw, sh) if norm(theta_j - polar(p)) < math.pi
        ]
        start = min(exits, key=lambda p: norm(polar(p) - theta_k))
        entry = min(entries, key=lambda p: norm(theta_j - polar(p)))
        phi = polar(entry) - 1.2 / r
        end = (cx + r * math.cos(phi), cy + r * math.sin(phi))
        f.arrows.append(
            f'<path d="M {start[0]:.3f},{start[1]:.3f} A {r} {r} 0 0 1 {end[0]:.3f},{end[1]:.3f}" '
            f'fill="none" stroke="{c["muted"]}" stroke-width="1.2" marker-end="url(#arrow)"/>'
        )

    def box_distance(ux: float, uy: float, a: float, b: float) -> float:
        terms = [a / abs(ux)] if abs(ux) > 1e-9 else []
        terms += [b / abs(uy)] if abs(uy) > 1e-9 else []
        return min(terms)

    for k, (name, sub, spoke, focal) in enumerate(STATIONS):
        theta, px, py, bx, by = boxes[k]
        if spoke:
            ux, uy = math.cos(theta), math.sin(theta)
            start = (
                px - box_distance(ux, uy, sw / 2, sh / 2) * ux,
                py - box_distance(ux, uy, sw / 2, sh / 2) * uy,
            )
            reach = box_distance(ux, uy, hw / 2, hh / 2) + 6
            end = (cx + reach * ux, cy + reach * uy)
            f.arrows.append(
                f'<path class="spoke" d="M {start[0]:.3f},{start[1]:.3f} L {end[0]:.3f},{end[1]:.3f}" fill="none" '
                f'stroke="{c["soft"]}" stroke-width="1" stroke-dasharray="5,4" marker-end="url(#arrow-soft)"/>'
            )
            mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
            w = label_width(spoke)
            # Beside the spoke, on the side away from the ring's centre line.
            lx = mx + (w / 2 + 10) * (1 if ux > 0 else -1)
            f.label(lx, my - 10, spoke, "soft")
        fill, stroke = (c["accent_tint"], c["accent"]) if focal else (c["paper"], c["ink"])
        name_color = c["accent"] if focal else c["ink"]
        f.nodes.append(
            f'<rect x="{bx}" y="{by}" width="{sw}" height="{sh}" rx="6" fill="{c["paper"]}"/>'
            f'<rect x="{bx}" y="{by}" width="{sw}" height="{sh}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1"/>'
            f'<text x="{bx + sw / 2}" y="{by + 28}" fill="{name_color}" font-size="12" font-weight="600" '
            f'font-family="{SANS}" text-anchor="middle">{escape(name)}</text>'
            f'<text x="{bx + sw / 2}" y="{by + 44}" fill="{c["muted"]}" font-size="9" font-family="{MONO}" '
            f'text-anchor="middle">{escape(sub)}</text>'
        )
    f.nodes.append(
        f'<rect x="{cx - hw / 2:g}" y="{cy - hh / 2:g}" width="{hw}" height="{hh}" rx="8" fill="{c["ink"]}"/>'
        f'<text x="{cx}" y="{cy - 4}" fill="{c["paper"]}" font-size="13" font-weight="600" font-family="{SANS}" '
        f'text-anchor="middle">Learned state</text>'
        f'<text x="{cx}" y="{cy + 14}" fill="{c["paper"]}" font-size="9" font-family="{MONO}" '
        f'text-anchor="middle" opacity="0.8">per user, no weights</text>'
    )
    f.extra.append(
        f'<text x="40" y="{height - 28}" fill="{c["muted"]}" font-size="8" font-family="{MONO}" '
        f'letter-spacing="0.18em">FOCAL STATION</text>'
        f'<text x="160" y="{height - 28}" fill="{c["muted"]}" font-size="9" font-family="{SANS}" '
        f'font-style="italic">Only what was verified is kept; a stateless chat or a test writes nothing, '
        "and Mahw erases what a chat taught.</text>"
    )
    return f


FIGURES = {
    "overview": (
        overview,
        "Architecture · MIZAN",
        "MIZAN directs, the language model speaks",
        "Architecture: a request reaches Tadbir, which understands it with Fahm, runs every tool through "
        "one gate into the sandbox or memory, asks the language model only for words or code, and sends "
        "unverified answers through Sidq, Isnad and Ahl al-Dhikr before they stream back.",
    ),
    "trust-layers": (
        layers,
        "Layer stack · MIZAN",
        "What a request passes before an answer is shown",
        "Layer stack of six checks from Amanah at the top to Ahl al-Dhikr at the bottom, with the tool "
        "gate highlighted as the focal layer.",
    ),
    "learning-loop": (
        loop,
        "Loop · MIZAN",
        "How MIZAN learns: verified outcomes only",
        "Loop of six stations, understand, act, verify, keep, reuse and re-check, around a hub of "
        "per-user learned state; keep and reuse write back to it.",
    ),
}


def main() -> None:
    for slug, (build, eyebrow, title, desc) in FIGURES.items():
        for skin in ("light", "dark"):
            figure = build(skin)
            name = slug if skin == "light" else f"{slug}-dark"
            (HERE / f"{name}.html").write_text(figure.html(eyebrow, title, desc), encoding="utf-8")
            print(f"wrote {name}.html")


if __name__ == "__main__":
    main()
