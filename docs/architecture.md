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

We decouple RMCS from AR. OM and AR become **external feeder systems**
extracted by **Oracle Integration Cloud (OIC)**. OIC hands the raw extracts
to this layer, which reconstructs an RMCS-compatible source document set and
emits a **file-based FBDI** ZIP. OIC then uploads the ZIP to **UCM** and
invokes the *Import Customer Contract Source Data* ESS job, so RMCS sees the
data as if it came from a non-Oracle source system.

```
+---------+    +----------+         +------ OIC orchestration ------+        +------+
|   OM    | -> |    AR    |  --->   |  extract -> custom_rmcs lib   |  --->  | UCM  |
+---------+    +----------+         |  -> FBDI ZIP -> UCM upload    |        +------+
   |               |                |  -> Import ESS job submit     |            |
   |   AR DFFs     |                +-------------------------------+            v
   | (omOrderNum,  |                              ^                          +------+
   |  omLineNum,   |    integration               |                          | RMCS |
   |  priceCompCode)|   load-state journal --------+                         +------+
   +-+    +--------+   (PENDING/LOADED/REJECTED, run_id)
     +----+
     SoR for OM<->AR<->RMCS relationship
```

Note: there is **no separate lineage store**. The OM <-> AR relationship
is read from AR DFFs on every run; the integration only persists *its
own* load state in the load-state journal.

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
| 1 | Ingest OM          | OM feeder adapter (OIC extract)    | `OMOrder` (with price components)       |
| 2 | Ingest AR          | AR feeder adapter (OIC extract)    | `ARInvoice` (split lines, with DFFs)    |
| 3 | Collapse to OM line| AR lines (read OM ref from DFFs)   | one revenue line per OM line            |
| 4 | Allocate SSP       | revenue lines + SSP catalog        | per-line allocated amounts              |
| 5 | Emit FBDI          | allocated revenue lines            | RMCS FBDI CSVs + control file in a ZIP  |
| 6 | Apply RMAs         | AR credit memos (read OM ref DFFs) | adjustment rows in the same FBDI batch  |
| 7 | Record state       | emitted POB lines + run_id         | `PENDING` rows in load-state journal     |
| 8 | Apply ESS feedback | OIC post-job callback              | journal entries -> LOADED / REJECTED    |

Stages 1-2 are pluggable behind interfaces in `custom_rmcs/feeders/`.
Stages 3-7 are deterministic functions over the canonical models. Stage 5
is implemented in `custom_rmcs/fbdi/`. Stage 8 is implemented by OIC
calling `LoadStateJournal.record_load_result()` after the ESS job
completes.

### Where OIC fits

OIC owns everything *outside* this library:

- **Inbound**: OIC integrations call OM and AR BICC extract jobs (or REST
  endpoints for incremental deltas), pick up the resulting files from UCM,
  and stage them as JSON for this library to consume. The shape of that JSON
  is defined by `custom_rmcs/feeders/json_feeder.py` and is intentionally a
  thin denormalization of the BICC/REST output.
- **Outbound**: OIC takes the FBDI ZIP produced by stage 6, uploads it to UCM
  through the UCM adapter, then submits the `Import Customer Contract Source
  Data` ESS job through the ERP Cloud adapter. It polls the job to terminal
  state and pulls the import error report.
- **Reconciliation**: OIC posts the job results back to this library so the
  load-state journal can mark each emitted POB line as `LOADED`,
  `REJECTED`, or `PARTIAL`, with the OIC run id and any error text from
  the import error report.

## 4. Where state lives

The integration deliberately keeps two concerns separate:

### 4a. OM <-> AR <-> RMCS relationship: AR DFFs (system of record)

Every AR invoice line and credit-memo line carries DFFs populated by
Autoinvoice from the originating OM line:

- `omOrderNumber`
- `omLineNumber`
- `priceComponentCode` (e.g. `LIST`, `CUSTOMER_PAY`, `INSURANCE_PAY`)

These are read on every pipeline run. There is no derived lineage index;
the deterministic identifier function `revenue_line_id(om_order, om_line)`
produces the same RMCS POB line id every time, so idempotency does not
require a stored map.

