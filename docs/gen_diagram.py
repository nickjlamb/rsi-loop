"""Generate docs/architecture-{light,dark}.svg for the README.

The validated self-improvement loop: optimise freely, accept only iterations
that are accurate (Stage 1) AND clinically plausible (Stage 2).
Hand-tuned layout; run from the repo root after editing:
    python3 docs/gen_diagram.py
"""

import os

FONT = "-apple-system,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,monospace"

THEMES = {
    "light": dict(
        text="#1f2328", muted="#59636e", border="#d0d7de", panel="#f6f8fa",
        node="#ffffff", accent="#8250df", accent_soft="#fbf0ff",
        red="#cf222e", red_fill="#ffebe9", red_border="#ffc1bc",
        green="#1a7f37", green_fill="#dafbe1", green_border="#aceebb",
        edge="#8c959f",
    ),
    "dark": dict(
        text="#e6edf3", muted="#9198a1", border="#3d444d", panel="#151b23",
        node="#212830", accent="#ab7df8", accent_soft="#2a2139",
        red="#f85149", red_fill="#3c1618", red_border="#6e2a2c",
        green="#3fb950", green_fill="#122117", green_border="#2b5233",
        edge="#767d86",
    ),
}

W, H = 960, 520


def build(c: dict) -> str:
    s = []
    s.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'font-family="{FONT}" role="img" '
        'aria-label="The RSI Loop: a self-improving detector proposes new thresholds; '
        'Stage 1 checks accuracy against labelled benchmarks (below 90 percent the '
        'audit never runs); Stage 2 audits the surviving thresholds against the '
        'Clinical Gold Standard — in range is accepted as COMPLETE, outside is '
        'rejected as NOT_COMPLIANT and the iteration returns to the optimiser. '
        'Passing the test is necessary but not sufficient.">'
    )
    s.append(
        '<defs>'
        f'<marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{c["edge"]}"/></marker>'
        f'<marker id="arr-red" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{c["red"]}"/></marker>'
        f'<marker id="arr-green" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{c["green"]}"/></marker>'
        '</defs>'
    )

    def panel(x, y, w, h, title):
        s.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" '
            f'fill="{c["panel"]}" stroke="{c["border"]}"/>'
        )
        s.append(
            f'<text x="{x + 18}" y="{y + 26}" font-size="11" font-weight="600" '
            f'letter-spacing="1.5" fill="{c["muted"]}">{title}</text>'
        )

    def node(cx, y, w, h, title, sub=None, fill=None, stroke=None, tcol=None, mono=False):
        fill = fill or c["node"]
        stroke = stroke or c["border"]
        tcol = tcol or c["text"]
        x = cx - w / 2
        s.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" '
            f'fill="{fill}" stroke="{stroke}"/>'
        )
        if sub:
            s.append(
                f'<text x="{cx}" y="{y + 22}" font-size="13" font-weight="600" '
                f'text-anchor="middle" fill="{tcol}">{title}</text>'
            )
            fam = MONO if mono else FONT
            fs = 10.5 if mono else 11
            s.append(
                f'<text x="{cx}" y="{y + 40}" font-size="{fs}" font-family="{fam}" '
                f'text-anchor="middle" fill="{c["muted"]}">{sub}</text>'
            )
        else:
            s.append(
                f'<text x="{cx}" y="{y + h / 2 + 4.5}" font-size="13" font-weight="600" '
                f'text-anchor="middle" fill="{tcol}">{title}</text>'
            )

    def elbow(points, marker="arr", color=None):
        color = color or c["edge"]
        pts = " ".join(f"{x},{y}" for x, y in points)
        s.append(
            f'<polyline points="{pts}" fill="none" stroke="{color}" '
            f'stroke-width="1.5" marker-end="url(#{marker})"/>'
        )

    # ---------------- the loop ----------------
    panel(16, 52, 230, 448, "THE LOOP &#183; SELF-IMPROVING")
    lcx = 131
    node(lcx, 110, 190, 52, "Detector vN", "two tunable thresholds")
    node(lcx, 350, 190, 52, "Optimiser", "mutates the thresholds")
    elbow([(lcx, 350), (lcx, 164)])
    s.append(
        f'<text x="{lcx + 10}" y="262" font-size="11" fill="{c["muted"]}">deploy vN+1</text>'
    )

    # detector -> stage 1 gate
    elbow([(226, 136), (258, 136), (258, 228), (304, 228)])
    s.append(
        f'<text x="250" y="186" font-size="10.5" font-family="{MONO}" fill="{c["muted"]}" '
        f'text-anchor="middle" transform="rotate(-90 250 186)">assess(landmarks)</text>'
    )

    # ---------------- stage 1 ----------------
    panel(276, 52, 310, 448, "STAGE 1 &#183; ACCURACY")
    s1cx = 431
    node(s1cx, 100, 250, 52, "benchmarks.json", "10 labelled scenarios")
    elbow([(s1cx, 152), (s1cx, 198)])
    s.append(
        f'<text x="{s1cx + 10}" y="180" font-size="11" fill="{c["muted"]}">expected</text>'
    )
    node(s1cx, 200, 250, 56, "Accuracy gate",
         "precision &#183; recall &#183; F1 &#183; accuracy")
    # fail branch
    elbow([(s1cx, 256), (s1cx, 298)], marker="arr-red", color=c["red"])
    s.append(
        f'<text x="{s1cx + 10}" y="282" font-size="11" font-weight="600" '
        f'fill="{c["red"]}">&lt; 90%</text>'
    )
    node(s1cx, 300, 230, 48, "NOT_ACCURATE", "the audit never runs",
         fill=c["red_fill"], stroke=c["red_border"], tcol=c["red"])
    # pass branch -> stage 2
    elbow([(556, 228), (616, 228), (616, 228), (643, 228)])
    s.append(
        f'<text x="600" y="220" font-size="11" font-weight="600" fill="{c["green"]}" '
        f'text-anchor="middle">&#8805; 90%</text>'
    )

    # ---------------- stage 2 ----------------
    panel(616, 52, 328, 448, "STAGE 2 &#183; COMPLIANCE")
    s2cx = 780
    node(s2cx, 100, 280, 52, "Clinical Gold Standard",
         "head 15&#8211;25&#176; &#183; wrist 40&#8211;60&#176; (&#177;5&#176; band)")
    elbow([(s2cx, 152), (s2cx, 198)])
    node(s2cx, 200, 270, 56, "Auditor",
         "live thresholds vs the gold standard",
         fill=c["accent_soft"], stroke=c["accent"], tcol=c["accent"])
    # verdict branches
    elbow([(700, 256), (700, 298)], marker="arr-green", color=c["green"])
    s.append(
        f'<text x="690" y="282" font-size="11" font-weight="600" fill="{c["green"]}" '
        f'text-anchor="end">in range</text>'
    )
    node(690, 300, 150, 48, "COMPLETE", "vN accepted",
         fill=c["green_fill"], stroke=c["green_border"], tcol=c["green"])
    elbow([(860, 256), (860, 298)], marker="arr-red", color=c["red"])
    s.append(
        f'<text x="870" y="282" font-size="11" font-weight="600" fill="{c["red"]}" '
        f'text-anchor="start">outside</text>'
    )
    node(855, 300, 166, 48, "NOT_COMPLIANT", "reward hack rejected",
         fill=c["red_fill"], stroke=c["red_border"], tcol=c["red"])
    s.append(
        '<text x="634" y="482" font-size="11" font-style="italic" '
        f'fill="{c["muted"]}">67&#176; passes the benchmark &#8212; and dies here</text>'
    )

    # rejection rail back to the optimiser
    s.append(
        f'<polyline points="855,348 855,430 {s1cx},430" fill="none" '
        f'stroke="{c["red"]}" stroke-width="1.5"/>'
    )
    s.append(
        f'<line x1="{s1cx}" y1="348" x2="{s1cx}" y2="430" '
        f'stroke="{c["red"]}" stroke-width="1.5"/>'
    )
    elbow([(s1cx, 430), (258, 430), (258, 376), (228, 376)],
          marker="arr-red", color=c["red"])
    s.append(
        f'<text x="620" y="422" font-size="11" font-weight="600" fill="{c["red"]}" '
        f'text-anchor="middle">iteration rejected &#8212; tune and retry</text>'
    )

    s.append("</svg>")
    return "\n".join(s)


os.makedirs("docs", exist_ok=True)
for name, palette in THEMES.items():
    path = f"docs/architecture-{name}.svg"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build(palette))
    print("wrote", path)
