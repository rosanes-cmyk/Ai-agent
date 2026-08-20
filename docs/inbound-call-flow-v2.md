# Twin Home Buyer — Inbound Call Flowchart v2.0

**Document:** Inbound Call Flow — Retell AI Conversation Flow build spec
**Supersedes:** Inbound Call Flowchart v1.0
**Build / Retell Implementation:** [CURRENT BUILDER]
**Approve:** Juan
**Status:** Draft for approval — items marked *PENDING CONFIRMATION* are not yet approved and must not be built as written.

> **Rule of this document:** a *Transfer Call* and a *Send Notification* are two different actions.
> **Gen** is a call-transfer destination. **Sabelli** is a notification / review recipient only.

---

## 0. What changed from v1.0

| # | Area | v1.0 | v2.0 |
|---|------|------|------|
| 1 | Realtor / Agent routing | Realtor → **Mariaelena** | Realtor → **GEN** (`X2`, endings `T9` / `T10`) |
| 2 | Sabelli | Treated as a person callers could be sent to | **Notification / escalation recipient only** on approved `T22` cases. No transfer node exists for Sabelli anywhere in the flow. |
| 3 | Legal / agency / mailer | Mixed into normal qualification | Isolated global hard-stop layer (`G-LEGAL`, `G-MAILER`) → `T22` notification to **Juan + Sabelli** |
| 4 | DNC | Handled ad hoc | Global node `G-DNC` → `T21`, sets `dnc_requested = true`, suppression process |
| 5 | Endings | Some branches unterminated | 24 named endings, every branch terminates |
| 6 | Build owner | Build: Seth | Build / Retell Implementation: **[CURRENT BUILDER]** |

**Retired ending IDs:** `T7` and `T8` were the v1.0 *Realtor → Mariaelena* endings (connected / message taken). They are retired and must not be rebuilt. The realtor branch now ends at `T9` / `T10`.

---

## 1. Legend

| Style | Meaning | Retell node type | Shape in diagrams |
|-------|---------|------------------|-------------------|
| **BLUE** | Conversation / action | Conversation node, Function node | rectangle |
| **DARK / BLACK** | Decision | Logic Split node | diamond |
| **GREEN** | Successful transfer / completed outcome | Transfer Call node, Ending node | subroutine / stadium |
| **YELLOW** | Notification / follow-up | Function node (webhook — no audio path) | hexagon |
| **RED** | Hard stop — legal / DNC / sensitive | Global node + Ending node | circle / stadium |
| **PURPLE** | Extract variable / data capture | Extract Dynamic Variables on a Conversation node | parallelogram |

**Edge styles — this distinction is load-bearing:**

- `──▶` **solid arrow** = the live call moves. Audio path. This is a *Transfer Call*.
- `--▶` **dashed arrow** = information moves, the call does not. This is a *Send Notification*.

Sabelli is only ever reached by a dashed arrow.

---

## 2. Master flow

### 2.1 Diagram A — Call arrival and intent routing

```mermaid
%%{init: {"theme":"base","themeVariables":{"fontFamily":"Archivo, ui-sans-serif, sans-serif","fontSize":"13px","lineColor":"#7E8896","textColor":"#7E8896","edgeLabelBackground":"transparent","primaryColor":"#1F6FB2","primaryTextColor":"#FFFFFF"},"flowchart":{"curve":"basis","nodeSpacing":38,"rankSpacing":52,"useMaxWidth":true}}}%%
flowchart TD
  A1["A1 · Call arrives on a Twin Home Buyer tracking number"]:::action
  V1[/"EXTRACT · source_channel, call_start_time, caller_id"/]:::extract
  Q1{"Q1 · Did a human team member answer within 3 rings?"}:::decision
  T1(["T1 · Human handled the call"]):::success
  A2["A2 · Mandatory AI opening — discloses AI assistant and call recording before any substantive conversation"]:::action
  Q2{"Q2 · Determine caller intent"}:::decision
  V2[/"EXTRACT · caller_intent, intent_attempts"/]:::extract
  SEL["Seller flow — Diagram B"]:::action
  GEN["Realtor flow to Gen — Diagram C"]:::action
  NON["Non-seller intake — Diagram D"]:::action
  Q7{"Q7 · Intent clear after 2 attempts?"}:::decision
  T20(["T20 · Spam or wrong number — polite end"]):::stop
  GH(("G-HUMAN")):::stop
  GLM(("G-LEGAL / G-MAILER")):::stop
  GD(("G-DNC")):::stop

  A1 --> V1 --> Q1
  Q1 -->|"YES"| T1
  Q1 -->|"NO or after hours"| A2
  A2 --> Q2 --> V2
  V2 -->|"1 New seller"| SEL
  V2 -->|"2 Seller callback"| SEL
  V2 -->|"3 Realtor or real estate agent"| GEN
  V2 -->|"4 Active contract or escrow"| NON
  V2 -->|"5 Title, escrow or lender"| NON
  V2 -->|"6 Past client"| NON
  V2 -->|"7 Buyer or investor"| NON
  V2 -->|"8 Vendor or subcontractor"| NON
  V2 -->|"9 Job applicant"| NON
  V2 -->|"10 Peninsula Plumbing caller"| NON
  V2 -->|"11 Spam or wrong number"| T20
  V2 -->|"12 Unclear caller"| Q7
  V2 -->|"13 Legal, agency or mailer"| GLM
  V2 -->|"14 DNC request"| GD
  Q7 -->|"YES · reclassify"| Q2
  Q7 -->|"NO · two failed attempts"| GH

  classDef action fill:#1F6FB2,stroke:#17578C,color:#FFFFFF
  classDef decision fill:#1C2530,stroke:#6B7787,color:#FFFFFF
  classDef success fill:#16785A,stroke:#0F5B45,color:#FFFFFF
  classDef notify fill:#A8730A,stroke:#835A07,color:#FFFFFF
  classDef stop fill:#A93529,stroke:#87281E,color:#FFFFFF
  classDef extract fill:#63459C,stroke:#4C3479,color:#FFFFFF
```

