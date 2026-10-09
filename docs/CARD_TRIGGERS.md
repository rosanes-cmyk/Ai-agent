# Exactly when each card fires

Every condition below is read from `deploy/main.py`. A card appears only when
**all** of its conditions hold; the "stays silent when" column is the list of
ways it does not appear, each of which is a real thing that has happened.

Generated 9 October 2026.

---

## 1. LIVE CALL CLAIMED

A Google Chat message arrives, and **all** of these are true:

| # | Condition | Fails when |
|---|---|---|
| 1 | sender is not a bot and not anonymous | the card's own app replies |
| 2 | message text, lowercased with punctuation stripped, is an **exact** match in the claim list | "ok ill take it" -- not in the list, close is not enough |
| 3 | it is **not** in the refusal list, which is checked first | `no`, `busy`, `wait` |
| 4 | the sender's Chat user id is on the `CLAIMANTS` roster | a new hire nobody added |
| 5 | a call is mapped to that thread and was mapped **120 seconds ago or less** | the rep read the card four minutes later |
| 6 | that call is not already claimed -- **first claim wins** | somebody beat them to it |
| 7 | Retell accepts the claim push | `RETELL_API_KEY` missing or rejected |

Condition 5 is the one that surprises people. **Two minutes, not "while the call
is live."** A seller can still be talking at 3 minutes and the claim will not
take.

Condition 4 fails silently for the person typing: they see their own message in
the thread and nothing else happens.

---

## 2. TRANSFERRED

A POST arrives with `action = transfer_complete`, and:

| # | Condition | Fails when |
|---|---|---|
| 1 | `call_id` is present | the Zapier field is unmapped |
| 2 | that `call_id` is in the claimed list | nobody claimed -- **silent on purpose**, the AI finishing a call is not news |
| 3 | `disconnection_reason` is **exactly** `call_transfer` | anything else gives card 3 instead |
| 4 | the claim recorded a thread | a claim made before this field existed |

Fires once, then forgets the call -- so a duplicate POST posts nothing.

---

## 3. TRANSFER DID NOT CONNECT

Identical to card 2 except condition 3 is inverted: `disconnection_reason` is
anything **other** than `call_transfer` -- `user_hangup`, `dial_failed`, an
error, or missing entirely.

This is the card that exists because a failed transfer used to look exactly
like a successful one.

---

## 4. NOW SPEAKING SPANISH

A POST arrives with `action = language_switch`, and:

| # | Condition | Fails when |
|---|---|---|
| 1 | `call_id` is present | -- |
| 2 | a card was mapped in that space **300 seconds ago or less** | a slow handover |

Condition 2 is deliberate. Retell logs the Spanish leg as a brand new call
carrying nothing that links it to the first, so the two are matched on time
alone. Past 5 minutes it posts **nothing** rather than hang a Spanish notice
under an unrelated seller's card.

---

## 5. AFTER HOURS

Retell's inbound webhook arrives and the office clock says closed. Closed means
**any** of:

- the day is in `OFFICE_CLOSED_DAYS` -- Sunday by default
- the hour is before `OFFICE_OPENS_HOUR` (8)
- the hour is `OFFICE_CLOSES_HOUR` (17) or later

Pacific time, decided by the listener, not by the AI.

---

## 6. PROPERTY VISIT BOOKED

A Chat message arrives in a thread that **has been marked as answered**, and:

| # | Condition | Fails when |
|---|---|---|
| 1 | the thread was marked within **24 hours** | a reply to yesterday's card |
| 2 | the text yields **both** a day and a time | "Sep 2" alone gives card 7 |
| 3 | it is not a no-appointment phrase | gives card 8 |
| 4 | the save succeeds | gives card 9 |

**A thread is marked only two ways:** Zapier sends `action = answered_call`
after a rep answers the ring group, or a transfer connects (card 2). On any
other thread a date is simply ignored.

---

## 7. STILL NEED

Same thread conditions as card 6, but the text gives only one of the two.
Three versions: missing the time, missing the day, or missing both.

---

## 8. NO APPOINTMENT

Same thread conditions, and the text is an exact match in the no-appointment
list.

Note `no` is in **both** this list and the refusal list for claims. Which one
applies depends on whether the thread is a live call or an answered one.

---

## 9. COULD NOT SAVE

Day and time both read correctly, but writing the booking failed. Carries what
it understood so a human can enter it by hand.

---

## The exact phrase lists

Matching is exact after lowercasing, stripping punctuation and collapsing
spaces. `O.K.` becomes `ok`; `10-4` becomes `104`.

**Claim (107):** `104`, `absolutely`, `affirmative`, `agreed`, `aight`, `aiight`, `all right`, `alright`, `aok`, `approved`, `available`, `available now`, `bet`, `certainly`, `claim`, `claim call`, `claim it`, `claim the call`, `confirmed`, `connect me`, `connect me now`, `copy`, `copy that`, `correct`, `definitely`, `do it`, `do it now`, `fine`, `fo sho`, `for sure`, `forsure`, `free now`, `go`, `go ahead`, `go for it`, `got it`, `i am available`, `i am free`, `i am ready`, `i can take it`, `i can take the call`, `i got it`, `i have it`, `i will take it`, `i will take the call`, `igh`, `ight`, `ill take it`, `ill take the call`, `im available`, `im free`, `im ready`, `ive got it`, `k`, `kay`, `kk`, `lets do it`, `lets do this`, `lets go`, `me`, `mine`, `mkay`, `no problem`, `no worries`, `of course`, `ok`, `okay`, `okey`, `okeydoke`, `okeydokey`, `okie`, `okiedokie`, `proceed`, `proceed now`, `put it through`, `put them through`, `ready`, `ready now`, `roger`, `roger that`, `send it`, `send it over`, `send it to me`, `send me the call`, `sure`, `sure thing`, `take it`, `take the call`, `transfer`, `transfer it`, `transfer me`, `transfer the call`, `transfer to me`, `understood`, `word`, `ya`, `yah`, `yea`, `yeah`, `yep`, `yes`, `yes please`, `yess`, `yesss`, `you bet`, `you got it`, `yup`

**Refusal, checked first (50):** `busy`, `call later`, `cannot`, `cannot take it`, `cannot take the call`, `cant`, `cant take it`, `cant take the call`, `do it later`, `do not send it`, `do not send it to me`, `do not transfer`, `do not transfer to me`, `dont send it`, `dont send it to me`, `dont transfer`, `dont transfer to me`, `give it to someone else`, `hold`, `hold on`, `i am busy`, `i am not sure`, `i am unavailable`, `i cannot`, `i cant`, `im busy`, `im not sure`, `im unavailable`, `later`, `maybe`, `maybe later`, `maybe next time`, `nah`, `naw`, `negative`, `no`, `nope`, `not me`, `not mine`, `not now`, `not sure`, `one moment`, `send it to someone else`, `someone else`, `unavailable`, `wait`, `wait a minute`, `wait a sec`, `wait a second`, `wait please`

**No appointment (15):** `did not book`, `didnt book`, `n a`, `na`, `nada`, `no`, `no appointment`, `no appointment set`, `no appt`, `no booking`, `none`, `nope`, `not booked`, `nothing`, `wala`

---

## Who may claim

The built-in roster is **Barbie Adorable, David Romero, Diego Villa, Era Miraflor**.

Setting the `CLAIMANTS` environment variable **replaces this list entirely**
rather than adding to it, so the live roster is whatever is set in Cloud Run.
Check there before concluding somebody is missing.

A roster entry with no phone number claims successfully and then the transfer
fails -- the log says `CLAIMANT_PHONE_MISSING` and names them.
