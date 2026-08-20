# Generates the Twin Home Buyer Inbound Retell AI Call Flow v2.1 flowchart as one large SVG.
import textwrap, pathlib

W = H = 0

def init(w, h):
    global W, H
    W, H = w, h
    out.clear()
    OVERFLOW.clear()
    e(f'<rect x="0" y="0" width="{w}" height="{h}" fill="{SHEET}"/>')
SANS = "Archivo, 'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "'IBM Plex Mono', ui-monospace, 'Courier New', monospace"

INK, DIM, FAINT = "#111823", "#4A5566", "#7E8896"
SHEET, RULE = "#FFFFFF", "#D6DDE6"
KINDS = {
    "action":   ("#1F6FB2", "#17578C", "#FFFFFF"),
    "extract":  ("#63459C", "#4C3479", "#FFFFFF"),
    "decision": ("#1C2530", "#0B1016", "#FFFFFF"),
    "transfer": ("#16785A", "#0F5B45", "#FFFFFF"),
    "notify":   ("#A8730A", "#7C5407", "#FFFFFF"),
    "stop":     ("#A93529", "#7E271D", "#FFFFFF"),
}
END_FILL = "#EEF2F6"
out = []
OVERFLOW = []
def e(s): out.append(s)
def esc(t): return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def wrap(text, box_w, fs, pad=22, mono=False):
    """Greedy wrap to the usable box width. IBM Plex Mono is ~0.60em per glyph,
    Archivo ~0.53em; using one factor for both overflows the mono lines."""
    if not text: return []
    cpl = max(6, int((box_w - 2 * pad) / (fs * (0.60 if mono else 0.53))))
    return textwrap.wrap(text, cpl) or [text]

def _fits(x, y, w, h, blocks, tag):
    rows = sum(len(t) if isinstance(t, list) else 1 for t, *_ in blocks)
    need = sum((len(t) if isinstance(t, list) else 1) * fs * 1.24 for t, _f, fs, *_ in blocks) \
           + 6 * max(0, rows - 1)
    if need > h - 12:
        OVERFLOW.append((tag, f"box {w:.0f}x{h:.0f} needs {need:.0f}px at ({x:.0f},{y:.0f})"))

def lines_block(x_c, y_c, blocks, gap=6):
    """blocks = [(text, font, size, weight, colour)] laid out as centred lines."""
    rows = []
    for text, font, fs, wt, col in blocks:
        for ln in text if isinstance(text, list) else [text]:
            rows.append((ln, font, fs, wt, col))
    total = sum(r[2] * 1.24 for r in rows) + gap * (len(rows) - 1)
    y = y_c - total / 2
    svg = []
    for ln, font, fs, wt, col in rows:
        y += fs * 0.98
        svg.append(f'<text x="{x_c:.0f}" y="{y:.0f}" text-anchor="middle" '
                   f'font-family="{font}" font-size="{fs}" font-weight="{wt}" '
                   f'fill="{col}">{esc(ln)}</text>')
        y += fs * 0.26 + gap
    return "".join(svg)

def node(x, y, w, h, kind, nid=None, title="", vars_=None, pending=None, rx=4):
    fill, stroke, fg = KINDS[kind]
    e(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
      f'stroke="{stroke}" stroke-width="2"/>')
    blocks = []
    if nid:   blocks.append(([nid], MONO, 19, 700, fg))
    if title: blocks.append((wrap(title, w, 20), SANS, 20, 500, fg))
    if vars_:
        vfs = 16
        while vfs > 12 and max((len(t) for t in vars_.split()), default=0) > \
              int((w - 36) / (vfs * 0.60)):
            vfs -= 1
        blocks.append((wrap(vars_, w, vfs, 18, mono=True), MONO, vfs, 400, fg))
    if pending: blocks.append((["PENDING " + pending], MONO, 15, 700, "#FFE9A8"))
    _fits(x, y, w, h, blocks, nid or title[:28])
    e(lines_block(x + w / 2, y + h / 2, blocks))

def diamond(cx, cy, w, h, nid=None, title="", pending=None):
    fill, stroke, fg = KINDS["decision"]
    e(f'<polygon points="{cx},{cy-h/2} {cx+w/2},{cy} {cx},{cy+h/2} {cx-w/2},{cy}" '
      f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
    blocks = []
    if nid:   blocks.append(([nid], MONO, 19, 700, "#8FB4D6"))
    if title: blocks.append((wrap(title, w * 0.72, 20), SANS, 20, 500, fg))
    if pending: blocks.append((["PENDING " + pending], MONO, 15, 700, "#FFD98A"))
    _fits(cx - w / 2, cy - h / 2, w * 0.72, h * 0.62, blocks, nid or "diamond")
    e(lines_block(cx, cy, blocks))

def ending(x, y, w, h, nid, title, colour="#16785A", note=None):
    e(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h/2:.0f}" fill="{END_FILL}" '
      f'stroke="{colour}" stroke-width="3.5"/>')
    blocks = [([nid], MONO, 19, 700, colour), (wrap(title, w, 18, 30), SANS, 18, 500, INK)]
    if note: blocks.append((wrap(note, w, 15, 30, mono=True), MONO, 15, 400, DIM))
    _fits(x, y, w, h, blocks, nid)
    e(lines_block(x + w / 2, y + h / 2, blocks))

