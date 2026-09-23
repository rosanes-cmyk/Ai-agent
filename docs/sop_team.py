"""The team's copy. Everything here is something a rep can act on."""

import sys
sys.path.insert(0, "/workspace/Ai-agent/docs")

from reportlab.lib.units import inch
from reportlab.platypus import Spacer

from build_sops import (
    build, bullets, callout, flow_steps, para, table,
)

S = []
A = S.append

A(para(
    "Every call is recorded, written out as text, and graded out of 100. "
    "Nobody has to press anything, and nobody has to remember to start it. "
    "This page tells you what happens on a call and the few things that are "
    "yours to do."))

# ---------------------------------------------------------------- inbound
A(para("When a seller calls us", "h1"))
A(flow_steps([
    ("Seller dials a campaign number", "From an ad, postcard or sign"),
    ("Your phones ring", "Everyone on that campaign rings at once"),
    ("First to answer takes the call", "Nothing to press, just answer"),
    ("If nobody answers, the AI picks up", "It talks to the seller for you"),
    ("The call is recorded, written out and graded", ""),
    ("It appears on the dashboard", "Within a few minutes"),
]))
A(para(
    "The phones only ring for a few seconds before the AI takes over. That "
    "is deliberate - a seller who waits is a seller who hangs up - so if you "
    "want the call, answer quickly."))

# --------------------------------------------------------------- outbound
A(para("When you call a seller", "h1"))
A(bullets([
    "Open the seller in REI BlackBook and press <b>Make a Call</b>",
    "REI rings your phone first, then connects the seller",
    "REI records the call and writes it out",
    "It reaches the dashboard, graded, usually within 5 to 10 minutes",
], numbered=True))
A(callout(
    "Calls made any other way do not exist",
    "If you dial from your own phone, there is no recording, no transcript "
    "and no score. As far as the dashboard is concerned the call never "
    "happened, and neither did your work on it."))

# ------------------------------------------------------------- the claim
A(para("Taking a live call from Google Chat", "h1"))
A(para(
    "When the AI answers a seller, a card appears in the "
    "<b>THB - Seller Call Routing &amp; Handoff</b> space. The seller is on "
    "the line right then, talking to the AI."))
A(para(
    "If you want that call, reply <b>ME</b> to the card. The AI finishes the "
    "sentence it is on, tells the seller someone has just freed up, and puts "
    "them through to your phone."))
A(bullets([
    "You have <b>2 minutes</b> from the card appearing",
    "<b>First person to reply gets it.</b> If someone beat you, nothing happens",
    "Reply in the thread under the card, not in the main channel",
    "Only reply ME if you can take the call right now - the seller is waiting",
]))

A(para("The cards you will see", "h2"))
A(para(
    "In Chat each of these carries a coloured dot. The names are what "
    "matters - they are printed here in the same colours."))
A(table([
    ["Card", "What it means", "What to do"],
    ['<font color="#c0392b"><b>LIVE SELLER CALL</b></font>',
     "A seller is on the phone with the AI right now.",
     "Reply <b>ME</b> within 2 minutes to take it."],
    ['<font color="#b8860b"><b>NOW SPEAKING SPANISH</b></font>',
     "The seller switched to Spanish, so the AI handed them to the Spanish "
     "assistant. Still live.",
     "If you speak Spanish, reply <b>ME</b> in that thread."],
    ['<font color="#c0392b"><b>CALLBACK NEEDED</b></font>',
     "The call has ended and nobody took it. The seller's details are on "
     "the card.",
     "Call them back as soon as you can."],
    ['<font color="#3d5a80"><b>AFTER HOURS</b></font>',
     "Someone called outside 8-5 and our answering service took it.",
     "Nothing tonight. The message reaches you in the morning."],
], [1.55 * inch, 2.75 * inch, 2.2 * inch]))

# ------------------------------------------------------------ after hours
A(para("After 5pm, weekends and Sunday", "h1"))
A(para(
    "Outside 8:00 AM to 5:00 PM, and all day Sunday, a live answering "
    "service picks up instead of the AI. They take the seller's details and "
    "those reach you the next working morning. You are not expected to "
    "answer the phone at 11pm."))

# ----------------------------------------------------------------- daily
A(para("Your day, in four lines", "h1"))
A(bullets([
    "Keep your phone on and near you - seller calls ring everyone at once",
    "Make outbound calls from inside REI BlackBook, using <b>Make a Call</b>",
    "<b>Say your name in the opening.</b> \"Twin Home Buyer, this is Era.\" "
    "That is how the system knows the call was yours",
    "Before you finish, open your page and read the coaching note on your "
    "worst call",
], numbered=True))
A(callout(
    "No name, no credit",
    "The system matches a call to you by hearing you introduce yourself. If "
    "nobody says a name, the call shows a dash instead of a person, and it "
    "counts for nobody."))

# ------------------------------------------------------------ your score
A(para("Your page", "h1"))
A(para(
    "Sign in and you see only your own calls. For each one you get a score "
    "out of 100, the single thing that would have helped most on that call, "
    "and the recording and transcript to play back."))

A(para("What the score measures", "h2"))
A(para(
    "Not whether you were nice. Whether you covered the things that turn a "
    "call into an appointment:"))
A(bullets([
    "Greeted the seller warmly",
    "Introduced the company and yourself by name",
    "Asked how they heard about us <i>(inbound only)</i>",
    "Asked why they want to sell",
    "Asked for the property address",
    "Asked about condition, timeline, and who is on title",
    "Asked for the appointment",
]))
A(para(
    "Most lost points come from skipping one of these, not from saying "
    "anything wrong."))

A(para("What does not get a score", "h2"))
A(para(
    "A call under 45 seconds inbound, or under 2 minutes outbound, is kept "
    "and counted but not graded. It shows <b>too short</b> where the score "
    "would be. A 20-second hang-up is not a coaching sample, and grading it "
    "would mark you down for a call that was never yours to win."))

# --------------------------------------------------------------- gotchas
A(para("Things people ask about", "h1"))
A(table([
    ["What you see", "What is happening"],
    ["My call is not showing",
     "Give it 10 minutes. Outbound calls have to finish processing in REI "
     "first. If it is still missing after that, it was not made through REI."],
    ["It says <b>too short</b>",
     "Under 45 seconds inbound, or 2 minutes outbound. Not a fault. The "
     "call still counts toward your total."],
    ["It has no name on it",
     "Nobody introduced themselves on that call. Say your name in the "
     "opening and it attaches to you automatically."],
    ["I replied ME and nothing happened",
     "Either someone replied first, or the 2 minutes had passed. Both are "
     "normal."],
], [1.85 * inch, 4.65 * inch]))

# ------------------------------------------------------------------- ask
A(para("Who to ask", "h1"))
A(para(
    "Anything not on this page - send a screenshot to <b>Jonathan</b> or "
    "<b>Seth</b>. The screenshot is usually enough to work out what happened."))

build(
    "/workspace/Ai-agent/docs/THB_Call_Guide_Team.pdf",
    "Call Guide",
    "Twin Home Buyer &nbsp;&middot;&nbsp; for the team &nbsp;&middot;&nbsp; "
    "questions to Jonathan or Seth",
    S,
    "Twin Home Buyer - Call Guide for the team",
)
print("team pdf written")
