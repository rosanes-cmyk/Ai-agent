# Twin Home Buyer — AI Agent

Build reference for the Twin Home Buyer Retell AI inbound voice agent.

## Current deliverable — v2.1

| File | What it is |
|---|---|
| [`docs/twin-home-buyer-call-flow-v2.1.svg`](docs/twin-home-buyer-call-flow-v2.1.svg) | **The flowchart.** One large sheet, the build map for Retell AI Conversation Flow. |
| `docs/twin-home-buyer-call-flow-v2.1.html` | Same chart as a zoomable page. |
| `docs/Twin-Home-Buyer-Call-Flow-v2.1.pdf` | Same chart, one 22 × 30.8 in sheet for printing. |
| `docs/Twin-Home-Buyer-Call-Flow-v2.1.png` | Same chart as an image. |

Status: **Updated Build Map** · Build / Retell implementation: **Current Builder** · Approval: **Juan**

## The rules that govern the build

1. **A Transfer Call moves the live caller. A Send Notification moves information only.**
   Solid arrows are transfers; dashed arrows are email / webhook / Zapier notifications.
2. **Realtor and real estate agent calls transfer to GEN.** This replaces the v1.0 routing.
3. **Live transfer destinations are Juan and Gen only.** Juan takes qualified sellers, seller
   callbacks where appropriate, active contract / escrow, and title / escrow / lender.
4. **Legal, agency and mailer hard stops send `N14` — an email notification to the Twin Home
   Buyer team: Cherry, Bryan, Thea, MC.** No live call transfers from that node.
5. Anything marked **PENDING CONFIRMATION** is not approved and must not be built as a guess.

## Superseded

`docs/inbound-call-flow-v2.*` is the earlier v2.0 draft, kept for history only. Its routing and
notification recipients are **void** — build from v2.1.
