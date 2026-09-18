# dracara-billing

The plan catalog and `entitlements()` — the one function that turns an
`organization_subscriptions` row into "may this organization write, which plan features does
it have, how many seats".

It is a package for the same reason `packages/scoring` is: two processes need the answer. The
API enforces it on every write (`deps.plan_gate`) and reports it to the UI (`GET /billing`);
the worker needs it so scheduled AI jobs skip organizations whose plan does not include AI. Two
copies of these rules would drift, and a worker that disagreed with the API about who has AI
would quietly spend tokens on organizations that are not paying for them.

Pure: no settings, no I/O. Mapping a plan to its Dodo Payments product id is configuration and
stays in `apps/api/app/services/billing.py`.

```
-e ../../packages/billing
```
