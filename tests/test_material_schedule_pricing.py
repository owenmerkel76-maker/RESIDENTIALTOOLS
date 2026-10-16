"""Built-up support geometry, native schedule orchestration and price contracts."""
import ast
import csv
import io
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import patch
from contextlib import nullcontext
import os
import re

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lib'))
from rt_layout import DEFAULTS,plan,beam_ply_items,settings
import rt_pricing as pricing
import rt_online_prices as online
import test_hardware_families as hardware
Id=hardware.Id


def function(name,scope):
    tree=ast.parse((ROOT/'lib/rt_schedules.py').read_text(encoding='utf-8'))
    node=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'rt_schedules.py','exec'),scope)
    return scope[name]


class BeamPlyTests(unittest.TestCase):
    def test_two_three_plies_touch_and_keep_post_tie_assembly_counts(self):
        for angle in (0,30,45):
            for count in (2,3):
                p=plan(dict(DEFAULTS,supports_enabled=True,hurricane_symbol_uid='tie',beam_plies=count,board_angle_deg=angle))
                self.assertEqual(p['counts']['beam_assemblies'],2)
                self.assertEqual(p['counts']['beams'],2*count)
                self.assertEqual(p['counts']['hurricane_straps'],20)
                self.assertEqual(len(p['posts']),6)
                for beam in p['beams']:
                    pieces=beam_ply_items(beam); a,b=beam['a'],beam['b']
                    length=math.hypot(b[0]-a[0],b[1]-a[1]); normal=(-(b[1]-a[1])/length,(b[0]-a[0])/length)
                    positions=sorted(sum((piece['a'][j]-a[j])*normal[j] for j in (0,1)) for piece in pieces)
                    self.assertTrue(all(abs(v-u-1.5/12)<1.e-7 for u,v in zip(positions,positions[1:])))
                    self.assertAlmostEqual(sum(positions),0)
                    self.assertTrue(all(piece['section_width_in']==1.5 for piece in pieces))

    def test_35_foot_beam_is_cut_over_posts_without_exceeding_stock(self):
        p=plan(dict(DEFAULTS,run_ft=35,supports_enabled=True,beam_plies=3))
        self.assertEqual(p['counts']['beams'],12)
        for beam in p['beams']:
            pieces=beam_ply_items(beam)
            self.assertEqual(len(pieces),6)
            post_x=[post['x'] for post in p['posts'] if post['beam_key']==beam['key']]
            for piece in pieces:
                self.assertLessEqual(math.dist(piece['a'],piece['b']),20+1.e-7)
                for x in (piece['a'][0],piece['b'][0]):
                    if 1.e-7<x<35-1.e-7: self.assertTrue(any(abs(x-support)<1.e-7 for support in post_x))
            self.assertAlmostEqual(sum(math.dist(piece['a'],piece['b']) for piece in pieces),105)

    def test_invalid_fractional_ply_count_and_unsupported_stock_split_stop(self):
        for value in (1,2.5,4):
            with self.assertRaises(ValueError): settings(dict(DEFAULTS,beam_plies=value))
        with self.assertRaisesRegex(ValueError,'beam stock-length split'):
            plan(dict(DEFAULTS,run_ft=35,supports_enabled=True,post_spacing_ft=20,beam_stock_ft=8))

    def test_native_rebuild_registers_every_ply_and_replaces_previous_pieces(self):
        fixture=hardware.HardwareRebuildTests(); fixture.setUp()
        s=dict(DEFAULTS,level_uid='level',supports_enabled=True)
        planned=plan(s); planned.update(members=[],boards=[],clips=[],hardware=[],posts=[],face_fasteners=[])
        fixture.scope['beam_ply_items']=beam_ply_items
        created=[]
        def create_member(doc,item,*args):
            fixture.serial+=1
            element=Obj(Id=Id(fixture.serial),UniqueId=str(fixture.serial),stamp={})
            fixture.elements[element.UniqueId]=element; created.append(item)
            return element
        fixture.scope['create_member']=create_member
        first=fixture.build(planned=planned)
        self.assertEqual(len(created),4)
        self.assertEqual([entry['item']['ply_index'] for entry in first['items']],[1,2,1,2])
        storage=next(element for element in fixture.elements.values() if element.stamp.get('role')=='LAYOUT')
        second=fixture.build(storage,first,planned)
        self.assertEqual(len(second['element_uids']),4)
        self.assertTrue(set(first['element_uids']).isdisjoint(fixture.elements))
        self.assertIn(fixture.manual_uid,fixture.elements)


