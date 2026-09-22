import unittest
from cargo_check import reconcile

def row(key='DEMO-1', packages='2', weight='10.50'):
    return dict(shipment_id=key, packages=packages, weight_lb=weight)

class ReconciliationTests(unittest.TestCase):
    def test_match(self):
        self.assertEqual(reconcile([row()], [row()])[0]['status'], 'MATCH')
    def test_differences(self):
        result = reconcile([row(packages='3', weight='12.75')], [row()])[0]
        self.assertEqual((result['status'], result['package_delta'], result['weight_lb_delta']), ('DIFFERENCE_REVIEW', '1', '2.25'))
    def test_missing(self):
        self.assertEqual([r['status'] for r in reconcile([row('A')], [row('B')])], ['MISSING_INVOICE', 'MISSING_MANIFEST'])
    def test_duplicates_never_auto_merged(self):
        self.assertEqual(reconcile([row(), row()], [row()])[0]['status'], 'DUPLICATE_REVIEW')
    def test_invalid(self):
        for value in ('NaN', 'Infinity', '-1', 'not-a-number'):
            self.assertEqual(reconcile([row(weight=value)], [row()])[0]['status'], 'INVALID_REVIEW')
    def test_fractional_packages(self):
        self.assertEqual(reconcile([row(packages='1.2')], [row()])[0]['status'], 'INVALID_REVIEW')
    def test_blank_id(self):
        with self.assertRaises(ValueError):
            reconcile([row('')], [row()])

if __name__ == '__main__':
    unittest.main()
