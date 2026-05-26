# Examples

Sample OIC-staged extracts you can feed through the CLI without any Oracle
connectivity. Each subdirectory is a self-contained scenario.

## Scenarios

| Scenario | What it shows |
|----------|---------------|
| [`single_line_split/`](single_line_split/)               | The minimum viable case: one OM line that AR splits into two price-component invoice lines (CUSTOMER_PAY + INSURANCE_PAY), collapsed back to one RMCS POB. |
| [`multi_line_with_discount/`](multi_line_with_discount/) | The canonical relative-SSP allocation case: three OM lines, line-level discount, AR per-line invoiced amounts diverge from RMCS revenue amounts (Opt Prog $430 -> $389.65, Sun SV $188 -> $212.95, Opt SV $116 -> $131.40), totals tie at $734. |

## How to run any of them

```bash
python -m custom_rmcs \
    --om-extract examples/<scenario>/om.json \
    --ar-extract examples/<scenario>/ar.json \
    --ssp-catalog examples/<scenario>/ssp.json \
    --state-journal /tmp/state.json \
    --out /tmp/rmcs_fbdi.zip \
    --run-id RUN-DEMO-1
```

After running, inspect the FBDI CSVs:

```bash
unzip -p /tmp/rmcs_fbdi.zip VRM_SOURCE_DOC_LINES_INT.csv
unzip -p /tmp/rmcs_fbdi.zip VRM_SOURCE_DOC_SUB_LINES_INT.csv
```

And the integration's load-state journal:

```bash
cat /tmp/state.json
```

You should see one journal entry per emitted RMCS POB line, all in
`PENDING` state, tagged with `RUN-DEMO-1`. In production, OIC's
post-ESS-job feedback step calls
`LoadStateJournal.record_load_result(...)` to flip them to `LOADED` (or
`REJECTED` if the import error report flagged the row).
