# Cross Platform AI Evidence

Volume IX-7 completes the AI Test Engineer baseline with a stable, immutable evidence card for
CarSystemUI and future dashboard consumers. Clients read ATEP projections rather than querying AI
tables directly.

## Projection sources

The service derives a card from one persisted analysis execution, log analysis, test suggestion,
root-cause risk analysis, or grounded chat exchange. It copies only the originating subject,
status, severity, an allowlisted headline, a summary of at most 1,000 characters, and up to 20
unique citations. A chat exchange can be projected only by its conversation owner.

Every projection declares `ai-evidence-v1`. New snapshots may be created when a mutable source such
as a reviewed suggestion changes state; existing snapshots remain immutable and replay-safe.

## Client boundary

`GET /api/v1/ai/evidence-projections` requires a `consumer` of `carsystemui` or `dashboard` and
supports optional subject type, subject identifier, and severity filters. The detail endpoint uses
the same response contract. Both require `ai_analysis:read`.

Creating a projection requires `ai_analysis:manage`. The operation cannot alter its source and the
API exposes no update or delete route. The projection contains no original request context,
instructions, raw logs, signal collections, candidate steps, questions, or vehicle commands.

Audit and outbox records contain projection and source identifiers, subject, status, severity,
citation count, consumer, and contract version. Summary text and citation values are excluded.

## API

- `POST /api/v1/ai/evidence-projections`
- `GET /api/v1/ai/evidence-projections?consumer=carsystemui`
- `GET /api/v1/ai/evidence-projections?consumer=dashboard`
- `GET /api/v1/ai/evidence-projections/{projection_id}`

The feature uses deterministic local transformations. It requires no model, API key, cloud
account, paid service, network inference, or GPU.
