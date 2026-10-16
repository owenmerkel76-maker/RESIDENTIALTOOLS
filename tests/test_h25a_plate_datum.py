"""H2.5A dimensional regression fixture, not a captured manufacturer RFA mesh.

The synthetic closed flanges preserve the US C-C-2026 p299 gross dimensions:
6 in overall, 1-3/8 in wide, and a plate line 2-3/16 in from either end.
Equal flange areas and overlapping tapered tails reproduce the former probe's
bad height assumption without claiming to validate all detail in Simpson CAD.
"""
import math
import random
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as Obj

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import rt_connector_geometry as g
import rt_connector_placement as placement


def polygon_prism(points, extrusion):
    """Triangulate a convex polygon and its translated cap (feet)."""
    cap = [g.add(point, extrusion) for point in points]
    triangles = []
    for i in range(1, len(points) - 1):
        triangles.append((points[0], points[i + 1], points[i]))
        triangles.append((cap[0], cap[i], cap[i + 1]))
    for i in range(len(points)):
        j = (i + 1) % len(points)
        triangles.extend(((points[i], points[j], cap[j]),
                          (points[i], cap[j], cap[i])))
    return triangles


def h25a_fixture():
    polygon = ((0, 3.8125), (1.375, 3.8125),
               (1.375, 1.625), (0, 0))
    upper = [(0, across / 12.0, z / 12.0) for across, z in polygon]
    lower = [(across / 12.0, 0, (1.625 - z) / 12.0)
             for across, z in polygon]
    return (polygon_prism(upper, (.0625 / 12.0, 0, 0)) +
            polygon_prism(lower, (0, .0625 / 12.0, 0)))


def refined(triangles, levels):
    for unused in range(levels):
        result = []
        for a, b, c in triangles:
            ab, bc, ca = (g.mul(g.add(a, b), .5),
                          g.mul(g.add(b, c), .5),
                          g.mul(g.add(c, a), .5))
            result.extend(((a, ab, ca), (ab, b, bc),
                           (ca, bc, c), (ab, bc, ca)))
        triangles = result
    return triangles


def rigid_transform(point):
    axis = g.unit((.21, .63, -.42))
    angle = 1.17
    rotated = g.add(g.add(g.mul(point, math.cos(angle)),
                          g.mul(g.cross(axis, point), math.sin(angle))),
                    g.mul(axis, g.dot(axis, point) * (1 - math.cos(angle))))
    return g.add(rotated, (13, -7, 8))


def transformed(triangles):
    return [tuple(rigid_transform(p) for p in tri) for tri in triangles]