### 2.2 Diagram B — Seller flow

Only seller calls (`caller_intent = new_seller` or `seller_callback`) run the qualification conversation.

```mermaid
%%{init: {"theme":"base","themeVariables":{"fontFamily":"Archivo, ui-sans-serif, sans-serif","fontSize":"13px","lineColor":"#7E8896","textColor":"#7E8896","edgeLabelBackground":"transparent"},"flowchart":{"curve":"basis","nodeSpacing":38,"rankSpacing":52,"useMaxWidth":true}}}%%
flowchart TD
  IN["From Q2 · New seller"]:::action
  INB["From Q2 · Seller callback"]:::action
  S1[/"S1 · Full name → seller_name"/]:::extract
  S2[/"S2 · Property street address and city → property_address, property_city"/]:::extract
  S3[/"S3 · Reason or motivation for selling → seller_reason · no legal, financial or valuation statements"/]:::extract
  S4[/"S4 · Selling timeline → seller_timeline"/]:::extract
  S5[/"S5 · Property condition → property_condition · include only if approved for this build"/]:::extract
  S6[/"S6 · Callback number, repeated back to the caller → callback_number, callback_confirmed"/]:::extract
  SC1[/"SC1 · Confirm name and property already on file → seller_name, property_address"/]:::extract
  F1["F1 · Create or update the seller lead record"]:::action
  N1{{"N1 · NOTIFY Juan — new seller lead"}}:::notify
  Q3{"Q3 · Qualifies for a live seller transfer under the approved rules?"}:::decision
  Q4{"Q4 · Call is inside the approved transfer cutoff? — PENDING JUAN CONFIRMATION"}:::decision
  X1[["X1 · TRANSFER CALL → JUAN · warm transfer"]]:::success
  Q5{"Q5 · Did Juan answer?"}:::decision
  Q6{"Q6 · New seller or returning seller?"}:::decision
  N2{{"N2 · NOTIFY Juan — seller callback follow-up task"}}:::notify
  N3{{"N3 · NOTIFY Juan — after-hours appointment or callback request"}}:::notify
  T2(["T2 · Warm transfer connected — Juan owns the call"]):::success
  T3(["T3 · Seller captured, Juan unavailable — callback created"]):::notifyEnd
  T4(["T4 · After-hours seller appointment or callback logged"]):::notifyEnd
  T5(["T5 · Seller not transfer-qualified — lead logged for Juan"]):::notifyEnd
  T6(["T6 · Returning seller message logged for Juan"]):::notifyEnd
  T25(["T25 · Transfer system failure — information saved, owner and Juan notified"]):::notifyEnd

  IN --> S1 --> S2 --> S3 --> S4 --> S5 --> S6
  INB --> SC1 --> S6
  S6 --> F1 --> N1 --> Q3
  Q3 -->|"NO"| T5
  Q3 -->|"YES"| Q4
  Q4 -->|"NO · after cutoff"| N3 -.-> T4
  Q4 -->|"YES"| X1 --> Q5
  Q5 -->|"Juan answers"| T2
  Q5 -->|"No answer"| N2 -.-> Q6
  Q5 -->|"Line or routing failure"| T25
  Q6 -->|"New seller"| T3
  Q6 -->|"Returning seller"| T6

  classDef action fill:#1F6FB2,stroke:#17578C,color:#FFFFFF
  classDef decision fill:#1C2530,stroke:#6B7787,color:#FFFFFF
  classDef success fill:#16785A,stroke:#0F5B45,color:#FFFFFF
  classDef notify fill:#A8730A,stroke:#835A07,color:#FFFFFF
  classDef notifyEnd fill:#8C6208,stroke:#6B4B06,color:#FFFFFF
  classDef stop fill:#A93529,stroke:#87281E,color:#FFFFFF
  classDef extract fill:#63459C,stroke:#4C3479,color:#FFFFFF
```

