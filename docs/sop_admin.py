"""The admin copy: the same system, plus where every piece is set."""

import sys
sys.path.insert(0, "/workspace/Ai-agent/docs")

from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Spacer

from build_sops import (
    build, bullets, callout, flow_steps, para, table,
)

S = []
A = S.append

A(para(
    "Everything the team sees, plus where it is configured. Two systems are "
    "involved and it helps to keep them apart: <b>the phone routing</b>, "
    "which decides whose phone rings and in what order, and <b>Call Coach</b>, "
    "which records, transcribes and grades whatever happens on the call."))

# ------------------------------------------------------------ the path
A(para("The whole path of an inbound call", "h1"))
A(flow_steps([
    ("Seller dials a campaign number",
     "One of ~52 tracking numbers, each with its own callflow"),
    ("Lead source is recorded",
     "Two webhooks fire before anything rings - this is what puts "
     "REDDIT or PPC on the card"),
    ("The team line rings", "5 to 10 seconds, set per campaign"),
    ("If nobody answers: the AI assistant",
     "It asks what time it is, then decides"),
    ("In hours: the AI runs the intake",
     "Posts the LIVE SELLER CALL card, anyone can claim with ME"),
    ("Out of hours: straight to the answering service",
     "One line, then a live person - no intake"),
    ("Nothing answered at all", "Missed-call alert fires"),
]))

A(callout(
    "The ring time is short on purpose, but check it",
    "Reddit currently rings the team for 5 seconds, PPC for 10. Five seconds "
    "is barely one ring, so in practice the team rarely gets a chance on "
    "that campaign. If you want people to have a real shot at answering, "
    "raise it - the cost is the seller waiting longer before the AI speaks."))

# ------------------------------------------------------------ after hours
A(para("The answering service, and the 8-5 rule", "h1"))
A(para(
    "The answering service answers everything outside the shift. This is "
    "decided by us, not by them - their own portal cannot stop their agents "
    "picking up, so the call simply never reaches them during the day."))

A(table([
    ["When", "Who takes the call"],
    ["Monday to Saturday, 8:00 AM - 4:59 PM", "The team, then the AI assistant"],
    ["Monday to Saturday, 5:00 PM - 7:59 AM", "The answering service"],
    ["All day Sunday", "The answering service"],
], [3.1 * inch, 3.4 * inch]))

A(para("How it decides", "h2"))
A(bullets([
    "The AI has no clock of its own. When a call arrives it asks our own "
    "server what time it is in California",
    "The server answers with the hour, the day, and a plain yes or no for "
    "whether the office is open",
    "<b>Open</b> - the normal assistant answers and runs the intake",
    "<b>Closed</b> - a second, much smaller assistant answers instead. It "
    "says one line, \"One moment, connecting you\", and passes the caller "
    "straight to the answering service",
    "A card is posted to Chat at the same moment so the team can see it "
    "happened",
]))

A(callout(
    "Why there are two assistants",
    "The main one has a long script and, after a fixed greeting, waits for "
    "the caller to speak before it does anything. Out of hours that pause is "
    "wasted - so a separate assistant with a three-line script speaks first "
    "and transfers immediately. Trying to do it with a rule inside the main "
    "script was tested and it sat silent for fifteen seconds instead."))

A(para("Changing the hours", "h2"))
A(para(
    "The shift is set in the server's settings, not in the code, so it can "
    "be changed without a developer:"))
A(table([
    ["Setting", "Meaning", "Default"],
    ["OFFICE_OPENS_HOUR", "Shift starts, on a 24-hour clock", "8"],
    ["OFFICE_CLOSES_HOUR", "Shift ends", "17 (5 PM)"],
    ["OFFICE_CLOSED_DAYS", "Days the team never works", "Sunday"],
    ["AFTER_HOURS_AGENT_ID", "Which assistant answers out of hours",
     "must be set"],
], [1.95 * inch, 3.35 * inch, 1.2 * inch]))
A(para(
    "The server prints what it read at startup, including whether each value "
    "came from a setting or a default. If a change does not seem to have "
    "taken, that line says so plainly rather than leaving you to guess."))

A(PageBreak())

# ------------------------------------------------------------- the claim
A(para("The ME claim, step by step", "h1"))
A(flow_steps([
    ("The AI answers a seller", "Call starts"),
    ("Card posted to Google Chat",
     "LIVE SELLER CALL, with the lead source and the caller's number"),
    ("A rep replies ME in the thread", "2-minute window"),
    ("First valid reply wins",
     "Later replies are ignored - one seller is never sent to two people"),
    ("The AI is told, mid-call",
     "It finishes its sentence, then offers the seller the handover"),
    ("Seller says yes", "Call transfers to that rep's phone"),
    ("LIVE CALL CLAIMED card posted", "Shows who took it and what was collected"),
]))

A(para("What can stop a claim landing", "h2"))
A(table([
    ["Symptom", "Cause", "Fix"],
    ["Rep types ME, nothing happens",
     "They are not on the claim roster, so the system does not recognise them",
     "Add their Google Chat user id to the roster setting"],
    ["Recognised, but the transfer fails",
     "On the roster but no phone number against their name",
     "Add their mobile to the roster entry"],
    ["Claim arrives after the call ended",
     "More than 2 minutes passed",
     "Nothing to fix. The callback card covers it"],
    ["Spanish call cannot be claimed",
     "The Spanish leg is a separate call. The claim has to follow it",
     "Reply ME in the thread under the Spanish notice, not the original card"],
], [1.75 * inch, 2.45 * inch, 2.3 * inch]))

# ------------------------------------------------------------- the sheet
A(para("Call Coach: the control sheet", "h1"))
A(para(
    "Call Coach is run entirely from one Google Sheet. No code, no restarts "
    "- it reads the sheet on every call."))

