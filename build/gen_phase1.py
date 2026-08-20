# Twin Home Buyer — Phase 1 Seller Inbound Call Flow (New Seller + Seller Callback only).
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from svgkit import *   # noqa
import svgkit as K

W, H = 3400, 4300
K.init(W, H)
node, diamond, ending, note, band, panel = K.node, K.diamond, K.ending, K.note, K.band, K.panel
label, section, e, lines_block = K.label, K.section, K.e, K.lines_block
call_arrow, notify_arrow = K.call_arrow, K.notify_arrow
INK, DIM, FAINT, RULE, MONO, SANS = K.INK, K.DIM, K.FAINT, K.RULE, K.MONO, K.SANS

# ---------------- TITLE BLOCK ----------------
e(f'<rect x="120" y="60" width="540" height="420" rx="6" fill="#FFFFFF" stroke="{INK}" stroke-width="3"/>')
e(f'<rect x="120" y="60" width="540" height="8" fill="#1F6FB2"/>')
label(148, 124, "TWIN HOME BUYER", 21, "#1F6FB2", MONO, 700)
label(148, 178, "Phase 1 Seller", 34, INK, wt=700)
label(148, 220, "Inbound Call Flow", 34, INK, wt=700)
e(f'<line x1="148" y1="252" x2="632" y2="252" stroke="{RULE}" stroke-width="2"/>')
for i, (k, v) in enumerate([("SCOPE", "New Seller + Seller Callback only"),
                            ("STATUS", "For Cherry's review — not yet approved"),
                            ("BUILD / RETELL", "Rosanes"),
                            ("APPROVAL", "Cherry first, then Juan")]):
    label(148, 288 + i * 48, k, 15, FAINT, MONO, 700)
    label(148, 312 + i * 48, v, 20, INK, wt=600)

# ---------------- SCOPE BANNER ----------------
note(700, 60, 1140, 200,
     "Build and approve these two caller types first. Do NOT build the Realtor, legal, plumbing, "
     "buyer, vendor, applicant or other branches yet — they are later phases. The goal is to get "
     "this seller flow approved before the rest of the Retell system is built.",
     colour="#1F6FB2", fill="#EAF2F9", title="PHASE 1 SCOPE")
note(700, 280, 1140, 200,
     "The Google Chat availability check runs at the same time as the AI conversation. Never build it "
     "as: notify → wait 30 seconds → check → continue. There must be no point where the caller hears "
     "silence waiting for Juan or Cherry.",
     colour="#A8730A", fill="#FDF7EA", title="TIMING PRINCIPLE")

# ---------------- THE CRITICAL RULE ----------------
band(1900, 60, 1380, 420, "A CLAIM DOES NOT INTERRUPT THE CALL",
     "mandatory — this is the rule most likely to be built wrong")
label(1930, 168, "If Juan or Cherry sends TRANSFER while the seller is talking, the AI must NOT transfer yet.", 20, INK, wt=600)
for i, t in enumerate(["Cut off the seller",
                       "Interrupt mid-sentence",
                       "Suddenly announce a transfer",
                       "Abandon the question being answered",
                       "Skip required information because somebody claimed"]):
    e(f'<text x="1948" y="{212 + i * 34}" font-family="{MONO}" font-size="20" font-weight="700" fill="#A93529">✗</text>')
    label(1982, 212 + i * 34, t, 19, INK)
e(f'<rect x="2560" y="196" width="690" height="176" rx="4" fill="#FFFFFF" stroke="#A93529" stroke-width="2"/>')
label(2584, 232, "CLAIM  =  PENDING TRANSFER", 20, "#A93529", MONO, 700)
label(2584, 266, "transfer_claim_status = claimed", 17, DIM, MONO)
label(2584, 292, "transfer_target = Juan | Cherry", 17, DIM, MONO)
label(2584, 326, "The AI keeps talking. The transfer waits for:", 18, INK, wt=600)
label(2584, 352, "seller finishes → intake complete → natural break", 17, "#16785A", MONO, 600)