**Notes on Diagram B**

- The transfer cutoff time is **PENDING JUAN CONFIRMATION**. Do not build a cutoff value until it is supplied.
- The live-transfer qualification test at `Q3` uses the approved Twin Home Buyer rules; the rule set itself is **PENDING JUAN CONFIRMATION**.
- `S5` (property condition) is built **only** if that field is approved for the Retell build. Otherwise the node is skipped and `property_condition` stays null.
- `N1` fires on every completed seller intake, whether or not a transfer happens, so no seller is ever captured without Juan being told.

### 2.3 Diagram C — Realtor / Agent → GEN (changed routing)

```mermaid
%%{init: {"theme":"base","themeVariables":{"fontFamily":"Archivo, ui-sans-serif, sans-serif","fontSize":"13px","lineColor":"#7E8896","textColor":"#7E8896","edgeLabelBackground":"transparent"},"flowchart":{"curve":"basis","nodeSpacing":38,"rankSpacing":52,"useMaxWidth":true}}}%%
flowchart TD
  IN["From Q2 · Realtor or real estate agent"]:::action
  R1[/"R1 · Name → caller_name"/]:::extract
  R2[/"R2 · Callback number, repeated back → callback_number, callback_confirmed"/]:::extract
  R3[/"R3 · Company or brokerage, only if naturally provided → caller_company"/]:::extract
  R4[/"R4 · One-line reason for the call → call_reason_line"/]:::extract
  F2["F2 · Create agent contact record · call_type = realtor_agent"]:::action
  Q8{"Q8 · Can Gen take the call right now?"}:::decision
  X2[["X2 · TRANSFER CALL → GEN"]]:::success
  Q9{"Q9 · Did Gen answer?"}:::decision
  T9(["T9 · Realtor / Agent → Gen · transfer connected"]):::success
  N4{{"N4 · NOTIFY GEN — realtor callback request with name, number, brokerage and reason"}}:::notify
  T10(["T10 · Realtor / Agent → Gen unavailable · information saved, Gen notified, call ended politely"]):::notifyEnd
  T25(["T25 · Transfer system failure — information saved, Gen and Juan notified"]):::notifyEnd

  IN --> R1 --> R2 --> R3 --> R4 --> F2 --> Q8
  Q8 -->|"YES"| X2 --> Q9
  Q8 -->|"NO or after hours"| N4
  Q9 -->|"Gen answers"| T9
  Q9 -->|"No answer"| N4
  Q9 -->|"Line or routing failure"| T25
  N4 -.-> T10

  classDef action fill:#1F6FB2,stroke:#17578C,color:#FFFFFF
  classDef decision fill:#1C2530,stroke:#6B7787,color:#FFFFFF
  classDef success fill:#16785A,stroke:#0F5B45,color:#FFFFFF
  classDef notify fill:#A8730A,stroke:#835A07,color:#FFFFFF
  classDef notifyEnd fill:#8C6208,stroke:#6B4B06,color:#FFFFFF
  classDef extract fill:#63459C,stroke:#4C3479,color:#FFFFFF
```

**Hard rules on this branch**

- Realtor / agent calls route to **GEN**. Not Mariaelena. Not Sabelli.
- No normal realtor notification goes to Sabelli.
- There is no edge of any kind from this branch to Sabelli.

### 2.4 Diagram D — Non-seller intake and routing

The AI does not attempt to answer substantive questions on these calls. It takes a message and routes.

Intake script: *"I'll get this to the right person. Can I get your name and the best number?"*

