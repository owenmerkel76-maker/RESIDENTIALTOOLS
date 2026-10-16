# -*- coding: utf-8 -*-
"""Supplier CSV prices with explicit units; no guessed or scraped prices."""
import csv
import hashlib
import io
import json
import os
import sys
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
from rt_quantities import csv_text

REQUIRED_COLUMNS=['item_key','description','unit','unit_price','currency','supplier','source_url','price_date']
PRICE_COLUMNS=REQUIRED_COLUMNS+['retail_units','price_zip','retail_product','online_status','verified']


def item_groups(rows,stock):
    groups={}
    for row in rows:
        board=row['role'] in ('BOARD','BORDER')
        materials=tuple(sorted(row.get('materials',[])))
        if board:
            identity=['BOARD_STOCK',row['stock_profile'],materials,row['stock_width_in'],row['depth_in'],row['stock_length_ft']]
            description='{0:g} ft composite {1} | {2:g} x {3:g} in | {4}'.format(
                row['stock_length_ft'],row['stock_profile'],row['stock_width_in'],row['depth_in'],', '.join(materials))
        else:
            identity=[row['role'],row['type_name'],materials,row['width_in'],row['depth_in']]
            description=row['role'].replace('_',' ').title()+' | '+row['type_name']+' | '+', '.join(materials)
        key='RT-'+hashlib.sha256(json.dumps(identity,ensure_ascii=True,separators=(',',':')).encode('utf-8')).hexdigest()[:16]
        unit='STOCK' if board else 'LF' if row['length_ft']>0 else 'EA'
        group=groups.setdefault(key,dict(item_key=key,description=description,unit=unit,installed_count=0,
                                        installed_length_ft=0,stock_quantity=0 if board else None,stock_complete=True))
        group['installed_count']+=1; group['installed_length_ft']+=row['length_ft']
        if board:
            group['stock_complete']=group['stock_complete'] and row.get('stock_eligible',True)
            group['stock_match']=(row['stock_profile'],materials,row['stock_width_in'],row['depth_in'],row['stock_length_ft'])
    for group in groups.values():
        if group['unit']!='STOCK': continue
        match=group.pop('stock_match'); estimates=[e for e in stock if (
            e['stock_profile'],tuple(sorted(e['materials'])),e['stock_width_in'],e['thickness_in'],e['board_stock_ft'])==match]
        group['stock_complete']=group['stock_complete'] and bool(estimates) and all(e['estimate_complete'] for e in estimates)
        group['stock_quantity']=sum(e['order_with_allowance'] for e in estimates) if group['stock_complete'] else None
    return sorted(groups.values(),key=lambda g:g['description'])


def read_prices(path):
    if os.path.getsize(path)>5*1024*1024: raise ValueError('Supplier pricing CSV must be smaller than 5 MB.')
    with io.open(path,'r',encoding='utf-8-sig') as stream: content=stream.read()
    reader=csv.DictReader(io.BytesIO(content.encode('utf-8')) if sys.version_info[0]<3 else io.StringIO(content))
    def text(value):
        return value.decode('utf-8') if isinstance(value,bytes) else value
    headers=[text(h) for h in (reader.fieldnames or [])]
    if len(headers)!=len(set(headers)) or any(h not in headers for h in REQUIRED_COLUMNS):
        raise ValueError('Use the supplier template headers: '+', '.join(PRICE_COLUMNS))
    prices={}
    for line,raw in enumerate(reader,2):
        if line>20001: raise ValueError('Supplier CSV is limited to 20,000 rows.')
        if None in raw or any(v is None for v in raw.values()): raise ValueError('Malformed supplier CSV row '+str(line))
        row=dict((text(k),text(v).strip()) for k,v in raw.items())
        row['currency']=row['currency'].upper()
        if not row['item_key']: continue
        if row['item_key'] in prices: raise ValueError('Duplicate supplier item_key on row '+str(line))
        if row['unit'] not in ('LF','EA','STOCK'): raise ValueError('Supplier unit must be LF, EA or STOCK on row '+str(line))
        if row['unit_price']:
            try: price=Decimal(row['unit_price'])
            except InvalidOperation: raise ValueError('Unit price must be numeric on row '+str(line))
            if not price.is_finite() or not 0<=price<=1000000000: raise ValueError('Unit price must be finite, nonnegative and at most 1,000,000,000 on row '+str(line))
            if len(row['currency'])!=3 or not row['currency'].isalpha(): raise ValueError('Enter a three-letter currency, e.g. USD, on row '+str(line))
        prices[row['item_key']]=row
    return prices


def template_text(groups):
    return csv_text([PRICE_COLUMNS]+[[g['item_key'],g['description'],g['unit'],'','USD','','','','','19464','','',''] for g in groups])


def priced_report(groups,prices):
    result=[]; totals={}; missing=0
    for group in groups:
        row=dict(group); price=prices.get(row['item_key']); row.update(unit_price='',extended_price='',currency='',supplier='',source_url='',price_date='',price_zip='',retail_product='')
        row['status']='NO PRICE'; unit=price['unit'] if price else row['unit']; row['unit']=unit
        row['pricing_quantity']={'LF':row['installed_length_ft'],'EA':row['installed_count'],'STOCK':row['stock_quantity']}[unit]
        if unit=='STOCK' and (row['stock_quantity'] is None or not row['stock_complete']):
            row['status']='STOCK QUANTITY NEEDS REVIEW'
        elif price and price.get('online_status') and price.get('verified')!='yes':
            row['status']='VERIFY RETAIL PRODUCT, PRICE AND STORE'
        elif price and price['unit_price']:
            for key in ('unit_price','currency','supplier','source_url','price_date','price_zip','retail_product'): row[key]=price.get(key,'')
            total=(Decimal(str(row['pricing_quantity']))*Decimal(row['unit_price'])).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            row['extended_price']=str(total); row['status']='PRICED' if row['price_date'] else 'PRICED - DATE NOT PROVIDED'
            totals[row['currency']]=totals.get(row['currency'],Decimal(0))+total
        if row['extended_price']=='': missing+=1
        result.append(row)
    return dict(rows=result,priced_subtotals=dict((currency,str(value)) for currency,value in totals.items()),unpriced_lines=missing,
                complete=not missing,notes='STOCK = estimated composite stock boards including entered extra allowance; LF = installed length; EA = installed pieces. Modeled connector nails/face screws count as EA. Unmodeled fasteners, tax, delivery, wood-stock waste and online price verification are excluded.')


def report_text(report):
    columns=['item_key','description','installed_count','installed_length_ft','stock_quantity','unit','pricing_quantity',
             'unit_price','extended_price','currency','supplier','source_url','price_date','price_zip','retail_product','status']
    return csv_text([columns]+[[row.get(key,'') if row.get(key) is not None else '' for key in columns] for row in report['rows']])
