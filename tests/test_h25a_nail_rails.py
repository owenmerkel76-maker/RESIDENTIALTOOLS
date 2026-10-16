"""Schematic tie nail rails stay on synthetic measured sheet metal.

These regressions do not establish manufacturer hole positions or capacity.
"""
import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import rt_connector_geometry as g
import rt_hardware_nails as nails
from rt_layout import DEFAULTS
from test_h25a_plate_datum import h25a_fixture, refined, transformed

IDENTITY = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


def on_triangle(point, tri):
    a, b, c = tri
    ab, ac, ap = g.sub(b, a), g.sub(c, a), g.sub(point, a)
    normal = g.cross(ab, ac)
    if g.size(normal) < 1.e-12:
        return False
    if abs(g.dot(ap, g.unit(normal))) > 1.e-7:
        return False
    aa, bb, cc = g.dot(ab, ab), g.dot(ab, ac), g.dot(ac, ac)
    denominator = aa * cc - bb * bb
    if denominator < 1.e-20:
        return False
    d, e = g.dot(ap, ab), g.dot(ap, ac)
    u, v = (cc * d - bb * e) / denominator, (aa * e - bb * d) / denominator
    return u >= -1.e-7 and v >= -1.e-7 and u + v <= 1 + 1.e-7


def items_for(profile):
    return nails.nail_items(profile, dict(datum=(0, 0, 0), target=IDENTITY),
                            dict(key='synthetic_tie'), 'H2.5A', DEFAULTS)