```mermaid
%%{init: {"theme":"base","themeVariables":{"fontFamily":"Archivo, ui-sans-serif, sans-serif","fontSize":"13px","lineColor":"#7E8896","textColor":"#7E8896","edgeLabelBackground":"transparent"},"flowchart":{"curve":"basis","nodeSpacing":30,"rankSpacing":50,"useMaxWidth":true}}}%%
flowchart TD
  IN["From Q2 · categories 4 to 10"]:::action
  A3["A3 · Simple intake — I'll get this to the right person. Can I get your name and the best number?"]:::action
  V3[/"EXTRACT · caller_name, callback_number, call_reason_line, call_type"/]:::extract
  Q10{"Q10 · Route on call_type"}:::decision

  Q11{"Q11 · Is Juan available for a live transfer?"}:::decision
  X3[["X3 · TRANSFER CALL → JUAN · active contract or escrow"]]:::success
  T11(["T11 · Active contract / escrow → Juan connected"]):::success
  N5{{"N5 · NOTIFY Juan — active deal message, time sensitive"}}:::notify
  T12(["T12 · Active contract / escrow message logged for Juan"]):::notifyEnd

  Q12{"Q12 · Is Juan available for a live transfer?"}:::decision
  X4[["X4 · TRANSFER CALL → JUAN · title, escrow or lender"]]:::success
  T13(["T13 · Title / escrow / lender → Juan connected"]):::success
  N6{{"N6 · NOTIFY Juan — title, escrow or lender message"}}:::notify
  T14(["T14 · Title / escrow / lender message logged for Juan"]):::notifyEnd

  N7{{"N7 · NOTIFY past-client follow-up owner — PENDING CONFIRMATION"}}:::notify
  T15(["T15 · Past client message routed to follow-up owner"]):::notifyEnd
  N8{{"N8 · NOTIFY buyer and investor owner — PENDING CONFIRMATION"}}:::notify
  T16(["T16 · Buyer / investor message routed to owner"]):::notifyEnd
  N9{{"N9 · NOTIFY vendor and subcontractor owner — PENDING CONFIRMATION"}}:::notify
  T17(["T17 · Vendor / subcontractor message routed to owner"]):::notifyEnd
  N10{{"N10 · NOTIFY recruiting — PENDING CONFIRMATION of recipient"}}:::notify
  T18(["T18 · Job applicant routed to recruiting"]):::notifyEnd
  A5["A5 · Peninsula Plumbing intake only — never convert to a Twin Home Buyer seller lead"]:::action
  N11{{"N11 · NOTIFY Peninsula Plumbing intake — plumbing log only"}}:::notify
  T25D(["T25 · Transfer system failure — information saved, owner and Juan notified"]):::notifyEnd
  T19(["T19 · Peninsula Plumbing message handled as plumbing only"]):::notifyEnd

  IN --> A3 --> V3 --> Q10
  Q10 -->|"active_contract_escrow"| Q11
  Q11 -->|"YES"| X3 --> T11
  Q11 -->|"NO"| N5 -.-> T12
  Q10 -->|"title_escrow_lender"| Q12
  Q12 -->|"YES"| X4 --> T13
  Q12 -->|"NO"| N6 -.-> T14
  Q10 -->|"past_client"| N7 -.-> T15
  Q10 -->|"buyer_investor"| N8 -.-> T16
  Q10 -->|"vendor_subcontractor"| N9 -.-> T17
  Q10 -->|"job_applicant"| N10 -.-> T18
  Q10 -->|"peninsula_plumbing"| A5 --> N11 -.-> T19
  X3 -->|"line or routing failure"| T25D
  X4 -->|"line or routing failure"| T25D

  classDef action fill:#1F6FB2,stroke:#17578C,color:#FFFFFF
  classDef decision fill:#1C2530,stroke:#6B7787,color:#FFFFFF
  classDef success fill:#16785A,stroke:#0F5B45,color:#FFFFFF
  classDef notify fill:#A8730A,stroke:#835A07,color:#FFFFFF
  classDef notifyEnd fill:#8C6208,stroke:#6B4B06,color:#FFFFFF
  classDef extract fill:#63459C,stroke:#4C3479,color:#FFFFFF
```

### 2.5 Diagram E — Global hard-stop layer

These four global nodes can interrupt the conversation from **any** node. A hard stop overrides the seller and non-seller flows.

