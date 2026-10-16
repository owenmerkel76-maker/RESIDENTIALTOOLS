# -*- coding: utf-8 -*-
"""Owned native schedules, quantities and reviewed retail/supplier pricing."""
import io
import json
import os
import traceback
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Architecture as AR
from pyrevit import forms,revit,script
import rt_revit as api
import rt_accessories
import rt_command
import rt_manager
import rt_quantities
import rt_forms
from rt_layout import number
from rt_layout import owned_registered


def measure(doc,parent,record,seen,cache=None):
    rows,volumes,warnings,board_lengths=[],{},[],[]
    cache={} if cache is None else cache
    names=cache.setdefault('types',{})
    coord=api.axes(parent['anchor'],parent['settings'])
    for entry in record['items']:
        uid=entry['unique_id']; item=entry['item']; role=item['role']
        if uid in seen: raise ValueError('One element appears in multiple quantity registries: '+uid)
        seen.add(uid); element=doc.GetElement(uid)
        if element is None:
            warnings.append('Missing registered element: '+uid); continue
        if not owned_registered(record,api.read_stamp(element),uid):
            raise ValueError('Quantity ownership changed for '+uid)
        if role in ('HARDWARE_PLANE','STAIR_PART','RAILING_PART'): continue
        length=0.0
        stock_eligible=True
        if role=='POST':
            points=api.vertices(element); length=max(p.Z for p in points)-min(p.Z for p in points)
        elif role in ('JOIST','RIM','BLOCK','JOINT_SUPPORT','BORDER_SUPPORT','BORDER_BACKING','BEAM'):
            location=element.Location
            if not isinstance(location,DB.LocationCurve): raise ValueError('Framing no longer has a curve: '+uid)
            length=location.Curve.Length
        elif role in ('BOARD','BORDER'):
            points=api.vertices(element)
            u=item.get('axis_vector')
            axis=(coord[1]*u[0]+coord[2]*u[1]) if u else (coord[2] if item.get('axis')=='B' else coord[1])
            length=max(p.DotProduct(axis) for p in points)-min(p.DotProduct(axis) for p in points)
            across=DB.XYZ(-axis.Y,axis.X,0)
            extent=max(p.DotProduct(across) for p in points)-min(p.DotProduct(across) for p in points)
            if extent>item['width_in']/12+.01/12:
                stock_eligible=False
                warnings.append('Board orientation/width changed; stock estimate excludes '+uid+'. Rebuild or verify the cut length.')
            else: board_lengths.append(length)
        elif role=='RAILING':
            length=sum(curve.Length for curve in element.GetPath())
        if role in ('BOARD','BORDER'):
            type_name='Schematic composite {0:g} x {1:g} in'.format(
                item['width_in'],parent['settings']['board_thickness_in'])
            if item.get('border_kind')=='breaker': type_name='Breaker board | '+type_name
        elif role=='CLIP' and parent['settings'].get('clip_mode')=='Schematic solids':
            type_name='Generic clip | 3/16 in schematic'
        elif role=='FACE_FASTENER': type_name='Generic deck face screw | schematic placeholder'
        elif role=='HARDWARE_NAIL':type_name=item['product']+' | '+item['application']
        else:
            type_id=element.GetTypeId(); key=api.id_value(type_id)
            if key not in names:
                type_element=doc.GetElement(type_id)
                names[key]=rt_accessories.label(type_element) if type_element is not None else role
            type_name=names[key]
        materials=[]
        # Native accessories are assembled from subcomponents. Avoid claiming a
        # partial/double-counted assembly volume; their detail stays in schedules.
        if role not in ('STAIR','RAILING'):
            for material_id in element.GetMaterialIds(False):
                material=doc.GetElement(material_id)
                volume=element.GetMaterialVolume(material_id)
                materials.append(material.Name)
                key=material.UniqueId
                current=volumes.setdefault(key,dict(name=material.Name,volume_ft3=0))
                current['volume_ft3']+=volume
        width=item.get('width_in',item.get('section_width_in',''))
        depth=item.get('depth_in',item.get('section_depth_in',''))
        if role in ('JOIST','RIM','JOINT_SUPPORT','BORDER_SUPPORT'):
            width=parent['settings']['joist_width_in']; depth=parent['settings']['joist_depth_in']
        elif role in ('BOARD','BORDER'): depth=parent['settings']['board_thickness_in']
        if role in ('JOIST','RIM','BLOCK','JOINT_SUPPORT','BORDER_SUPPORT','BORDER_BACKING','BEAM','POST') and hasattr(element,'Symbol'):
            current=api.post_dimensions(element.Symbol) if role=='POST' else api.type_dimensions(element.Symbol)
            keys=('joist_width_in','joist_depth_in')
            width=current.get(keys[0],''); depth=current.get(keys[1],'')
            if width=='' or depth=='':
                warnings.append('Current type section could not be read for '+uid+'; missing dimensions are left blank, not copied from the old build.')
        rows.append(dict(layout_name=parent['settings']['name'],layout_id=parent.get('layout_id',''),role=role,unique_id=uid,
                         element_id=api.id_value(element.Id),type_name=type_name,length_ft=length,
                         board_kind=item.get('border_kind'),application=item.get('application',''),
                         connector_model=item.get('connector_model',''),fastener_source=item.get('source_url',''),
                         stock_eligible=stock_eligible,stock_width_in=parent['settings'].get('board_width_in',item.get('width_in','')),
                         stock_length_ft=parent['settings'].get('stock_ft',20),
                         assembly_key=item.get('assembly_key',''),ply_index=item.get('ply_index',0),
                         stock_profile=('Routed border (verify stock)' if role=='BORDER' and item.get('edge_mode')!='square' else
                                        'Square-edge' if role=='BORDER' or item.get('edge_mode')=='square' else 'Grooved field'),
                         width_in=width,depth_in=depth,
                         materials=materials))
    return rows,volumes,warnings,board_lengths


