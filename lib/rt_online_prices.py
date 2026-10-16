# -*- coding: utf-8 -*-
"""Public retailer offers and a local, user-reviewed price worksheet."""
import json
import re
from datetime import date
from decimal import Decimal
try:
    from urllib.parse import urlparse,urlencode
    from urllib.request import Request,urlopen
except ImportError:
    from urlparse import urlparse
    from urllib import urlencode
    from urllib2 import Request,urlopen
from rt_pricing import PRICE_COLUMNS
try: text_types=(basestring,)
except NameError: text_types=(str,)


def product_url(url):
    parsed=urlparse(url)
    host=(parsed.hostname or '').lower()
    valid=(host in ('homedepot.com','www.homedepot.com') and parsed.path.startswith('/p/')) or (
        host in ('lowes.com','www.lowes.com') and parsed.path.startswith('/pd/'))
    if parsed.scheme!='https' or not valid or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Use a public https Home Depot /p/ or Lowe\'s /pd/ product URL.')
    return 'https://'+host+parsed.path


def fetch_page(url):
    request=Request(product_url(url),headers={'User-Agent':'RESIDENTIALTOOLS-price-review/1.0','Accept':'text/html'})
    response=urlopen(request,timeout=6)
    try:
        product_url(response.geturl())  # Never follow a redirect to another host.
        data=response.read(3*1024*1024+1)
        if len(data)>3*1024*1024: raise ValueError('Retail page exceeds the 3 MB lookup limit.')
        return data.decode('utf-8','replace')
    finally: response.close()


def extract_offer(page):
    products=[]
    def walk(value):
        if isinstance(value,list):
            for item in value: walk(item)
        elif isinstance(value,dict):
            kind=value.get('@type',[]); kind=[kind] if isinstance(kind,text_types) else kind
            if not isinstance(kind,list): kind=[]
            if 'Product' in kind: products.append(value)
            for child in value.values():
                if isinstance(child,(dict,list)): walk(child)
    for script in re.findall(r'<script\b[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script\s*>',page,re.I|re.S):
        try: walk(json.loads(script))
        except ValueError: pass
    candidates=[]
    for product in products:
        offers=product.get('offers',[]); offers=[offers] if isinstance(offers,dict) else offers
        for offer in offers:
            if not isinstance(offer,dict) or offer.get('priceCurrency')!='USD' or 'price' not in offer: continue
            try: price=Decimal(str(offer['price']))
            except Exception: continue
            if price.is_finite() and 0<=price<=1000000000:
                candidates.append(dict(retail_price=str(price),retail_product=product.get('name',''),currency='USD'))
    if len(set((value['retail_price'],value['retail_product']) for value in candidates))!=1:
        raise ValueError('No single unambiguous public product price. Review the local store page manually.')
    return candidates[0]


def lookup(prices,zip_code,fetch=fetch_page,progress=None):
    if not re.match(r'^\d{5}$',zip_code): raise ValueError('Enter a five-digit store ZIP code.')
    result=dict((key,dict(value)) for key,value in prices.items()); cache={}; checked=0
    for key,row in result.items():
        if not row.get('source_url'): continue
        checked+=1
        if progress and not progress(checked): break
        row.update(verified='',price_zip=zip_code,unit_price='',online_status='REVIEW REQUIRED')
        try:
            url=product_url(row['source_url'])
            if url not in cache:
                if len(cache)>=12: raise ValueError('Twelve unique product pages per lookup; use another pass for remaining items.')
                try: cache[url]=extract_offer(fetch(url))
                except Exception as error: cache[url]=str(error)
            quote=cache[url]
            if not isinstance(quote,dict): raise ValueError(quote)
            row.update(quote,source_url=url,price_date=date.today().isoformat())
            units=Decimal(row.get('retail_units') or '0')
            if not units.is_finite() or units<=0: raise ValueError('Enter pricing units per retail pack/board before converting the price.')
            row['unit_price']=str((Decimal(quote['retail_price'])/units).quantize(Decimal('.000001')))
            row['online_status']='PUBLIC OFFER - VERIFY PRODUCT, PACK AND STORE '+zip_code
        except Exception as error: row['online_status']='MANUAL REVIEW: '+str(error)[:180]
    return result