```mermaid
%%{init: {"theme":"base","themeVariables":{"fontFamily":"Archivo, ui-sans-serif, sans-serif","fontSize":"13px","lineColor":"#7E8896","textColor":"#7E8896","edgeLabelBackground":"transparent"},"flowchart":{"curve":"basis","nodeSpacing":34,"rankSpacing":50,"useMaxWidth":true}}}%%
flowchart TD
  ANY["Any conversation node · A2, S1 to S6, SC1, R1 to R4, A3, A5"]:::action
  GD(("G-DNC · take me off your list, stop calling me, do not contact me")):::stop
  GL(("G-LEGAL · attorney, lawyer, lawsuit, subpoena, legal threat, regulator, investigator, agency")):::stop
  GM(("G-MAILER · mailer, letter, check, postcard, how did you get my address, marketing complaint")):::stop
  GH(("G-HUMAN · asks for a human, hostile, or not understood after two attempts")):::stop
  HS2["HS2 · DNC acknowledgment in approved wording · stop all qualification"]:::action
  V5[/"EXTRACT · dnc_requested = true"/]:::extract
  N13{{"N13 · NOTIFY suppression process and compliance owner"}}:::notify
  T21(["T21 · DNC honored · no transfer, no further qualification"]):::stop
  HS1["HS1 · Stop qualification. Capture the approved minimum only. Do not explain the mailer, defend the company, confirm or deny anything, speculate, or improvise"]:::action
  V4[/"EXTRACT · hard_stop_type, hard_stop_reference, legal_party_name, agency_name"/]:::extract
  F3["F3 · Preserve transcript and recording · transcript_id"]:::action
  N14{{"N14 · NOTIFY and ESCALATE → JUAN plus SABELLI · review recipients only, no call transfer"}}:::notify
  T22(["T22 · Legal / agency / mailer sensitive escalation · no transfer occurred"]):::stop
  Q13{"Q13 · Is an approved human available right now?"}:::decision
  X5[["X5 · TRANSFER CALL → on-call human · destination PENDING CONFIRMATION"]]:::success
  T23(["T23 · Human escalation connected"]):::success
  N12{{"N12 · NOTIFY human escalation callback queue"}}:::notify
  T24(["T24 · Human escalation callback logged"]):::notifyEnd

  ANY --> GD
  ANY --> GL
  ANY --> GM
  ANY --> GH
  GD --> HS2 --> V5 --> N13 -.-> T21
  GL --> HS1
  GM --> HS1
  HS1 --> V4 --> F3 --> N14 -.-> T22
  GH --> Q13
  Q13 -->|"YES"| X5 --> T23
  Q13 -->|"NO"| N12 -.-> T24
  X5 -->|"no answer or line failure"| N12

  classDef action fill:#1F6FB2,stroke:#17578C,color:#FFFFFF
  classDef decision fill:#1C2530,stroke:#6B7787,color:#FFFFFF
  classDef success fill:#16785A,stroke:#0F5B45,color:#FFFFFF
  classDef notify fill:#A8730A,stroke:#835A07,color:#FFFFFF
  classDef notifyEnd fill:#8C6208,stroke:#6B4B06,color:#FFFFFF
  classDef stop fill:#A93529,stroke:#87281E,color:#FFFFFF
  classDef extract fill:#63459C,stroke:#4C3479,color:#FFFFFF
```

**Sabelli rule.** `N14` is a notification. The call does not move. There is no `Transfer to Sabelli` node in this build, and none may be added. Sabelli appears exactly once in the flow, as a review recipient on `T22`.

**Proposed hard-stop precedence** — *PENDING JUAN CONFIRMATION*: `G-DNC` → `G-LEGAL` → `G-MAILER` → `G-HUMAN` → normal flow. If a caller both requests DNC and raises a legal or mailer matter, the proposal is to honor the DNC (`T21`) **and** send the `T22` notification, recording both endings. Do not build the combination rule until it is confirmed.

---

## 3. Retell node map

| Flow node | Retell node type | Purpose | Exits |
|---|---|---|---|
| `A1` | Call start / inbound trigger | Entry on a tracking number | `V1` |
| `V1` | Extract Dynamic Variables | `source_channel`, `call_start_time`, `caller_id` | `Q1` |
| `Q1` | Logic Split | Human answered within 3 rings | `T1`, `A2` |
| `A2` | Conversation | Mandatory AI + recording disclosure | `Q2` |
| `Q2` | Logic Split (14-way) | Intent classification | `V2` |
| `V2` | Extract Dynamic Variables | `caller_intent`, `intent_attempts` | seller / realtor / non-seller / stops |
| `S1`–`S6`, `SC1` | Conversation + Extract | Seller qualification capture | next in sequence |
| `F1` | Function | Create or update seller lead | `N1` |
| `N1`–`N14` | Function (webhook) | Send notification — **no audio path** | ending |
| `Q3`–`Q13` | Logic Split | Routing and availability tests | per diagram |
| `X1`–`X5` | Transfer Call | Move the live call | ending or failure branch |
| `R1`–`R4` | Conversation + Extract | Realtor capture | `F2` |
| `F2` | Function | Create agent contact record | `Q8` |
| `A3` | Conversation | Non-seller simple intake | `V3` |
| `V3` | Extract Dynamic Variables | `caller_name`, `callback_number`, `call_reason_line`, `call_type` | `Q10` |
| `A5` | Conversation | Peninsula Plumbing intake only | `N11` |
| `G-LEGAL`, `G-MAILER`, `G-DNC`, `G-HUMAN` | Global node | Interrupt from anywhere | `HS1`, `HS2`, `Q13` |
| `HS1`, `HS2` | Conversation | Constrained hard-stop scripts | `V4`, `V5` |
| `F3` | Function | Preserve transcript and recording | `N14` |
| `T1`–`T26` | Ending node | Terminal disposition | — |

---

## 4. Conversation nodes