class ScheduleTests(unittest.TestCase):
    def test_refresh_excludes_only_unregistered_scope_markers_and_reuses_owned_view(self):
        class Parameter:
            HasValue=True; IsReadOnly=False
            def __init__(self,value): self.value=value
            def AsString(self): return self.value
            def Set(self,value): self.value=value; return True
        category=Obj(Id=Id(-10),Name='Structural Framing')
        def element(uid,scope):
            parameter=Parameter(scope)
            return Obj(UniqueId=uid,Category=category,get_Parameter=lambda key:parameter,scope=parameter,geometry='preserved')
        owned=element('owned','RTD|deck'); copied=element('copied','RTD|deck'); other=element('manual','OTHER')
        view=Obj(Name='User named managed schedule',Id=Id(20))
        class Collector:
            def OfClass(self,kind): return [view]
            def OfCategoryId(self,category): return self
            def WhereElementIsNotElementType(self): return [owned,copied,other]
        stamped=[]; configured=[]; written=[]
        api=Obj(id_value=lambda eid:eid.Value,read_stamp=lambda view:dict(owner='owner',role='MATERIAL_SCHEDULE',category_id=-10),
                transaction=lambda *args:nullcontext(),write_stamp=lambda view,value:written.append(value))
        scope=dict(DB=Obj(FilteredElementCollector=lambda doc:Collector(),ViewSchedule='schedule',
                         Category=Obj(GetCategory=lambda doc,eid:category),ElementId=Id),api=api,OWNER='owner',VERSION=1,
                   bind_parameters=lambda *args:{},field_guid=lambda key:key,PREFIX='RTD|',
                   set_values=lambda element,values,required:stamped.append(element.UniqueId),row_values=lambda row:row,
                   owned_schedule=lambda *args:view,configure_schedule=lambda *args:configured.append(args),os=os,re=re)
        refresh=function('refresh',scope)
        doc=Obj(GetElement=lambda uid:owned,Regenerate=lambda:None)
        views,excluded=refresh(doc,[dict(unique_id='owned',layout_id='deck',layout_name='Deck')],'all','reports',lambda text:None)
        self.assertEqual(views,[view]); self.assertEqual(excluded,1); self.assertEqual(stamped,['owned'])
        self.assertEqual(copied.scope.value,''); self.assertEqual(other.scope.value,'OTHER')
        self.assertEqual(copied.geometry,'preserved'); self.assertEqual(view.Name,'User named managed schedule')
        self.assertEqual(len(configured),1); self.assertEqual(written[0]['layout_id'],'SCHEDULE:all')

    def test_same_name_parameter_conflict_is_rejected_before_binding(self):
        class Iterator:
            def Reset(self): self.done=False
            def MoveNext(self):
                if self.done: return False
                self.done=True; return True
            Key=Obj(Name='RTD_Scope',Id=Id(20)); Current=Obj()
        app=Obj(Create=Obj(NewCategorySet=lambda:None))
        scope=dict(FIELDS=[('scope','RTD_Scope','text','Managed scope')],
                   definitions=lambda *args:{'scope':Obj()},field_guid=lambda key:'own-guid',
                   DB=Obj(SharedParameterElement=Obj(Lookup=lambda *args:Obj(Id=Id(21)))))
        bind=function('bind_parameters',scope)
        doc=Obj(Application=app,ParameterBindings=Obj(ForwardIterator=lambda:Iterator()))
        with self.assertRaisesRegex(ValueError,'unrelated parameter will not be replaced'):
            bind(doc,[],'definition-file')

    def test_scope_and_numeric_section_metadata_do_not_merge_materials(self):
        scope=dict(scope_token=lambda value:'RTD|'+value)
        values=function('row_values',scope)
        row=dict(layout_id='deck',layout_name='Deck',role='BEAM',type_name='2x10',width_in=1.5,depth_in=9.25,
                 length_ft=17.50000000001,materials=['Treated'],assembly_key='BEAM_1',ply_index=2)
        first=values(row); second=values(dict(row,materials=['Untreated']))
        self.assertEqual(first['scope'],'RTD|deck'); self.assertEqual(first['component'],'Beam ply')
        self.assertEqual(first['cut'],17.5); self.assertEqual(first['ply'],2)
        self.assertNotEqual(first['group'],second['group'])

    def test_temporary_shared_parameter_path_is_restored_on_failure(self):
        app=Obj(SharedParametersFilename='existing-user-file',OpenSharedParameterFile=lambda:None)
        create=function('definitions',dict(io=Obj(open=lambda *args,**kwargs:io.StringIO())))
        with self.assertRaisesRegex(ValueError,'temporary takeoff parameter file'):
            create(app,'our-parameters.txt')
        self.assertEqual(app.SharedParametersFilename,'existing-user-file')

    def test_schedule_uses_registered_scope_grouped_native_counts_and_total_lengths(self):
        specs=ast.parse((ROOT/'lib/rt_schedules.py').read_text(encoding='utf-8'))
        fields=ast.literal_eval(next(node.value for node in specs.body if isinstance(node,ast.Assign) and any(getattr(n,'id','')=='FIELDS' for n in node.targets)))
        class Definition:
            def __init__(self): self.fields=[]; self.filters=[]; self.sorts=[]
            def ClearFields(self): self.fields=[]
            def ClearFilters(self): self.filters=[]
            def ClearSortGroupFields(self): self.sorts=[]
            def GetSchedulableFields(self): return [Obj(ParameterId=Id(i+1)) for i in range(len(fields))]
            def AddField(self,item):
                result=Obj(FieldId=len(self.fields)); self.fields.append(result); return result
            def AddSortGroupField(self,value): self.sorts.append(value)
            def AddFilter(self,value): self.filters.append(value)
        db=Obj(ScheduleFieldDisplayType=Obj(Totals='totals'),ScheduleFieldType=Obj(Count='count'),
               ScheduleSortGroupField=lambda fid:fid,ScheduleFilterType=Obj(BeginsWith='prefix',Equal='exact'),
               ScheduleFilter=lambda fid,kind,value:(fid,kind,value))
        configure=function('configure_schedule',dict(FIELDS=fields,DB=db,api=Obj(id_value=lambda value:value.Value),PREFIX='RTD|',scope_token=lambda value:'RTD|'+value))
        ids=dict((field[0],Id(i+1)) for i,field in enumerate(fields)); definition=Definition()
        configure(Obj(Definition=definition),ids,'deck')
        self.assertFalse(definition.IsItemized); self.assertEqual(len(definition.sorts),4)
        self.assertEqual(definition.filters[0][1:],('exact','RTD|deck'))
        self.assertEqual(definition.fields[-1].ColumnHeading,'Pieces')
        self.assertTrue(any(getattr(field,'DisplayType','')=='totals' for field in definition.fields))
        configure(Obj(Definition=definition),ids,'all')
        self.assertEqual(len(definition.fields),len(fields)+1)
        self.assertEqual(definition.filters[0][1:],('prefix','RTD|'))


