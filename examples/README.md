# Examples

Sample OIC-staged extracts and an SSP catalog. Use them to smoke-test the
CLI end-to-end without any Oracle connectivity:

```bash
python -m custom_rmcs \
    --om-extract examples/om.json \
    --ar-extract examples/ar.json \
    --ssp-catalog examples/ssp.json \
    --lineage-store examples/state/lineage.json \
    --out examples/out/rmcs_fbdi.zip
```

After running, inspect the ZIP:

```bash
unzip -p examples/out/rmcs_fbdi.zip VRM_SOURCE_DOC_LINES_INT.csv
```

You should see one revenue line per OM line, with `ALLOCATED_AMOUNT` equal
to the sum of the customer- and insurance-responsible AR amounts.
