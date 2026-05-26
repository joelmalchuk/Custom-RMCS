# Functional Solution Design: Custom OM/AR -> RMCS Integration

| | |
|---|---|
| **Document type** | Functional Solution Design (FSD) |
| **Status** | Draft for review |
| **Audience** | Controllership, Revenue Accounting, IT Apps, Internal Audit, Oracle implementation partner |
| **Related** | `docs/architecture.md` (technical design), code under `custom_rmcs/` |

---

## 1. Purpose

This document describes, at a functional level, how the business will record
sales orders that have a customer-responsible portion and an insurance-
responsible portion such that:

1. The commercial sales order in Oracle Fusion Cloud Order Management (OM)
   remains intact (one order, one line per item, one list price).
2. The AR invoice produced from that order **separates** the customer-pay
   and insurance-pay amounts onto distinct invoice lines so accounting and
   downstream financial systems can post, age, and collect them
   independently.
3. Revenue in Oracle Revenue Management Cloud Service (RMCS) is still
   recognized against the **original commercial line** as a single
   performance obligation, with externally computed standalone selling
   price (SSP) and discount allocation.
4. Returns (RMAs), credit memos, and contract modifications flow back to
   the same performance obligation in RMCS regardless of which AR line
   they were issued against.

## 2. Business problem

The business uses a homegrown order management application (OMG) to drop
sales orders into Oracle OM. Accounting requires that the AR invoice for
each order be split between the patient/customer-responsible amount and
the payer/insurance-responsible amount. The only Oracle-native way to
achieve this is to attach **price components** to the OM order line. That
mechanism is fit for purpose on the AR side -- but it breaks the seeded
OM -> AR -> RMCS revenue integration in three ways:

| # | Break point                                                                                       | Functional consequence                                                |
|---|---------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| 1 | RMCS no longer receives the original list price; it only sees the split AR amounts                | Native SSP / discount allocation cannot run                           |
| 2 | The seeded source-document mapping in RMCS assumes one AR line per OM line                        | The transformed AR data is rejected or mis-allocated by the seeded job |
| 3 | RMAs and credit memos hit a single price component (e.g. CUSTOMER_PAY) rather than the OM line     | Reversals lose lineage to the original performance obligation         |

## 3. Solution at a glance

The seeded AR -> RMCS integration is replaced with a custom integration
layer, built on **Oracle Integration Cloud (OIC)**, that treats OM and AR
as external feeder systems and loads RMCS using a **file-based FBDI**
import. The OM commercial line -- not the AR invoice line -- is the unit
of revenue recognition.

```
+---------+    +----------+         +------ OIC orchestration ------+        +------+
|   OM    | -> |    AR    |  --->   |  extract -> transformation    |  --->  | UCM  |
+---------+    +----------+         |  -> FBDI ZIP -> UCM upload    |        +------+
     ^             ^                |  -> Import ESS job submit     |            |
     |             |                +-------------------------------+            v
     |             |                              ^                          +------+
     |             |                              |                          | RMCS |
     +------ lineage store (system of record) ----+                          +------+
```

Key functional principles:

- **OM stays unchanged commercially.** One OM line per item, one list price,
  price components are *billing-only* metadata.
- **AR shows the split.** Two AR invoice lines per OM line: one for
  customer-pay, one for insurance-pay, both referencing the same OM line.
- **RMCS sees one performance obligation per OM line.** The split is
  collapsed before it reaches RMCS.
- **SSP and discount allocation are externalized.** RMCS receives pre-
  allocated source documents and does not run its own allocation.
- **Lineage is persisted.** Every AR-side event can be traced back to the
  originating OM line and the corresponding RMCS performance obligation.

## 4. Scope

### 4.1 In scope

- OM sales orders that carry price-component splits between CUSTOMER_PAY
  and INSURANCE_PAY (and optionally a LIST component).
