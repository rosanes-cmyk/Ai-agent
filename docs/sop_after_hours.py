"""The after-hours handoff, as a document somebody can be handed.

Separate from the two call SOPs because it answers a different question.
Those describe what to do; this one describes what the system does when
nobody is there to do anything -- and, more usefully, how to tell whether
it is still doing it. Every check in the last section was run on the live
service on 5 November 2026 and the results are printed with them, because
a checklist with no answers beside it gets filled in from memory the
second time.
"""

from build_sops import (
    S, build, bullets, callout, flow_steps, para, table,
)
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, PageBreak, Spacer

VERIFIED = "5 November 2026"


def shot(name, caption, width=5.6):
    """A screenshot, scaled to the page, with what it proves written under it.

    Cropped before it got here. The Cloud Run shot in particular is trimmed
    to the one row that matters: the two webhook values above it are already
    cut off by the field edge, but a credential half-shown in a document that
    gets forwarded is still a credential half-shown.
    """
    img = ImageReader("proof/%s.png" % name)
    w, h = img.getSize()
    out = Image("proof/%s.png" % name, width=width * inch,
                height=width * inch * h / w)
    out.hAlign = "LEFT"
    return [out, Spacer(1, 4), para(caption, "note"), Spacer(1, 12)]


def heading(text):
    return para(text, "h2")


story = []

story += [
    heading("What this covers"),
    para(
        "A seller rings outside the shift. Nobody is at a desk. This is what "
        "happens to that call, why it was built this way, and the four ways "
        "it can go wrong -- one of which looks exactly like it working."
    ),
    Spacer(1, 10),

    heading("The shift"),
    table(
        [
            ["When", "Who takes the call"],
            ["Mon to Sat, 8:00 AM - 4:59 PM Pacific", "the team, then the Voice AI"],
            ["Mon to Sat, 5:00 PM - 7:59 AM", "the live answering service"],
            ["All day Sunday", "the live answering service"],
        ],
        [2.6 * inch, 3.4 * inch],
    ),
    Spacer(1, 10),

    heading("What happens, step by step"),
    flow_steps([
        ("The seller dials",
         "Outside the shift. They do not know that, and nothing they hear "
         "tells them."),
        ("Retell asks what time it is",
         "Before the AI speaks a word, Retell calls the listener. This is the "
         "only moment the hour can still change the call."),
        ("The listener decides",
         "It works out the hour itself and answers open or closed. The AI is "
         "not asked to judge it."),
        ("A different agent is swapped in",
         "For a closed call only. The after-hours agent has a one-line "
         "script and no intake."),
        ("The card is posted",
         "AFTER HOURS -- HANDING TO THE ANSWERING SERVICE, with the caller's "
         "number and the time, so the morning shift sees the night."),
        ("The agent speaks once and transfers",
         "\"One moment, connecting you.\" Then straight to the answering "
         "service on +1 408 868 5175. It asks nothing."),
        ("The message reaches the team",
         "The answering service takes it and passes it on in the morning."),
    ]),
    Spacer(1, 10),

    heading("Why it was built this way"),
    para(
        "<b>The listener decides the hour, not the AI.</b> Asking a language "
        "model to compare 16 against 17 in the middle of a conversation is a "
        "coin toss, and that comparison decides whether a seller reaches a "
        "person or an intake. The listener works it out and hands the agent a "
        "plain yes or no."
    ),
    para(
        "<b>It is a separate agent, not a rule in the main prompt.</b> After a "
        "fixed greeting the main agent has nothing to respond to, so it takes "
        "no turn at all until silence forces one. On test it sat for fifteen "
        "seconds and then started the intake. An agent that speaks first has "
        "no such gap."
    ),
    para(
        "<b>The card says \"handing to\", not \"handed to\".</b> It is posted "
        "when the call arrives, because that is the only moment we are "
        "certain it is an out-of-hours call -- the transfer leg looks the "
        "same as a Spanish handover or a claim. If the transfer then fails, "
        "the agent takes the seller's name and number itself and the usual "
        "callback card follows, so the team sees the truth either way."
    ),
    Spacer(1, 10),

    heading("The four ways it goes wrong"),
    callout(
        "The one that looks like it is working",
        "If AFTER_HOURS_AGENT_ID is not set, the card still posts saying the "
        "seller is going to the answering service -- but with no agent to "
        "swap in, the main agent takes the call and runs the full daytime "
        "intake, at eleven at night, with nobody awake to act on it. The card "
        "reads identically either way. The only signal is "
        "AFTER_HOURS_AGENT_ID_NOT_SET in the log.",
    ),
    Spacer(1, 6),
    bullets([
        "<b>The clock webhook does not answer.</b> Retell runs the call with "
        "no clock at all, no agent is swapped in and no card is posted. The "
        "seller gets the daytime intake. This is the failure that left the "
        "hour empty on every call for weeks before anyone noticed.",
        "<b>The hours are still overridden from a test.</b> The two hour "
        "settings exist so this path can be tested in daylight. Left set, the "
        "shift is silently wrong in whichever direction the test needed.",
        "<b>The Chat webhook is missing.</b> The handoff still happens and the "
        "seller still reaches the answering service -- but nobody is told it "
        "happened.",
    ]),
    Spacer(1, 10),

    heading("How to check it, and what we found"),
    para(
        f"All three were run against the live service on {VERIFIED}. Doing "
        "them again takes about five minutes."
    ),
    table(
        [
            ["Check", "Where", "Result"],
            ["The transfer number",
             "Retell, the after-hours agent, transfer_to_sas",
             "PASS  +1 408 868 5175"],
            ["The agent is wired up",
             "Cloud Run, Variables and Secrets, AFTER_HOURS_AGENT_ID",
             "PASS  matches the live agent"],
            ["The hours are not overridden",
             "ask the listener the time and compare",
             "PASS  9 AM read as open"],
        ],
        [1.5 * inch, 2.7 * inch, 1.8 * inch],
    ),
    Spacer(1, 6),
    para(
        "There are two agents in Retell with similar names. Only one is live. "
        "Check the agent id in the browser's address bar against the value in "
        "Cloud Run rather than going by the name -- the wrong one either "
        "repeats the connecting line or never says it.",
        "note",
    ),
    Spacer(1, 10),

    heading("What this does not do"),
    para(
        "There is no duty person. The system has two states, in-shift and "
        "answering service, and nothing between them: an evening rota where a "
        "named person takes calls until ten is not built. Every seller is "
        "answered, and none of them reach a member of the team after five."
    ),
    para(
        "The after-hours agent itself -- its script and the number it dials -- "
        "lives in Retell, not in the code. If calls stop reaching the "
        "answering service, start there.",
    ),
]