# ---------------- LEGEND ----------------
panel(120, 510, 3160, 170, "LEGEND")
lx = 150
for kind, name in [("action", "Conversation / Action"), ("extract", "Extract Variables"),
                   ("decision", "Logic Split"), ("transfer", "Transfer Call"),
                   ("notify", "Function / Notify"), ("stop", "Critical Rule")]:
    fill, stroke, _ = K.KINDS[kind]
    e(f'<rect x="{lx}" y="600" width="56" height="38" rx="3" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
    label(lx + 68, 624, name, 18, INK, wt=600)
    lx += 300
e(f'<rect x="{lx}" y="600" width="56" height="38" rx="19" fill="{K.END_FILL}" stroke="#16785A" stroke-width="3"/>')
label(lx + 68, 624, "Ending", 18, INK, wt=600)
e(f'<line x1="2200" y1="608" x2="2320" y2="608" stroke="#16785A" stroke-width="4" marker-end="url(#solid-16785A)"/>')
label(2336, 615, "SOLID = live call moves (transfer)", 18, "#16785A", MONO, 600)
e(f'<line x1="2200" y1="646" x2="2320" y2="646" stroke="#A8730A" stroke-width="4" stroke-dasharray="12 7" marker-end="url(#open-A8730A)"/>')
label(2336, 653, "DASHED = notification only, no transfer", 18, "#A8730A", MONO, 600)

# ---------------- INTAKE SPINE ----------------
section(700, 720, 420, "INCOMING CALL")
node(700, 786, 420, 110, "action", nid="A1", title="Call arrives on the Twin Home Buyer inbound / tracking number")
node(700, 926, 420, 124, "extract", nid="EXTRACT", vars_="caller_id · source_channel · call_start_time")
call_arrow([(910, 896), (910, 926)])
diamond(910, 1180, 500, 190, nid="Q1", title="Did a human answer within 3 rings?")
call_arrow([(910, 1050), (910, 1085)])
ending(240, 1120, 400, 120, "T1", "Human handles the call", "#16785A", "Retell AI does not continue")
call_arrow([(660, 1180), (648, 1180)], label="YES", lx=654, ly=1156, anchor="middle")
node(700, 1330, 420, 160, "action", nid="A2",
     title="Retell AI answers and gives the approved AI / recording disclosure. No seller qualification before the disclosure is complete.")
call_arrow([(910, 1275), (910, 1330)], label="NO / AFTER HOURS", lx=930, ly=1310, anchor="start")
diamond(910, 1620, 560, 200, nid="Q2", title="Identify caller — New Seller or Seller Callback?")
call_arrow([(910, 1490), (910, 1520)])
node(700, 1750, 420, 110, "extract", nid="EXTRACT", vars_="caller_type")
call_arrow([(910, 1720), (910, 1750)])
note(240, 1750, 420, 110, "Every other caller type is a later phase. Phase 1 recognises these two only.",
     colour="#1F6FB2", fill="#EAF2F9", title="PHASE 1")

# ---------------- N1 GOOGLE CHAT ALERT ----------------
node(1560, 1580, 620, 200, "notify", nid="N1",
     title="GOOGLE CHAT LIVE ALERT → JUAN + CHERRY — sent the moment the caller is classified",
     vars_="target delay 1 – 3 s")
notify_arrow([(1190, 1620), (1560, 1620)], label="IMMEDIATE", lx=1375, ly=1596, anchor="middle")
note(1560, 1800, 620, 140, "Sending this must NOT stop or pause the AI conversation. The AI keeps "
     "talking to the seller.", title="DOES NOT PAUSE THE AI")
e(f'<rect x="2260" y="1560" width="1020" height="380" rx="6" fill="#F7F9FB" stroke="{RULE}" stroke-width="2"/>')
e(f'<rect x="2260" y="1560" width="1020" height="4" fill="#A8730A"/>')
label(2288, 1608, "WHAT THE GOOGLE CHAT ALERT CONTAINS", 22, INK, wt=700)
for i, t in enumerate(["Call type — New Seller or Seller Callback",
                       "Caller name, if already captured",
                       "Caller phone number",
                       "Property address, if already captured",
                       "Call start time and current call status"]):
    label(2300, 1654 + i * 30, "• " + t, 19, DIM)
e(f'<rect x="2288" y="1812" width="964" height="104" rx="4" fill="#FFFFFF" stroke="#A8730A" stroke-width="2"/>')
label(2312, 1848, "AI is currently on a New Seller call.", 20, INK, wt=700)
label(2312, 1876, "John Smith · 650-555-1234 · Property: collecting now · AI gathering information", 17, DIM, MONO)
e(f'<rect x="2312" y="1888" width="150" height="20" rx="3" fill="#16785A"/>')
e(lines_block(2387, 1898, [(["CLAIM: JUAN"], MONO, 13, 700, "#FFFFFF")]))
e(f'<rect x="2478" y="1888" width="164" height="20" rx="3" fill="#16785A"/>')
e(lines_block(2560, 1898, [(["CLAIM: CHERRY"], MONO, 13, 700, "#FFFFFF")]))

# ---------------- CAPTURE COLUMNS ----------------
section(240, 1900, 880, "AI CONTINUES THE CONVERSATION  —  DATA GATHERING", "#63459C")
NS = 1966
node(240, NS,       420, 100, "extract", nid="S1", title="Full name", vars_="seller_name")
node(240, NS + 116, 420, 140, "extract", nid="S2", title="Best callback number — repeat it back to the caller",
     vars_="callback_number · callback_confirmed")
node(240, NS + 272, 420, 124, "extract", nid="S3", title="Property address — street and city",
     vars_="property_address · property_city")
node(240, NS + 412, 420, 140, "extract", nid="S4", title="Reason / motivation — let the caller finish, do not interrupt",
     vars_="seller_reason")
node(240, NS + 568, 420, 116, "extract", nid="S5", title="Timeline — when they hope to sell",
     vars_="seller_timeline")
node(240, NS + 700, 420, 176, "action", nid="S6", title="Additional approved questions only — e.g. property condition if approved later",
     pending="CHERRY / JUAN APPROVAL")
label(450, NS - 22, "NEW SELLER", 21, "#63459C", MONO, 700, anchor="middle")
for a, b in [(100, 116), (256, 272), (396, 412), (552, 568), (684, 700)]:
    call_arrow([(450, NS + a), (450, NS + b)])

node(700, NS,       420, 100, "extract", nid="SC1", title="Confirm identity — seller name", vars_="seller_name")
node(700, NS + 116, 420, 172, "extract", nid="SC2", title="Confirm the property they are calling about — do not re-ask the full address if the record identifies it")
node(700, NS + 304, 420, 124, "extract", nid="SC3", title="Confirm best callback number",
     vars_="callback_number · callback_confirmed")
node(700, NS + 444, 420, 140, "extract", nid="SC4", title="Reason for the callback — what they need help with",
     vars_="callback_reason")
label(910, NS - 22, "SELLER CALLBACK", 21, "#63459C", MONO, 700, anchor="middle")
for a, b in [(100, 116), (288, 304), (428, 444)]:
    call_arrow([(910, NS + a), (910, NS + b)])
note(700, NS + 600, 420, 140, "Do NOT restart the New Seller questionnaire. The AI recognises this is an "
     "existing seller and confirms rather than re-asks.", colour="#63459C", fill="#F0EAF8",
     title="EXISTING SELLER")
call_arrow([(910, NS + 584), (910, NS + 600)])
call_arrow([(910, 1860), (910, 1900)])
call_arrow([(910, 1946), (450, 1946), (450, NS)])
call_arrow([(910, 1946), (910, NS)])
label(1140, NS + 300, "45 – 90 s of real conversation.", 19, DIM, wt=600)
label(1140, NS + 328, "This is not delay — the seller", 19, DIM)
label(1140, NS + 356, "is actively talking to the AI.", 19, DIM)

# ---------------- PARALLEL CLAIM LANE ----------------
band(1560, 1990, 1720, 700, "MEANWHILE  —  IN PARALLEL", "claim status updates while the AI keeps gathering information",
     colour="#16785A", fill="#EDF6F2")
node(1600, 2090, 560, 150, "action", nid="CLAIM",
     title="Juan or Cherry claims the live call in Google Chat")
node(1600, 2270, 560, 160, "extract", nid="EXTRACT",
     vars_="transfer_claim_status = claimed · transfer_target = Juan | Cherry · transfer_requested_at")
call_arrow([(1880, 2240), (1880, 2270)], colour="#16785A")
node(2220, 2090, 500, 150, "extract", nid="NO CLAIM",
     title="Nobody responds", vars_="transfer_claim_status = none")
note(2220, 2270, 1020, 160, "Their useful response window is from classification until the AI finishes the "
     "required intake — typically 45 – 90 s. There is no fixed 10 / 20 / 30 second deadline, and the "
     "caller never waits on it.", colour="#16785A", fill="#FFFFFF", title="RESPONSE WINDOW")
note(1600, 2470, 1640, 180, "A claim arriving while the caller is speaking causes 0 seconds of interruption. "
     "The AI finishes the current answer, completes any missing required information, and only then makes "
     "the handoff statement.", title="0 s INTERRUPTION")
notify_arrow([(2770, 1940), (2770, 1990)], label="claim actions", lx=2790, ly=1974, anchor="start")

# ---------------- TRANSFER READINESS ----------------
diamond(910, 2980, 620, 200, nid="Q3", title="Has someone claimed the call?")
call_arrow([(450, NS + 876), (450, 2880), (910, 2880)])
call_arrow([(910, NS + 740), (910, 2880)])
diamond(910, 3190, 620, 180, nid="Q4", title="Is the minimum required intake complete?")
call_arrow([(910, 3080), (910, 3100)], label="CLAIMED — Juan or Cherry", lx=930, ly=3096, anchor="start")
call_arrow([(600, 3190), (180, 3190), (180, 2592), (234, 2592)],
           colour="#63459C", label="NO — keep gathering, then re-check", lx=196, ly=2900, anchor="start")
note(2560, 2740, 720, 160, "The required fields that must be complete before a live transfer are not yet defined.",
     colour="#A8730A", fill="#FDF7EA", title="PENDING CHERRY CONFIRMATION")

# ---------------- OUTCOME LANES ----------------
LANE_Y = 3400
for x0, who, hid, xid, tconn, tfail, pron in [
        (140, "JUAN", "H1", "X1", "T2", "T4", "him"),
        (1000, "CHERRY", "H2", "X2", "T3", "T5", "her")]:
    node(x0, LANE_Y, 700, 130, "action", nid=hid,
         title=f"Natural handoff — “Thank you. {who.title()} is available now, so I'm going to connect you with {pron}.”",
         vars_="2 – 4 s")
    node(x0 + 175, LANE_Y + 170, 350, 120, "transfer", nid=xid, title=f"TRANSFER CALL → {who}",
         vars_="starts 1 – 3 s later")
    call_arrow([(x0 + 350, LANE_Y + 130), (x0 + 350, LANE_Y + 170)], colour="#16785A")
    diamond(x0 + 350, LANE_Y + 400, 480, 170, nid="", title=f"Did {who.title()} answer?")
    call_arrow([(x0 + 350, LANE_Y + 290), (x0 + 350, LANE_Y + 315)])
    ending(x0, LANE_Y + 520, 340, 140, tconn, f"Seller connected to {who.title()}",
           "#16785A", "transfer_result = connected")
    call_arrow([(x0 + 200, LANE_Y + 470), (x0 + 170, LANE_Y + 470), (x0 + 170, LANE_Y + 520)],
               colour="#16785A", label="YES", lx=x0 + 160, ly=LANE_Y + 452, anchor="end")
    node(x0 + 360, LANE_Y + 520, 340, 140, "notify", nid="",
         title=f"Save everything captured, create the callback and notify {who.title()}",
         vars_="transfer_result = no_answer")
    call_arrow([(x0 + 500, LANE_Y + 470), (x0 + 530, LANE_Y + 470), (x0 + 530, LANE_Y + 520)],
               label="NO", lx=x0 + 540, ly=LANE_Y + 452, anchor="start")
    ending(x0 + 360, LANE_Y + 690, 340, 140, tfail, f"{who.title()} transfer unsuccessful — callback created",
           "#A8730A", "the lead is never lost")
    notify_arrow([(x0 + 530, LANE_Y + 660), (x0 + 530, LANE_Y + 690)])
call_arrow([(910, 3280), (910, 3330), (490, 3330), (490, LANE_Y)], colour="#16785A",
           label="YES · claimed by Juan", lx=505, ly=3318, anchor="start")
call_arrow([(910, 3280), (910, 3330), (1350, 3330), (1350, LANE_Y)], colour="#16785A",
           label="YES · claimed by Cherry", lx=1335, ly=3318, anchor="end")

# --- nobody claimed
node(1900, LANE_Y, 620, 130, "action", nid="F1", title="Save the seller lead",
     vars_="Retell → Zapier → REI BlackBook  ·  approved address data → Google Sheet")
call_arrow([(1220, 2980), (1900, 2980), (1900, LANE_Y)], label="NOBODY CLAIMED", lx=1560, ly=2956, anchor="middle")
node(1900, LANE_Y + 170, 620, 130, "notify", nid="N2",
     title="Callback notification — seller called, intake complete, nobody claimed, callback required")
notify_arrow([(2210, LANE_Y + 130), (2210, LANE_Y + 170)])
node(1900, LANE_Y + 340, 620, 130, "action", nid="F2", title="Create the approved callback task",
     vars_="callback_required = true")
call_arrow([(2210, LANE_Y + 300), (2210, LANE_Y + 340)])
ending(1900, LANE_Y + 520, 620, 140, "T6", "Seller information captured — callback required",
       "#A8730A", "AI ends politely, the team follows up")
call_arrow([(2210, LANE_Y + 470), (2210, LANE_Y + 520)])
note(1900, LANE_Y + 690, 620, 140, "The AI must never sit silently waiting for a claim, and never make the "
     "seller wait. Callback SLA is not yet set.", colour="#A8730A", fill="#FDF7EA",
     title="PENDING — CALLBACK SLA")

# ---------------- PANELS ----------------
panel(2600, 3320, 680, 810, "TARGET TIMING")
ty = 3392
for k, v in [("AI answers", "after the 3-ring window"), ("AI disclosure", "3 – 6 s"),
             ("Identify caller type", "5 – 15 s after answering"), ("Google Chat alert", "1 – 3 s, immediate"),
             ("Information gathering", "45 – 90 s of conversation"), ("Claim window", "classification → intake done"),
             ("Claim while speaking", "0 s interruption"), ("Handoff statement", "2 – 4 s"),
             ("Transfer starts", "1 – 3 s after handoff"),
             ("Perceived delay after intake", "≈ 3 – 7 s to ringing")]:
    label(2628, ty, k, 18, INK, wt=600)
    label(2628, ty + 24, v, 17, "#16785A", MONO, 600)
    ty += 60
label(2628, ty + 6, "Excludes how long Juan or", 17, DIM)
label(2628, ty + 30, "Cherry takes to pick up.", 17, DIM)

panel(140, 4250, 0, 0, "")
K.out.pop(); K.out.pop(); K.out.pop()

K.render('/workspace/Ai-agent/docs/twin-home-buyer-phase1-seller-flow.svg',
         'Twin Home Buyer Phase 1 seller inbound call flow: incoming call, AI disclosure, New Seller and '
         'Seller Callback capture, an immediate Google Chat alert to Juan and Cherry that never pauses the '
         'AI, a claim that becomes a pending transfer instead of interrupting, live transfer to Juan or '
         'Cherry, and a callback path when nobody claims.')