def run_legacy():
    doc=revit.doc
    if doc is None or doc.IsFamilyDocument or str(doc.Application.VersionNumber) not in ('2025','2027'):
        forms.alert('Open a Revit 2025/2027 project.',title='Material List'); return
    folder,path,log=rt_command.log_session(doc,'Material List')
    try:
        parents=api.layout_records(doc)
        if not parents: forms.alert('Build a managed deck first.',title='Material List'); return
        labels=['All managed decks']+[rt_manager._label(record) for storage,record in parents]
        choice=forms.SelectFromList.show(labels,title='Material List | Scope',multiselect=False,button_name='Report')
        if choice is None: return
        selected=parents if choice==labels[0] else [parents[labels.index(choice)-1]]
        def validate_options(values):
            return dict(extra=number(values['extra'],'Extra board allowance (%)',0,100),
                        kerf=number(values['kerf'],'Saw kerf (inches)',0,1),
                        trim=number(values['trim'],'Total end trim (inches)',0,24))
        inputs=rt_forms.show('Material List','Installed quantities stay separate from purchasing estimates. Square-edge and grooved stock/materials are packed separately.',
            [dict(key='extra',label='Extra board-order allowance (%)',value=10),
             dict(key='kerf',label='Saw kerf between cuts (inches)',value=.125),
             dict(key='trim',label='Total end-trim allowance per stock board (inches)',value=0)],validate_options,
            lambda v:'Extra {0:g}% | Kerf {1:g} in | Total end trim {2:g} in per board.'.format(v['extra'],v['kerf'],v['trim']),'Export quantities')
        if inputs is None: return
        extra,kerf,trim=inputs['extra'],inputs['kerf'],inputs['trim']
        rows,volumes,warnings,stock,seen=[],{},[],[],set(); cache={}
        for storage,parent in selected:
            children=rt_accessories.records(doc,parent['layout_id'])
            deck_rows=[]
            for record in [parent]+[child for child_storage,child in children]:
                current,mats,notes,cuts=measure(doc,parent,record,seen,cache)
                rows.extend(current); deck_rows.extend(current); warnings.extend(notes)
                for key,value in mats.items():
                    target=volumes.setdefault(key,dict(name=value['name'],volume_ft3=0))
                    target['volume_ft3']+=value['volume_ft3']
                if record.get('parent_generation') and record['parent_generation']!=parent['generation']:
                    warnings.append('Stairs/railings were built for an earlier deck generation; verify alignment and rerun their commands.')
            estimates=rt_quantities.grouped_stock(deck_rows,parent['settings']['stock_ft'],kerf,trim,extra)
            for estimate in estimates:
                estimate['layout_name']=parent['settings']['name']
                if not estimate['estimate_complete']:
                    warnings.append('Ordering withheld for {0} / {1}: a cut exceeds usable stock after trim.'.format(parent['settings']['name'],estimate['stock_profile']))
            stock.extend(estimates)
        grouped={}
        for row in rows:
            key=(row['role'],row['type_name'],', '.join(row['materials']))
            value=grouped.setdefault(key,dict(count=0,length_ft=0))
            value['count']+=1; value['length_ft']+=row['length_ft']
        installed=[['role','type','materials','installed_count','installed_length_ft']]
        for key,value in sorted(grouped.items()): installed.append(list(key)+[value['count'],value['length_ft']])
        pieces=[['layout','role','element_id','unique_id','type','length_ft','width_in','depth_in','materials']]
        pieces.extend([r['layout_name'],r['role'],r['element_id'],r['unique_id'],r['type_name'],r['length_ft'],
                       r['width_in'],r['depth_in'],', '.join(r['materials'])] for r in rows)
        material_rows=[['material','modeled_volume_ft3']]+[[v['name'],v['volume_ft3']] for v in volumes.values()]
        order=[['layout','profile','materials','stock_width_in','thickness_in','stock_length_ft','estimated_stock_boards','extra_percent','order_with_extra','installed_cut_length_ft','complete']]
        order.extend([e['layout_name'],e['stock_profile'],', '.join(e['materials']),e['stock_width_in'],e['thickness_in'],e['board_stock_ft'],e['stock_pieces'] if e['stock_pieces'] is not None else '',extra,e['order_with_allowance'] if e['order_with_allowance'] is not None else '',e['installed_length_ft'],e['estimate_complete']] for e in stock)
        for name,table in (('installed_quantities.csv',installed),('piece_list.csv',pieces),('modeled_material_volumes.csv',material_rows),('board_order_estimate.csv',order)):
            with io.open(os.path.join(folder,name),'w',encoding='utf-8-sig') as stream: stream.write(rt_quantities.csv_text(table))
        limitations=['Stock groups separate profiles/materials and use entered kerf/end trim; no ripped-width recovery or optimized nesting. Manual rotations/oversized cuts require review.',
                     'Native stairs/railings are counted as assemblies/paths. Use Revit schedules for their tread/stringer/baluster materials.',
                     'Only registered modeled nails/screws are counted. Unknown connector nail schedules, post bases/caps and footings are not inferred.',
                     'Copied/unregistered manual elements are excluded.']
        report=dict(installed_pieces=rows,materials=list(volumes.values()),board_stock=stock,warnings=warnings,limitations=limitations)
        with io.open(os.path.join(folder,'material_list.json'),'w',encoding='utf-8') as stream: stream.write(api.text_type(json.dumps(report,indent=2)))
        log('Exported read-only material list: '+str(len(rows))+' installed instances/assemblies.')
        action=forms.alert('Exported {0} installed instances/assemblies.\n\nReports: {1}\n\n{2}\n\n{3}'.format(
            len(rows),folder,'\n'.join(warnings),'\n'.join(limitations)),title='Material List | Complete',
            options=['Open reports','Close'])
        if action=='Open reports': os.startfile(folder)
    except Exception:
        detail=traceback.format_exc(); log(detail); script.get_logger().error(detail)
        forms.alert('Material report stopped. Model unchanged.\n\n'+detail[-1000:]+'\nLog: '+path,title='Material List | Error')