class PricingTests(unittest.TestCase):
    def group(self,unit='LF'):
        return dict(item_key='one',description='2x10 lumber',unit=unit,installed_count=3,installed_length_ft=10,
                    stock_quantity=2 if unit=='STOCK' else None,stock_complete=True)
    def price(self,unit='LF',price='2.50',currency='USD'):
        return dict(item_key='one',description='2x10',unit=unit,unit_price=price,currency=currency,
                    supplier='Retailer',source_url='',price_date='2026-10-14')

    def test_units_and_currencies_have_separate_honest_subtotals(self):
        group=self.group(); second=dict(self.group(),item_key='two')
        third=dict(self.group('STOCK'),item_key='three')
        report=pricing.priced_report([group,second,third],dict(one=self.price(),two=self.price('EA','3','CAD'),three=self.price('STOCK','30')))
        self.assertEqual(report['priced_subtotals'],dict(USD='85.00',CAD='9.00'))
        self.assertTrue(report['complete'])
        blank=pricing.priced_report([group],{})
        self.assertEqual(blank['rows'][0]['extended_price'],''); self.assertFalse(blank['complete'])

    def test_board_stock_prices_use_ordered_stock_quantity_and_hold_incomplete_estimates(self):
        report=pricing.priced_report([self.group('STOCK')],dict(one=self.price('STOCK','30')))
        self.assertEqual(report['priced_subtotals'],dict(USD='60.00'))
        report=pricing.priced_report([dict(self.group('STOCK'),stock_complete=False,stock_quantity=None)],dict(one=self.price('STOCK','30')))
        self.assertFalse(report['complete']); self.assertFalse(report['priced_subtotals'])

    def test_supplier_template_roundtrips_unicode_and_rejects_duplicate_prices(self):
        groups=[dict(self.group(),description='Treated — 2x10')]
        content=[pricing.template_text(groups)]
        with patch.object(pricing.os.path,'getsize',return_value=100),patch.object(pricing.io,'open',side_effect=lambda *args,**kwargs:io.StringIO(content[0])):
            self.assertEqual(pricing.read_prices('prices.csv')['one']['unit_price'],'')
            content[0]=pricing.template_text(groups+[groups[0]])
            with self.assertRaisesRegex(ValueError,'Duplicate'): pricing.read_prices('prices.csv')

    def test_unverified_online_offer_never_enters_estimated_total(self):
        price=dict(self.price(),online_status='PUBLIC OFFER',verified='')
        self.assertFalse(pricing.priced_report([self.group()],dict(one=price))['priced_subtotals'])
        price['verified']='yes'
        self.assertEqual(pricing.priced_report([self.group()],dict(one=price))['priced_subtotals'],dict(USD='25.00'))


