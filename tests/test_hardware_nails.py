"""Published quantity groups and schematic 3D nail geometry; not Revit approval."""
import math
import unittest
from types import SimpleNamespace as Obj
from test_connector_geometry import box,hanger,angle,rotated
import rt_connector_geometry as g
import rt_connector_placement as placement
import rt_hardware_nails as nails
from rt_layout import DEFAULTS,plan,owned_registered,OWNER,VERSION


def tie():
    return box((0,0,.15),(.045,1.375,3.8125))+box((0,0,-2.1875),(1.375,.045,-.15))


def ring():
    triangles=[]
    inner=[(.09/12*math.cos(i*math.pi/4),.09/12*math.sin(i*math.pi/4),0) for i in range(8)]
    outer=[(.7/12*math.cos(i*math.pi/4),.7/12*math.sin(i*math.pi/4),0) for i in range(8)]
    for i in range(8):
        j=(i+1)%8
        triangles.extend([(outer[i],outer[j],inner[j]),(outer[i],inner[j],inner[i])])
    return triangles


class TieAndNailTests(unittest.TestCase):
    def test_tie_contact_tabs_and_transition_do_not_depend_on_family_origin_axes(self):
        for geometry in (tie(),rotated(tie())):
            profile=g.tie_profile(geometry)
            self.assertEqual(profile['kind'],'tie')
            self.assertAlmostEqual(profile['details']['transition_gap_in'],.3)
            coord=tuple(Obj(X=x,Y=y,Z=z) for x,y,z in ((0,0,0),(1,0,0),(0,1,0)))
            profile['native_basis']=((1,0,0),(0,1,0),(0,0,1))
            for end in (0,1):
                item=dict(role='HURRICANE_STRAP',x=5,y=1 if end==0 else 9,beam_outward=(0,-1 if end==0 else 1),joist_width_in=1.5,beam_width_in=3,z_offset_in=-9.25)
                fit=placement.placement(profile,item,coord,8)
                self.assertAlmostEqual(abs(fit['datum'][0]-5),.75/12)
                self.assertAlmostEqual(fit['datum'][1],item['y']+(-1 if end==0 else 1)*1.5/12)
                self.assertAlmostEqual(fit['datum'][2],8-9.25/12)
                upper_direction=g.mul(fit['target'][2],profile['details']['upper_sign'])
                self.assertAlmostEqual(g.dot(upper_direction,(0,0,1)),1)

    def test_touching_coplanar_thin_end_faces_do_not_extend_the_upper_tab(self):
        triangles=box((0,0,0),(.045,1.375,3.8125))+box((0,0,-2.1875),(1.375,.045,0))
        profile=g.tie_profile(triangles)
        self.assertAlmostEqual(profile['details']['transition_gap_in'],0)

    def test_h25a_name_and_envelope_do_not_override_incompatible_tab_regions(self):
        triangles=(box((0,0,-1.4125),(.0625,1.375,3.8125))+
                   box((0,0,-2.1875),(1.375,.0625,2.9875)))
        with self.assertRaisesRegex(ValueError,'do not straddle its published plate line'):
            g.tie_profile(triangles,model='H2.5A')

    def test_paired_joists_put_tie_tabs_on_outer_faces_and_keep_them_when_decking_rotates(self):
        from rt_layout import hanger_groups
        for angle in (0,30):
            p=plan(dict(DEFAULTS,run_ft=19.5,span_ft=11,picture_frame=True,border_courses=2,
                        double_border_joists=True,supports_enabled=True,hurricane_symbol_uid='tie',
                        board_row_layout='Balanced edge rips',board_angle_deg=angle))
            ties=[h for h in p['hardware'] if h['role']=='HURRICANE_STRAP']
            self.assertTrue(any(h['joist_side']==-1 for h in ties));self.assertTrue(any(h['joist_side']==1 for h in ties))
            for h in ties:
                self.assertAlmostEqual(math.hypot(*h['joist_across']),1)
                self.assertAlmostEqual(sum(a*b for a,b in zip(h['joist_across'],h['beam_outward'])),0)
            if angle==0:
                for group in hanger_groups(p['members'],1.5):
                    if len(group)!=2:continue
                    self.assertTrue(all(h['joist_side']==-1 for h in ties if h['joist_key']==group[0]['key']))
                    self.assertTrue(all(h['joist_side']==1 for h in ties if h['joist_key']==group[1]['key']))

    def test_closed_mesh_hole_is_detected_but_outer_plate_loop_is_not_a_nail_hole(self):
        profile=dict(origin=(0,0,0),axes=((1,0,0),(0,1,0),(0,0,1)))
        holes=g.measured_holes(ring(),profile)
        self.assertEqual(len(holes),1)
        self.assertLess(g.size(holes[0]['center']),1.e-8)

    def test_recognized_nail_counts_sizes_and_unknown_model_omission(self):
        for name,count in (('LUS24',6),('LUS26',8),('LUS28',10),('LUS210',12),('LUS210-2',14),('C_L90_3d_Cad',10),('L70Z',8),('C_H25A_3d',10),('H2_5A',10)):
            spec=nails.schedule(name,DEFAULTS)
            self.assertEqual(sum(g['count'] for g in spec['groups']),count)
        self.assertIsNone(nails.schedule('custom hanger',DEFAULTS))
        self.assertIsNone(nails.schedule('LUS2100',DEFAULTS))
        self.assertIsNone(nails.schedule('LUS210-3',DEFAULTS))
        standard=nails.schedule('LUS210-2',dict(DEFAULTS,hanger_nail_header=nails.HEADER_MODES[1]))
        self.assertTrue(all(g['diameter_in']==.162 and g['length_in']==3.5 for g in standard['groups']))
        short=nails.schedule('LUS210-2',DEFAULTS)
        self.assertEqual([(g['diameter_in'],g['length_in']) for g in short['groups']],[(.148,1.5),(.148,3)])
        self.assertTrue(short['notes'])

    def test_individual_schematic_nails_match_schedule_and_double_shear_points_into_header(self):
        for model,profile in (('LUS210',g.hanger_profile(hanger(),1.5,9.25)),('L90',g.angle_profile(angle())),('H25A',g.tie_profile(tie()))):
            fit=dict(datum=(0,0,0),target=((1,0,0),(0,1,0),(0,0,1)))
            items,notes=nails.nail_items(profile,fit,dict(key='connector'),model,DEFAULTS)
            self.assertEqual(len(items),sum(row['count'] for row in nails.schedule(model,DEFAULTS)['groups']))
            self.assertEqual(len(items),len({item['key'] for item in items}))
            self.assertTrue(all(item['schematic'] and not item['measured_hole'] for item in items))
            self.assertTrue(any('schematic' in n for n in notes))
            pocket=[item for item in items if item['application']=='joist double-shear']
            self.assertEqual(len(pocket),len(set(round(item['head'][2],7) for item in pocket)))
            for item in items:
                self.assertAlmostEqual(g.size(item['direction']),1)
                if item['application']=='joist double-shear':
                    self.assertAlmostEqual(item['direction'][1],-math.sqrt(.5))
                    self.assertLess(item['direction'][0]*item['head'][0],0)

    def test_required_count_and_nails_off_do_not_double_count_connectors(self):
        p=plan(dict(DEFAULTS,run_ft=19.5,span_ft=11,picture_frame=True,border_courses=2,
                    double_border_joists=True,supports_enabled=True,hanger_symbol_uid='single',double_hanger_symbol_uid='double',
                    hurricane_symbol_uid='tie',corner_strap_symbol_uid='angle',
                    hardware_model_names=dict(HANGER='LUS210',DOUBLE_HANGER='LUS210-2',HURRICANE_STRAP='H25A',CORNER_STRAP='L90')))
        expected=sum({'HANGER':12,'DOUBLE_HANGER':14,'HURRICANE_STRAP':10,'CORNER_STRAP':10}[h['role']] for h in p['hardware'])
        self.assertEqual(p['counts']['hardware_nails'],expected)
        off=plan(dict(p['settings'],hardware_nails_enabled=False))
        self.assertNotIn('hardware_nails',off['counts'])

    def test_nails_are_eligible_only_with_exact_registry_ownership(self):
        record=dict(layout_id='deck',generation='a',element_uids=['nail'])
        stamp=dict(owner=OWNER,version=VERSION,layout_id='deck',generation='a',role='HARDWARE_NAIL')
        self.assertTrue(owned_registered(record,stamp,'nail'))
        self.assertFalse(owned_registered(record,stamp,'manual-nail'))

    def test_nail_registry_replaces_and_removes_individual_elements_with_hardware(self):
        import test_hardware_families as hardware
        fixture=hardware.HardwareRebuildTests();fixture.setUp()
        adapter=fixture.scope['rt_connector_placement'];adapter.ROLES=('HANGER',)
        adapter.build_profiles=lambda doc,symbols,items,*args:{('HANGER',fixture.symbol.UniqueId,None,None):{}}
        adapter.placement=lambda *args:dict(plane_key=(0,0,1,0),normal=(0,0,1),datum=(0,0,0),target=((1,0,0),(0,1,0),(0,0,1)),origin=(0,0,0))
        fixture.scope['rt_hardware_nails']=Obj(schedule=lambda *args:{'model':'test'},nail_items=lambda profile,fit,item,*args:(
            [dict(key=item['key']+'_nail_'+str(i),role='HARDWARE_NAIL',measured_hole=False) for i in range(2)],[]))
        fixture.scope['create_hardware_nail']=fixture.scope['create_hardware']
        fixture.planned['settings']['hardware_nails_enabled']=True
        first=fixture.build();self.assertEqual(first['counts']['hardware_nails'],4)
        self.assertEqual(sum(row['item']['role']=='HARDWARE_NAIL' for row in first['items']),4)
        storage=next(e for e in fixture.elements.values() if e.stamp.get('role')=='LAYOUT')
        fixture.planned['settings']['hardware_nails_enabled']=False
        second=fixture.build(storage,first)
        self.assertTrue(set(first['element_uids']).isdisjoint(fixture.elements))
        self.assertFalse(any(row['item']['role']=='HARDWARE_NAIL' for row in second['items']))
        self.assertIn(fixture.manual_uid,fixture.elements)

    def test_native_nail_shape_has_true_shank_length_and_perpendicular_head_ring(self):
        from test_hardware_families import Vector
        from test_clip_hardware_repairs import functions
        import rt_clip
        Vector.BasisZ=Vector(0,0,1);Vector.BasisX=Vector(1,0,0)
        recorded=[]
        scope=functions('rt_revit.py',{'create_hardware_nail'},dict(DB=Obj(XYZ=Vector),rt_clip=rt_clip,
            extrusion=lambda points,axis,length,steel:recorded.append((points,axis,length)) or 'solid',
            shape=lambda doc,solids,name,layout,item:solids))
        item=dict(head=(12,15,8),direction=(-math.sqrt(.5),-math.sqrt(.5),0),diameter_in=.148,nail_length_in=3,product='test')
        self.assertEqual(scope['create_hardware_nail'](None,item,'steel','deck'),['solid','solid'])
        self.assertAlmostEqual(recorded[0][2]*12,3)
        self.assertAlmostEqual(recorded[1][2]*12,.035)
        for point in recorded[0][0]:
            delta=point-Vector(*item['head'])
            self.assertAlmostEqual(delta.DotProduct(recorded[0][1]),0)
            self.assertAlmostEqual(delta.GetLength()*12,.148/2)

    def test_material_rows_keep_nails_as_each_and_separate_fastening_applications(self):
        import rt_pricing
        from test_clip_hardware_repairs import functions
        row=dict(layout_id='deck',layout_name='Deck',role='HARDWARE_NAIL',type_name='.148 x 3 hand nail | joist double-shear',
                 application='joist double-shear',length_ft=0,width_in='',depth_in='',materials=['HDG schematic'])
        groups=rt_pricing.item_groups([row,row],[])
        self.assertEqual(groups[0]['unit'],'EA');self.assertEqual(groups[0]['installed_count'],2)
        scope=functions('rt_schedules.py',{'row_values'},dict(scope_token=lambda key:'scope'))
        fields=scope['row_values'](row)
        self.assertEqual(fields['component'],'Hardware nail / joist double-shear')
        self.assertEqual(fields['product'],row['type_name'])


if __name__=='__main__':unittest.main()
