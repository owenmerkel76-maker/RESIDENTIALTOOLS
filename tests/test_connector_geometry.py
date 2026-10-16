"""Contact frame tests with synthetic plate geometry, not manufacturer RFA tests."""
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lib'))
import rt_connector_geometry as g
import rt_connector_placement as native


def box(low,high):
    p=[tuple((low[j],high[j])[int(bool(i&(1<<j)))]/12 for j in range(3)) for i in range(8)]
    faces=((0,2,3,1),(4,5,7,6),(0,1,5,4),(2,6,7,3),(0,4,6,2),(1,3,7,5))
    return [tuple(p[i] for i in tri) for a,b,c,d in faces for tri in ((a,b,c),(a,c,d))]


def hanger(width=1.5625):
    t=.06; w=width/2
    return (box((-w,-t,0),(w,2,t))+box((-w-1,-t,0),(w+1,0,8))+
            box((-w-t,0,0),(-w,2,7.5))+box((w,0,0),(w+t,2,7.5)))


def angle():
    return box((0,0,-4.5),(.06,1.5,4.5))+box((0,0,-4.5),(1.5,.06,4.5))


def rotated(triangles):
    source=((1,0,0),(0,1,0),(0,0,1)); target=((0,0,1),(1,0,0),(0,1,0))
    return [tuple(g.add(g.rotate(p,source,target),(2,-3,7)) for p in tri) for tri in triangles]


class ContactGeometryTests(unittest.TestCase):
    def test_measured_datum_mapping_for_both_hanger_ends_and_vertical_corner(self):
        from types import SimpleNamespace as Obj
        def v(a):return Obj(X=a[0],Y=a[1],Z=a[2])
        coord=tuple(v(a) for a in ((100,200,0),(0,1,0),(-1,0,0)))
        for role,triangles in (('HANGER',rotated(hanger())),('CORNER_STRAP',rotated(angle()))):
            profile=g.hanger_profile(triangles,1.5,9.25) if role=='HANGER' else g.angle_profile(triangles)
            profile['native_basis']=((1,0,0),(0,1,0),(0,0,1))
            for end in (0,1):
                item=dict(role=role,x=2,y=3,direction=(0,1 if end==0 else -1),rotation_deg=end*90,z_offset_in=-9.25)
                fit=native.placement(profile,item,coord,8)
                mapped=g.add(fit['origin'],g.rotate(profile['origin'],profile['axes'],fit['target']))
                self.assertLess(g.size(g.sub(mapped,(97,202,8-9.25/12))),1.e-8)
                self.assertAlmostEqual(g.dot(fit['direction'],fit['normal']),0)
                self.assertEqual(fit['target'][2],(0,0,1))

    def test_single_and_double_hanger_seat_matches_width_without_axis_assumptions(self):
        for width,joist in ((1.5625,1.5),(3.125,3)):
            for triangles in (hanger(width),rotated(hanger(width))):
                p=g.hanger_profile(triangles,joist,9.25)
                self.assertAlmostEqual(p['details']['clear_width_in'],width)
                self.assertAlmostEqual(p['bounds'][2][0]*12,-.06)
                self.assertAlmostEqual(p['bounds'][1][0],0)

    def test_angle_contact_planes_and_length_center_follow_family_geometry(self):
        for triangles in (angle(),rotated(angle())):
            p=g.angle_profile(triangles)
            self.assertAlmostEqual(p['bounds'][0][0],0)
            self.assertAlmostEqual(p['bounds'][1][0],0)
            self.assertAlmostEqual(p['bounds'][2][0]*12,-4.5)
            self.assertAlmostEqual(p['bounds'][2][1]*12,4.5)

    def test_wrong_width_or_non_angle_is_rejected(self):
        with self.assertRaises(ValueError):g.hanger_profile(hanger(),3,9.25)
        with self.assertRaises(ValueError):g.angle_profile(box((0,0,0),(3,3,3)))

    def test_full_frame_rotations_include_half_turn_and_tilt(self):
        source=((1,0,0),(0,1,0),(0,0,1))
        for target in (((-1,0,0),(0,-1,0),(0,0,1)),((0,0,1),(1,0,0),(0,1,0)),source):
            axis,theta=native.rotation_axis_angle(source,target)
            for a,b in zip(source,target):
                rotated_vector=g.add(g.add(g.mul(a,math.cos(theta)),g.mul(g.cross(axis,a),math.sin(theta))),g.mul(axis,g.dot(axis,a)*(1-math.cos(theta))))
                self.assertLess(g.size(g.sub(rotated_vector,b)),1.e-8)

    def test_probe_rolls_back_even_when_creation_fails(self):
        from types import SimpleNamespace
        events=[]
        sub=SimpleNamespace(Start=lambda:events.append('start'),RollBack=lambda:events.append('rollback'))
        db=SimpleNamespace(SubTransaction=lambda doc:sub,XYZ=lambda *args:None,
                           FamilyPlacementType=SimpleNamespace(WorkPlaneBased='work'))
        symbol=SimpleNamespace(Family=SimpleNamespace(FamilyPlacementType='point'))
        old=native.point_instance
        try:
            def fail(*args):raise ValueError('creation failed')
            native.point_instance=fail
            with self.assertRaisesRegex(ValueError,'creation failed'):
                native.probe(None,symbol,{},None,db,None,lambda message:None)
        finally:native.point_instance=old
        self.assertEqual(events,['start','rollback'])


if __name__=='__main__':unittest.main()