class OnlinePriceTests(unittest.TestCase):
    PAGE='<script type="application/ld+json">{"@type":"Product","name":"Treated 2x10 x16","offers":{"@type":"Offer","price":"24.00","priceCurrency":"USD"}}</script>'
    def test_exact_public_offer_and_units_are_reviewed_not_claimed_local(self):
        price=dict(item_key='one',source_url='https://www.homedepot.com/p/test/123?tracking=removed',retail_units='16',unit='LF')
        result=online.lookup(dict(one=price),'19464',fetch=lambda url:self.PAGE)['one']
        self.assertEqual(result['unit_price'],'1.500000'); self.assertEqual(result['verified'],'')
        self.assertEqual(result['source_url'],'https://www.homedepot.com/p/test/123')
        self.assertIn('VERIFY',result['online_status'])

    def test_unavailable_and_ambiguous_offers_stay_unpriced(self):
        with self.assertRaises(ValueError): online.extract_offer('<h1>Choose a store for prices</h1>')
        with self.assertRaises(ValueError): online.extract_offer(self.PAGE+self.PAGE.replace('24.00','25.00'))
        price=dict(source_url='https://www.lowes.com/pd/test/123',retail_units='1')
        def blocked(url): raise ValueError('HTTP 403')
        result=online.lookup(dict(one=price),'19464',fetch=blocked)['one']
        self.assertEqual(result['unit_price'],''); self.assertIn('MANUAL REVIEW',result['online_status'])

    def test_only_official_product_hosts_and_paths_are_requested(self):
        for url in ('http://www.lowes.com/pd/a','https://lowes.com.evil.test/pd/a','https://localhost/p/a','https://www.homedepot.com/c/login'):
            with self.assertRaises(ValueError): online.product_url(url)

    def test_worksheet_escapes_external_names_and_keeps_verification_control(self):
        group=dict(item_key='one',description='</script><img src=x>',installed_count=2,installed_length_ft=12,
                   stock_quantity=None,unit='LF')
        page=online.worksheet([group],{},'19464')
        self.assertEqual(page.count('</script>'),1)
        self.assertIn('Save supplier_prices.csv',page); self.assertIn('19464',page)


if __name__=='__main__': unittest.main()
