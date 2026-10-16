"""Regressions for missed clip supports and connector placement conventions."""
import ast
import math
from pathlib import Path
import sys
from types import SimpleNamespace as Obj
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lib'))
import rt_layout as layout
import rt_simpson_catalog as catalog
from test_hardware_families import Vector,Id


def functions(module,names,scope):
    tree=ast.parse((ROOT/'lib'/module).read_text(encoding='utf-8'))
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),module,'exec'),scope)
    return scope


class ClipRepairTests(unittest.TestCase):
    def setUp(self):
        self.rows=[(0,.4,'both'),(.415625,.815625,'both')]
        self.boards=[dict(role='BOARD',row=i,start=0,end=4,low=row[0],high=row[1],edge_mode='both')
                     for i,row in enumerate(self.rows)]
        self.members=[dict(key='JOIST',role='JOIST',a=(1,0),b=(1,1)),
                      dict(key='BACKING',role='BORDER_BACKING',a=(2,0),b=(3,1)),
                      dict(key='BLOCK',role='BLOCK',a=(3,0),b=(4,1)),
                      dict(key='PARALLEL',role='RIM',a=(0,.4),b=(4,.4)),
                      dict(key='SHORT',role='JOIST',a=(0,0),b=(0,.2))]

    def test_crossing_blocking_and_border_backing_receive_clips(self):
        clips=layout.clip_crossings(self.boards,self.members,self.rows)
        self.assertEqual({clip['support_key'] for clip in clips},{'JOIST','BACKING','BLOCK'})
        self.assertEqual(len({(c['x'],c['y']) for c in clips}),3)
        self.assertEqual(layout.clip_crossings(self.boards,self.members*2,self.rows),clips)

    def test_square_edges_and_outside_polygon_do_not_receive_hidden_clips(self):
        self.boards[0]['edge_mode']='square'
        self.assertEqual(layout.clip_crossings(self.boards,self.members,self.rows),[])
        self.boards[0]['edge_mode']='both'
        self.boards[0]['polygon']=[(0,0),(.5,0),(.5,.4),(0,.4)]
        self.assertEqual(layout.clip_crossings(self.boards,self.members,self.rows),[])

    def test_angled_layout_includes_crossing_border_supports(self):
        p=layout.plan(dict(layout.DEFAULTS,board_angle_deg=30,picture_frame=True,double_border_joists=True,blocking=True))
        self.assertTrue(any(c['support_role'] in ('RIM','BLOCK','BORDER_BACKING') for c in p['clips']))
        self.assertEqual(p['counts']['clips'],len({(round(c['x'],7),round(c['y'],7)) for c in p['clips']}))


class HardwareRepairTests(unittest.TestCase):
    def test_known_products_cannot_be_assigned_to_wrong_connection(self):
        for name,role in [('C_LUS210_3d_Cad_MULT_Prod','hanger'),('C_LUS210-2_3d_Cad_MULT_Prod','double_hanger'),
                          ('C_H25A_3d_Cad_MULT_Prod','hurricane'),('C_A35_3d_Cad_MULT_Prod','framing_angle'),
                          ('C_L90_3d_Cad_MULT_Prod','corner'),('L70Z','corner'),('RT_CAMO_clip','clip')]:
            self.assertEqual(catalog.known_role(name),role)
            for picker in ('hanger','double_hanger','hurricane','corner'):
                self.assertEqual(catalog.role_allowed(name,picker),picker==role)
        self.assertTrue(catalog.role_allowed('My reviewed custom angle','corner'))

    def test_hanger_direction_uses_member_vector_once_on_rotated_decks(self):
        scope=functions('rt_revit.py',{'hardware_direction'},dict(math=math))
        for deck in (0,.3,1.2):
            coord=(None,Vector(math.cos(deck),math.sin(deck)),Vector(-math.sin(deck),math.cos(deck)))
            for member in (0,.7):
                directions=[]
                for end in (0,1):
                    inward=(-math.sin(member),math.cos(member))
                    if end: inward=tuple(-v for v in inward)
                    item=dict(direction=inward,end=end,rotation_deg=999,family_rotation_deg=180)
                    x=scope['hardware_direction'](item,coord)
                    expected=deck+member+math.pi+(math.pi if end else 0)
                    self.assertAlmostEqual(x.X,math.cos(expected)); self.assertAlmostEqual(x.Y,math.sin(expected))
                    directions.append(x)
                self.assertAlmostEqual(directions[0].DotProduct(directions[1]),-1)

    def test_point_hardware_uses_absolute_orientation_not_added_family_rotation(self):
        turns=[]; current=.4
        instance=Obj(Id=Id(2**40),GetTransform=lambda:Obj(BasisX=Vector(math.cos(current),math.sin(current))))
        db=Obj(FamilyPlacementType=Obj(WorkPlaneBased='wp'),BuiltInCategory=Obj(OST_StructConnections=-2),ElementId=Id,
               XYZ=Vector,Line=Obj(CreateBound=lambda a,b:None),
               ElementTransformUtils=Obj(RotateElement=lambda doc,eid,axis,angle:turns.append(angle)))
        Vector.BasisZ=Vector(0,0,1)
        scope=functions('rt_revit.py',{'hardware_direction','create_hardware'},dict(DB=db,math=math,
                        world_point=lambda *args:Vector(0,0,0),StructuralType=Obj(NonStructural='nonstructural')))
        doc=Obj(Create=Obj(NewFamilyInstance=lambda *args:instance),Regenerate=lambda:None)
        symbol=Obj(Family=Obj(FamilyPlacementType='point'),Category=Obj(Id=Id(-2)))
        scope['create_hardware'](doc,dict(x=0,y=0,direction=(0,1),family_rotation_deg=180),
                                 (None,Vector(1,0),Vector(0,1)),0,None,symbol)
        self.assertAlmostEqual(turns[0],math.pi-current)

    def test_corner_angles_use_inner_faces_and_skip_return_or_skew_corners(self):
        s=dict(layout.DEFAULTS,corner_strap_symbol_uid='L90')
        corners=layout.corner_connections([(0,0),(12,0),(12,10),(0,10)],s)
        self.assertEqual(len(corners),4)
        self.assertAlmostEqual(corners[0]['x'],1.5/12); self.assertAlmostEqual(corners[0]['y'],1.5/12)
        self.assertTrue(all(c['z_offset_in']==-9.25/2 for c in corners))
        stepped=[(0,0),(12,0),(12,8),(6,8),(6,12),(0,12)]
        corners=layout.corner_connections(stepped,s)
        self.assertEqual(len(corners),5)
        self.assertNotIn([6,8],[c['vertex'] for c in corners])
        self.assertEqual(layout.corner_connections([(0,0),(12,0),(6,10)],s),[])

    def test_accessory_snapshot_filters_both_instances_and_existing_types(self):
        class Collector:
            def WhereElementIsNotElementType(self): self.ids=[Id(1)]; return self
            def WhereElementIsElementType(self): self.ids=[Id(2**40)]; return self
            def ToElementIds(self): return self.ids  # Unfiltered extraction raises.
        scope=functions('rt_accessories.py',{'snapshot_element_ids'},dict(
            DB=Obj(FilteredElementCollector=lambda doc:Collector()),api=Obj(id_value=lambda eid:eid.Value)))
        self.assertEqual(scope['snapshot_element_ids'](None),{1,2**40})


if __name__=='__main__': unittest.main()
