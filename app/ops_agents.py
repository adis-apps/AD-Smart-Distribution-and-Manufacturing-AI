"""Explainable operations agents for the packaging/distribution POC.
Synthetic transactions only. Corrections are proposed for human approval, never transmitted.
"""
from datetime import date, timedelta
import random
import pandas as pd
from sqlalchemy import text
from app.db import engine


def init_ops_tables():
    with engine.begin() as c:
        c.execute(text('''CREATE TABLE IF NOT EXISTS edi_transactions (
          transaction_id VARCHAR(40) PRIMARY KEY, transaction_type VARCHAR(10) NOT NULL,
          partner_id VARCHAR(40), customer_id VARCHAR(40), order_ref VARCHAR(40),
          product_id VARCHAR(40), sku_partner VARCHAR(80), uom VARCHAR(20), quantity INTEGER,
          amount NUMERIC(14,2), ship_to VARCHAR(80), event_date VARCHAR(10),
          status VARCHAR(30), raw_message TEXT, validation_result TEXT, proposed_fix TEXT,
          action_status VARCHAR(30) DEFAULT 'Needs Review')'''))
        c.execute(text('''CREATE TABLE IF NOT EXISTS supply_plan (
          plan_id VARCHAR(40) PRIMARY KEY, product_id VARCHAR(40) NOT NULL,
          forecast_qty INTEGER NOT NULL, open_customer_orders INTEGER NOT NULL,
          open_purchase_orders INTEGER NOT NULL, inventory_qty INTEGER NOT NULL,
          safety_stock INTEGER NOT NULL, supplier_eta VARCHAR(10), line_capacity_qty INTEGER,
          warehouse VARCHAR(80), as_of_date VARCHAR(10))'''))
        c.execute(text('''CREATE TABLE IF NOT EXISTS agent_action_log (
          action_id INTEGER PRIMARY KEY AUTOINCREMENT, agent_name VARCHAR(80), entity_id VARCHAR(80),
          action_type VARCHAR(80), proposal TEXT, status VARCHAR(30) DEFAULT 'Draft',
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'''))


def seed_ops_data():
    init_ops_tables()
    with engine.connect() as c:
        products = pd.read_sql(text('SELECT product_id, list_price FROM products ORDER BY product_id'), c)
        customers = pd.read_sql(text('SELECT customer_id FROM customers ORDER BY customer_id'), c)
        inv = pd.read_sql(text('SELECT product_id, available_qty FROM inventory'), c).set_index('product_id').to_dict('index')
    if products.empty or customers.empty: raise RuntimeError('Run python -m app.seed_data first')
    today=date.today(); rng=random.Random(6012026); txns=[]; plans=[]
    # Mix clean and problematic inbound/outbound documents for exception workflow demos.
    for i in range(1,31):
        p=products.iloc[(i*3)%len(products)]; pid=str(p.product_id); cid=str(customers.iloc[i%len(customers)].customer_id)
        typ=['850','850','855','856','810','997'][i%6]
        issue=['clean','unknown_sku','bad_uom','missing_shipto','qty_mismatch','amount_mismatch','missing_order_ref'][i%7]
        qty=rng.choice([100,250,500,1000,2500]); price=float(p.list_price or 1); amount=round(qty*price,2)
        if issue=='qty_mismatch' and typ in ('856','810'): qty=max(1,qty-25)
        if issue=='amount_mismatch' and typ=='810': amount=round(amount*1.04,2)
        sku=f'{pid}-TP' if issue!='unknown_sku' else 'UNKNOWN-TP-SKU'
        uom='CS' if issue!='bad_uom' else 'EA'; shipto='SHIP-001' if issue!='missing_shipto' else ''
        order_ref=f'PO-{1000+i}' if issue!='missing_order_ref' else ''
        status='Received' if issue=='clean' else 'Validation Needed'
        raw=f'Synthetic EDI {typ}; issue={issue}; partner=TP-{i%4+1}'
        proposed={
          'unknown_sku':'Resolve trading-partner SKU to internal product crosswalk; do not guess a product.',
          'bad_uom':'Confirm partner UOM conversion (EA/CS/PAL) and quantity semantics before accepting.',
          'missing_shipto':'Request/resolve a valid ship-to code from partner master data.',
          'qty_mismatch':'Compare PO, shipment, and invoice quantities; route variance for approval.',
          'amount_mismatch':'Reconcile invoice extension, price agreement, freight, and tax before posting.',
          'missing_order_ref':'Recover the original PO/order reference from partner control data.',
          'clean':'No deterministic pre-validation issue found; continue standard processing.'}[issue]
        txns.append(dict(transaction_id=f'EDI-{i:05d}',transaction_type=typ,partner_id=f'TP-{i%4+1}',customer_id=cid,
          order_ref=order_ref,product_id=pid,sku_partner=sku,uom=uom,quantity=qty,amount=amount,ship_to=shipto,
          event_date=(today-timedelta(days=i%5)).isoformat(),status=status,raw_message=raw,validation_result=None,
          proposed_fix=proposed,action_status='Needs Review' if issue!='clean' else 'Ready'))
    for i,row in enumerate(txns[:min(18,len(txns))],1):
        pid=row['product_id']; available=int(inv.get(pid,{}).get('available_qty',0)); forecast=rng.randint(300,1800); orders=rng.randint(200,1200); po=rng.randint(0,900); safety=rng.randint(100,400)
        plans.append(dict(plan_id=f'SUP-{i:04d}',product_id=pid,forecast_qty=forecast,open_customer_orders=orders,
          open_purchase_orders=po,inventory_qty=available,safety_stock=safety,
          supplier_eta=(today+timedelta(days=rng.randint(2,14))).isoformat(),line_capacity_qty=rng.randint(500,2500),
          warehouse=rng.choice(['Los Angeles DC','Dallas DC','Chicago DC']),as_of_date=today.isoformat()))
    with engine.begin() as c:
        for table,rows in [('edi_transactions',txns),('supply_plan',plans)]:
            c.execute(text(f'DELETE FROM {table}'))
            cols=list(rows[0].keys()); c.execute(text(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(':'+x for x in cols)})"),rows)
        c.execute(text('DELETE FROM agent_action_log'))
    return {'edi_transactions':len(txns),'supply_plans':len(plans)}