def collect_current(doc,parents,extra=10,kerf=.125,trim=0):
    rows=[]; stock=[]; warnings=[]; seen=set(); cache={}
    for storage,parent in parents:
        deck_rows=[]
        for record in [parent]+[child for child_storage,child in rt_accessories.records(doc,parent['layout_id'])]:
            current,mats,notes,cuts=measure(doc,parent,record,seen,cache)
            rows.extend(current); deck_rows.extend(current); warnings.extend(notes)
            if record.get('parent_generation') and record['parent_generation']!=parent['generation']:
                warnings.append('Rerun stairs/railings built for an earlier deck generation.')
        stock.extend(rt_quantities.grouped_stock(deck_rows,parent['settings']['stock_ft'],kerf,trim,extra))
    return rows,stock,warnings


def run():
    """Schedules first, or one clear pricing/template CSV; detail exports optional."""
    doc=revit.doc
    if doc is None or doc.IsFamilyDocument or str(doc.Application.VersionNumber) not in ('2025','2027'):
        forms.alert('Open a Revit 2025/2027 project.',title='Material List'); return
    folder,path,log=rt_command.log_session(doc,'Material List')
    committed=False
    try:
        parents=api.layout_records(doc)
        if not parents: forms.alert('Build a managed deck first.',title='Material List'); return
        choices=[('All managed decks','all')]+[(rt_manager._label(record),record['layout_id']) for storage,record in parents]
        def validate(values):
            result=dict(action=values['action'],scope=values['scope'],prices=values['prices'].strip(),zip=values['zip'].strip(),extra=10,kerf=.125,trim=0)
            if values['action'] in ('csv','online'):
                result.update(extra=number(values['extra'],'Extra board allowance (%)',0,100),
                              kerf=number(values['kerf'],'Saw kerf (inches)',0,1),trim=number(values['trim'],'End trim (inches)',0,24))
                if result['prices']:
                    import rt_pricing
                    rt_pricing.read_prices(result['prices'])
            if values['action']=='online':
                import re
                if not re.match(r'^\d{5}$',result['zip']): raise ValueError('Enter a five-digit store ZIP code.')
            return result
        instructions=dict(schedules='Create/update native category schedules in the Project Browser and open one. Refresh after manual edits or copies.',
                          csv='Export one materials_and_pricing.csv. Missing prices stay blank. Extra/kerf/trim apply to composite stock estimates.',
                          template='Export supplier_prices.csv with stable item keys and blank prices. Fill unit_price, supplier and price_date; then import for a priced CSV.',
                          online='Open a Lowe\'s/Home Depot price worksheet. Exact product URLs in your optional CSV get a public-offer lookup; all matches, packs and local prices need review.',
                          details='Open the previous detailed exports workflow for individual pieces, volumes and diagnostics.')
        values=rt_forms.show('Material List','Use Revit schedules for installed quantities, or one CSV for materials/pricing. Supplier prices are optional; no online prices are guessed.',
            [dict(key='action',label='What would you like to create?',kind='choice',choices=[('Revit schedules (recommended)','schedules'),('Materials + pricing CSV','csv'),('Lowe\'s / Home Depot pricing worksheet','online'),('Supplier pricing template CSV','template'),('Detailed legacy reports','details')],value='schedules'),
             dict(key='scope',label='Deck scope',kind='choice',choices=choices,value='all'),
             dict(key='prices',label='Optional supplier pricing CSV (pricing export / online worksheet)',kind='file',value=''),
             dict(key='zip',label='Retail store ZIP — online worksheet',value='19464'),
             dict(key='extra',label='Extra composite-stock allowance (%) — CSV only',value=10),
             dict(key='kerf',label='Saw kerf between stock cuts (inches) — CSV only',value=.125),
             dict(key='trim',label='Total end trim per stock board (inches) — CSV only',value=0)],
            validate,lambda v:instructions[v['action']],'Create selected output')
        if values is None: return
        if values['action']=='details': run_legacy(); return
        selected=parents if values['scope']=='all' else [(storage,parent) for storage,parent in parents if parent['layout_id']==values['scope']]
        if values['action']=='schedules':
            import rt_schedules
            # All current owned pieces retain membership when refreshing a
            # schedule filtered to one selected deck.
            rows,stock,warnings=collect_current(doc,parents)
            views,excluded=rt_schedules.refresh(doc,rows,values['scope'],folder,log)
            committed=True
            view=next((view for view in views if view.Definition.CategoryId.Equals(DB.ElementId(DB.BuiltInCategory.OST_StructuralFraming))),views[0] if views else None)
            if view is not None: revit.uidoc.RequestViewChange(view)
            forms.alert('Created/refreshed {0} Revit schedules under Schedules/Quantities in the Project Browser.\n\n'
                        'Pieces are installed counts; each beam ply counts separately. Open rows/fields in Revit as usual.\n'
                        'Refresh Material List after manual geometry/type edits or copies. Generated rebuilds refresh planned membership/lengths.\n\n'
                        '{1}\nLog: {2}'.format(len(views),'\n'.join(warnings),path),title='Material List | Revit schedules')
            return
        import rt_pricing
        rows,stock,warnings=collect_current(doc,selected,values['extra'],values['kerf'],values['trim'])
        groups=rt_pricing.item_groups(rows,stock)
        if values['action']=='online':
            import rt_online_prices
            existing=rt_pricing.read_prices(values['prices']) if values['prices'] else {}
            prices={}
            for group in groups:
                row=dict((key,'') for key in rt_pricing.PRICE_COLUMNS)
                row.update(item_key=group['item_key'],description=group['description'],unit=group['unit'],currency='USD',price_zip=values['zip'])
                row.update(existing.get(group['item_key'],{})); prices[group['item_key']]=row
            count=sum(bool(row['source_url']) for row in prices.values())
            if count:
                with forms.ProgressBar(title='Reviewing public retail offers ({value} of {max_value})',cancellable=True) as bar:
                    def progress(value):
                        bar.update_progress(value,count)
                        return not bar.cancelled
                    prices=rt_online_prices.lookup(prices,values['zip'],progress=progress)
            output=os.path.join(folder,'retail_price_review.html')
            with io.open(output,'w',encoding='utf-8') as stream: stream.write(rt_online_prices.worksheet(groups,prices,values['zip']))
            log('Created retailer price worksheet for ZIP '+values['zip']+'; public offers are unverified until user review.')
            os.startfile(output)
            return
        if values['action']=='template':
            output=os.path.join(folder,'supplier_prices.csv'); content=rt_pricing.template_text(groups)
            message='Fill the blank unit_price values, supplier and price_date. Units: STOCK = composite stock board, LF = installed linear foot, EA = installed piece. Then choose Materials + pricing CSV and browse to this file.'
        else:
            prices=rt_pricing.read_prices(values['prices']) if values['prices'] else {}
            report=rt_pricing.priced_report(groups,prices)
            output=os.path.join(folder,'materials_and_pricing.csv'); content=rt_pricing.report_text(report)
            totals=', '.join(currency+' '+total for currency,total in sorted(report['priced_subtotals'].items())) or 'No prices supplied'
            message='Priced subtotal: '+totals+'\nUnpriced/review lines: '+str(report['unpriced_lines'])+'\n\n'+report['notes']
        with io.open(output,'w',encoding='utf-8-sig') as stream: stream.write(content)
        log('Exported '+output)
        choice=forms.alert(message+'\n\n'+('\n'.join(warnings)+'\n' if warnings else '')+'File: '+output,
                           title='Material List | CSV ready',options=['Open CSV','Open folder','Close'])
        if choice=='Open CSV': os.startfile(output)
        elif choice=='Open folder': os.startfile(folder)
    except Exception:
        detail=traceback.format_exc(); log(detail); script.get_logger().error(detail)
        state='Schedule changes were committed; a later display/report step failed.' if committed else 'Material List stopped; no schedule transaction was committed.'
        forms.alert(state+'\n\n'+detail[-1200:]+'\nLog: '+path,title='Material List | Error')
