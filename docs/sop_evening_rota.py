"""The evening duty rota, as a document somebody can be handed.

Written the day it went live, because the useful half of this is not the
rule -- the rule fits in a table -- but the evidence that the rule is
actually running, and the one bug that made it look like it was running
when it was not. Every check in the proof section was made against the
live service on 5 November 2026 and the answer is printed beside it.
"""

from build_sops import (
    S, build, bullets, callout, flow_steps, para, table,
)
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, PageBreak, Spacer

VERIFIED = "5 November 2026"


def shot(name, caption, width=6.2):
    img = ImageReader("proof/%s.png" % name)
    w, h = img.getSize()
    out = Image("proof/%s.png" % name, width=width * inch,
                height=width * inch * h / w)
    out.hAlign = "LEFT"
    return [out, Spacer(1, 4), para(caption, "note"), Spacer(1, 10)]


def heading(text):
    return para(text, "h2")


story = []

# ----------------------------------------------------------------- what

story += [
    para(
        "Until today an evening call rang the whole ring group and then the "
        "answering service. At seven in the evening the group is a list of "
        "people who went home at five, so the ringing was a formality and "
        "the answering service took almost all of it. A seller who reaches a "
        "person is worth more than the same seller reaching a message "
        "service, so one named person now covers each evening and only their "
        "phone rings.",
        "lead",
    ),
    Spacer(1, 6),

    heading("The rule"),
    table(
        [
            ["When (Pacific)", "Who rings", "For how long"],
            ["Mon-Sat  8:00 AM - 4:59 PM", "the ring group, unchanged", "25 seconds"],
            ["Mon-Sat  5:00 PM - 5:59 PM", "nobody - answering service", "-"],
            ["Mon-Sat  6:00 PM - 9:59 PM", "the duty person, alone", "20 seconds"],
            ["Mon-Sat  10:00 PM - 7:59 AM", "nobody - answering service", "-"],
            ["Sunday, all day", "nobody - answering service", "-"],
        ],
        [2.3 * inch, 2.5 * inch, 1.2 * inch],
    ),
    para(
        "The answering service is +1 408 868 5175. After ten o'clock it is "
        "not a fallback, it is the destination: no team phone rings at all.",
    ),
    Spacer(1, 4),
    callout(
        "The hour between five and six",
        "The office closes at 5:00 PM and the duty evening starts at 6:00 PM, "
        "so calls in that hour go to the answering service. That is what the "
        "settings currently say rather than something anybody decided. "
        "Setting DUTY_STARTS_HOUR to 17 closes the gap and hands the hour to "
        "the duty person instead.",
    ),
]

# ----------------------------------------------------------------- flow

story += [
    heading("The flow, call by call"),
    flow_steps([
        ("A seller dials a tracking number",
         "Any of them. The rota is not per-number; it applies to every call "
         "that reaches the Call Coach phone webhook."),
        ("Profit Dial says which number was dialled",
         "That decides the daytime ring group, exactly as before. Nothing "
         "here changed."),
        ("The clock is read in the office's timezone",
         "America/Los_Angeles, asked for explicitly. The server is in Iriga, "
         "sixteen hours ahead, and reading its own clock would have rung the "
         "duty person through the night."),
        ("8:00 AM - 4:59 PM: the ring group rings",
         "The rota steps aside entirely. The daytime path is untouched."),
        ("6:00 PM - 9:59 PM: the Reps tab is read",
         "Whoever is marked for that weekday in the Duty column, and is "
         "Active, and has a mobile. Read live on every call, so a swap in "
         "the sheet takes effect on the next ring with no restart."),
        ("Their phone rings for 20 seconds",
         "One person, not the group. Shorter than the daytime window on "
         "purpose: in the day a seller waits on a team, any of whom might "
         "reach a handset; in the evening on one person who is either "
         "holding their phone or is not."),
        ("No answer, or nobody on duty, or 10:00 PM onwards",
         "The answering service takes the call."),
    ]),
]

story += [
    heading("Where the rota lives"),
    para(
        "In the <b>Reps</b> tab of the Call Coach sheet, in a column called "
        "<b>Duty</b>. Not in a settings file: a rota is the most changeable "
        "thing in an office and none of those changes should need a deploy "
        "or a restart."
    ),
    table(
        [
            ["Name", "Duty", "Covers"],
            ["Thea", "Mon, Wed, Fri", "Monday, Wednesday, Friday evenings"],
            ["Cherry", "Tue, Thu", "Tuesday and Thursday evenings"],
            ["everyone else", "blank", "nothing - which is correct"],
        ],
        [1.5 * inch, 1.9 * inch, 2.6 * inch],
    ),
    para(
        "A blank cell means that person covers no evenings. A weekday nobody "
        "covers is not an error either: it falls to the answering service, "
        "which is where the call went before any of this existed. "
        "\"Mon, Wed, Fri\" and \"Monday/Wednesday\" and \"MON WED\" are all "
        "read the same way, because the column is typed by a person."
    ),
]

# ------------------------------------------------------------- the bug

story += [PageBreak(), para("The bug that cost the first four test calls", "h1")]