def _records(sql,params=None):
    with engine.connect() as c: return pd.read_sql(text(sql),c,params=params or {}).to_dict('records')


def validate_transaction(transaction_id):
    rows=_records('SELECT * FROM edi_transactions WHERE transaction_id=:id',{'id':transaction_id})
    if not rows: return None
    r=rows[0]; errors=[]; warnings=[]; typ=str(r['transaction_type'])
    if typ in ('850','855','856','810') and not r.get('order_ref'): errors.append('Missing PO/order reference')
    if typ in ('850','855','856','810') and not r.get('ship_to'): errors.append('Missing ship-to code')
    if typ in ('850','855','856','810') and str(r.get('sku_partner','')).startswith('UNKNOWN'): errors.append('Partner SKU has no verified crosswalk')
    if r.get('uom') not in ('EA','CS','PAL'): errors.append('Unrecognized UOM; approved partner conversion required')
    if not r.get('quantity') or int(r['quantity'])<=0: errors.append('Quantity must be positive')
    if typ=='810' and (r.get('amount') is None or float(r['amount'])<=0): errors.append('Invoice amount must be positive')
    if typ=='856' and r.get('quantity') is not None: warnings.append('Compare shipped quantity and carton/pack details against the accepted order before sending ASN')
    if typ=='997' and not r.get('order_ref'): warnings.append('Functional acknowledgement should reference the original transaction control number; demo data may not include it')
    result={'transaction_id':transaction_id,'transaction_type':typ,'partner_id':r['partner_id'],'errors':errors,'warnings':warnings,
      'valid':not errors,'severity':'High' if len(errors)>=2 else ('Medium' if errors or warnings else 'Low'),
      'recommended_action':r.get('proposed_fix') if errors or warnings else 'No blocking issue detected; continue standard validation.',
      'safe_to_auto_correct':False,'human_approval_required':bool(errors or warnings),
      'note':'Pre-validation heuristic for synthetic POC data. Validate against the partner implementation guide before production use.'}
    with engine.begin() as c:
        c.execute(text('UPDATE edi_transactions SET validation_result=:v,status=:s WHERE transaction_id=:id'),{'v':str(result),'s':'Rejected - Precheck' if errors else ('Warning - Review' if warnings else 'Precheck Passed'),'id':transaction_id})
    return result


def edi_exceptions():
    rows=_records('SELECT * FROM edi_transactions ORDER BY event_date DESC, transaction_id')
    output=[]
    for r in rows:
        v=validate_transaction(r['transaction_id'])
        r.update({'errors':v['errors'],'warnings':v['warnings'],'severity':v['severity'],'recommended_action':v['recommended_action'],'precheck_valid':v['valid']})
        output.append(r)
    return output


def supply_reconcile():
    rows=_records('SELECT s.*,p.product_name FROM supply_plan s JOIN products p ON p.product_id=s.product_id ORDER BY s.plan_id')
    for r in rows:
        demand=int(r['forecast_qty'])+int(r['open_customer_orders']); supply=int(r['inventory_qty'])+int(r['open_purchase_orders'])
        net=supply-demand; shortage=max(0,demand+int(r['safety_stock'])-supply)
        r['projected_net_qty']=net; r['shortage_to_safety_stock']=shortage
        r['status']='Shortage Risk' if shortage>0 else ('Potential Excess' if net>int(r['safety_stock'])*2 else 'Balanced')
        actions=[]
        if shortage>0: actions += ['Validate supplier ETA and expedite only if customer need date requires it','Check alternate warehouse or approved substitute','Draft PO quantity/expedite adjustment for planner approval']
        elif r['status']=='Potential Excess': actions += ['Review forecast assumptions and open PO cancellation/reschedule options']
        else: actions += ['Continue monitoring demand, open orders, and safety stock']
        r['recommended_actions']=actions
    return rows


def draft_action(agent_name,entity_id,action_type,proposal):
    with engine.begin() as c:
        result=c.execute(text('INSERT INTO agent_action_log (agent_name,entity_id,action_type,proposal,status) VALUES (:a,:e,:t,:p,\'Draft\')'),{'a':agent_name,'e':entity_id,'t':action_type,'p':proposal})
        aid=result.lastrowid if engine.dialect.name=='sqlite' else None
    return {'saved':True,'action_id':aid,'status':'Draft','message':'Draft logged for human review; nothing was transmitted or changed in a source system.'}
