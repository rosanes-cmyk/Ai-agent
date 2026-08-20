# Twin Home Buyer — AI Agent

Build reference for the Twin Home Buyer Retell AI inbound voice agent.

## Phase 1 — build and approve this first

| File | What it is |
|---|---|
| [`docs/twin-home-buyer-phase1-seller-flow.svg`](docs/twin-home-buyer-phase1-seller-flow.svg) | **Phase 1 seller flow.** New Seller + Seller Callback only. |
| `docs/twin-home-buyer-phase1-seller-flow.html` | Same chart, zoomable. |
| `docs/twin-home-buyer-phase1-seller-flow.pdf` | Same chart, one sheet for printing. |

Cherry reviews Phase 1 before the rest of the Retell system is built. The rules that matter most:

- The **Google Chat live alert** to Juan and Cherry fires the moment the caller is classified, and it
  **never pauses the AI conversation**.
- **A claim does not interrupt the call.** If Juan or Cherry sends TRANSFER while the seller is
  talking, it becomes a *pending* transfer. The AI finishes the answer, completes the required
  intake, and only then makes the handoff statement.
- **Nobody claims → callback.** The AI never sits silently waiting.

## Full inbound map — v2.1

| File | What it is |
|---|---|
| [`docs/twin-home-buyer-call-flow-v2.1.svg`](docs/twin-home-buyer-call-flow-v2.1.svg) | **The flowchart.** One large sheet, the build map for Retell AI Conversation Flow. |
| `docs/twin-home-buyer-call-flow-v2.1.html` | Same chart as a zoomable page. |
| `docs/Twin-Home-Buyer-Call-Flow-v2.1.pdf` | Same chart, one 22 × 30.8 in sheet for printing. |
| `docs/Twin-Home-Buyer-Call-Flow-v2.1.png` | Same chart as an image. |

Status: **Updated Build Map** · Build / Retell implementation: **Rosanes** · Approval: **Juan**

## The rules that govern the build

1. **A Transfer Call moves the live caller. A Send Notification moves information only.**
   Solid arrows are transfers; dashed arrows are email / webhook / Zapier notifications.
2. **Realtor and real estate agent calls transfer to GEN.** This replaces the v1.0 routing.
3. **Live transfer destinations are Juan and Gen only.** Juan takes qualified sellers, seller
   callbacks where appropriate, active contract / escrow, and title / escrow / lender.
4. **Legal, agency and mailer hard stops send `N14` — an email notification to the Twin Home
   Buyer team: Cherry, Bryan, Thea, MC.** No live call transfers from that node.
5. **`H4` — never give a price, offer, home value or valuation.** A caller asking for one is routed
   into the approved seller → Juan transfer / callback process.
6. **`H6` — a plumbing caller who mentions selling stays a plumbing caller.** Never convert the call
   into a Twin Home Buyer seller lead; it ends at `T19`.
7. **A caller who is a minor** stops seller qualification and goes to human escalation (`G-HUMAN`).
8. Anything marked **PENDING CONFIRMATION** is not approved and must not be built as a guess.

## Superseded

`docs/inbound-call-flow-v2.*` is the earlier v2.0 draft, kept for history only. Its routing and
notification recipients are **void** — build from v2.1.
