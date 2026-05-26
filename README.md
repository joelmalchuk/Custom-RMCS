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

- Treats OM and AR as **external feeder systems**, extracted by Oracle
  Integration Cloud (OIC).
- Reconstructs RMCS-compatible source documents from the split AR lines using
  the OM line as the unit of revenue.
- Reads the OM <-> AR relationship directly from **AR DFFs** populated by
  Autoinvoice (`omOrderNumber`, `omLineNumber`, `priceComponentCode`); AR
  is the system of record. The integration does not maintain a separate
  lineage store.
- Persists only its own **load state** in a narrow journal (PENDING /
  LOADED / REJECTED / PARTIAL) tagged with the OIC run id, used for
  reconciliation and period-close exceptions.
- Provides externally managed **SSP** and **discount allocation** logic that
  RMCS imports as pre-allocated source data.
- Emits the output as **file-based FBDI** (CSV + control files, packaged as a
  ZIP) for the RMCS *Import Customer Contract Source Data* import process.

## Transport: OIC + FBDI

This library is the transformation core. The runtime around it is OIC:

1. An OIC orchestration extracts OM and AR data (BICC extracts and/or REST).
2. OIC posts the extracts (as JSON) to this library, either by invoking the
   CLI in a function step or by calling an HTTP service that wraps it.
3. The library produces an RMCS FBDI ZIP at the path specified by OIC.
4. OIC uploads the ZIP to **UCM** and invokes the ERP Cloud *Import Customer
   Contract Source Data* ESS job via the ERP Cloud adapter.
5. OIC polls the ESS job for completion, fetches the error report, and
   feeds reconciliation back to this library's lineage store.

See:

- [`docs/functional-solution-design.md`](docs/functional-solution-design.md)
  -- functional view for Controllership / Revenue Accounting / Audit.
- [`docs/architecture.md`](docs/architecture.md) -- technical design.

## Project layout

```
custom_rmcs/
  models/         # canonical data structures (OM, AR, RMCS)
  feeders/        # OM and AR feeder adapters (consume OIC extracts)
  identifiers.py  # deterministic source-doc / revenue-line id functions
  state/          # load-state journal (PENDING / LOADED / REJECTED / PARTIAL)
  transform/      # rebuild RMCS source documents from AR (DFFs)
  allocation/     # SSP catalog + relative-SSP discount reallocation
  rma/            # RMA reconstruction against original commercial lines
  fbdi/           # FBDI CSV writer + ZIP packager for RMCS import
  pipeline.py     # orchestrator that wires the stages together
  __main__.py     # CLI entrypoint OIC invokes
tests/            # pytest suite covering the key business scenarios
docs/             # architecture and operational documentation
examples/         # OIC-staged extract samples + per-scenario walkthroughs
```

## Quick start

Requires Python 3.10+.

```bash
pip install -e ".[dev]"
pytest
```

## CLI

```bash
python -m custom_rmcs \
    --om-extract ./extracts/om.json \
    --ar-extract ./extracts/ar.json \
    --ssp-catalog ./extracts/ssp.json \
    --state-journal ./state/load_state.json \
    --out ./out/rmcs_fbdi.zip \
    --run-id "$OIC_RUN_ID"
```

The CLI is what an OIC integration calls from a function/SSH step; everything
about the actual Oracle transport (UCM upload, ESS job submission) lives in
OIC, not here. After the FBDI ESS job completes, OIC calls back into this
library via `LoadStateJournal.record_load_result()` to flip journal entries
to `LOADED` / `REJECTED` / `PARTIAL`.

## Examples

Two scenarios live in [`examples/`](examples/README.md):

- `single_line_split/` -- one OM line with a customer/insurance split.
- `multi_line_with_discount/` -- three OM lines with line-level discount
  where AR per-line invoiced amounts diverge from RMCS revenue (the
  textbook relative-SSP allocation case).

## Status

Scaffold + reference implementation with JSON-file feeders that match what an
OIC BICC/REST extract step would dump. The FBDI CSV schema is configurable
because Oracle revises template columns between releases — adjust
`custom_rmcs/fbdi/schema.py` to your tenant's current template before
go-live.