- AR invoices and credit memos derived from those OM orders.
- RMCS source document creation (original, modification, adjustment).
- ASC 606 / IFRS 15 *relative SSP* allocation across performance
  obligations within an OM order.
- RMA and credit-memo flow back to the originating performance obligation.
- Reconciliation between AR and RMCS at the OM line level.

### 4.2 Out of scope

- Sales orders that do not use price-component splits (these continue
  through the seeded integration unchanged).
- Cash application, collections, and dunning -- these remain native AR.
- Costing and inventory accounting -- unaffected.
- Manual revenue adjustments performed directly in RMCS by Revenue
  Accounting outside the integration.
- Tax calculation -- continues through native AR.

## 5. Actors and stakeholders

| Actor / role                | Responsibility                                                                 |
|-----------------------------|--------------------------------------------------------------------------------|
| OMG (source application)    | Originates sales orders, drives OM with price-component splits                 |
| Order Management user       | Manages exceptions on OM orders that fail downstream                           |
| AR Billing Specialist       | Reviews and releases AR invoices; issues credit memos                          |
| Revenue Accountant          | Owns SSP catalog governance; reviews RMCS exceptions; closes the revenue book  |
| Integration Operator        | Monitors OIC orchestration; handles transport-level failures                   |
| Internal Audit              | Reviews lineage, allocation, and reconciliation controls                       |
| Controller                  | Signs off on period-end revenue                                                |

## 6. End-to-end process flows

### 6.1 Order-to-Cash-to-Revenue (happy path)

1. OMG creates a sales order in Oracle OM with one or more lines. Each line
   carries price components: a LIST amount (or implicit list = customer +
   insurance), a CUSTOMER_PAY amount, and an INSURANCE_PAY amount.
2. OM fulfills the line per its normal DOO flow.
3. OM hands the fulfilled line to AR (Receivables Invoice -- Autoinvoice).
   AR generates **two invoice lines per OM line**, one per price component,
   each referencing the originating OM order and line numbers.
4. **OIC** (scheduled or event-driven) extracts:
   - new/changed OM orders since the last successful run, and
   - new/changed AR invoices and credit memos since the last successful run.
5. OIC stages the extracts as JSON and invokes the **custom integration
   layer** (this codebase).
6. The integration layer:
   - **Builds lineage** -- ties every AR line back to its OM line and
     assigns a deterministic *revenue line id* per OM line.
   - **Collapses** the split AR lines back to one revenue line per OM line.
   - **Allocates** the transaction price across performance obligations
     within the OM order using the externally managed SSP catalog
     (relative-SSP method).
   - **Emits a file-based FBDI ZIP** containing the RMCS source-document
     header, lines, sub-lines (billing-party reference), and the import
     control file.
7. OIC uploads the FBDI ZIP to **UCM** and submits the *Import Customer
   Contract Source Data* ESS job through the ERP Cloud adapter.
8. OIC polls the ESS job until terminal state. On success, it marks the
   relevant lineage entries as `LOADED`; on partial/failure, it pulls the
   import error report and marks the affected entries `REJECTED` for
   human review.
9. RMCS owns recognition from this point: identify contract -> performance
   obligation -> allocation already done -> recognition schedule based on
   the fulfillment date emitted in the source document.

### 6.2 Contract modifications

A *contract modification* is any OM action that changes the commercial
contents of a line that has already been transmitted to RMCS (price
change, quantity change, item substitution, cancellation).

1. OMG updates the OM order. OM emits the change downstream to AR per its
   normal flow (and produces a credit/rebill or net-zero adjustment as
   appropriate).
2. The next OIC run detects the changed OM order (via the BICC delta /
   last-update timestamp).
3. The integration layer marks the new payload as a **modification** of
   the prior source document (by setting the modification flag and
   referencing the prior source-document number), re-runs allocation, and
   re-emits the FBDI.
4. RMCS reallocates the transaction price across the affected
   performance obligations per ASC 606 modification rules. Because we
   externalize allocation, the allocator does this; RMCS receives the
   already-reallocated amounts.