A(para("The Numbers tab", "h2"))
A(para("One row per campaign number. Three columns matter:"))
A(table([
    ["Column", "What to put in it"],
    ["Number", "The campaign's tracking number, the one sellers dial"],
    ["Ring Group",
     "Who should answer. Several mobiles separated by commas, or one group "
     "number"],
    ["No Answer",
     "Where the call goes if nobody picks up - usually the AI line. Leave "
     "blank for no AI"],
], [1.5 * inch, 5.0 * inch]))
A(callout(
    "The mistake worth avoiding",
    "Putting one person's mobile in Ring Group. Then only that phone rings, "
    "and every time they are busy the seller gets the AI instead of a human. "
    "List everyone who should take that campaign."))

A(para("The Reps tab", "h2"))
A(para("One row per person:"))
A(table([
    ["Column", "What it does"],
    ["Rep ID", "Short lowercase name, like <b>era</b>"],
    ["Name", "How it shows on the dashboard"],
    ["Mobile", "Their phone, so <b>inbound</b> calls attach to them"],
    ["REI User", "Their REI BlackBook id, so <b>outbound</b> calls attach"],
], [1.5 * inch, 5.0 * inch]))
A(para(
    "Without REI User, that rep's outbound calls show a dash instead of "
    "their name."))

# -------------------------------------------------------------- weekly
A(para("Every week", "h1"))
A(bullets([
    "<b>Executive page</b> - check calls, average score and appointments",
    "<b>Reps page</b> - look for anyone at zero calls. That is almost always "
    "a missing Mobile or REI User, not a lazy rep",
    "<b>Hang-ups under 30 seconds</b> - if this is high, the openings need "
    "work, not the closing",
    "<b>Inbound vs outbound score per rep</b> - people are often strong at "
    "one and weak at the other",
], numbered=True))

A(para("The buttons", "h2"))
A(table([
    ["Button", "Where", "When to use it"],
    ["Fix rep names", "Calls page",
     "After adding a Mobile or REI User. Attaches past calls to the right "
     "person"],
    ["Score unscored", "Reps page", "Grades any call that was missed"],
    ["Repair the Sheet", "Reps page", "Fixes missing columns after an update"],
], [1.5 * inch, 1.2 * inch, 3.8 * inch]))

A(PageBreak())

# ------------------------------------------------------------ troubles
A(para("When something looks wrong", "h1"))
A(table([
    ["What you see", "What it means", "What to do"],
    ["Sellers keep getting the AI",
     "Ring Group has one person in it, or the ring time is very short",
     "Add more numbers to that row, or raise the ring seconds"],
    ["A rep shows 0 calls", "Their Mobile or REI User is missing",
     "Fill it in on the Reps tab, then click Fix rep names"],
    ["Rep column shows a dash",
     "Nobody said their name, and their REI id is not mapped",
     "Add the REI User id, or remind the rep to introduce themselves"],
    ["Score shows <b>too short</b>",
     "Under 45s inbound or 2 min outbound", "Nothing. Working as intended"],
    ["A call is missing",
     "Made outside REI, or REI is still processing it",
     "Wait 10 minutes. If still missing, it was not made through REI"],
    ["Dashboard shows 502", "The server is not running",
     "Start the Call Coach task on the office PC"],
    ["Red quota banner", "Google is rate-limiting reads during a busy spell",
     "Clears by itself in a minute"],
    ["Caller reaches the AI in English but is Spanish",
     "The assistant needs two unusable answers in a row before it hands over",
     "Normal. It fires on the second one"],
    ["No card when the office is closed",
     "The after-hours assistant is not set",
     "Check AFTER_HOURS_AGENT_ID is filled in"],
], [1.85 * inch, 2.35 * inch, 2.3 * inch]))

# --------------------------------------------------------- known issues
A(para("Known issues, still open", "h1"))
A(para(
    "Recorded here so nobody spends an afternoon rediscovering them."))
A(table([
    ["Issue", "Where it stands"],
    ["<b>CALL ANSWERED BY A TEAM MEMBER can be wrong</b>",
     "The phone system calls a call \"answered\" the moment anything picks "
     "up - including voicemail and the recording system. So the card can fire "
     "when the AI actually took the call. Removed from the Reddit number, "
     "which stopped the false cards but also stopped the true ones. Still "
     "present on every other number."],
    ["<b>That card carries no call reference</b>",
     "It is posted on a delay, so it lands in the middle of whatever call is "
     "happening at that moment and looks like it belongs to it. Adding the "
     "reference and the call time would fix the confusion on its own."],
    ["<b>The routing automation runs several times per call</b>",
     "Seen firing seven times in three minutes. Harmless so far, but it is "
     "the likely source of any duplicate cards."],
    ["<b>50 numbers still need the corrected callflow</b>",
     "Only the Reddit number has the current shape. The rest still have the "
     "old answered-webhook arrangement."],
], [2.3 * inch, 4.2 * inch]))

# ------------------------------------------------------------------- ask
A(para("Who to ask", "h1"))
A(para(
    "Anything not on these pages - send a screenshot to <b>Jonathan</b> or "
    "<b>Seth</b>. For anything touching the phone routing, the AI assistant "
    "or the answering service, say which campaign number the call came in on. "
    "Each number has its own callflow and they are not all identical."))

build(
    "/workspace/Ai-agent/docs/THB_Call_System_Admin.pdf",
    "Call System - Admin Guide",
    "Twin Home Buyer &nbsp;&middot;&nbsp; phone routing, the AI assistant, "
    "the answering service and Call Coach",
    S,
    "Twin Home Buyer - Call System Admin Guide",
)
print("admin pdf written")