class H25ANailRailTests(unittest.TestCase):
    def assert_heads_on_tab(self, triangles):
        profile = g.tie_profile(triangles, model='H2.5A')
        items, notes = items_for(profile)
        self.assertEqual(len(items), 10)
        self.assertTrue(any('schematic mounting-face pattern' in note for note in notes))
        by_group = {}
        for item in items:
            group = item['application']
            self.assertTrue(item['schematic'])
            self.assertFalse(item['measured_hole'])
            local = item['head']
            native_head = g.add(profile['origin'], g.rotate(local, IDENTITY, profile['axes']))
            self.assertTrue(any(on_triangle(native_head, tri) for tri in triangles),
                            (group, local, native_head))
            physical_height = local[2] * profile['details']['upper_sign']
            if group == 'joist tie tab':
                self.assertGreater(physical_height * 12, .35)
                self.assertEqual(item['direction'], (-1, 0, 0))
                plane_axis, across_axis = 0, 1
            else:
                self.assertLess(physical_height * 12, -.35)
                self.assertEqual(item['direction'], (0, -1, 0))
                plane_axis, across_axis = 1, 0
            rail = profile['details']['schematic_nail_rails'][group]
            self.assertAlmostEqual(local[plane_axis], rail['plane'])
            self.assertAlmostEqual(local[across_axis], rail['across'])
            self.assertTrue(any(a < local[2] < b for a, b in rail['intervals']))
            by_group.setdefault(group, []).append((physical_height, local[across_axis]))
        return {group: sorted(points) for group, points in by_group.items()}

    def test_all_ten_schematic_heads_are_on_solid_metal_and_correct_physical_tab(self):
        self.assert_heads_on_tab(h25a_fixture())

    def test_transformed_refined_and_reordered_meshes_preserve_physical_nail_rails(self):
        expected = self.assert_heads_on_tab(h25a_fixture())
        for triangles in (transformed(h25a_fixture()), refined(h25a_fixture(), 3),
                          transformed(list(reversed(refined(h25a_fixture(), 2))))):
            actual = self.assert_heads_on_tab(triangles)
            self.assertEqual(set(actual), set(expected))
            for group in actual:
                for found, original in zip(actual[group], expected[group]):
                    for a, b in zip(found, original):
                        self.assertAlmostEqual(a, b, places=7)

    def test_disjoint_solid_intervals_skip_gaps_and_keep_surface_clearance(self):
        profile = g.tie_profile(h25a_fixture(), model='H2.5A')
        group = 'joist tie tab'
        sign = profile['details']['upper_sign']
        # Deliberately introduce a large absent-metal interval into a rail.
        positive = ((.04, .06), (.12, .20))
        intervals = [(a, b) if sign > 0 else (-b, -a) for a, b in positive]
        profile['details']['schematic_nail_rails'][group]['intervals'] = intervals
        positions = nails.fallback(profile, group, 5)
        self.assertEqual(len(positions), 5)
        clearance = .08 / 12
        for point, direction in positions:
            self.assertTrue(any(a + clearance - 1.e-9 <= point[2] <= b - clearance + 1.e-9
                                for a, b in intervals))
        physical = sorted(point[2] * sign for point, unused in positions)
        self.assertTrue(any(z < .06 for z in physical))
        self.assertTrue(any(z > .12 for z in physical))

    def test_empty_or_outside_tab_rails_fail_closed_instead_of_putting_heads_in_air(self):
        profile = g.tie_profile(h25a_fixture(), model='H2.5A')
        group = 'joist tie tab'
        sign = profile['details']['upper_sign']
        for intervals in ([], [[0, .02 * sign]], [[1, 2]], [[0, float('nan')]]):
            modified = copy.deepcopy(profile)
            modified['details']['schematic_nail_rails'][group]['intervals'] = intervals
            with self.assertRaisesRegex(ValueError, 'No safe measured mounting-face interval'):
                nails.fallback(modified, group, 5)

    def test_missing_named_rail_fails_closed_but_legacy_profile_keeps_compatibility(self):
        profile = g.tie_profile(h25a_fixture(), model='H2.5A')
        del profile['details']['schematic_nail_rails']['joist tie tab']
        with self.assertRaisesRegex(ValueError, 'No measured mounting-face rail'):
            nails.fallback(profile, 'joist tie tab', 5)
        del profile['details']['schematic_nail_rails']
        items, notes = items_for(profile)
        self.assertEqual(len(items), 10)
        self.assertTrue(all(item['schematic'] and not item['measured_hole'] for item in items))

    def test_adjacent_triangle_intervals_merge_before_adding_edge_clearance(self):
        rail = dict(intervals=[[.04, .06], [.06, .08], [.08, .12]])
        positions = nails.rail_positions(rail, .035, .13, 5)
        self.assertAlmostEqual(positions[0], .04 + .08 / 12)
        self.assertAlmostEqual(positions[-1], .12 - .08 / 12)
        self.assertEqual(len(positions), 5)
        self.assertTrue(any(.06 < z < .08 for z in positions))

    def test_complete_measured_hole_groups_bypass_unusable_schematic_rails(self):
        profile = g.tie_profile(h25a_fixture(), model='H2.5A')
        profile['holes'] = []
        for group in ('joist tie tab', 'beam tie tab'):
            for point, inward in nails.fallback(profile, group, 5):
                profile['holes'].append(dict(center=point, normal=g.mul(inward, -1),
                                             diameter_in=.2))
            profile['details']['schematic_nail_rails'][group]['intervals'] = []
        items, notes = items_for(profile)
        self.assertEqual(len(items), 10)
        self.assertTrue(all(item['measured_hole'] for item in items))
        self.assertFalse(any('CAD holes were unavailable' in note for note in notes))

    def test_optional_empty_nail_rails_do_not_prevent_fitting_connector_profile(self):
        # A rail failure affects requested schematic nails, not fitting a tie
        # for a build where optional nails are disabled or actual holes exist.
        empty_rail = dict(plane=0, across=.6875 / 12, intervals=[])
        with mock.patch.object(g, 'mounting_rail', return_value=empty_rail):
            profile = g.tie_profile(h25a_fixture(), model='H2.5A')
        self.assertEqual(profile['kind'], 'tie')
        self.assertEqual(profile['details']['plate_line_from_lower_in'], 2.1875)
        with self.assertRaisesRegex(ValueError, 'No safe measured mounting-face interval'):
            items_for(profile)


if __name__ == '__main__':
    unittest.main()
