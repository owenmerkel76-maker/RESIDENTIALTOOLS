"""Regression geometry for the user's square corner / screw / full-row repairs."""
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lib'))
import rt_geometry as geo
import rt_border_fasteners as bf
from rt_layout import DEFAULTS,plan,board_rows


def example(**values):
    settings=dict(DEFAULTS,run_ft=19.5,span_ft=11,picture_frame=True,border_courses=2,
                  blocking=True,double_border_joists=True,border_fastening=bf.MODES[2])
    settings.update(values)
    return plan(settings)


class DeckDetailTests(unittest.TestCase):
    def test_full_start_or_end_keeps_stock_width_and_gap_at_both_axes_and_border_counts(self):
        for axis in ('A','B'):
            for courses in (1,2):
                for mode,end in (('Full board at start',0),('Full board at end',-1)):
                    p=example(board_axis=axis,border_courses=courses,board_row_layout=mode)
                    rows=p['rows']; self.assertAlmostEqual((rows[end][1]-rows[end][0])*12,5.5)
                    for a,b in zip(rows,rows[1:]):self.assertAlmostEqual(b[0]-a[1],.1875/12)
                    self.assertTrue(all((b-a)*12<=5.5+geo.EPS for a,b,unused in rows))

    def test_unusable_rip_requires_explicit_choice_and_balanced_remains_available(self):
        with self.assertRaisesRegex(ValueError,'final rip'):board_rows(6/12,5.5,.1875,'Full board at start')
        rows=board_rows(10,5.5,.1875,'Balanced edge rips')
        self.assertAlmostEqual(rows[0][1]-rows[0][0],rows[-1][1]-rows[-1][0])

    def test_rectangular_and_return_rim_footprints_cover_ring_without_gaps_or_overlap(self):
        for poly in ([(0,0),(19.5,0),(19.5,11),(0,11)],
                     [(0,0),(20,0),(20,8),(10,8),(10,12),(0,12)]):
            width=1.5/12; rims=geo.perimeter_members(poly,width,[])
            s=dict(DEFAULTS); outlines=[bf.member_outline(m,s) for m in rims]
            for i,a in enumerate(outlines):
                for b in outlines[i+1:]:self.assertLess(abs(geo.area(geo.intersect_convex(a,b))),1.e-7)
            self.assertAlmostEqual(sum(abs(geo.area(p)) for p in outlines),abs(geo.area(poly))-abs(geo.area(geo.inset(poly,width))))

    def test_redundant_collinear_joist_is_not_duplicated_as_rim(self):
        poly=[(0,0),(12,0),(12,10),(0,10)]; w=1.5/12
        rims=geo.perimeter_members(poly,w,[dict(a=(w/2,w),b=(w/2,10-w))])
        self.assertEqual(len(rims),3)

    def test_miter_end_screws_remain_at_requested_setback_and_all_receive_backing(self):
        p=example(); self.assertFalse(p['unsupported_border_fasteners'])
        boards={b['key']:b for b in p['boards']}
        for screw in p['face_fasteners']:
            point=screw['x'],screw['y']; self.assertIsNotNone(bf.support_at(point,p['members'],p['settings']))
            if screw['face_kind']!='border' or screw['station_kind']!='end':continue
            poly=bf.outline(boards[screw['board_key']]);u,n=bf.axes(boards[screw['board_key']])
            end_edges=[(a,b) for a,b in zip(poly,poly[1:]+poly[:1]) if abs(bf.dot(bf.sub(b,a),n))>bf.EPS]
            self.assertAlmostEqual(min(geo.edge_distance(point,a,b) for a,b in end_edges)*12,1,places=5)
        backing=[m for m in p['members'] if m.get('face_backing')]
        self.assertTrue(backing)
        for a in backing:
            for b in p['members']:
                if a is b:continue
                self.assertLess(abs(geo.area(geo.intersect_convex(bf.member_outline(a,p['settings']),bf.member_outline(b,p['settings'])))),bf.EPS)

    def test_touching_double_joists_supply_one_regular_station_toward_board_middle(self):
        board=dict(start=0,end=12,low=0,high=.458,role='BORDER')
        members=[dict(role='JOIST',a=(x,-1),b=(x,2)) for x in (1,1.125,5,10,10.125)]
        self.assertEqual(bf.regular_face_stations(board,members,DEFAULTS,0,12),[1.125,5,10])

    def test_flat_field_edges_add_face_rows_and_missing_support_is_never_counted(self):
        p=example(); screws=[v for v in p['face_fasteners'] if v['face_kind']=='field_edge']
        self.assertEqual(len(screws),30)
        self.assertEqual(len({v['board_key'] for v in screws}),2)
        off=example(field_edge_face_screws=False)
        self.assertFalse(any(v['face_kind']=='field_edge' for v in off['face_fasteners']))
        missing=example(border_add_backing=False)
        self.assertTrue(missing['unsupported_border_fasteners'])
        self.assertLess(len(missing['face_fasteners']),len(p['face_fasteners']))

    def test_narrow_field_edge_explicitly_reports_omitted_face_row(self):
        p=plan(DEFAULTS)
        self.assertTrue(any('too narrow' in warning for warning in p['warnings']))


if __name__=='__main__':unittest.main()
