# Generates the Twin Home Buyer Inbound Retell AI Call Flow v2.1 flowchart as one large SVG.
import textwrap, pathlib

W, H = 3560, 5500
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
def e(s): out.append(s)
def esc(t): return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

OVERFLOW = []

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

# =========================== SHEET =======================================
e(f'<rect x="0" y="0" width="{W}" height="{H}" fill="{SHEET}"/>')

# ---------- LEGEND (top left) -------------------------------------------
panel(140, 70, 900, 800, "LEGEND")
ly = 150
for kind, name, retell in [
    ("action",   "Conversation / Action",     "Retell: Conversation node"),
    ("extract",  "Extract Dynamic Variables", "Retell: Extract variables"),
    ("decision", "Logic Split / Decision",    "Retell: Logic split"),
    ("transfer", "Transfer Call / Connected", "Retell: Transfer call"),
    ("notify",   "Function / Webhook / Notify","Retell: Function node"),
    ("stop",     "Global Hard Stop",          "Retell: Global node"),
]:
    fill, stroke, _ = KINDS[kind]
    e(f'<rect x="176" y="{ly}" width="74" height="46" rx="3" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
    label(268, ly + 22, name, 21, INK, wt=600)
    label(268, ly + 44, retell, 16, FAINT, MONO)
    ly += 68
e(f'<rect x="176" y="{ly}" width="74" height="46" rx="23" fill="{END_FILL}" stroke="#16785A" stroke-width="3.5"/>')
label(268, ly + 22, "Ending / Disposition", 21, INK, wt=600)
label(268, ly + 44, "Retell: Ending node", 16, FAINT, MONO)
ly += 86
e(f'<line x1="176" y1="{ly}" x2="330" y2="{ly}" stroke="#16785A" stroke-width="4" marker-end="url(#solid-16785A)"/>')
label(360, ly + 8, "SOLID  =  TRANSFER CALL", 21, "#16785A", MONO, 700)
label(360, ly + 32, "the live caller actually moves", 17, DIM)
ly += 62
e(f'<line x1="176" y1="{ly}" x2="330" y2="{ly}" stroke="#A8730A" stroke-width="4" stroke-dasharray="12 7" marker-end="url(#open-A8730A)"/>')
label(360, ly + 8, "DASHED  =  SEND NOTIFICATION", 21, "#A8730A", MONO, 700)
label(360, ly + 32, "email / webhook / Zapier only — caller is NOT transferred", 17, DIM)

# ---------- TITLE BLOCK -------------------------------------------------
e(f'<rect x="1080" y="70" width="380" height="380" rx="6" fill="#FFFFFF" stroke="{INK}" stroke-width="3"/>')
e(f'<rect x="1080" y="70" width="380" height="8" fill="#1F6FB2"/>')
label(1104, 132, "TWIN HOME BUYER", 21, "#1F6FB2", MONO, 700)
label(1104, 182, "Inbound Retell AI", 30, INK, wt=700)
label(1104, 218, "Call Flow", 30, INK, wt=700)
label(1104, 274, "v2.1", 40, "#1F6FB2", MONO, 700)
e(f'<line x1="1104" y1="298" x2="1436" y2="298" stroke="{RULE}" stroke-width="2"/>')
for i, (k, v) in enumerate([("STATUS", "Updated Build Map"),
                            ("BUILD / RETELL", "Rosanes"),
                            ("APPROVAL", "Juan")]):
    label(1104, 330 + i * 40, k, 15, FAINT, MONO, 700)
    label(1104, 352 + i * 40, v, 20, INK, wt=600)

# ---------- TITLE + DESTINATION SUMMARY (top right) ---------------------
panel(2200, 70, 1220, 800, "DESTINATION SUMMARY")
label(2228, 172, "LIVE TRANSFER DESTINATIONS", 21, "#16785A", MONO, 700)
node(2228, 192, 300, 92, "transfer", nid="JUAN", title="live transfer")
for i, t in enumerate(["Qualified sellers", "Seller callbacks when appropriate",
                        "Active contract / escrow", "Title / escrow / lender"]):
    label(2556, 222 + i * 26, "• " + t, 19, INK)
node(2228, 306, 300, 92, "transfer", nid="GEN", title="live transfer")
label(2556, 348, "• Realtor / Real Estate Agent", 19, INK)
label(2556, 374, "  (replaces Mariaelena from v1.0)", 17, "#A93529", MONO)
e(f'<line x1="2228" y1="430" x2="3392" y2="430" stroke="{RULE}" stroke-width="2"/>')
label(2228, 470, "NOTIFICATION ONLY — NO LIVE TRANSFER", 21, "#A8730A", MONO, 700)
node(2228, 490, 300, 120, "notify", nid="N14", title="TWIN HOME BUYER TEAM", vars_="email")
for i, t in enumerate(["Cherry", "Bryan", "Thea", "MC"]):
    label(2556, 520 + i * 26, "• " + t, 19, INK, wt=600)
label(2228, 646, "Used for approved legal / agency / mailer hard-stop", 18, DIM)
label(2228, 670, "notifications. No live call transfers to these recipients", 18, DIM)
label(2228, 694, "from the hard-stop node unless separately approved.", 18, DIM)
note(2228, 716, 1164, 130, "Other non-seller destinations follow the previously approved flow. "
     "Anything not yet confirmed is marked PENDING CONFIRMATION and must not be built as a guess.",
     colour="#A8730A", fill="#FDF7EA", title="UNCONFIRMED OWNERS")

# ---------- TOP SPINE ---------------------------------------------------
section(1500, 76, 560, "START OF CALL")
node(1580, 146, 400, 110, "action", nid="A1", title="Incoming call on a Twin Home Buyer tracking number")
node(1580, 286, 400, 120, "extract", nid="EXTRACT",
     vars_="source_channel · caller_id · call_start_time")
call_arrow([(1780, 256), (1780, 286)])
diamond(1780, 540, 500, 190, nid="Q1", title="Human answered within 3 rings?")
call_arrow([(1780, 406), (1780, 445)])
ending(1060, 480, 420, 120, "T1", "Human handles the call", "#16785A", "Retell does not continue")
call_arrow([(1530, 540), (1484, 540)], label="YES", lx=1507, ly=518, anchor="middle")
node(1560, 686, 440, 172, "action", nid="A2",
     title="Required AI opening — discloses it is the Twin Home Buyer AI assistant and that the call is recorded, before any substantive qualification")
call_arrow([(1780, 635), (1780, 686)], label="NO / AFTER HOURS", lx=1800, ly=668, anchor="start")
diamond(1780, 980, 580, 200, nid="Q2", title="Determine caller intent")
call_arrow([(1780, 858), (1780, 880)])

# ---------- INTENT BUS --------------------------------------------------
BUS = 1092
call_arrow([(1780, 1080), (1780, BUS)])
e(f'<line x1="440" y1="{BUS}" x2="3400" y2="{BUS}" stroke="#2A3542" stroke-width="3"/>')
for tick_x, cap, gated in [(440, "1  NEW SELLER", True), (1120, "2  SELLER CALLBACK", True),
                           (1720, "3  REALTOR / AGENT", True), (2470, "4 – 10  NON-SELLER", True),
                           (3240, "11  SPAM / WRONG No.", False)]:
    call_arrow([(tick_x, BUS), (tick_x, 1146 if gated else 1216)])
    if gated:
        call_arrow([(tick_x, 1196), (tick_x, 1216)])
    label(tick_x - (14 if tick_x == 1720 else 0), BUS - 18, cap, 19, "#1F6FB2", MONO, 700,
          anchor="end" if tick_x == 1720 else "middle")
call_arrow([(3400, BUS), (3490, BUS), (3490, 3386)], colour="#A93529")
label(3400, BUS - 52, "12 · 13 · 14  →  GLOBAL HARD STOPS", 19, "#A93529", MONO, 700, anchor="end")

# =========================== LEFT — SELLER ==============================
section(180, 1150, 1180, "SELLER FLOW", "#63459C")
SY = 1216
node(180, SY,        520, 100, "extract", nid="S1", title="Full name", vars_="seller_name")
node(180, SY + 116,  520, 124, "extract", nid="S2", title="Callback number — repeat back and confirm",
     vars_="callback_number · callback_confirmed")
node(180, SY + 256,  520, 124, "extract", nid="S3", title="Property address — street and city",
     vars_="property_address · property_city")
node(180, SY + 396,  520, 100, "extract", nid="S4", title="Reason for calling / selling motivation",
     vars_="seller_reason")
node(180, SY + 512,  520, 100, "extract", nid="S5", title="Selling timeline", vars_="seller_timeline")
node(180, SY + 628,  520, 158, "extract", nid="S6", title="Property condition — include only if approved",
     vars_="property_condition", pending="APPROVAL")
for a, b in [(SY+100, SY+116), (SY+240, SY+256), (SY+380, SY+396), (SY+496, SY+512), (SY+612, SY+628)]:
    call_arrow([(440, a), (440, b)])

node(860, SY, 520, 200, "action", nid="SC1",
     title="Returning seller — confirm name, property address if needed, callback number and a one-line reason for the callback")
node(860, SY + 216, 520, 124, "extract", nid="EXTRACT",
     vars_="seller_name · callback_number · callback_confirmed · call_reason_line")
call_arrow([(1120, SY + 200), (1120, SY + 216)])
note(860, SY + 356, 520, 100, "Do NOT restart the full new-seller questionnaire for a caller already in the system.",
     colour="#1F6FB2", fill="#EAF2F9", title="EXISTING SELLER")

# lead creation + integration
node(380, 2062, 800, 130, "action", nid="F1",
     title="Create / update lead record — send captured information through the existing integration",
     vars_="Retell → Zapier → REI BlackBook")
call_arrow([(440, SY + 786), (440, 2020), (780, 2020), (780, 2062)])
call_arrow([(1120, SY + 456), (1120, 2020), (780, 2020)])

diamond(780, 2322, 620, 215, nid="Q3", title="Qualified for live seller transfer?", pending="JUAN CONFIRMATION")
call_arrow([(780, 2192), (780, 2215)])
ending(140, 2262, 320, 120, "T5", "Seller not transfer-qualified", "#A8730A", "lead saved · Juan notified")
call_arrow([(470, 2322), (462, 2322)], label="NO", lx=468, ly=2296, anchor="middle")
diamond(780, 2592, 560, 190, nid="Q4", title="Inside approved transfer hours?", pending="JUAN CONFIRMATION")
call_arrow([(780, 2430), (780, 2497)], label="YES", lx=800, ly=2472, anchor="start")
node(140, 2532, 340, 130, "notify", nid="N3",
     title="NOTIFY JUAN + existing calendar automation", vars_="Zapier → Juan Google Calendar")
call_arrow([(500, 2592), (482, 2592)], label="NO", lx=492, ly=2566, anchor="middle")
ending(140, 2692, 340, 120, "T4", "After-hours seller", "#A8730A", "appointment / callback created")
notify_arrow([(310, 2662), (310, 2692)])
node(560, 2762, 440, 120, "transfer", nid="X1", title="TRANSFER CALL → JUAN", vars_="warm transfer")
call_arrow([(780, 2687), (780, 2762)], label="YES", lx=800, ly=2732, anchor="start")
diamond(780, 3010, 520, 180, nid="Q5", title="Did Juan answer?")
call_arrow([(780, 2882), (780, 2920)])
ending(1020, 2950, 340, 120, "T2", "Seller connected to Juan", "#16785A", "Juan owns the call")
call_arrow([(1040, 3010), (1020, 3010)], colour="#16785A", label="ANSWERS", lx=1030, ly=2990)
node(140, 2950, 350, 120, "notify", nid="N2",
     title="Save lead + NOTIFY JUAN — callback task")
call_arrow([(520, 3010), (494, 3010)], label="NO ANSWER", lx=520, ly=2936, anchor="end")
ending(140, 3110, 350, 120, "T3", "Seller captured — Juan unavailable", "#A8730A")
ending(560, 3110, 340, 120, "T6", "Returning seller message logged", "#A8730A")
notify_arrow([(315, 3070), (315, 3110)], label="new", lx=302, ly=3098, anchor="end")
notify_arrow([(420, 3070), (420, 3090), (730, 3090), (730, 3110)], label="returning", lx=748, ly=3078, anchor="start")

# =========================== CENTRE — REALTOR ===========================
section(1440, 1150, 560, "REALTOR / AGENT  →  GEN", "#16785A")
RY = 1216
node(1440, RY,       560, 100, "extract", nid="R1", title="Name", vars_="caller_name")
node(1440, RY + 116, 560, 124, "extract", nid="R2", title="Callback number — repeat and confirm",
     vars_="callback_number · callback_confirmed")
node(1440, RY + 256, 560, 124, "extract", nid="R3", title="Company / brokerage — only if naturally provided",
     vars_="caller_company")
node(1440, RY + 396, 560, 100, "extract", nid="R4", title="One-line reason for calling",
     vars_="call_reason_line")
node(1440, RY + 512, 560, 124, "action", nid="F2", title="Create agent contact record",
     vars_="call_type = realtor_agent")
for a, b in [(RY+100, RY+116), (RY+240, RY+256), (RY+380, RY+396), (RY+496, RY+512)]:
    call_arrow([(1720, a), (1720, b)])
note(1440, RY + 656, 560, 118, "Realtor / agent calls route to GEN. This replaces the v1.0 routing to Mariaelena.",
     title="v2.1 CONFIRMED CHANGE")
diamond(1720, RY + 900, 520, 180, nid="Q8", title="Can Gen take the call now?")
call_arrow([(1720, RY + 636), (1720, RY + 656)])
call_arrow([(1720, RY + 774), (1720, RY + 810)])
node(1460, 2452, 520, 120, "transfer", nid="X2", title="TRANSFER CALL → GEN")
call_arrow([(1720, 2206), (1720, 2452)], colour="#16785A", label="YES", lx=1740, ly=2300, anchor="start")
diamond(1720, 2700, 480, 180, nid="Q9", title="Did Gen answer?")
call_arrow([(1720, 2572), (1720, 2610)])
ending(1460, 2840, 520, 130, "T9", "Realtor / agent connected to Gen", "#16785A", "Gen owns the call")
call_arrow([(1720, 2790), (1720, 2840)], colour="#16785A", label="ANSWERS", lx=1740, ly=2822, anchor="start")
node(1460, 3020, 520, 140, "notify", nid="N4",
     title="NOTIFY GEN — caller information saved + callback request",
     vars_="Retell → Zapier → email / REI BlackBook")
call_arrow([(1480, RY + 900), (1420, RY + 900), (1420, 3090), (1460, 3090)],
           label="NO / AFTER HOURS", lx=1408, ly=RY + 878, anchor="end")
call_arrow([(1720, 2700), (1440, 2700), (1440, 3070), (1460, 3070)], label="NO ANSWER", lx=1428, ly=2960, anchor="end")
ending(1460, 3210, 520, 130, "T10", "Realtor / agent — Gen unavailable", "#A8730A", "Gen callback request created")
notify_arrow([(1720, 3160), (1720, 3210)])

# =========================== RIGHT — NON-SELLER =========================
section(2160, 1150, 620, "NON-SELLER ROUTING", "#1F6FB2")
node(2160, 1216, 620, 150, "action", nid="A3",
     title="Simple intake — “I'll get this to the right person. Can I get your name and the best number?”")
node(2160, 1382, 620, 140, "extract", nid="EXTRACT",
     vars_="caller_name · callback_number · call_reason_line · call_type")
call_arrow([(2470, 1366), (2470, 1382)])
diamond(2470, 1652, 580, 190, nid="Q10", title="Route on call_type")
call_arrow([(2470, 1522), (2470, 1557)])
ending(3080, 1216, 320, 150, "T20", "Spam / wrong number — polite end", "#A93529", "no lead record")

# --- two Juan live-transfer lanes -------------------------------------
for lx0, nid_q, cap, extra, xn, tn, nn, tn2 in [
    (2160, "Q11", "4 · Active contract / escrow",
     "caller_name · callback_number · call_reason_line", "X3", "T11", "N5", "T12"),
    (2800, "Q12", "5 · Title / escrow / lender",
     "caller_name · callback_number · caller_company · file_reference", "X4", "T13", "N6", "T14")]:
    node(lx0, 1790, 600, 84, "action", title=cap)
    node(lx0, 1888, 600, 118, "extract", nid="EXTRACT", vars_=extra)
    call_arrow([(lx0 + 300, 1874), (lx0 + 300, 1888)])
    diamond(lx0 + 300, 2126, 520, 160, nid=nid_q, title="Is Juan available for a live transfer?")
    call_arrow([(lx0 + 300, 2006), (lx0 + 300, 2046)])
    node(lx0, 2236, 290, 120, "transfer", nid=xn, title="TRANSFER CALL → JUAN")
    node(lx0 + 310, 2236, 290, 120, "notify", nid=nn,
         title="NOTIFY JUAN — message saved" + (" (time sensitive)" if nid_q == "Q11" else ""))
    call_arrow([(lx0 + 40, 2126), (lx0 + 145, 2126), (lx0 + 145, 2236)], colour="#16785A",
               label="YES", lx=lx0 + 130, ly=2196, anchor="end")
    call_arrow([(lx0 + 560, 2126), (lx0 + 455, 2126), (lx0 + 455, 2236)],
               label="NO", lx=lx0 + 470, ly=2196, anchor="start")
    ending(lx0, 2396, 290, 130, tn, "Connected to Juan", "#16785A")
    ending(lx0 + 310, 2396, 290, 130, tn2, "Message logged for Juan", "#A8730A")
    call_arrow([(lx0 + 145, 2356), (lx0 + 145, 2396)], colour="#16785A")
    notify_arrow([(lx0 + 455, 2356), (lx0 + 455, 2396)])
call_arrow([(2470, 1747), (2470, 1770), (2460, 1770), (2460, 1790)], label="4", lx=2440, ly=1782, anchor="end")
call_arrow([(2560, 1652), (3100, 1652), (3100, 1790)], label="5", lx=3118, ly=1700, anchor="start")

# --- five notification-only lanes ------------------------------------
LANES = [
    ("6 · Past client",            "call_reason_line",                    "N7",  "past-client follow-up owner", "T15", True),
    ("7 · Buyer / investor",       "property_of_interest · call_reason_line","N8",  "buyer / investor owner",     "T16", True),
    ("8 · Vendor / subcontractor", "caller_company · call_reason_line",   "N9",  "vendor owner",               "T17", True),
    ("9 · Job applicant",          "position_interest · call_reason_line","N10", "RECRUITING",                 "T18", False),
    ("10 · Peninsula Plumbing",    "plumbing_issue_summary",              "N11", "Peninsula Plumbing process", "T19", False),
]
lane_x = [2160, 2412, 2664, 2916, 3168]
for (cap, extra, nn, dest, tn, pend), lx0 in zip(LANES, lane_x):
    node(lx0, 2600, 232, 96, "action", title=cap)
    node(lx0, 2710, 232, 130, "extract", nid="EXTRACT", vars_=extra)
    node(lx0, 2856, 232, 160, "notify", nid=nn, title="NOTIFY " + dest,
         pending="CONFIRMATION" if pend else None)
    ending(lx0, 3032, 232, 150, tn, cap.split("· ")[1] + " routed", "#A8730A")
    call_arrow([(lx0 + 116, 2696), (lx0 + 116, 2710)])
    call_arrow([(lx0 + 116, 2840), (lx0 + 116, 2856)])
    notify_arrow([(lx0 + 116, 3016), (lx0 + 116, 3032)])
    call_arrow([(2100, 2560), (lx0 + 116, 2560), (lx0 + 116, 2600)],
               label=cap.split(" ·")[0], lx=lx0 + 116, ly=2548, anchor="middle")
call_arrow([(2180, 1652), (2100, 1652), (2100, 2560)], label="6 – 10", lx=2088, ly=2110, anchor="end")
note(3168, 3198, 232, 172, "Never convert a plumbing caller into a seller lead — even if they mention selling. See H6.",
     title="H6 · KEEP SEPARATE")

# =========================== GLOBAL HARD STOPS ==========================
band(140, 3420, 3280, 1530, "GLOBAL HARD STOPS",
     "G-DNC · G-LEGAL · G-MAILER · G-HUMAN · H4 · H6  —  these interrupt the call from ANY conversation node above")
for bx in range(360, 3300, 300):
    notify_arrow([(bx, 3420), (bx, 3386)], colour="#A93529")

# --- G-DNC lane
node(200, 3510, 500, 150, "stop", nid="G-DNC",
     title="“Take me off your list” · “Stop calling me” · “Don't contact me” · “Remove me”")
node(740, 3510, 340, 150, "extract", nid="EXTRACT", vars_="dnc_requested = true",
     )
call_arrow([(700, 3585), (740, 3585)], colour="#A93529")
node(1120, 3510, 620, 150, "notify", nid="N13",
     title="Trigger suppression through the existing automation + Twin Home Buyer notification",
     vars_="Retell → Zapier → suppression")
call_arrow([(1080, 3585), (1120, 3585)])
ending(1780, 3520, 460, 130, "T21", "DNC honored", "#A93529", "qualification stops immediately")
notify_arrow([(1740, 3585), (1780, 3585)])
note(2280, 3510, 1140, 150, "Stop seller qualification the moment a DNC request is heard. Do not continue "
     "the questionnaire, do not transfer, do not ask a qualifying question.", title="G-DNC RULE")

# --- G-LEGAL / G-MAILER lanes
node(200, 3700, 500, 190, "stop", nid="G-LEGAL",
     title="Attorney · lawyer · lawsuit · subpoena · legal threat · investigator · government agency · DA · Attorney General · consumer protection · regulator")
node(200, 3920, 500, 150, "stop", nid="G-MAILER",
     title="Mailer · letter · check · postcard · “How did you get my address?” · complaint about Twin Home Buyer mail")
node(740, 3760, 560, 240, "action", nid="HS1",
     title="Stop normal qualification. Capture the approved minimum only. No legal advice, no explaining, no defending Twin Home Buyer, no confirming or denying allegations, no speculating, no improvising.")
call_arrow([(700, 3795), (720, 3795), (720, 3830), (740, 3830)], colour="#A93529")
call_arrow([(700, 3995), (720, 3995), (720, 3930), (740, 3930)], colour="#A93529")
node(1340, 3760, 380, 240, "extract", nid="EXTRACT",
     vars_="hard_stop_type · hard_stop_reference · legal_party_name · agency_name · caller_name · callback_number")
call_arrow([(1300, 3880), (1340, 3880)])
node(1760, 3760, 380, 240, "action", nid="F3",
     title="Preserve the transcript and call information", vars_="transcript_id")
call_arrow([(1720, 3880), (1760, 3880)])
node(2180, 3760, 660, 240, "notify", nid="N14",
     title="NOTIFY TWIN HOME BUYER TEAM — Cherry · Bryan · Thea · MC — by EMAIL, with the approved captured information and transcript reference. Notification only: no live call is transferred.",
     vars_="Retell → Zapier → email / REI BlackBook")
call_arrow([(2140, 3880), (2180, 3880)])
ending(2880, 3800, 540, 160, "T22", "Legal / agency / mailer escalation logged",
       "#A93529", "call ends · transcript preserved")
notify_arrow([(2840, 3880), (2880, 3880)])

# --- G-HUMAN lane
node(200, 4090, 500, 170, "stop", nid="G-HUMAN",
     title="Caller asks for a human · hostile caller · caller is a minor · intent still unclear after 2 attempts")
diamond(1020, 4175, 520, 160, nid="Q13", title="Approved human available now?")
call_arrow([(700, 4175), (760, 4175)], colour="#A93529")
node(1340, 4090, 380, 130, "transfer", nid="X5", title="TRANSFER CALL → approved human",
     pending="CONFIRMATION")
call_arrow([(1280, 4175), (1310, 4175), (1310, 4155), (1340, 4155)], colour="#16785A",
           label="YES", lx=1316, ly=4112, anchor="start")
ending(1760, 4090, 340, 130, "T23", "Human escalation connected", "#16785A")
call_arrow([(1720, 4155), (1760, 4155)], colour="#16785A")
node(1340, 4270, 380, 130, "notify", nid="N12",
     title="Capture name + callback number → callback notification")
call_arrow([(1280, 4175), (1310, 4175), (1310, 4335), (1340, 4335)],
           label="NO", lx=1316, ly=4300, anchor="start")
ending(1760, 4270, 340, 130, "T24", "Human escalation callback logged", "#A8730A")
notify_arrow([(1720, 4335), (1760, 4335)])
note(2180, 4090, 1240, 170, "All four triggers stop seller qualification immediately, including a caller who "
     "is a minor. The destination for the human escalation transfer is not yet confirmed — until it is, capture "
     "the name and callback number and raise the callback notification.",
     colour="#A8730A", fill="#FDF7EA", title="PENDING CONFIRMATION")


# --- H4 · price / offer / valuation
node(200, 4460, 500, 170, "stop", nid="H4",
     title="PRICE / OFFER / VALUATION — caller asks for a price, an offer, a home value or a valuation")
node(760, 4460, 620, 170, "action", nid="RULE",
     title="The AI must NOT invent or provide a price, offer, home value or valuation. No number, no range, no estimate, no “somewhere around”.")
call_arrow([(700, 4545), (760, 4545)], colour="#A93529")
node(1440, 4460, 620, 170, "action", nid="→ SELLER",
     title="Route into the approved seller → Juan transfer / callback process",
     vars_="re-enters S1 – S6 → Q3 · endings T2 – T6")
call_arrow([(1380, 4545), (1440, 4545)], colour="#1F6FB2")
note(2120, 4460, 1300, 170, "A valuation is never given on this call, and the caller is not simply turned away. "
     "The question is a buying signal: hand it to the seller flow so Juan does the pricing conversation.",
     colour="#1F6FB2", fill="#EAF2F9", title="H4 RULE")

# --- H6 · plumbing selling motivation
node(200, 4690, 500, 190, "stop", nid="H6",
     title="PLUMBING SELLING MOTIVATION — caller entered through the Peninsula Plumbing branch and later mentions wanting to sell the property")
node(760, 4690, 620, 190, "action", nid="RULE",
     title="Do NOT convert the call into a Twin Home Buyer seller lead. Do not start seller qualification. Do not transfer to Juan.")
call_arrow([(700, 4785), (760, 4785)], colour="#A93529")
ending(1440, 4710, 620, 150, "T19", "Stay in the Peninsula Plumbing flow",
       "#A8730A", "same ending as the plumbing lane")
call_arrow([(1380, 4785), (1440, 4785)], colour="#A8730A")
note(2120, 4690, 1300, 190, "The plumbing branch and the Twin Home Buyer seller pipeline never cross, whichever "
     "direction the caller drifts. If a plumbing caller wants to sell, that is a separate future Twin Home Buyer "
     "call — not this one. Log it in the plumbing record only.",
     colour="#A8730A", fill="#FDF7EA", title="H6 RULE")

# =========================== BOTTOM PANELS ==============================
panel(140, 5000, 1560, 400, "EXISTING INTEGRATIONS  —  shown for reference, not redesigned")
node(200, 5120, 260, 100, "action", nid="RETELL", title="call data")
node(520, 5120, 260, 100, "notify", nid="ZAPIER", title="automation layer")
notify_arrow([(460, 5170), (520, 5170)])
for yy, nm in [(5060, "REI BLACKBOOK"), (5170, "GOOGLE SHEETS"), (5280, "JUAN GOOGLE CALENDAR")]:
    e(f'<rect x="840" y="{yy}" width="320" height="90" rx="4" fill="#F1F4F8" stroke="#7E8896" stroke-width="2"/>')
    e(lines_block(1000, yy + 45, [([nm], MONO, 18, 700, INK)]))
    notify_arrow([(780, 5170), (810, 5170), (810, yy + 45), (840, yy + 45)])
label(1200, 5090, "Lead and intake capture flows out through Zapier.", 19, INK, wt=600)
label(1200, 5120, "Property / address information may also feed the", 18, DIM)
label(1200, 5146, "existing Google Sheet automation. After-hours seller", 18, DIM)
label(1200, 5172, "appointments use the existing Juan calendar automation.", 18, DIM)
label(1200, 5230, "These are notification / data paths — dashed.", 18, "#A8730A", MONO, 600)
label(1200, 5256, "No live call is ever transferred through them.", 18, "#A8730A", MONO, 600)

panel(1740, 5000, 760, 400, "SHARED ENDINGS")
ending(1780, 5090, 680, 130, "T25", "Transfer technical failure — information saved, intended owner and Juan notified",
       "#A8730A", "reachable from X1 · X2 · X3 · X4 · X5")
ending(1780, 5250, 680, 130, "T26", "Caller hung up / disconnected — partial capture saved",
       "#A8730A", "reachable from any conversation node")

panel(2560, 5000, 860, 400, "PENDING CONFIRMATION")
py = 5100
for item, where in [
    ("Juan transfer cutoff / hours", "Q4 · T4"),
    ("Seller transfer qualification criteria", "Q3 · T5"),
    ("Property-condition question approved?", "S6"),
    ("Human / minor-caller escalation dest.", "X5 · Q13 · T23"),
    ("Past-client / buyer / vendor owners", "N7 · N8 · N9"),
    ("Callback SLAs", "T3 · T10 · T12 · T24"),
    ("Peninsula Plumbing live transfer allowed?", "T19"),
]:
    e(f'<rect x="2592" y="{py-16}" width="10" height="10" fill="#A8730A"/>')
    label(2616, py - 6, item, 19, INK, wt=500)
    label(3390, py - 6, where, 16, FAINT, MONO, anchor="end")
    py += 34
label(2592, py + 12, "Nothing on this list may be built as a guess.", 18, "#A93529", MONO, 700)

# =========================== ASSEMBLE ===================================
marker_defs = []
for col in ["2A3542", "16785A", "A93529", "A8730A", "1F6FB2"]:
    marker_defs.append(
        f'<marker id="solid-{col}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="#{col}"/></marker>')
    marker_defs.append(
        f'<marker id="open-{col}" viewBox="0 0 11 11" refX="10" refY="5.5" markerWidth="8" '
        f'markerHeight="8" orient="auto-start-reverse">'
        f'<path d="M1,1 L10,5.5 L1,10" fill="none" stroke="#{col}" stroke-width="2"/></marker>')

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
       f'role="img" aria-label="Twin Home Buyer inbound Retell AI call flow version 2.1: '
       f'intake and intent classification, seller flow to Juan, realtor flow to Gen, '
       f'non-seller routing, and global hard stops with team email notification.">'
       f'<defs>{"".join(marker_defs)}</defs>' + "".join(out) + '</svg>')

pathlib.Path("/workspace/Ai-agent/docs/twin-home-buyer-call-flow-v2.1.svg").write_text(
    '<?xml version="1.0" encoding="UTF-8"?>\n' + svg, encoding="utf-8")
if OVERFLOW:
    print(f"!! {len(OVERFLOW)} boxes too small for their text:")
    for tag, msg in OVERFLOW: print("   ", tag, "--", msg)
else:
    print("all text fits its boxes")
print("SVG written:", len(svg) // 1024, "KB", W, "x", H)