### 6.3 RMAs and credit memos

1. AR Billing issues a credit memo against one or both price-component
   AR lines for an OM line. (Pure-customer write-offs, pure-insurance
   denials, and full RMAs are all expressed this way.)
2. The next OIC run extracts the credit memo.
3. The integration layer:
   - Looks up each credit-memo line in the lineage store to find the
     originating OM line and revenue line id.
   - **Aggregates** the credit-memo lines that hit the same OM line into a
     single adjustment line so RMCS sees one negative entry per
     performance obligation (revenue recognition is at the POB level, not
     the price-component level).
   - Emits an adjustment source document referencing the prior original
     source document.
4. RMCS reverses recognized revenue against the original performance
   obligation; if the credit changes the contract value (not just quantity),
   reallocation is rerun.

### 6.4 Reconciliation (daily and period-end)

The integration produces, from the lineage store, a reconciliation report:

| Metric                                 | Source              | Tolerance               |
|----------------------------------------|---------------------|-------------------------|
| Sum of AR billed amounts per OM line   | AR (customer+insurance) | 0.00 vs RMCS line total |
| Sum of RMCS allocated amounts per OM line | RMCS source doc lines | -- exact match expected -- |
| Count of OM lines without RMCS docs    | Lineage store       | 0 outside SLA window    |
| Count of REJECTED lineage entries      | Lineage store       | 0 at period close       |

Revenue Accounting reviews and clears any non-zero variance before close.

### 6.5 Exception handling

| Exception                                                  | Detected by         | Disposition                                                                            |
|-------------------------------------------------------------|---------------------|----------------------------------------------------------------------------------------|
| AR line references an OM line not present in OM extract     | Lineage builder     | Quarantined; OIC notifies Integration Operator; AR Billing investigates                |
| No SSP available for an item or item class                  | SSP catalog lookup  | Revenue line falls through to "as-billed"; flagged for Revenue Accountant override     |
| FBDI import ESS job returns partial failure                 | OIC poll            | Failed rows marked REJECTED in lineage; success rows marked LOADED; report attached    |
| Credit memo references an AR line with no lineage entry     | RMA builder         | Hard error; OIC notifies Revenue Accountant; lineage must be rebuilt before re-run     |
| Contract modification arrives before original is LOADED     | Pipeline orchestrator | Modification deferred until original confirmed LOADED in lineage store                  |

## 7. Functional requirements

| ID    | Requirement                                                                                                              | Priority |
|-------|--------------------------------------------------------------------------------------------------------------------------|----------|
| FR-01 | OM order lines may carry CUSTOMER_PAY and INSURANCE_PAY price components in addition to the LIST price                   | Must     |
| FR-02 | AR invoice lines must reference the originating OM order number and OM line number                                       | Must     |
| FR-03 | The integration must produce exactly one RMCS performance obligation per OM order line                                   | Must     |
| FR-04 | The customer/insurance split must be carried into RMCS as sub-line reference data, not as separate performance obligations | Must     |
| FR-05 | SSP must be sourced from an externally managed catalog keyed by item, item class, and effective date                    | Must     |
| FR-06 | Transaction price must be allocated using the relative-SSP method to the cent, with last-line residual correction        | Must     |
| FR-07 | RMAs/credit memos must aggregate by OM line and emit one adjustment entry per performance obligation                      | Must     |
| FR-08 | Replays of the same OM/AR data must not produce duplicate RMCS rows (idempotent source document numbers)                  | Must     |
| FR-09 | The lineage store must record `PENDING`, `LOADED`, `REJECTED`, `PARTIAL` states per AR line                              | Must     |
| FR-10 | A daily AR-vs-RMCS reconciliation report must be produced per OM order                                                   | Must     |
| FR-11 | Contract modifications must be flagged and reference the prior source document number                                    | Must     |
| FR-12 | Exception cases (FR-05 no-SSP, FR-09 REJECTED) must be visible to Revenue Accountant in OIC monitoring                   | Must     |
| FR-13 | Sales orders without price-component splits must continue through the seeded integration unaffected                       | Must     |
| FR-14 | The FBDI column schema must be release-aligned with the target RMCS template and version-controlled                       | Must     |
| FR-15 | Tax amounts on the AR invoice must not flow into RMCS as part of the allocated transaction price                          | Must     |

