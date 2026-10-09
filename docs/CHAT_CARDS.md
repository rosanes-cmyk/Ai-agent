# Google Chat cards — the Voice AI Listener

Every card below is printed by running the live code in `deploy/main.py`,
not transcribed by hand. Generated 9 October 2026.

The four other cards your team sees — the LIVE SELLER CALL card, CALL
ANSWERED BY A TEAM MEMBER, CALLBACK NEEDED and the legal escalation — are
built in Zapier, so their wording lives in the Zap editor and cannot be
printed from here.

## 1. LIVE CALL CLAIMED

**Fires when:** a rep types ME in the thread

```
🟡 *LIVE CALL CLAIMED — CONNECTING*

🙋 *Claimed By:* Cherry
🔄 *Status:* Transferring to Cherry now

🏷️ *Lead Source:* PPC
👤 *Name:* Seth Oilveros
📞 *Phone:* +15103945339
🏠 *Property:* 123 Main St, Los Angeles
📋 *Caller Type:* Seller
📝 *Reason:* Relocating
⏱️ *Timeline:* 30 days
💰 *Asking Price:* $450,000

🤖 Voice AI Agent will finish the seller's current response and make a natural handoff to Cherry.

Ref: call_0dac97bc1e7e
```

## 2. TRANSFERRED

**Fires when:** the transfer connected (disconnection_reason = call_transfer)

```
🟢 *TRANSFERRED — CHERRY IS ON THE CALL*

The seller is speaking with Cherry now.
The Voice AI has left the call.

Booked a property visit? Reply with the day and time:
Sep 2, 2pm
Nothing booked? Ignore this.

Ref: call_0dac97bc1e7e
```

## 3. TRANSFER DID NOT CONNECT

**Fires when:** claimed, but the seller was never put through

```
⚠️ *TRANSFER DID NOT CONNECT*

Cherry claimed this call, but the seller was never put through.
📞 *Call them back:* +15103945339
📋 *Ended by:* user_hangup

Nobody else can claim this call now — ring the seller yourself.
<users/all>

Ref: call_0dac97bc1e7e
```

## 4. NOW SPEAKING SPANISH

**Fires when:** the AI could not understand two answers in a row

```
🇪🇸 *NOW SPEAKING SPANISH*

The seller could not carry on in English.
Handed to the Spanish AI — the call is still live.

A Spanish speaker should take this one.
📞 Reply "ME" to claim.

<users/all>

Ref: call_0dac97bc1e7e
```

## 5. AFTER HOURS

**Fires when:** a call arrives outside 8am-5pm, or any time Sunday

*The time below reads 10:00 AM only because the sample was rendered during
the shift. In use it carries the real out-of-hours time.*

```
🌙 *AFTER HOURS — HANDING TO THE ANSWERING SERVICE*

A seller called outside the 8-5 shift.
The Voice AI is passing them to a live answering service now.

📞 *Caller:* +15103945339
🕑 *Time:* 10:00 AM on Friday

No action needed now — the message reaches you in the morning.
```

## 6. PROPERTY VISIT BOOKED

**Fires when:** a rep replies in the thread with a day and time

*"Sep 2" renders as 9/2/**2027** because September 2nd 2026 has already
passed and the parser takes the next one. The example in the prompt above
is inherited from the Zapier card -- typed literally, it books a year out.*

```
✅ *PROPERTY VISIT BOOKED*

👤 Seth Oilveros
📅 9/2/2027 at 2:00 PM
🏠 123 Main St, Los Angeles
🚗 Assigned: Juan

Sent to Property Visit — calendar event follows.
```

## 7. STILL NEED

**Fires when:** the booking reply is missing the day or the time

```
⚠️ Still need the time.
Reply with the time only, e.g. *2pm*
```

## 8. NO APPOINTMENT

**Fires when:** a rep says there is no appointment from this call

```
✅ Noted — no appointment from this call.
```