### 4b. Integration load state: load-state journal

A small, narrow store recording the result of each emitted POB line:

- `(source_document_number, source_document_line_number)` -- key
- `om_order_number`, `om_line_number` -- denormalized for reporting
- `state` -- `PENDING` / `LOADED` / `REJECTED` / `PARTIAL`
- `last_run_id` -- the OIC run id that emitted (or last touched) the row
- `last_error` -- error text from the FBDI import error report
- `loaded_at` -- ISO timestamp when the row went `LOADED`

The journal is implemented in `custom_rmcs/state/`. The reference impl is
JSON file backed; production should swap in a database-backed
implementation by subclassing `LoadStateJournal`. The journal is what
the daily reconciliation report and the period-close exception list are
built from -- and nothing else.

This separation prevents a custom store from drifting from AR's
authoritative relationship data and keeps the integration's blast radius
limited to its own operational state.

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
2. Each credit-memo line carries the same OM-ref DFFs as the originating
   AR invoice line. `custom_rmcs/rma/` reads them directly and routes the
   credit to the corresponding RMCS POB via `revenue_line_id(om_order,
   om_line)`.
3. `custom_rmcs/rma/` emits a negative `RMCSAdjustmentDocument` line
   against the original POB, preserving the contract identifier and
   performance-obligation reference RMCS needs for proper reversal.
4. If the RMA changes the price (not just the quantity), allocation is
   rerun and the delta is emitted as a modification document.

## 7. Operational concerns

- **Idempotency**: every emitted RMCS document carries a deterministic
  `source_document_number` derived from the OM order number (+ revision
  for modifications). Replays do not create duplicates; `LOADED` journal
  entries are preserved across re-emits (`REJECTED` entries are reset to
  `PENDING` so corrective re-emits can be re-attempted).
- **Reconciliation**: the load-state journal joined to the AR feed is the
  basis for a daily reconciliation report that compares (sum of AR
  amounts) vs. (sum of RMCS allocated amounts) per OM order.
- **Backfill**: stages 3-6 are pure and can be re-run over historical
  feeder data without side effects beyond updating the journal.

## 8. FBDI emission (stage 6)

The RMCS *Import Customer Contract Source Data* FBDI template is a workbook
that, when prepared, produces a small set of CSV files plus a control file,
zipped together. The relevant interface tables are:

- `VRM_SOURCE_DOCUMENTS_INT`  -- one row per source document header
- `VRM_SOURCE_DOC_LINES_INT`  -- one row per performance obligation
- `VRM_SOURCE_DOC_SUB_LINES_INT` -- optional, used when a line has sub-lines
- `VRM_SRC_DOC_BILL_PLANS_INT`, `VRM_SRC_DOC_REV_PLANS_INT` -- billing /
  revenue plans when applicable

The exact column lists in these CSVs are versioned by Oracle release. We
keep them in `custom_rmcs/fbdi/schema.py` as ordered tuples so they are
easy to diff against the current template export.

The emitter writes:

```
out/rmcs_fbdi.zip
  VRM_SOURCE_DOCUMENTS_INT.csv
  VRM_SOURCE_DOC_LINES_INT.csv
  VRM_SOURCE_DOC_SUB_LINES_INT.csv
  VrmExtImportTemplate.properties  (control / load-request metadata)
```

The ZIP path is returned to OIC, which performs the UCM upload and ESS
submission.

## 9. Out of scope (for this scaffold)

- Concrete Oracle Cloud REST / BICC clients. OIC owns the actual extracts;
  this library consumes the OIC-staged JSON. A reference JSON shape is
  documented in `custom_rmcs/feeders/json_feeder.py`.
- The UCM upload and ESS job submission. Those are OIC integration steps,
  not Python code.
- Persistence backend for the load-state journal. The reference
  implementation uses a JSON file; swap in a database-backed store for
  production by subclassing `LoadStateJournal`.
- Authentication, retries, observability -- these belong in OIC and in the
  runtime that hosts this library, not in the integration logic itself.
