# Architecture: Custom OM/AR -> RMCS Integration

## 1. Problem statement

OMG (homegrown order app) creates sales orders in Oracle Fusion Cloud Order
Management (OM). The business needs the AR invoice that results from a sales
order to split the financial obligation between:

- a **customer-responsible amount** (patient pay, copay, deductible), and
- an **insurance-responsible amount** (payer-responsible portion),

so that downstream financial systems can post and age them separately.

The only viable Oracle-native mechanism for this split is **OM price
components**. Price components generate distinct AR invoice lines under the
same OM order line, each carrying its own amount and a price-component
classifier (e.g. `LIST`, `CUSTOMER_PAY`, `INSURANCE_PAY`).

### Why the seeded RMCS integration breaks

The seeded DOO -> AR -> RMCS integration assumes a 1:1 relationship between an
OM order line and an AR invoice line. RMCS uses that AR invoice line as the
revenue source document, and it relies on receiving the original OM list price
as the input to its standalone selling price (SSP) and discount allocation
engine.

When price components split a single OM line into multiple AR lines:

- the **list price** is no longer carried unambiguously to RMCS;
- the AR lines that arrive in RMCS no longer match a unique performance
  obligation, breaking allocation;
- RMA flows back from AR can no longer be tied to a single commercial line.

The seeded `Import AutoInvoice` -> `Manage Customer Contract Sources` ->
`Identify Customer Contracts` -> `Allocate Transaction Price` pipeline rejects
the transformed structure or, worse, allocates incorrectly.

## 2. Solution overview

We decouple RMCS from AR. OM and AR become **external feeder systems** read by
this layer, which reconstructs an RMCS-compatible source document set and
loads it through the RMCS Source Document REST/FBDI import surface as if it
came from a non-Oracle system.

```
+---------+      +----------+      +----------------------+      +-------+
|   OM    | ---> |    AR    | ---> | custom_rmcs pipeline | ---> | RMCS  |
+---------+      +----------+      +----------------------+      +-------+
     |               |                       ^
     |               |                       |
     +------- lineage map (persisted) -------+
```

Key properties:

1. The **OM order line** (not the AR line) is the unit of revenue / performance
   obligation in RMCS.
2. Price-component splits are recorded but **collapsed** before reaching RMCS:
   the layer rebuilds a single RMCS source-document line per OM line and emits
   the customer/insurance split as *billing-only* metadata, not as separate
   performance obligations.
3. SSP and discount allocation are computed **outside** Oracle, against an
   externally managed SSP catalog, and the results are pushed to RMCS as
   pre-allocated source data so RMCS's own allocation engine does not need to
   run.
4. A persisted **lineage map** ties every AR line back to its originating OM
   line, which lets us correctly route RMAs and credits to the right
   performance obligation.

## 3. Pipeline stages

The pipeline is implemented in `custom_rmcs/pipeline.py` as a sequence of
pure transformations over canonical models. Each stage is independently
testable.

| # | Stage              | Input                              | Output                                  |
|---|--------------------|------------------------------------|-----------------------------------------|
| 1 | Ingest OM          | OM feeder adapter                  | `OMOrder` (with price components)       |
| 2 | Ingest AR          | AR feeder adapter                  | `ARInvoice` (split lines)               |
| 3 | Build lineage      | `OMOrder` + `ARInvoice`            | `LineageMap`                            |
| 4 | Collapse to OM line| AR lines + lineage                 | one revenue line per OM line            |
| 5 | Allocate SSP       | revenue lines + SSP catalog        | per-line allocated amounts              |
| 6 | Emit RMCS docs     | allocated revenue lines + lineage  | `RMCSSourceDocument`                    |
| 7 | Apply RMAs         | AR credit memos + lineage          | adjustments referencing original POBs   |

Stages 1-2 are pluggable behind interfaces in `custom_rmcs/feeders/`. Stages
3-7 are deterministic functions over the canonical models.

## 4. Lineage model

`LineageMap` stores, for each AR invoice line:

- `om_order_number`, `om_line_number` -- the original commercial line
- `price_component_code` -- e.g. `CUSTOMER_PAY`, `INSURANCE_PAY`
- `is_billing_split` -- True when the AR line exists solely because of the
  price-component split (i.e. it is **not** a separate performance obligation)
- `original_revenue_line_id` -- the synthetic RMCS line that represents the
  collapsed OM line

This is the single source of truth used by RMA and reallocation processing.

## 5. SSP and discount allocation

`custom_rmcs/allocation/` implements the **relative SSP** allocation method:

- An externally managed `SSPCatalog` returns the SSP for an item / item-class /
  effective date.
- For each contract (OM order), we compute the sum of SSPs and the actual
  transaction price (OM list price net of order-level discounts), then
  allocate the discount across performance obligations proportional to SSP.
- The output is `AllocatedRevenueLine` carrying both the allocated transaction
  price and the residual customer/insurance billing split (for traceability
  only -- not for revenue recognition).

This replaces RMCS's native allocation, which we cannot use because RMCS no
longer sees the original list price.

## 6. RMA / reallocation handling

When AR issues a credit memo against a split invoice line:

1. The credit memo is ingested by the AR feeder.
2. The lineage map resolves it back to the originating OM line / RMCS POB.
3. `custom_rmcs/rma/` emits a negative `RMCSSourceDocument` line against the
   original POB, preserving the contract identifier and performance obligation
   reference RMCS needs for proper reversal.
4. If the RMA changes the price (not just the quantity), allocation is rerun
   and the delta is emitted as a modification document.

## 7. Operational concerns

- **Idempotency**: every emitted RMCS document carries a deterministic
  `source_document_number` derived from `om_order_number` + `om_line_number`
  (+ revision for modifications). Replays do not create duplicates.
- **Reconciliation**: the lineage map is the basis for a daily reconciliation
  report that compares (sum of AR amounts) vs. (sum of RMCS revenue lines)
  per OM order.
- **Backfill**: stages 3-7 are pure and can be re-run over historical
  feeder data without side effects beyond updating the lineage store.

## 8. Out of scope (for this scaffold)

- Concrete Oracle Cloud REST / BICC / FBDI clients. The feeder interfaces are
  defined; in-memory implementations are provided for testing. Production
  adapters should be added in `custom_rmcs/feeders/oracle/`.
- Persistence backend for the lineage store. The reference implementation
  uses an in-memory dict; swap in a database-backed store for production.
- Authentication, retries, observability -- these belong in the runtime that
  hosts this library, not in the integration logic itself.
