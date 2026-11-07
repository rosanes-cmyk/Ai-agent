"""Why two calls stopped halfway on 5 November, written out in full.

A step that had never once succeeded was sitting in the middle of the
call pipeline, and because Zapier halts a run at the first failed step,
every call that reached it lost everything after it. The failure was
loud -- a red error on every single run -- and invisible, because nobody
reads a history page that is mostly green ticks.
"""

from build_sops import (
    S, build, bullets, callout, flow_steps, para, table,
)
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, PageBreak, Spacer

FIXED = "7 November 2026"


def shot(name, caption, width=5.9):
    img = ImageReader("proof/%s.png" % name)
    w, h = img.getSize()
    out = Image("proof/%s.png" % name, width=width * inch,
                height=width * inch * h / w)
    out.hAlign = "LEFT"
    return [out, Spacer(1, 4), para(caption, "note"), Spacer(1, 12)]


def heading(text):
    return para(text, "h2")


story = []

# -------------------------------------------------------- what happened

story += [
    para(
        "On 5 November two seller calls went halfway through the system and "
        "stopped. Steps 1 to 15 ran. Steps 17 to 27 did not. Nobody was told, "
        "and nothing on a phone or in a chat room looked wrong.",
        "lead",
    ),
    para(
        "The cause was step 16: a POST to another Zap, which answered "
        "<b>\"please unsubscribe me!\"</b>. Zapier stops a run at the first "
        "step that errors, so everything after step 16 was skipped."
    ),
    Spacer(1, 6),

    heading("What \"please unsubscribe me!\" means"),
    para(
        "It is not a server being down or a network problem. It is the exact "
        "reply Zapier's own catch hooks give when the Zap behind them is not "
        "live. The receiving end is telling the sender to stop calling: there "
        "is nobody here."
    ),
    callout(
        "Which makes the diagnosis a lookup, not a hunt",
        "That one phrase says the target Zap exists and is switched off. "
        "It rules out a bad URL, a timeout, a credential, and a rate limit "
        "in one line -- which is why this took twenty minutes to settle "
        "once anybody actually read the error.",
    ),
]

# ------------------------------------------------------------- the trace

story += [
    heading("Following it to the end"),
    flow_steps([
        ("Step 16 posts to hook 4hgbqo2",
         "Sending call_id, section5, section5_detail, dnc and call_type -- "
         "the compliance fields off the call analysis."),
        ("4hgbqo2 answers \"please unsubscribe me!\"",
         "So that hook belongs to a Zap that is not running."),
        ("The Zap it belongs to is \"(Copy) Retell Monday AI\"",
         "Switched off, and marked Draft -- never published, not "
         "switched off later. Someone duplicated a Zap to edit it and "
         "stopped partway."),
        ("The live original is \"Retell Monday AI\", hook 4hmkrz1",
         "A different hook. Nothing in the call pipeline posts to it."),
        ("That live Zap has run zero times in 30 days",
         "So it is not quietly doing the job instead. Nothing has been "
         "feeding it either."),
    ]),
    para(
        "Which settles what step 16 was for, and what to do about it: it "
        "pointed at a copy somebody abandoned mid-edit. It has almost "
        "certainly <b>never</b> succeeded -- this was not a working step that "
        "broke on 5 November."
    ),
]

# ------------------------------------------------------------ the choice

story += [
    heading("Three options, and why it was the second"),
    table(
        [
            ["Option", "Verdict"],
            ["A. Turn the target Zap on",
             "No. It is an unfinished draft. Publishing half-edited work into "
             "a live call pipeline trades one fault for a worse one."],
            ["B. Remove step 16",
             "Yes. It has never delivered anything, so nothing that was "
             "working is lost -- and calls stop dying."],
            ["C. Repoint it at the live Zap",
             "Not yet. The live Zap writes to a monday.com board that has "
             "received nothing for a month. Wiring a call pipeline to a "
             "board nobody reads is work, not a fix."],
        ],
        [1.9 * inch, 4.1 * inch],
    ),
    para(
        "Step 16 was deleted and the Zap published. If anyone turns out to "
        "use that monday.com board, a replacement step can be added later "
        "pointing at <b>4hmkrz1</b> -- with its error handling set so it can "
        "never halt a call again."
    ),
    Spacer(1, 4),
    callout(
        "The part worth remembering",
        "A step whose only job is to notify something else was able to stop "
        "sellers' calls being processed. That is the real defect, and it is "
        "not specific to step 16: any new POST added to this Zap can do the "
        "same thing. Anything non-essential in the middle of a call pipeline "
        "needs to be unable to halt it.",
    ),
]

# ----------------------------------------------------------- what it cost

story += [
    para("What it cost", "h1"),
    bullets([
        "<b>Two calls on 5 November</b> lost steps 17 to 27 entirely.",
        "<b>Every call before that</b> hit the same error. The run halted "
        "each time; only the two on the 5th were traced.",
        "<b>Zapier tasks.</b> A failed step still counts. With the account "
        "moving to the 2,000-task plan, a step that fails on every call is "
        "allowance spent on nothing.",
        "<b>A month of noise.</b> Zap history carried a red error on every "
        "run, which is how a history page stops being read.",
    ]),
]

# ---------------------------------------------------------------- proof

story += [PageBreak(), para("The proof", "h1")]
story += [para("In the order the checks were made, on %s." % FIXED),
          Spacer(1, 8)]

story += shot(
    "z1-error",
    "<b>1. The failure.</b> Step 16, 5 November 14:11:50 Pacific. "
    "\"The app returned 'please unsubscribe me!'\" -- the reply a Zapier "
    "catch hook gives when its Zap is not live.",
    width=3.9,
)
story += shot(
    "z2-url",
    "<b>2. Where it was posting.</b> Hook <b>4hgbqo2</b>, carrying the "
    "compliance fields: section5, section5 detail, dnc, call type.",
    width=3.7,
)
story += shot(
    "z3-zap-list",
    "<b>3. Who owns that hook.</b> \"(Copy) Retell Monday AI\" -- toggle "
    "off. Opening it showed <b>Draft</b>: never published. The live "
    "\"Retell Monday AI\" below it is on, and answers a different hook, "
    "4hmkrz1.",
)
story += shot(
    "z4-zero-runs",
    "<b>4. The live Zap is not doing it instead.</b> Zero runs in 30 days. "
    "Nothing feeds 4hmkrz1 either, so no monday.com item or Sheets row has "
    "been created in at least a month.",
)
story += shot(
    "z5-after",
    "<b>5. After the fix.</b> Three consecutive runs of THB SELLER CALL "
    "ROUTING, all Successful, each through 24+ steps. Before, every run "
    "stopped at 16.",
)

build(
    "THB_Zap_Step16_Failure.pdf",
    "The Step 16 Failure",
    "Why two calls stopped halfway on 5 November, and what was done about it",
    story,
    "Twin Home Buyer  |  diagnosed and fixed %s" % FIXED,
)
print("built THB_Zap_Step16_Failure.pdf")