## 8. Functional data model

Entities the business cares about (technical attribute lists are in
`docs/architecture.md`):

```
OMOrder
  +-- OMOrderLine                   (unit of revenue / POB)
        +-- OMPriceComponent        (LIST, CUSTOMER_PAY, INSURANCE_PAY)
ARInvoice
  +-- ARInvoiceLine                 (one per price component, refs OM line)
ARCreditMemo
  +-- ARCreditMemoLine              (refs AR line + OM line)
LineageMap
  +-- LineageEntry                  (AR line <-> OM line <-> RMCS POB)
SSPCatalog                          (item / class -> SSP per unit, effective-dated)
RMCSSourceDocument                  (one per OM order)
  +-- RMCSSourceDocumentLine        (one per OM line == one POB)
        +-- billing sub-lines       (customer-pay, insurance-pay; reference only)
RMCSAdjustmentDocument              (one per credit memo)
```

The **lineage map** is the single source of truth for routing AR-side
events to RMCS performance obligations and is also the basis of the
reconciliation report.

## 9. Integration touchpoints

| From      | To        | Mechanism                                 | Frequency        | Owner |
|-----------|-----------|-------------------------------------------|------------------|-------|
| OMG       | OM        | Existing OMG -> OM interface              | Real-time / batch | Apps  |
| OM        | AR        | Seeded DOO -> Autoinvoice                 | Per fulfillment  | Oracle |
| OM        | OIC       | BICC extract / REST (incremental delta)   | Scheduled        | OIC   |
| AR        | OIC       | BICC extract / REST (incremental delta)   | Scheduled        | OIC   |
| OIC       | Integration layer | CLI / HTTP function step          | Per OIC run      | This codebase |
| Integration layer | OIC | FBDI ZIP file return                | Per OIC run      | This codebase |
| OIC       | UCM       | UCM adapter (file upload)                 | Per OIC run      | OIC   |
| OIC       | RMCS      | ERP Cloud adapter -> *Import Customer Contract Source Data* ESS job | Per OIC run | OIC |
| RMCS      | OIC       | ESS job result + error report             | On job complete  | OIC   |
| OIC       | Integration layer | Job result feedback              | On job complete  | This codebase (lineage store update) |

## 10. Controls and segregation of duties

- **Change control on the SSP catalog**: only Revenue Accounting can
  modify SSP values; changes are versioned and effective-dated.
- **No direct write to RMCS** by the integration outside the FBDI ESS job
  -- the ESS job is the only entry point.
- **Idempotent source document numbers** -- replays cannot create
  duplicates without an explicit operator action.
- **Lineage immutability** -- once an entry is `LOADED`, only Revenue
  Accountant can change its state, and only via documented exception
  workflows.
- **Reconciliation sign-off** -- daily reconciliation report must be
  acknowledged by Revenue Accounting; period close cannot proceed with
  open exceptions.
- **Segregation**: AR Billing cannot release SSP changes; Revenue
  Accountant cannot release AR invoices; Integration Operator cannot
  change SSPs or override REJECTED entries.

## 11. Reporting

Produced from the lineage store and the AR/RMCS extracts:

1. **Daily AR-to-RMCS reconciliation** -- per OM order, per OM line, per
   day. Variances flagged.
2. **Allocation exception report** -- OM lines that fell through to
   "as-billed" due to missing SSP.
3. **Lineage state report** -- counts of `PENDING`, `LOADED`, `REJECTED`
   by age bucket.
