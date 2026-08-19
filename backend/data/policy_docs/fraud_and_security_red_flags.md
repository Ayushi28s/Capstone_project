# Fraud & Security Red Flags (Support Reference)

## Why this exists
CommerceOps AI's refund-anomaly check automatically flags a customer submitting several
refund requests just under the $250 auto-approval threshold in a short window — but that's
one specific pattern the system catches on its own. This document covers what a human
reviewer should watch for beyond what's automated, since not every fraud pattern is
something a threshold check can catch.

## Patterns worth a second look
- **New account, unusually large first order.** A brand-new account placing an order well
  above typical first-purchase value, especially with expedited shipping, is a common
  stolen-card pattern.
- **Shipping and billing address mismatch**, particularly when the shipping address is a
  freight-forwarder or a different city/state than the billing address with no prior order
  history explaining it (e.g. a gift).
- **Refund requested to a different payment method** than the original charge. Legitimate
  refunds go back to the original payment method — a request to redirect a refund elsewhere
  is a hard stop, escalate immediately, do not process.
- **Rapid sequential orders from the same new account**, each just under a value that would
  trigger manual review, mirroring the same "stay under the threshold" logic the automated
  refund-anomaly check watches for, just applied to purchases instead of refunds.
- **A customer who can't answer basic order-verification questions** (approximate order
  date, what was ordered, delivery address) but insists on an immediate refund or address
  change — a legitimate customer usually has at least partial recall.

## What to do when something looks off
Do not accuse a customer of fraud directly, and do not process the request while
uncertain. Escalate per the Employee Escalation Procedures — the fraud-suspicion path
specifically routes to the on-duty manager and Finance the same day, regardless of dollar
amount. Document exactly what looked unusual; a specific observation ("shipping address is
a known freight-forwarder city, billing address is unrelated") is far more useful to
whoever reviews it than a general "this felt off."

## What this is not
This is not a replacement for the system's automated checks, and it's not a license to
delay or deny a legitimate customer over an unusual-but-explainable pattern (a customer
shipping a gift to a different address, for example). The goal is a second, human layer of
judgment on top of the automated one — not suspicion by default.