class H25APlateDatumTests(unittest.TestCase):
    def assert_plate_datum(self, triangles):
        profile = g.tie_profile(triangles, model='H2.5A')
        up = g.mul(profile['axes'][2], profile['details']['upper_sign'])
        points = [point for tri in triangles for point in tri]
        low, high = g.extent(points, up)
        datum = g.dot(profile['origin'], up)
        self.assertAlmostEqual((high - low) * 12, 6, places=7)
        self.assertAlmostEqual((datum - low) * 12, 2.1875, places=7)
        self.assertAlmostEqual((high - datum) * 12, 3.8125, places=7)
        self.assertAlmostEqual(profile['details']['height_in'], 6, places=7)
        self.assertEqual(profile['details']['plate_line_from_lower_in'], 2.1875)
        self.assertLess(profile['details']['transition_gap_in'], -1)
        self.assertIn('published plate line', profile['details']['datum'])
        self.assertAlmostEqual(g.dot(g.cross(*profile['axes'][:2]),
                                     profile['axes'][2]), 1, places=8)
        # The two measured outer mounting planes pass through the datum.
        for axis in profile['axes'][:2]:
            candidates = [face for face in g.planes(triangles)
                          if abs(g.dot(face['n'], axis)) > 1 - 1.e-6]
            self.assertTrue(any(abs(g.dot(g.sub(face['points'][0],
                                                 profile['origin']), axis)) < 1.e-7
                                for face in candidates))
        return profile

    def test_equal_flange_heights_with_overlapping_tails_use_published_plate_line(self):
        triangles = h25a_fixture()
        profile = self.assert_plate_datum(triangles)
        # The old gap midpoint sits 13/16 in away from the published datum.
        self.assertAlmostEqual(abs(g.dot(profile['origin'], (0, 0, 1)) * 12 - .8125),
                               .8125, places=7)

    def test_published_datum_is_independent_of_family_origin_and_axes(self):
        profile = self.assert_plate_datum(transformed(h25a_fixture()))
        up = g.mul(profile['axes'][2], profile['details']['upper_sign'])
        rotated_vertical = g.sub(rigid_transform((0, 0, 1)),
                                rigid_transform((0, 0, 0)))
        self.assertAlmostEqual(abs(g.dot(up, rotated_vertical)), 1, places=8)

    def test_triangle_order_winding_and_narrow_mesh_refinement_preserve_datum(self):
        triangles = h25a_fixture()
        shuffled = list(reversed([tuple(reversed(tri)) for tri in triangles]))
        random.Random(19464).shuffle(shuffled)
        self.assert_plate_datum(shuffled)
        # Four subdivisions make transverse triangles narrower than the
        # former 0.15-in-per-triangle test, while preserving each surface.
        dense = refined(triangles, 4)
        self.assertTrue(all((max(p[1] for p in tri) - min(p[1] for p in tri)) * 12 < .15
                            for tri in dense))
        self.assert_plate_datum(dense)
        self.assert_plate_datum(transformed(list(reversed(dense))))

    def test_area_centroid_is_not_biased_by_selective_tessellation(self):
        triangle = ((0, 0, 0), (0, 2, 0), (0, 0, 3))
        neighbor = ((0, 2, 0), (0, 4, 0), (0, 0, 3))
        original = g.area_centroid([triangle, neighbor])
        selective = g.area_centroid(refined([triangle], 4) + [neighbor])
        self.assertLess(g.size(g.sub(original, selective)), 1.e-10)
        # Upper and lower face triangulation densities may also differ.
        mesh = h25a_fixture()
        self.assert_plate_datum(refined(mesh[:12], 3) + mesh[12:])

    def test_unknown_overlapping_tie_cannot_borrow_h25a_plate_datum(self):
        with self.assertRaisesRegex(ValueError, 'model-specific plate-line datum'):
            g.tie_profile(h25a_fixture())

    def test_recognized_h25a_with_wrong_overall_height_is_rejected(self):
        scaled = [tuple((x, y, z * 1.05) for x, y, z in tri)
                  for tri in h25a_fixture()]
        with self.assertRaisesRegex(ValueError, 'must measure 6 inches overall'):
            g.tie_profile(scaled, model='H2.5A')

    def test_recognized_h25a_with_wrong_flange_width_is_rejected(self):
        scaled = [tuple((x * 2, y * 2, z) for x, y, z in tri)
                  for tri in h25a_fixture()]
        with self.assertRaisesRegex(ValueError, 'flange width is inconsistent'):
            g.tie_profile(scaled, model='H2.5A')

    def test_beam_top_and_outer_contact_planes_map_at_both_ends_and_paired_sides(self):
        coord = tuple(Obj(X=x, Y=y, Z=z) for x, y, z in
                      ((100, 200, 0), (0, 1, 0), (-1, 0, 0)))
        for triangles in (h25a_fixture(), transformed(h25a_fixture())):
            profile = self.assert_plate_datum(triangles)
            profile['native_basis'] = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
            for end in (-1, 1):
                for side in (None, -1, 1):
                    item = dict(role='HURRICANE_STRAP', x=5, y=1 if end < 0 else 9,
                                beam_outward=(0, end), joist_across=(1, 0),
                                joist_side=side, joist_width_in=1.5,
                                beam_width_in=4.5, z_offset_in=-9.25)
                    fit = placement.placement(profile, item, coord, 8)
                    world_datum = g.add(fit['origin'], g.rotate(profile['origin'],
                                                              profile['axes'], fit['target']))
                    self.assertLess(g.size(g.sub(world_datum, fit['datum'])), 1.e-8)
                    self.assertAlmostEqual(world_datum[2], 8 - 9.25 / 12.0)
                    world_up = g.mul(fit['target'][2], profile['details']['upper_sign'])
                    self.assertAlmostEqual(g.dot(world_up, (0, 0, 1)), 1)
                    center = (100 - item['y'], 205, world_datum[2])
                    displacement = g.sub(world_datum, center)
                    self.assertAlmostEqual(g.dot(displacement, fit['target'][0]) * 12, .75)
                    self.assertAlmostEqual(g.dot(displacement, fit['target'][1]) * 12, 2.25)
                    mapped_points = [g.add(fit['origin'], g.rotate(point, profile['axes'],
                                                                 fit['target']))
                                     for tri in triangles for point in tri]
                    low, high = g.extent(mapped_points, (0, 0, 1))
                    self.assertAlmostEqual((world_datum[2] - low) * 12, 2.1875, places=7)
                    self.assertAlmostEqual((high - world_datum[2]) * 12, 3.8125, places=7)


if __name__ == '__main__':
    unittest.main()