story += [PageBreak(), heading("The proof")]
story += [para(
    "Taken on %s, in the order the checks were run. Anyone repeating them "
    "should see the same three things." % VERIFIED
), Spacer(1, 10)]

story += shot(
    "1-cloudrun",
    "<b>Check 2.</b> Cloud Run, Variables and Secrets. AFTER_HOURS_AGENT_ID "
    "is set, and this is the value the next shot has to match. Cropped to "
    "this row on purpose.",
)
story += shot(
    "2-retell-agent",
    "<b>Check 2, matched.</b> The browser's address bar on the live agent. "
    "The id matches, and the agent is THB After Hours - SAS Handoff. There "
    "is a second agent with a similar name that does NOT match, so the name "
    "alone proves nothing.",
    width=6.2,
)
story += shot(
    "3-transfer-number",
    "<b>Check 1.</b> The transfer_to_sas function on that agent. The "
    "destination is +1 408 868 5175, and Cold Transfer is correct here - the "
    "answering service needs the call, not a briefing.",
)
story += [para(
    "<b>Check 3</b> left no screenshot because it was not a screen. The "
    "listener was asked the time directly and answered 9 AM, Thursday, "
    "office_open: yes - which is only true if the hours are the real ones. "
    "A test override would have returned closed.",
)]


build(
    "THB_After_Hours_Handoff.pdf",
    "After Hours",
    "What happens to a seller who rings when nobody is there",
    story,
    f"Twin Home Buyer  |  verified against the live service {VERIFIED}",
)
print("built THB_After_Hours_Handoff.pdf")
