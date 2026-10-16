"""Supported border fastening, actual grooves, orientation and guarded rebuild."""
import ast
import math
from pathlib import Path
import sys
from types import SimpleNamespace as Obj
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lib'))
import rt_border_fasteners as bf
import rt_geometry as geo
import rt_clip
import rt_board_profile
from rt_layout import DEFAULTS,plan,settings,owned_registered,OWNER,VERSION
import test_hardware_families as hardware
from test_clip_hardware_repairs import functions
Vector=hardware.Vector


class BorderFastenerTests(unittest.TestCase):
    def build(self,mode=1,**values):
        options=dict(DEFAULTS,picture_frame=True,board_row_layout='Balanced edge rips',field_edge_face_screws=False,border_fastening=bf.MODES[mode])
        options.update(values)
        return plan(options)

    def test_existing_layout_default_preserves_square_profiles_and_counts(self):
        p=self.build(0)
        self.assertEqual(p['counts']['clips'],190)
        self.assertFalse(p.get('face_fasteners'))
        self.assertTrue(all(b['edge_mode']=='square' for b in p['boards'] if b['role']=='BORDER'))

    def test_single_border_adds_only_supported_parallel_long_edge_clips(self):
        p=self.build()
        self.assertEqual(p['counts']['border_clips'],20)
        self.assertEqual(p['counts']['clips'],210)
        by_key={b['key']:b for b in p['boards']}
        for clip in p['clips']:
            if clip.get('clip_kind')!='border':continue
            a,b=[by_key[key] for key in clip['board_keys']]
            self.assertAlmostEqual(abs(bf.dot(bf.axes(a)[0],bf.axes(b)[0])),1)
            self.assertIsNotNone(bf.support_at((clip['x'],clip['y']),p['members'],p['settings']))
        for board in p['boards']:
            if board['role']=='BORDER':self.assertIn(board['edge_mode'],('left','right'))

    def test_double_borders_have_turned_clips_and_nonoverlapping_cross_backing(self):
        p=self.build(border_courses=2)
        self.assertEqual(p['counts']['border_clips'],52)
        self.assertTrue(any(abs(c.get('rotation_deg',0))==90 for c in p['clips']))
        added=[m for m in p['members'] if m.get('fastener_backing')]
        self.assertTrue(added)
        for new in added:
            for other in p['members']:
                if new is other:continue
                intersection=geo.intersect_convex(bf.member_outline(new,p['settings']),bf.member_outline(other,p['settings']))
                self.assertLessEqual(abs(geo.area(intersection)),bf.EPS)
        self.assertFalse(p['unsupported_border_fasteners'])

    def test_disabling_backing_flags_and_omits_unsupported_border_clips(self):
        p=self.build(border_courses=2,border_add_backing=False)
        self.assertTrue(p['unsupported_border_fasteners'])
        self.assertLess(p['counts']['border_clips'],52)
        self.assertFalse(any(m.get('fastener_backing') for m in p['members']))
        self.assertTrue(any('excluded from counts' in w for w in p['warnings']))

    def test_face_screws_keep_square_borders_and_real_board_support_clearances(self):
        p=self.build(2,border_courses=2)
        self.assertEqual(p['counts']['face_fasteners'],len(p['face_fasteners']))
        self.assertGreater(p['counts']['face_fasteners'],100)
        boards={b['key']:b for b in p['boards']}
        for screw in p['face_fasteners']:
            poly=bf.outline(boards[screw['board_key']]); point=(screw['x'],screw['y'])
            self.assertTrue(geo.point_inside(point,poly))
            self.assertGreaterEqual(min(geo.edge_distance(point,a,b) for a,b in zip(poly,poly[1:]+poly[:1])),1/12-bf.EPS)
            self.assertIsNotNone(bf.support_at(point,p['members'],p['settings']))
            self.assertTrue(screw['schematic'])
        self.assertTrue(all(b['edge_mode']=='square' for b in p['boards'] if b['role']=='BORDER'))

    def test_angles_and_returns_keep_unique_supported_positions(self):
        stepped=[(0,0),(20,0),(20,8),(10,8),(10,12),(0,12)]
        for mode in (1,2):
            for angle in (0,30,45):
                p=self.build(mode,border_courses=2,footprint_polygon=stepped,board_angle_deg=angle)
                pieces=p['clips']+p.get('face_fasteners',[])
                self.assertEqual(len(pieces),len({(round(c['x'],7),round(c['y'],7)) for c in pieces}))
                self.assertTrue(all(geo.point_inside((c['x'],c['y']),geo.frame(p['settings'])['polygon']) for c in pieces))

    def test_diagonal_single_border_does_not_put_clips_in_end_grain(self):
        p=self.build(board_angle_deg=30)
        self.assertEqual(p['counts']['border_clips'],0)
        self.assertTrue(any('End-to-side' in warning for warning in p['warnings']))

    def test_fasteners_off_removes_screws_and_auto_backing(self):
        p=self.build(2,border_courses=2,clips_enabled=False)
        self.assertFalse(p['clips']);self.assertFalse(p.get('face_fasteners'))
        self.assertFalse(any(m.get('fastener_backing') for m in p['members']))
        self.assertTrue(all(b['edge_mode']=='square' for b in p['boards'] if b['role']=='BORDER'))

    def test_breaker_stock_is_distinct_and_no_perpendicular_end_clips(self):
        p=plan(dict(DEFAULTS,run_ft=30,seam_border=True,border_fastening=bf.MODES[1]))
        self.assertEqual(p['counts']['border_clips'],0)
        field=[b for b in p['boards'] if b['role']=='BOARD']
        self.assertIn('right',{b['edge_mode'] for b in field})  # Exposed field rip not routed for a perpendicular breaker.

    def test_bad_mode_and_setbacks_stop_before_native_build(self):
        with self.assertRaisesRegex(ValueError,'fastening method'):settings(dict(border_fastening='unknown'))
        with self.assertRaisesRegex(ValueError,'setback'):self.build(2,border_end_setback_in=5)