story += [
    para(
        "Worth writing down because it is the exact failure this system is "
        "prone to, and because it looked from the outside like the rota "
        "simply had not been built.",
        "lead",
    ),
    para(
        "The Duty column went into the sheet. The rota was switched on. "
        "Every test call still went to the answering service."
    ),
    para(
        "The rota was not wrong. It never saw the column. The code builds "
        "its read range from its own list of expected headers -- "
        "<b>Reps!A2:J</b> -- so a column typed into the sheet past the last "
        "one it knows about is never fetched at all. Duty was the eleventh "
        "column in a ten-column range. Every rep came back with an empty "
        "Duty, nobody matched the weekday, and the call fell through to the "
        "answering service."
    ),
    callout(
        "Why this took four calls to find",
        "The fallthrough is deliberate and silent. \"Nobody is on duty "
        "tonight\" and \"the rota is broken\" produce the identical outcome: "
        "the answering service answers, and the call sounds like it worked. "
        "Any failure whose symptom is the previous correct behaviour costs "
        "real time to find.",
    ),
    para(
        "Two things were needed. The header list now declares <b>Duty</b>, "
        "so the range reaches it. And because rows are matched to headers by "
        "position, the column has to sit in <b>K</b> on the sheet -- the "
        "blank spacer column it was originally typed past would have shifted "
        "every value by one."
    ),
    para(
        "Committed as <b>817da9a</b>, with a test that fails if anybody "
        "appends a column to that sheet again without declaring it.",
    ),
]

# ----------------------------------------------------------------- test

story += [
    para("What was tested", "h1"),
    table(
        [
            ["Check", "Result"],
            ["Automated tests, whole backend",
             "729 passed, 1 pre-existing failure unrelated to this work"],
            ["Rota tests specifically", "12 of 12 passed"],
            ["Live call, Thursday 11:xx Pacific, before the fix",
             "rang the answering service - WRONG"],
            ["Live call, Thursday 1:xx Pacific, after the fix",
             "rang Cherry alone - CORRECT"],
        ],
        [2.6 * inch, 3.4 * inch],
    ),
    para(
        "The live calls were made with the duty window temporarily moved to "
        "the current hour, so the evening path could be exercised in the "
        "afternoon. Those three overrides have been removed and the window "
        "is back to 6:00 PM - 10:00 PM."
    ),
    Spacer(1, 4),
    heading("The twelve rota tests, by name"),
    bullets([
        "a rota is typed by a person, so read it the way a person writes it",
        "daytime is untouched - the whole group still rings",
        "between six and ten only the duty person rings",
        "the rota follows the day, not the person",
        "after ten the answering service is rung directly, not left empty",
        "the gap between five and six goes to the answering service",
        "a day nobody covers is not an error, it is the old behaviour",
        "on duty with no mobile is an error, and says whose",
        "an inactive rep does not cover an evening",
        "Sunday is closed all day, so the evening window does not open",
        "the office hour decides, not the server's",
        "the evening rings for twenty seconds, the day for twenty-five",
    ]),
]

# ---------------------------------------------------------------- proof

story += [PageBreak(), para("The proof", "h1")]
story += [para(
    "Taken on %s, in the order the checks were run." % VERIFIED
), Spacer(1, 8)]

story += shot(
    "4-duty-column-L",
    "<b>Before.</b> The Duty column typed into column L, past the blank "
    "spacer in K. The sheet looks right and reads right to a person. The "
    "code's range stopped at J, so every one of these cells was invisible "
    "to it and the rota found nobody on duty.",
)
story += shot(
    "5-duty-column-K",
    "<b>After.</b> The same column moved into K, with the header now "
    "declared in the code. This is the layout the rota reads. The rows were "
    "also swapped at this point - Thea on Mon/Wed/Fri, Cherry on Tue/Thu - "
    "so that Thursday's test call would exercise a different person than the "
    "earlier attempts.",
)
story += [para(
    "<b>The live call</b> left no screenshot because the evidence was a "
    "ringing phone: at 1:xx PM Pacific on Thursday 5 November, with the duty "
    "window moved to that hour, a call to the tracking line rang Cherry's "
    "handset alone and no other phone on the team. Confirmed by the office.",
)]

# --------------------------------------------------------------- open

story += [
    para("Still open", "h1"),
    bullets([
        "<b>The morning report does not send.</b> It is built and logged "
        "every morning at 8:00 and then goes nowhere, because "
        "REPORT_WEBHOOK_URL is not set. It needs a Zapier catch hook wired "
        "to Gmail. This is the right failure to have - a report nobody "
        "receives is better than a mail server inside a phone system - but "
        "it is not done.",
        "<b>The five-to-six gap</b> above, if the hour should belong to the "
        "duty person.",
        "<b>Cherry's number is in TRAINING_NUMBERS.</b> Calls on it are "
        "filed as practice drills, which means they are dropped from the "
        "marketing figures. Unrelated to the rota, but it is her number the "
        "rota now rings.",
    ]),
]

build(
    "THB_Evening_Duty_Rota.pdf",
    "The Evening Duty Rota",
    "Who rings after five, why, and the evidence that it works",
    story,
    "Twin Home Buyer  |  verified against the live service %s" % VERIFIED,
)
print("built THB_Evening_Duty_Rota.pdf")
