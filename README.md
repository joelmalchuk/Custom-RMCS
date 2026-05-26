# Custom-RMCS

A custom integration layer that decouples Oracle Fusion Cloud Order Management
(OM) and Oracle Fusion Cloud Receivables (AR) from Oracle Revenue Management
Cloud Service (RMCS), so that an OM "price component" split of customer- vs.
insurance-responsible amounts can flow through to AR without breaking RMCS's
discount allocation, reallocation, and RMA processing.

## Why this exists

The business uses a homegrown order management application (OMG) to create
sales orders in Oracle OM. Accounting requires that the AR invoice for a single
commercial order line be split between the portion the customer pays and the
portion the insurer pays, so downstream financial systems can recognize the two
as distinct obligations. The only viable mechanism inside Oracle OM is **price
components**, which generate separate AR invoice lines for each component.

Once the price-component approach is used:

1. RMCS no longer receives the original OM list price required for native
   standalone selling price (SSP) allocation.
2. The seeded DOO -> AR -> RMCS integration job rejects the transformed
   invoice structure because it loses the 1:1 OM line to AR line relationship
   that the seeded source-document mapping assumes.
3. RMA and reallocation flows can no longer be tied back to the original
   commercial OM line through Oracle's seeded lineage.

This project replaces the seeded AR -> RMCS integration with a custom pipeline
that:

- Treats OM and AR as **external feeder systems**.
- Reconstructs RMCS-compatible source documents from the split AR lines using
  the OM line as the unit of revenue.
- Maintains an explicit **line lineage map** so that RMAs and reallocations
  reference the original commercial line, not the split AR lines.
- Provides externally managed **SSP** and **discount allocation** logic that
  RMCS imports as pre-allocated source data.

See [`docs/architecture.md`](docs/architecture.md) for the full design.

## Project layout

```
custom_rmcs/
  models/         # canonical data structures (OM, AR, RMCS, lineage)
  feeders/        # OM and AR feeder adapters (read-only ingestion)
  lineage/        # OM-line <-> AR-line lineage tracking
  transform/      # rebuild RMCS source documents from AR + lineage
  allocation/     # SSP catalog + discount reallocation
  rma/            # RMA reconstruction against original commercial lines
  pipeline.py     # orchestrator that wires the stages together
tests/            # pytest suite covering the key business scenarios
docs/             # architecture and operational documentation
```

## Quick start

Requires Python 3.10+.

```bash
pip install -e ".[dev]"
pytest
```

## Status

Scaffold + reference implementation with in-memory feeder adapters. Concrete
Oracle Cloud REST / BICC adapters are stubbed; replace them with real clients
before going to production.