class NativeFastenerTests(unittest.TestCase):
    def test_loaded_clip_uses_border_rotation_and_initial_family_transform(self):
        angles=[]; initial=math.radians(30)
        instance=Obj(Id=hardware.Id(2**40),GetTransform=lambda:Obj(BasisX=Vector(math.cos(initial),math.sin(initial))))
        db=Obj(XYZ=Obj(BasisZ=Vector(0,0,1)),Line=Obj(CreateBound=lambda *args:None),
               ElementTransformUtils=Obj(RotateElement=lambda doc,eid,axis,angle:angles.append(angle)))
        scope=functions('rt_revit.py',{'create_clip'},dict(DB=db,math=math,StructuralType=Obj(NonStructural='nonstructural'),
            world_point=lambda coord,x,y,z:Vector(x,y,z)))
        doc=Obj(Create=Obj(NewFamilyInstance=lambda *args:instance))
        deck=math.radians(20)
        scope['create_clip'](doc,dict(x=0,y=0,rotation_deg=90),
                             (None,Vector(math.cos(deck),math.sin(deck))),0,'level','symbol',{},'layout')
        self.assertAlmostEqual(angles[0],math.radians(80))

    def test_schematic_clip_rotates_geometry_with_the_border(self):
        contours=[]
        scope=functions('rt_revit.py',{'schematic_clip_solids'},dict(math=math,rt_clip=rt_clip,
            world_point=lambda coord,x,y,z:Vector(x,y,z),DB=Obj(XYZ=Obj(BasisZ=Vector(0,0,1))),
            extrusion=lambda points,*args:contours.append(points)))
        scope['schematic_clip_solids'](None,dict(x=2,y=3,rotation_deg=90),0,dict(nylon=1,steel=2))
        x,y=rt_clip.parts()[0][0][0]
        self.assertAlmostEqual(contours[0][0].X,2-y/12)
        self.assertAlmostEqual(contours[0][0].Y,3+x/12)

    def test_grooved_border_uses_swept_profile_and_miter_trim(self):
        calls=[]; trims=[]
        db=Obj(XYZ=Obj(BasisZ=Vector(0,0,1)),BooleanOperationsType=Obj(Intersect='intersect'),
               BooleanOperationsUtils=Obj(ExecuteBooleanOperation=lambda a,b,kind:trims.append(kind) or a))
        scope=functions('rt_revit.py',{'create_board'},dict(DB=db,rt_board_profile=rt_board_profile,
            world_point=lambda coord,x,y,z:Vector(x,y,z),shape=lambda doc,solids,*args:solids,
            extrusion=lambda points,direction,length,material:calls.append((points,direction,length)) or len(calls)))
        board=dict(role='BORDER',key='test',edge_mode='right',width_in=5.5,axis_vector=(0,1),
                   polygon=[(0,0),(5.5/12,5.5/12),(5.5/12,10),(0,10)])
        scope['create_board'](None,board,(None,Vector(1,0),Vector(0,1)),0,dict(board_thickness_in=.94),1,'layout')
        self.assertGreater(len(calls[0][0]),4)
        self.assertAlmostEqual(calls[0][1].Y,1);self.assertAlmostEqual(calls[0][2],10)
        self.assertEqual(trims,['intersect'])

    def test_face_fasteners_are_registered_replaced_and_removed_when_off(self):
        fixture=hardware.HardwareRebuildTests();fixture.setUp()
        fixture.scope['create_face_fastener']=fixture.scope['create_hardware_plane']
        p=dict(fixture.planned,hardware=[],face_fasteners=[dict(key='FACE_1',role='FACE_FASTENER'),dict(key='FACE_2',role='FACE_FASTENER')],
               settings=dict(fixture.planned['settings'],board_thickness_in=.94),counts=dict(face_fasteners=2))
        first=fixture.build(planned=p)
        self.assertEqual(len(first['element_uids']),2)
        self.assertTrue(all(owned_registered(first,fixture.elements[uid].stamp,uid) for uid in first['element_uids']))
        storage=next(e for e in fixture.elements.values() if e.stamp.get('role')=='LAYOUT')
        second=fixture.build(storage,first,p)
        self.assertTrue(set(first['element_uids']).isdisjoint(fixture.elements))
        off=dict(p,face_fasteners=[],counts=dict(face_fasteners=0))
        fixture.build(storage,second,off)
        self.assertTrue(set(second['element_uids']).isdisjoint(fixture.elements))
        self.assertIn(fixture.manual_uid,fixture.elements)


if __name__=='__main__':unittest.main()
