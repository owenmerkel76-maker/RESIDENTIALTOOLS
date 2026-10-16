import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from rt_layout import DEFAULTS, plan


class BlockingTests(unittest.TestCase):
    def check_layout(self, polygon=None):
        result = plan(dict(DEFAULTS, run_ft=28, span_ft=15,
                           footprint_polygon=polygon, blocking=True,
                           supports_enabled=True, boards_enabled=False, clips_enabled=False))
        blocks = [m for m in result['members'] if m['role']=='BLOCK']
        beams = sorted(set(m['a'][1] for m in result['beams']))
        self.assertTrue(blocks)
        self.assertEqual(set(m['row_center'] for m in blocks),
                         set(beams+[(beams[0]+beams[1])/2]))
        for center in set(m['row_center'] for m in blocks):
            row = sorted([m for m in blocks if m['row_center']==center], key=lambda m:m['a'][0])
            self.assertGreater(len(row), 2)
            for a,b in zip(row,row[1:]):
                self.assertAlmostEqual(abs(a['a'][1]-b['a'][1]), 1.5/12)
                self.assertAlmostEqual(b['a'][0]-a['b'][0], 1.5/12)
        return result

    def test_rectangular_beam_and_midspan_courses(self):
        self.check_layout()

    def test_stepped_beam_and_midspan_courses(self):
        self.check_layout([(0,0),(28,0),(28,12),(16,12),(16,15),(0,15)])

    def test_disabled_option_adds_no_blocks(self):
        result = plan(dict(DEFAULTS, supports_enabled=True, blocking=False,
                           boards_enabled=False, clips_enabled=False))
        self.assertFalse(any(m['role']=='BLOCK' for m in result['members']))

    def test_stepped_outline_blocks_reach_both_side_rims(self):
        result = self.check_layout([(0,0),(28,0),(28,12),(16,12),(16,15),(0,15)])
        for center in set(m['row_center'] for m in result['members'] if m['role']=='BLOCK'):
            blocks = [m for m in result['members'] if m['role']=='BLOCK' and m['row_center']==center]
            self.assertAlmostEqual(min(m['a'][0] for m in blocks), 1.5/12)
            self.assertAlmostEqual(max(m['b'][0] for m in blocks), 28-1.5/12)