4. **Modification audit trail** -- every RMCS modification document with
   its prior version and the responsible OIC run id.
5. **Period-close package** -- aggregated revenue by item class and
   business unit, reconciled to AR billed amounts, for inclusion in the
   month-end review.

## 12. Assumptions and dependencies

- OM is configured to populate `om_order_number` and `om_line_number` on
  every AR line it generates from a price-component-driven order.
- BICC extracts (or REST equivalents) for OM orders, AR invoices, and AR
  credit memos are available with reliable last-update timestamps.
- The RMCS *Import Customer Contract Source Data* FBDI template is
  available in the target environment and its current column list is
  reflected in `custom_rmcs/fbdi/schema.py`.
- OIC has connectivity to OM/AR (REST), UCM (UCM adapter), and ERP Cloud
  (ERP Cloud adapter for ESS job submission).
- An externally managed SSP catalog exists or will be created with
  effective-dated entries; Revenue Accounting owns its governance.

## 13. Risks and mitigations

| Risk                                                                          | Likelihood | Impact | Mitigation                                                                                  |
|-------------------------------------------------------------------------------|------------|--------|---------------------------------------------------------------------------------------------|
| FBDI column list changes with an Oracle quarterly release                      | Medium     | Medium | Schema kept in one file; quarterly review against template; release-gated regression tests   |
| SSP catalog stale or missing entries at period close                           | Medium     | High   | Allocation exception report reviewed daily; period-close blocker on open exceptions          |
| Late-arriving AR data lands after period close                                 | Medium     | Medium | Lineage state tracks PENDING; post-close adjustments routed through normal late-entry process |
| OIC outage delays load                                                         | Low        | Medium | Backfill is safe (idempotent); SLA monitoring on OIC orchestration                            |
| Manual changes in RMCS bypass the integration                                  | Low        | High   | Revenue Accountant policy + audit; reconciliation surfaces deltas                             |
| Tax incorrectly included in the FBDI allocated amount                          | Low        | High   | FR-15 enforced in the AR extract step; reconciliation includes tax-vs-revenue split           |
| Cross-currency OM orders (multi-currency on one order)                         | Low        | Medium | Out of scope for v1; pipeline validates currency consistency per order and quarantines       |

## 14. Non-functional considerations (functional view)

| Concern         | Target                                                                                   |
|-----------------|------------------------------------------------------------------------------------------|
| Latency         | New OM line visible in RMCS within one business day of fulfillment                       |
| Throughput      | Sized for the daily AR invoice volume of the business; OIC scheduling tunes batch window |
| Availability    | Pipeline tolerates OIC outage of up to 72h without data loss (lineage replay)            |
| Auditability    | Every emitted RMCS document traces back to OIC run id, OM extract, and AR extract        |
| Maintainability | FBDI column changes localized; OIC and integration layer can be released independently   |

## 15. Glossary

- **DOO** -- Distributed Order Orchestration; OM's fulfillment engine.
- **FBDI** -- File-Based Data Import; Oracle's CSV-in-ZIP load mechanism.
- **OIC** -- Oracle Integration Cloud.
- **OM** -- Oracle Fusion Cloud Order Management.
- **AR** -- Oracle Fusion Cloud Receivables.
- **RMCS** -- Oracle Revenue Management Cloud Service.
- **UCM** -- Universal Content Management (where FBDI ZIPs are landed).
- **ESS** -- Enterprise Scheduler Service (where the import job runs).
- **POB** -- Performance obligation (ASC 606 / IFRS 15).
- **SSP** -- Standalone selling price.
- **Relative SSP method** -- ASC 606 allocation method that distributes
  the transaction price across performance obligations in proportion to
  each POB's SSP.
- **Price component** -- An OM construct that lets a single order line
  produce multiple billed amounts (e.g. customer-pay, insurance-pay).
- **Lineage entry** -- Persisted record tying one AR invoice line to its
  originating OM line and the resulting RMCS performance obligation.
