# Pi management UI — superseded

The 6 October deferral is superseded by the locked plan [PUBLISHING_PIPELINE_PLAN.md](PUBLISHING_PIPELINE_PLAN.md). The UI is built and tested (7 October 2026) and awaits the owner-approved installation; see [PI_UI.md](PI_UI.md).

Every item of the original scope is implemented: batch browsing and import with validation, previews, hashes and storage; America/New_York (or any explicit zone) schedule preview with DST and UTC; owner-reviewed cadence and finite schedule approval; published links, token health, quota budgets, exhausted content and blocked jobs; pause and uncertain-job reconciliation without duplicate publication. Credentials stay server-side; access is the existing tailnet-only Tailscale Serve plus a mandatory passcode.
