# Example: 3-line order with line-level discount and customer/insurance split

This is the canonical example showing why the integration exists. It
demonstrates that the AR per-line invoiced amounts (which reflect the
discount as it was billed) **diverge** from the RMCS per-line revenue
amounts (which reflect ASC 606 relative-SSP allocation), even though the
totals tie.

## The order

| Item     | Order units | Gross value (= SSP) | Discount on AR | Initial invoiced amount | RMCS revenue (allocated) |
|----------|:-----------:|--------------------:|---------------:|------------------------:|-------------------------:|
| Opt Prog | 1           | $430.00             |    $0.00       |   $430.00               |    $389.65               |
| Sun SV   | 1           | $235.00             |  $-47.00       |   $188.00               |    $212.95               |
| Opt SV   | 1           | $145.00             |  $-29.00       |   $116.00               |    $131.40               |
| **Total**|             |  **$810.00**        | **$-76.00**    |  **$734.00**            |  **$734.00**             |

Notes:

- The "Gross value" is the OM `LIST` price component on each line. We use
  it as the SSP in `ssp.json` for this example; in production the SSP
  catalog is governed independently and the gross/list price is used only
  for billing.
- "Discount on AR" is implicit: it is the difference between the OM
  `LIST` amount and the sum of the `CUSTOMER_PAY` + `INSURANCE_PAY`
  components on the same OM line. AR sees the lower amount.
- "Initial invoiced amount" = `CUSTOMER_PAY` + `INSURANCE_PAY` amounts on
  the AR side for that OM line. Sums to the contract transaction price.
- "RMCS revenue (allocated)" is the relative-SSP allocation of the $734
  transaction price across performance obligations weighted by SSP. The
  integration emits these amounts to RMCS pre-allocated; RMCS does not
  reallocate.
- Rounded to whole dollars (as Finance often presents it) the revenue
  amounts are **$390 / $213 / $131**, which still sum to $734. The
  cent-precise allocator emits **$389.65 / $212.95 / $131.40** and uses a
  last-line residual to guarantee the total ties to the cent.

## Customer / insurance split

The split below is illustrative (25% customer-pay / 75% insurance-pay on
each line). It is *billing-only* and does not affect revenue allocation:

| Item     | Customer-pay | Insurance-pay |
|----------|-------------:|--------------:|
| Opt Prog | $107.50      | $322.50       |
| Sun SV   |  $47.00      | $141.00       |
| Opt SV   |  $29.00      |  $87.00       |

Each OM line therefore produces **two AR invoice lines** (one per price
component), giving 6 AR lines total. The integration collapses these
back to 3 RMCS performance obligations.

## Run it

```bash
python -m custom_rmcs \
    --om-extract examples/multi_line_with_discount/om.json \
    --ar-extract examples/multi_line_with_discount/ar.json \
    --ssp-catalog examples/multi_line_with_discount/ssp.json \
    --state-journal /tmp/state.json \
    --out /tmp/rmcs_fbdi.zip \
    --run-id RUN-DEMO-1
```

Inspect the line-level CSV inside the ZIP:

```bash
unzip -p /tmp/rmcs_fbdi.zip VRM_SOURCE_DOC_LINES_INT.csv
```

You should see exactly 3 rows -- one per OM line -- with
`ALLOCATED_AMOUNT` of `389.65`, `212.95`, and `131.40` respectively. The
sub-line CSV (`VRM_SOURCE_DOC_SUB_LINES_INT.csv`) preserves the
customer/insurance billing split for downstream reconciliation but RMCS
recognizes revenue at the line level only.
