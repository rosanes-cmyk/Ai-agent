# Twin Home Buyer — AI Agent

Specifications for the Twin Home Buyer Retell AI voice agent.

## Documents

| Document | Purpose |
|---|---|
| [`docs/inbound-call-flow-v2.md`](docs/inbound-call-flow-v2.md) | Inbound Call Flowchart **v2.0** — the build spec for Retell AI Conversation Flow. Diagrams, node registries, extract variables, endings, and open approvals. |
| `docs/inbound-call-flow-v2.html` | The same spec as a shareable visual page. |

## Two rules that govern the build

1. **Realtor and agent calls transfer to GEN.** Not Mariaelena (retired in v2.0), not Sabelli.
2. **A Transfer Call and a Send Notification are different actions.** Sabelli is a notification and
   review recipient on approved legal, agency and mailer escalations (`T22`) only. No transfer node
   for Sabelli exists in the build.

Anything marked **PENDING CONFIRMATION** is not approved and must not be built as written.
Build / Retell implementation: **[CURRENT BUILDER]** · Approve: **Juan**