| ID | Name | Notes |
|---|---|---|
| `A1` | Call arrives | Stores `source_channel` |
| `A2` | Mandatory AI opening | AI disclosure + recording disclosure before any substantive conversation. Approved Twin Home Buyer opening text — **PENDING CONFIRMATION** of final wording. |
| `A3` | Non-seller simple intake | "I'll get this to the right person. Can I get your name and the best number?" |
| `A5` | Peninsula Plumbing intake | Plumbing only. Never converts to a seller lead. |
| `S1`–`S6` | Seller qualification prompts | See Diagram B |
| `SC1` | Returning-seller confirmation | Confirms name and property already on file |
| `R1`–`R4` | Realtor capture prompts | Name, number, brokerage, one-line reason |
| `HS1` | Hard-stop minimum capture | No explanation, defense, confirmation, denial or speculation |
| `HS2` | DNC acknowledgment | Approved wording — **PENDING CONFIRMATION** |
| `F1` | Create or update seller lead | Function node |
| `F2` | Create agent contact record | Function node |
| `F3` | Preserve transcript and recording | Function node |

## 5. Decision nodes

| ID | Question | Exits |
|---|---|---|
| `Q1` | Did a human answer within 3 rings? | YES → `T1` · NO / after hours → `A2` |
| `Q2` | Which of the 14 caller intents? | 14 exits |
| `Q3` | Qualifies for a live seller transfer? | YES → `Q4` · NO → `T5` |
| `Q4` | Inside the approved transfer cutoff? *(cutoff PENDING JUAN CONFIRMATION)* | YES → `X1` · NO → `N3` |
| `Q5` | Did Juan answer the warm transfer? | Answered → `T2` · No answer → `N2` · Failure → `T25` |
| `Q6` | New seller or returning seller? | `T3` / `T6` |
| `Q7` | Intent clear after 2 attempts? | YES → `Q2` · NO → `G-HUMAN` |
| `Q8` | Can Gen take the call now? | YES → `X2` · NO → `N4` |
| `Q9` | Did Gen answer? | Answered → `T9` · No answer → `N4` · Failure → `T25` |
| `Q10` | Route on `call_type` | 7 exits |
| `Q11` | Juan available — active contract or escrow? | YES → `X3` · NO → `N5` |
| `Q12` | Juan available — title, escrow or lender? | YES → `X4` · NO → `N6` |
| `Q13` | Approved human available now? | YES → `X5` · NO → `N12` |

## 6. Global nodes

| ID | Trigger phrases and conditions | Action | Ending |
|---|---|---|---|
| `G-LEGAL` | Attorney, lawyer, lawsuit, subpoena, legal threat, regulator, investigator, government or consumer-protection agency | Stop qualification → `HS1` | `T22` |
| `G-MAILER` | Mailer, letter, check, postcard, "how did you get my address", complaint about previous marketing correspondence | Stop qualification → `HS1` | `T22` |
| `G-DNC` | "Take me off your list", "stop calling me", "do not contact me" or equivalent | Stop conversation → `HS2`, set `dnc_requested = true` | `T21` |
| `G-HUMAN` | Explicit request for a human, hostile caller, or not understood after two attempts | Stop qualification → `Q13` | `T23` / `T24` |

Each global node is reachable from `A2`, `S1`–`S6`, `SC1`, `R1`–`R4`, `A3` and `A5`.

## 7. Transfer Call nodes

Every entry here moves the live call. There are five, and none of them is Sabelli.

| ID | Destination | Trigger | Success | Failure |
|---|---|---|---|---|
| `X1` | **Juan** | Qualified seller inside the cutoff | `T2` | `N2` → `T3` / `T6`, or `T25` |
| `X2` | **GEN** | Realtor or real estate agent | `T9` | `N4` → `T10`, or `T25` |
| `X3` | **Juan** | Active contract or escrow | `T11` | `N5` → `T12` |
| `X4` | **Juan** | Title, escrow or lender | `T13` | `N6` → `T14` |
| `X5` | **On-call human** — *PENDING CONFIRMATION* | Human requested or hostile caller | `T23` | `N12` → `T24` |

A `X6` transfer to a Peninsula Plumbing line is **PENDING CONFIRMATION**; until a number is approved, plumbing calls take a message only (`T19`).

## 8. Notification nodes

Every entry here sends information. None of them moves the call.

| ID | Recipient | Content | Fires at |
|---|---|---|---|
| `N1` | Juan | New seller lead, all captured fields | Every completed seller intake |
| `N2` | Juan | Seller callback follow-up task | Warm transfer not answered |
| `N3` | Juan | After-hours seller appointment or callback | Outside the transfer cutoff |
| `N4` | **Gen** | Realtor callback request — name, number, brokerage, reason | Gen unavailable or no answer |
| `N5` | Juan | Active deal message, time sensitive | Juan unavailable |
| `N6` | Juan | Title, escrow or lender message | Juan unavailable |
| `N7` | Past-client follow-up owner — *PENDING* | Past-client message | Always |
| `N8` | Buyer / investor owner — *PENDING* | Buyer or investor message | Always |
| `N9` | Vendor / subcontractor owner — *PENDING* | Vendor message | Always |
| `N10` | Recruiting — *PENDING* | Applicant name, number, role interest | Always |
| `N11` | Peninsula Plumbing intake | Plumbing message, plumbing log only | Always |
| `N12` | Human escalation queue | Hostile or human-requested callback | No human available |
| `N13` | Suppression process + compliance owner — *PENDING* | DNC request | On `G-DNC` |
| `N14` | **Juan + Sabelli** | Sensitive legal / agency / mailer escalation with transcript and recording | On `G-LEGAL` or `G-MAILER` |

