"""Local, read-only sales briefing over a fictional presentation dataset."""
import argparse
import csv
import json
import sys
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

DATA_FILE = Path(__file__).resolve().parents[1] / 'assets' / 'sales.csv'
FIELDS = ['order_id', 'date', 'city', 'customer', 'product', 'quantity', 'unit_price', 'status']
VIEWS = ['overview', 'orders', 'cities', 'customers', 'products']


def load_rows(path):
    rows, seen, order_meta = [], set(), {}
    with Path(path).open(encoding='utf-8', newline='') as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != FIELDS:
            raise ValueError('销售数据字段不完整')
        for row in reader:
            day = date.fromisoformat(row['date'])
            quantity, price = int(row['quantity']), Decimal(row['unit_price'])
            key = (row['order_id'], row['product'])
            meta = tuple(row[k] for k in ['date', 'city', 'customer', 'status'])
            if (any(not row[k].strip() for k in FIELDS) or not row['order_id'].startswith('XS')
                    or key in seen or quantity <= 0 or not price.is_finite() or price < 0
                    or price != price.quantize(Decimal('0.01'))
                    or (row['order_id'] in order_meta and order_meta[row['order_id']] != meta)):
                raise ValueError('销售数据无效或订单信息不一致')
            seen.add(key)
            order_meta[row['order_id']] = meta
            rows.append({**row, 'quantity': quantity, 'unit_price': price,
                         'amount': quantity * price, '_day': day})
    if not rows:
        raise ValueError('销售数据为空')
    return rows


def query(path=DATA_FILE, *, view='overview', city='', customer='', product='', order_id='',
          month='', start='', end='', status=''):
    started = time.perf_counter()
    if view not in VIEWS or (month and (start or end)):
        raise ValueError('查询维度无效，月份与日期区间不能同时使用')
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date()
    if month == 'current':
        month = today.strftime('%Y-%m')
    if month:
        if len(month) != 7 or date.fromisoformat(month + '-01').strftime('%Y-%m') != month:
            raise ValueError('月份须为 YYYY-MM')
    first, last = date.fromisoformat(start) if start else None, date.fromisoformat(end) if end else None
    if first and last and first > last:
        raise ValueError('开始日期不能晚于结束日期')
    all_rows = load_rows(path)
    filters = {'city': city, 'customer': customer, 'product': product, 'order_id': order_id.upper(), 'status': status}
    rows = [r for r in all_rows if all(not v or r[k] == v for k, v in filters.items())
            and (not month or r['date'].startswith(month))
            and (not first or r['_day'] >= first) and (not last or r['_day'] <= last)]
    total = sum((r['amount'] for r in rows), Decimal('0.00'))
    orders = {}
    for row in rows:
        order = orders.setdefault(row['order_id'], {k: row[k] for k in ['order_id', 'date', 'city', 'customer', 'status']})
        order.setdefault('items', []).append({k: row[k] for k in ['product', 'quantity', 'unit_price', 'amount']})
        order['amount'] = order.get('amount', Decimal('0.00')) + row['amount']
    groups = []
    dimension = {'cities': 'city', 'customers': 'customer', 'products': 'product'}.get(view)
    if dimension:
        names = sorted({r[dimension] for r in rows})
        for name in names:
            items = [r for r in rows if r[dimension] == name]
            groups.append({'name': name, 'orders': len({r['order_id'] for r in items}),
                           'quantity': sum(r['quantity'] for r in items),
                           'amount': sum((r['amount'] for r in items), Decimal('0.00'))})
        groups.sort(key=lambda g: (-g['amount'], g['name']))
    scope = '、'.join([v for v in [month, start + '至' + end if start or end else '', *filters.values()] if v]) or '全部记录'
    if not rows:
        summary = f'当前销售数据中没有符合“{scope}”的记录。'
    elif dimension:
        summary = f'{scope}：' + '；'.join(f'{g["name"]}{g["orders"]}笔订单，{g["quantity"]}件，金额{g["amount"]:.2f}元' for g in groups) + '。'
    elif view == 'orders' or order_id:
        summary = f'{scope}共{len(orders)}笔订单。' + '；'.join(
            f'{o["order_id"]}，{o["customer"]}，' + '、'.join(f'{i["product"]}{i["quantity"]}件' for i in o['items'])
            + f'，金额{o["amount"]:.2f}元，{o["status"]}' for o in orders.values()) + '。'
    else:
        summary = f'{scope}共{len(orders)}笔订单，销售额{total:.2f}元，销售数量{sum(r["quantity"] for r in rows)}件。'
    result = {'status': 'completed', 'source': 'presentation_sample', 'is_demo': True,
              'current_date': today.isoformat(),
              'dataset_period': {'start': min(r['date'] for r in all_rows), 'end': max(r['date'] for r in all_rows)},
              'filters': {**filters, 'month': month, 'start': start, 'end': end},
              'data': {'currency': 'CNY', 'orders': len(orders), 'revenue': total,
                       'quantity': sum(r['quantity'] for r in rows), 'groups': groups,
                       'order_details': list(orders.values()) if view == 'orders' or order_id else []},
              'summary': summary, 'elapsed_ms': round((time.perf_counter() - started) * 1000, 3)}
    return json.loads(json.dumps(result, ensure_ascii=False, default=lambda value: f'{value:.2f}'))


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('查询参数不支持')


def main():
    parser = Parser(description='公司经营数据')
    parser.add_argument('--view', choices=VIEWS, default='overview')
    for field in ['city', 'customer', 'product', 'order-id', 'month', 'start', 'end', 'status']:
        parser.add_argument('--' + field, default='')
    try:
        result = query(**vars(parser.parse_args()))
    except (OSError, ValueError, KeyError, TypeError, InvalidOperation, csv.Error):
        print(json.dumps({'status': 'error', 'is_demo': True,
                          'summary': '销售查询失败，没有有效结果；请检查数据和查询条件。'}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
