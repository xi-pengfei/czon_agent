import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/demo-sales-quick-query/scripts/query.py'
spec = importlib.util.spec_from_file_location('demo_sales_query', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SalesBriefTests(unittest.TestCase):
    def test_all_orders_counted_once_and_source_retained(self):
        result = module.query()
        self.assertTrue(result['is_demo'])
        self.assertEqual(result['source'], 'presentation_sample')
        self.assertEqual(result['data']['orders'], 8)
        self.assertEqual(result['data']['quantity'], 90)
        self.assertEqual(result['data']['revenue'], '18400.00')

    def test_beijing_order_details_and_followup(self):
        result = module.query(view='orders', city='北京')['data']
        self.assertEqual(result['orders'], 4)
        self.assertEqual(result['revenue'], '7700.00')
        self.assertEqual([o['order_id'] for o in result['order_details']], ['XS001', 'XS003', 'XS005', 'XS008'])
        pending = module.query(city='北京', status='待发货')['data']
        self.assertEqual((pending['orders'], pending['revenue']), (3, '4900.00'))

    def test_product_amount_is_not_full_order_amount(self):
        data = module.query(city='北京', product='工业网关')['data']
        self.assertEqual((data['orders'], data['quantity'], data['revenue']), (2, 5, '4000.00'))
        order = module.query(order_id='xs001')['data']['order_details'][0]
        self.assertEqual(len(order['items']), 2)
        self.assertEqual(order['amount'], '2800.00')

    def test_groups_rankings_and_ties(self):
        groups = module.query(view='cities')['data']['groups']
        self.assertEqual([(g['name'], g['amount']) for g in groups], [('北京', '7700.00'), ('深圳', '6500.00'), ('上海', '4200.00')])
        products = module.query(view='products')['data']['groups']
        self.assertEqual(products[0]['name'], '工业网关')
        self.assertEqual(max(products, key=lambda g: g['quantity'])['name'], '温度传感器')
        customers = module.query(view='customers')['data']['groups']
        self.assertEqual({g['name'] for g in customers if g['amount'] == '4200.00'}, {'浦江机电', '南海设备'})

    def test_dates_and_no_matching_rows(self):
        self.assertEqual(module.query(start='2026-11-01', end='2026-11-07')['data']['revenue'], '10400.00')
        for filters in [{'month': '2026-10'}, {'city': '广州'}, {'order_id': 'XS999'}]:
            result = module.query(**filters)
            self.assertEqual(result['data']['orders'], 0)
            self.assertIn('没有符合', result['summary'])
        for filters in [{'month': '2026-13'}, {'start': '2026-11-14', 'end': '2026-11-01'}, {'month': '2026-11', 'start': '2026-11-01'}]:
            with self.assertRaises(ValueError):
                module.query(**filters)

    def test_bad_data_and_decimal_precision(self):
        header = ','.join(module.FIELDS) + '\n'
        valid = 'XS001,2026-11-01,北京,A,传感器,3,0.10,已发货\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.csv'
            path.write_text(header + valid)
            self.assertEqual(module.query(path)['data']['revenue'], '0.30')
            for rows in ['', valid + valid, valid.replace('0.10', 'NaN'), valid + valid.replace('传感器', '网关').replace('北京', '上海')]:
                path.write_text(header + rows)
                with self.assertRaises(ValueError):
                    module.query(path)

    def test_unsupported_cli_returns_error_without_numbers(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--real-data'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['status'], 'error')
        self.assertNotIn('data', json.loads(result.stdout))
