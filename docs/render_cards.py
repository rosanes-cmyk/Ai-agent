import sys, json, io, urllib.request
sys.path.insert(0, "/workspace/Ai-agent/deploy")
import main

posted = []

class FakeResp:
    status = 200
    def read(self): return b'{"thread":{"name":"spaces/AAA/threads/BBB"},"name":"spaces/AAA/messages/X"}'
    def __enter__(self): return self
    def __exit__(self, *a): return False

def fake_urlopen(req, *a, **k):
    try:
        body = json.loads((req.data or b"{}").decode())
    except Exception:
        body = {}
    if "text" in body:
        posted.append(body["text"])
    return FakeResp()

urllib.request.urlopen = fake_urlopen
main.send_booking_to_intake = lambda f: True
main.send_claim_to_sheet = lambda *a, **k: True

main.GOOGLE_CHAT_WEBHOOK_URL = "https://chat.example/hook"
main.CHAT_WEBHOOK_OTHER_LEADS = "https://chat.example/hook"
try:
    main.CHAT_WEBHOOKS = {main.OTHER_LEADS_SPACE: "https://chat.example/hook"}
except Exception:
    pass
main.get_chat_webhook = lambda space=None: "https://chat.example/hook"

class Req:
    method = "POST"
    def __init__(self, p): self._p = p
    def get_json(self, silent=False): return self._p
    args = {}

CALL, THREAD, SPACE = "call_0dac97bc1e7e", "spaces/AAA/threads/BBB", "spaces/AAA"
SELLER = {"phone": "+15103945339", "name": "Seth Oilveros", "lead_source": "PPC",
          "property": "123 Main St, Los Angeles", "caller_type": "Seller",
          "reason": "Relocating", "timeline": "30 days", "asking_price": "$450,000"}

out = []
def grab(title, note):
    if posted:
        out.append((title, note, posted[-1]))
    posted.clear()

def claim():
    main.CALL_DATA[CALL] = dict(SELLER)
    main.CLAIMED_CALLS[CALL] = {"claimed_by": "Cherry", "claimed_at": 0, "sender_id": "u1",
                                "claim_text": "me", "space": SPACE, "thread_id": THREAD}
    main.ANSWERED_THREADS.clear()

# 1 claimed
claim()
main.send_claimed_notification(CALL, "Cherry", SPACE)
grab("LIVE CALL CLAIMED", "a rep types ME in the thread")

# 2 transferred
claim()
main.hello_http(Req({"action": "transfer_complete", "call_id": CALL,
                     "disconnection_reason": "call_transfer"}))
grab("TRANSFERRED", "the transfer connected (disconnection_reason = call_transfer)")

# 3 failed
claim()
main.hello_http(Req({"action": "transfer_complete", "call_id": CALL,
                     "disconnection_reason": "user_hangup"}))
grab("TRANSFER DID NOT CONNECT", "claimed, but the seller was never put through")

# 4 spanish
main.LATEST_CALLS[main.space_from_resource(SPACE)] = {"thread_id": THREAD, "call_id": CALL,
                                             "mapped_at": __import__("time").time()}
main.hello_http(Req({"action": "language_switch", "call_id": CALL, "language": "Spanish",
                     "space": SPACE}))
grab("NOW SPEAKING SPANISH", "the AI could not understand two answers in a row")

# 5 after hours
main.send_after_hours_notice(main.office_clock(), "+15103945339")
grab("AFTER HOURS", "a call arrives outside 8am-5pm, or any time Sunday")

def reply(text):
    main.hello_http(Req({"type": "MESSAGE", "message": {
        "text": text, "sender": {"name": "users/123", "type": "HUMAN"},
        "thread": {"name": THREAD}}}))

# 6 booked
claim(); main.hello_http(Req({"action": "transfer_complete", "call_id": CALL,
                              "disconnection_reason": "call_transfer"})); posted.clear()
reply("Sep 2, 2pm")
grab("PROPERTY VISIT BOOKED", "a rep replies in the thread with a day and time")

# 7 still need
claim(); main.hello_http(Req({"action": "transfer_complete", "call_id": CALL,
                              "disconnection_reason": "call_transfer"})); posted.clear()
reply("Sep 2")
grab("STILL NEED", "the booking reply is missing the day or the time")

# 8 no appointment
claim(); main.hello_http(Req({"action": "transfer_complete", "call_id": CALL,
                              "disconnection_reason": "call_transfer"})); posted.clear()
reply("no appointment")
grab("NO APPOINTMENT", "a rep says there is no appointment from this call")

doc = ["# Google Chat cards — the Voice AI Listener", "",
       "Every card below is printed by running the live code in `deploy/main.py`,",
       "not transcribed by hand. Generated 9 October 2026.", "",
       "The four other cards your team sees — the LIVE SELLER CALL card, CALL",
       "ANSWERED BY A TEAM MEMBER, CALLBACK NEEDED and the legal escalation — are",
       "built in Zapier, so their wording lives in the Zap editor and cannot be",
       "printed from here.", ""]
for i, (title, note, body) in enumerate(out, 1):
    doc += [f"## {i}. {title}", "", f"**Fires when:** {note}", "", "```", body, "```", ""]

io.open("CHAT_CARDS.md", "w", encoding="utf-8").write("\n".join(doc))
print(f"rendered {len(out)} cards")
for t, _, _ in out: print("  -", t)