def note(x, y, w, h, text, colour="#A93529", fill="#FDF0EE", title=None):
    e(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" fill="{fill}" '
      f'stroke="{colour}" stroke-width="2" stroke-dasharray="9 5"/>')
    blocks = []
    if title: blocks.append(([title], MONO, 16, 700, colour))
    blocks.append((wrap(text, w, 17, 20), SANS, 17, 500, "#5B2A22" if colour == "#A93529" else INK))
    e(lines_block(x + w / 2, y + h / 2, blocks))

# ---- arrows -------------------------------------------------------------
def path_d(pts):
    return "M " + " L ".join(f"{px:.0f},{py:.0f}" for px, py in pts)

def call_arrow(pts, colour="#2A3542", label=None, lx=None, ly=None, anchor="middle", w=3):
    e(f'<path d="{path_d(pts)}" fill="none" stroke="{colour}" stroke-width="{w}" '
      f'stroke-linejoin="round" marker-end="url(#solid-{colour.lstrip("#")})"/>')
    if label:
        mx = lx if lx is not None else (pts[0][0] + pts[-1][0]) / 2
        my = ly if ly is not None else (pts[0][1] + pts[-1][1]) / 2
        e(f'<text x="{mx:.0f}" y="{my:.0f}" text-anchor="{anchor}" font-family="{MONO}" '
          f'font-size="17" font-weight="600" fill="{colour}">{esc(label)}</text>')

def notify_arrow(pts, label=None, lx=None, ly=None, anchor="middle", colour="#A8730A"):
    e(f'<path d="{path_d(pts)}" fill="none" stroke="{colour}" stroke-width="3" '
      f'stroke-dasharray="12 7" stroke-linejoin="round" marker-end="url(#open-{colour.lstrip("#")})"/>')
    if label:
        mx = lx if lx is not None else (pts[0][0] + pts[-1][0]) / 2
        my = ly if ly is not None else (pts[0][1] + pts[-1][1]) / 2
        e(f'<text x="{mx:.0f}" y="{my:.0f}" text-anchor="{anchor}" font-family="{MONO}" '
          f'font-size="17" font-weight="600" fill="{colour}">{esc(label)}</text>')

def band(x, y, w, h, title, sub=None, colour="#A93529", fill="#FCF1EF"):
    e(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" '
      f'stroke="{colour}" stroke-width="3"/>')
    e(f'<text x="{x+30}" y="{y+46}" font-family="{SANS}" font-size="30" font-weight="700" '
      f'fill="{colour}">{esc(title)}</text>')
    if sub:
        e(f'<text x="{x+30}" y="{y+80}" font-family="{MONO}" font-size="19" '
          f'fill="{colour}">{esc(sub)}</text>')

def panel(x, y, w, h, title):
    e(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="#F7F9FB" '
      f'stroke="{RULE}" stroke-width="2"/>')
    e(f'<rect x="{x}" y="{y}" width="{w}" height="4" fill="#1F6FB2"/>')
    e(f'<text x="{x+28}" y="{y+52}" font-family="{SANS}" font-size="26" font-weight="700" '
      f'fill="{INK}">{esc(title)}</text>')

def label(x, y, text, fs=20, col=DIM, font=None, wt=500, anchor="start"):
    e(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{font or SANS}" '
      f'font-size="{fs}" font-weight="{wt}" fill="{col}">{esc(text)}</text>')

def section(x, y, w, text, colour="#1F6FB2"):
    e(f'<rect x="{x}" y="{y}" width="{w}" height="46" rx="3" fill="{colour}"/>')
    e(f'<text x="{x+18}" y="{y+32}" font-family="{SANS}" font-size="24" font-weight="700" '
      f'fill="#FFFFFF" letter-spacing="1.5">{esc(text)}</text>')



def render(path, aria):
    marker_defs = []
    for col in ["2A3542", "16785A", "A93529", "A8730A", "1F6FB2", "63459C"]:
        marker_defs.append(
            f'<marker id="solid-{col}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="#{col}"/></marker>')
        marker_defs.append(
            f'<marker id="open-{col}" viewBox="0 0 11 11" refX="10" refY="5.5" markerWidth="8" '
            f'markerHeight="8" orient="auto-start-reverse">'
            f'<path d="M1,1 L10,5.5 L1,10" fill="none" stroke="#{col}" stroke-width="2"/></marker>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="{aria}"><defs>{"".join(marker_defs)}</defs>' + "".join(out) + '</svg>')
    pathlib.Path(path).write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + svg, encoding="utf-8")
    if OVERFLOW:
        print(f"!! {len(OVERFLOW)} boxes too small for their text:")
        for tag, msg in OVERFLOW: print("   ", tag, "--", msg)
    else:
        print("all text fits its boxes")
    print(f"{path}: {len(svg)//1024} KB, {W} x {H}")
    return svg
