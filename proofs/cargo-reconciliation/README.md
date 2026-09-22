# Shipment CSV reconciliation — demonstration

An executable Python sample for comparing two normalized CSV exports by shipment ID. All included records are synthetic (`DEMO-*`); this is not client work or a claim of past client results.

The report separates exact matches, quantity/weight differences, duplicate IDs, missing records and invalid quantities. It never silently merges duplicate IDs. Counts use decimal arithmetic and package counts must be whole numbers.

## Run

Python 3.11+; standard library only. No API, upload, account or paid dependency.

```bash
python3 -m unittest -v
python3 cargo_check.py manifest.csv invoices.csv > report.csv
```

Each input needs `shipment_id,packages,weight_lb`. Differences are manifest minus invoice. The seven tests cover matching, discrepancies, missing records, duplicates, invalid numeric values, fractional package counts and blank IDs.

## Scope and limits

This is a sample for an agreed data reconciliation task, not a production shipment or accounting system. It compares package counts and weights only; it does not calculate money, classify customs goods, assess tax, or certify delivery. Missing/duplicate rows require review, and this sample does not normalize units or validate every field on unmatched rows. Open external CSVs as text or use a spreadsheet import with formula interpretation disabled; IDs are preserved verbatim.

For a paid pilot, agree the two input schemas, record limit, expected output and acceptance examples before handling buyer data. Do not publish customer exports in this repository.