`N14` is the only notification Sabelli receives, and it is a review notification, not a transfer.

## 9. Extract variables

| Variable | Captured at | Required | Notes |
|---|---|---|---|
| `source_channel` | `V1` | yes | Tracking number the call arrived on |
| `call_start_time` | `V1` | yes | Used by the cutoff test at `Q4` |
| `caller_id` | `V1` | yes | Inbound number |
| `human_answered` | `Q1` | yes | Drives `T1` |
| `caller_intent` | `V2` | yes | One of the 14 categories |
| `intent_attempts` | `V2` | yes | Two failures route to `G-HUMAN` |
| `seller_name` | `S1` / `SC1` | yes for sellers | |
| `property_address` | `S2` / `SC1` | yes for sellers | Street address |
| `property_city` | `S2` | yes for sellers | |
| `seller_reason` | `S3` | yes for sellers | Motivation, captured verbatim |
| `seller_timeline` | `S4` | yes for sellers | |
| `property_condition` | `S5` | conditional | Only if this field is approved for the build |
| `callback_number` | `S6` / `R2` / `V3` | yes | |
| `callback_confirmed` | `S6` / `R2` | yes | Set true only after the number is repeated back |
| `caller_name` | `R1` / `V3` | yes for non-sellers | |
| `caller_company` | `R3` | optional | Brokerage, only if naturally provided |
| `call_reason_line` | `R4` / `V3` | yes for non-sellers | One line, no interpretation |
| `call_type` | `V3` | yes for non-sellers | Routing key at `Q10` |
| `transfer_attempted` | `X1`–`X5` | system | |
| `transfer_result` | `X1`–`X5` | system | `connected`, `no_answer`, `failed` |
| `dnc_requested` | `V5` | on `G-DNC` | Set `true`, triggers suppression |
| `hard_stop_type` | `V4` | on hard stop | `legal`, `agency`, `mailer` |
| `hard_stop_reference` | `V4` | on hard stop | Mailer, letter, check or postcard reference if the caller offers one |
| `legal_party_name` | `V4` | on legal stop | Attorney, firm or caller name |
| `agency_name` | `V4` | on agency stop | |
| `transcript_id` | `F3` | on hard stop | Preserved transcript and recording |
| `hostile_flag` | `G-HUMAN` | conditional | |
| `plumbing_issue_summary` | `A5` | for plumbing calls | Plumbing log only |
| `applicant_role_interest` | `A3` | for applicants | |

## 10. Ending nodes