def worksheet(groups,prices,zip_code):
    data=[]
    for group in groups:
        row=dict(group); row.update(prices.get(group['item_key'],{})); row.setdefault('price_zip',zip_code)
        data.append(row)
    payload=json.dumps(dict(rows=data,columns=PRICE_COLUMNS,zip=zip_code,date=date.today().isoformat()),ensure_ascii=True).replace('<','\\u003c')
    return u'''<!doctype html><html><meta charset="utf-8"><title>RESIDENTIALTOOLS pricing review</title>
<style>body{font:15px system-ui;margin:28px;background:#f4f6f8;color:#172c3b}main{max-width:1150px;margin:auto}header,article{background:white;padding:20px;margin:16px 0;border:1px solid #ced7dd;border-radius:8px}h1{margin:0 0 12px}h2{font-size:17px}button,a{margin:4px 8px 8px 0;padding:8px;cursor:pointer}button{background:#173f5f;color:white;border:0;border-radius:4px}.fields{display:grid;grid-template-columns:repeat(3,minmax(190px,1fr));gap:12px}label{display:block}input,select{box-sizing:border-box;display:block;width:100%;padding:7px;margin-top:4px}input[type=checkbox]{display:inline;width:auto}.note{color:#455a64}.status{color:#8b4200}#save{position:sticky;top:8px;z-index:1;font-weight:bold}.url{grid-column:span 2}</style>
<main><header><h1>Review online prices — ZIP <span id="zip"></span></h1>
<p>Choose the actual store/location on Lowe’s or Home Depot. Verify product, grade/treatment, stock length and pack size before using a price. Search links do not set the retailer’s store automatically.</p>
<p class="note">Public offers are suggestions until you check the verified box. Blocked or unavailable prices stay blank. STOCK means one composite stock board; LF means one installed linear foot; EA means one installed piece. For a $24 sixteen-foot board priced per LF, enter 16 pricing units per retail board. For a 50-clip pack priced per EA, enter 50.</p>
<button id="save">Save supplier_prices.csv</button><p>Then return to Material List → Materials + pricing CSV and browse to the saved file.</p></header><div id="items"></div></main>
<script>const data=PAYLOAD;document.getElementById('zip').textContent=data.zip;const output=[];
function node(tag,text){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e}
for(const row of data.rows){const card=node('article');card.append(node('h2',row.description));card.append(node('p','Installed: '+row.installed_count+' pieces / '+row.installed_length_ft.toFixed(2)+' ft. Composite stock order: '+(row.stock_quantity===null?'needs review':row.stock_quantity||'not applicable')));
for(const supplier of ['Home Depot','Lowe’s']){const a=node('a',supplier+' search');const query=row.description+' '+data.zip;a.href=supplier==='Home Depot'?'https://www.homedepot.com/s/'+encodeURIComponent(query):'https://www.lowes.com/search?searchTerm='+encodeURIComponent(query);a.target='_blank';a.rel='noopener noreferrer';card.append(a)}
card.append(node('p',row.retail_product||''));const status=node('p',row.online_status||'Find the exact retail product and enter its price.');status.className='status';card.append(status);const grid=node('div');grid.className='fields';const inputs={};
function field(key,title,value){const label=node('label',title);const control=node('input');control.value=value===undefined?'':value;label.append(control);grid.append(label);inputs[key]=control;return control}
field('unit','Pricing unit (LF, EA or STOCK)',row.unit);const retail=field('retail_price','Listed retail price ($ per board/pack)',row.retail_price);const pack=field('retail_units','Pricing units per retail board/pack',row.retail_units|| (row.unit==='STOCK'?'1':''));const rate=field('unit_price','Price per pricing unit ($)',row.unit_price);field('supplier','Supplier / store name',row.supplier);field('price_date','Checked date (YYYY-MM-DD)',row.price_date||data.date);field('source_url','Exact product URL',row.source_url);field('currency','Currency',row.currency||'USD');field('price_zip','Verified store ZIP',row.price_zip||data.zip);
function convert(){const a=Number(retail.value),b=Number(pack.value);if(retail.value!==''&&Number.isFinite(a)&&a>=0&&Number.isFinite(b)&&b>0)rate.value=(a/b).toFixed(6)}retail.addEventListener('input',convert);pack.addEventListener('input',convert);card.append(grid);const verify=node('label',' I verified product, pricing unit/pack, price and store location.');const checkbox=node('input');checkbox.type='checkbox';checkbox.checked=row.verified==='yes';verify.prepend(checkbox);card.append(verify);document.getElementById('items').append(card);output.push({row,inputs,checkbox});}
document.getElementById('save').onclick=()=>{const rows=[data.columns];for(const item of output){const row={...item.row};for(const key in item.inputs)row[key]=item.inputs[key].value.trim();if(row.unit_price!==''&&(!['LF','EA','STOCK'].includes(row.unit)||!Number.isFinite(Number(row.unit_price))||Number(row.unit_price)<0)){alert('Check price/unit for '+row.description);return}row.verified=item.checkbox.checked?'yes':'';if(row.unit_price!==''&&!item.checkbox.checked)row.online_status='REVIEW REQUIRED';else if(item.checkbox.checked)row.online_status='USER VERIFIED RETAIL PRICE';rows.push(data.columns.map(key=>row[key]||''))}const cell=value=>{let s=String(value);if(/^[\\s]*[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"'};const csv='\\uFEFF'+rows.map(row=>row.map(cell).join(',')).join('\\r\\n');const link=node('a');link.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));link.download='supplier_prices.csv';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),5000)};
</script></html>'''.replace('PAYLOAD',payload)
