"""Synthetic proof of work: reconcile normalized shipment CSVs, not customs advice.
Run: python3 cargo_check.py manifest.csv invoices.csv > report.csv
Columns: shipment_id,packages,weight_lb. Duplicate IDs are never auto-merged.
"""
import csv
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation


def read_rows(path):
    with open(path, newline='', encoding='utf-8-sig') as source:
        reader = csv.DictReader(source)
        required = {'shipment_id', 'packages', 'weight_lb'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('Missing required columns')
        return list(reader)


def reconcile(manifest, invoices):
    indexes = []
    for rows in (manifest, invoices):
        index = defaultdict(list)
        for row in rows:
            key = row.get('shipment_id', '').strip()
            if not key:
                raise ValueError('Blank shipment ID; fix input before reconciliation')
            index[key].append(row)
        indexes.append(index)
    left, right = indexes
    results = []
    for key in sorted(left.keys() | right.keys()):
        status = 'MATCH'
        package_delta = weight_delta = ''
        if len(left[key]) > 1 or len(right[key]) > 1:
            status = 'DUPLICATE_REVIEW'
        elif not left[key]:
            status = 'MISSING_MANIFEST'
        elif not right[key]:
            status = 'MISSING_INVOICE'
        else:
            try:
                values = [Decimal(row[field]) for row in (left[key][0], right[key][0])
                          for field in ('packages', 'weight_lb')]
                if any(not value.is_finite() or value < 0 for value in values):
                    raise ValueError('Invalid quantity')
                if values[0] != values[0].to_integral_value() or values[2] != values[2].to_integral_value():
                    raise ValueError('Packages must be whole numbers')
                package_delta = values[0] - values[2]
                weight_delta = values[1] - values[3]
                if package_delta or weight_delta:
                    status = 'DIFFERENCE_REVIEW'
            except (InvalidOperation, ValueError, KeyError, TypeError):
                status = 'INVALID_REVIEW'
        results.append({'shipment_id': key, 'status': status,
                        'package_delta': str(package_delta), 'weight_lb_delta': str(weight_delta)})
    return results


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: python3 cargo_check.py manifest.csv invoices.csv')
    report = reconcile(read_rows(sys.argv[1]), read_rows(sys.argv[2]))
    writer = csv.DictWriter(sys.stdout, fieldnames=['shipment_id', 'status', 'package_delta', 'weight_lb_delta'])
    writer.writeheader()
    writer.writerows(report)