| ID | What happened | Owner | Notification | Transfer | CRM action | Follow-up |
|---|---|---|---|---|---|---|
| `T1` | Human answered within 3 rings | Answering team member | No | No — human answered directly | Logged by the team member per existing process | Owned by whoever answered |
| `T2` | Qualified seller warm-transferred and connected | Juan | Lead summary to Juan | **Yes → Juan** | Seller lead with all `S1`–`S6` fields | Juan owns from the transfer forward |
| `T3` | Seller captured, Juan did not answer | Juan | `N1` + `N2` | Attempted, not connected | Seller lead, `transfer_result = no_answer` | Callback task for Juan — SLA *PENDING* |
| `T4` | Seller call outside the transfer cutoff | Juan | `N1` + `N3` | No | Seller lead, after-hours flag | Approved after-hours appointment or callback process — *PENDING* |
| `T5` | Seller did not meet the live-transfer rules | Juan | `N1` | No | Seller lead, `transfer_eligible = false` | Juan reviews the lead |
| `T6` | Returning seller, message taken | Juan | `N1` + `N2` | Attempted or skipped | Appended to the existing lead | Juan callback |
| `T9` | **Realtor / agent transferred to Gen and connected** | **Gen** | Contact record to Gen | **Yes → Gen** | Agent contact with reason | Gen owns the call |
| `T10` | Realtor / agent — Gen unavailable | **Gen** | `N4` | No, or attempted and not connected | Agent contact saved | Gen callback — SLA *PENDING* |
| `T11` | Active contract / escrow connected to Juan | Juan | Message summary | **Yes → Juan** | Attached to the deal record | Juan |
| `T12` | Active contract / escrow message taken | Juan | `N5` | Attempted, not connected | Attached to the deal record, time-sensitive flag | Juan same business day — *PENDING* |
| `T13` | Title / escrow / lender connected to Juan | Juan | Message summary | **Yes → Juan** | Attached to the relevant file | Juan |
| `T14` | Title / escrow / lender message taken | Juan | `N6` | Attempted, not connected | Attached to the relevant file | Juan |
| `T15` | Past client message routed | Follow-up owner — *PENDING* | `N7` | No | Past-client record updated | Owner callback — *PENDING* |
| `T16` | Buyer / investor message routed | Buyer-investor owner — *PENDING* | `N8` | No | Buyer list record | Owner callback — *PENDING* |
| `T17` | Vendor / subcontractor message routed | Internal owner — *PENDING* | `N9` | No | Vendor record | Owner callback — *PENDING* |
| `T18` | Job applicant routed to recruiting | Recruiting — *PENDING* | `N10` | No | Applicant record | Recruiting process |
| `T19` | Peninsula Plumbing call handled as plumbing | Peninsula Plumbing | `N11` | No — transfer line *PENDING* | Plumbing log only. **Never** the Twin Home Buyer seller pipeline | Plumbing process |
| `T20` | Spam or wrong number | None | No | No | Disposition `spam_wrong_number` | None. Optionally add to the screening list |
| `T21` | **DNC honored** | Compliance owner — *PENDING* | `N13` | **No** | `dnc_requested = true`, suppress across all marketing lists | Confirm suppression applied within the approved window — *PENDING* |
| `T22` | **Legal / agency / mailer sensitive escalation** | Juan | `N14` → **Juan + Sabelli** with transcript | **No — and no transfer to Sabelli exists** | Restricted sensitive-matter record | Juan and Sabelli review. Caller told someone will follow up — wording *PENDING* |
| `T23` | Human escalation connected | On-call human — *PENDING* | Call summary | **Yes → on-call human** | Call note | Human owns the call |
| `T24` | Human escalation callback logged — includes unclear callers after two attempts | On-call human — *PENDING* | `N12` | No | Call note with partial capture | Human callback — SLA *PENDING* |
| `T25` | Transfer failed technically — line or routing error | Intended destination + Juan | Notification to the intended owner and Juan | Attempted, failed | Full capture saved, `transfer_result = failed` | Callback by the intended owner |
| `T26` | Caller disconnected mid-flow | Depends on capture | Only if seller, realtor or hard-stop content was captured | No | Partial capture saved with `call_incomplete = true` | Callback if a confirmed number exists |

**How `T26` is reached.** `T26` has no incoming edge in the diagrams by design. It is wired to Retell's call-ended / caller-hung-up event on every conversation node, so a dropped call always lands on a named disposition instead of vanishing.

**Retired:** `T7`, `T8` — the v1.0 *Realtor → Mariaelena* endings. Do not rebuild.

---

## 11. Pending confirmation

Nothing in this list may be built as a guess. Each needs Juan's or Cherry's sign-off first.

| # | Item | Needed from | Blocks |
|---|---|---|---|
| 1 | **Seller transfer cutoff time** and the after-hours boundary | Juan | `Q4`, `T4` |
| 2 | **Seller live-transfer qualification rules** — what makes a seller transfer-worthy | Juan | `Q3`, `T5` |
| 3 | Whether **`S5` property condition** is approved for this build | Juan | `S5` |
| 4 | Approved **AI opening wording** (`A2`) | Juan / Cherry | `A2` |
| 5 | Gen's **transfer number and availability hours** | Juan / Gen | `X2`, `Q8` |
| 6 | **Past-client** follow-up owner | Juan | `N7`, `T15` |
| 7 | **Buyer / investor** owner | Juan | `N8`, `T16` |
| 8 | **Vendor / subcontractor** owner | Juan | `N9`, `T17` |
| 9 | **Recruiting** notification recipient | Juan / Cherry | `N10`, `T18` |
| 10 | Whether Peninsula Plumbing calls may be **transferred** to a plumbing line, or message-only | Juan | `X6`, `T19` |
| 11 | **On-call human** destination and hours for escalation | Juan | `X5`, `Q13`, `T23` |
| 12 | **DNC suppression** administrator and confirmation window | Juan / Cherry | `N13`, `T21` |
| 13 | Approved **caller-facing wording** for `HS1`, `HS2` and the `T22` close | Juan / Cherry | `HS1`, `HS2`, `T22` |
| 14 | **Hard-stop precedence** and the DNC-plus-legal combination rule | Juan | Global layer |
| 15 | **Callback SLAs** for `T3`, `T10`, `T12`, `T24` | Juan | Follow-up tasks |
| 16 | Notification channel — SMS, email or CRM task — per recipient | Juan | All `N` nodes |
| 17 | Name of the **[CURRENT BUILDER]** for the title block | Juan | Document header |
