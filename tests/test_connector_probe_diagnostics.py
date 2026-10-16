"""Pure adapter checks for local mesh diagnostics and probe rollback.

Uses the dimensional synthetic H2.5A fixture, not an actual native Revit mesh.
"""
import json
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace as Obj
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import rt_connector_geometry as geometry
import rt_connector_placement as adapter
from test_h25a_plate_datum import h25a_fixture


@contextmanager
def replay_folder():
    # Python's Windows 0700 TemporaryDirectory ACL cannot be reopened by some
    # restricted test tokens. Inherit this workspace's ACL and clean our files.
    folder = Path(__file__).parent / ('probe_replay_' + uuid.uuid4().hex)
    folder.mkdir()
    try:
        yield folder
    finally:
        for path in folder.glob('connector_probe_HURRICANE_STRAP_*.json'):
            path.unlink()
        folder.rmdir()


def probe_harness(family_name, triangles, report_folder=None, item_overrides=None):
    events = []
    messages = []
    transaction = Obj(Start=lambda: events.append('start'),
                      RollBack=lambda: events.append('rollback'))
    db = Obj(SubTransaction=lambda doc: transaction,
             XYZ=lambda *xyz: xyz,
             FamilyPlacementType=Obj(WorkPlaneBased='work-plane'))
    doc = Obj(Regenerate=lambda: events.append('regenerate'))
    symbol = Obj(UniqueId='fixture:uid/unsafe?characters',
                 Family=Obj(Name=family_name, FamilyPlacementType='point'))
    item = dict(role='HURRICANE_STRAP', width_in=1.5, depth_in=9.25)
    item.update(item_overrides or {})

    def log(message):
        messages.append(message)

    if report_folder is not None:
        log.report_folder = str(report_folder)

    def run():
        with mock.patch.object(adapter, 'point_instance', return_value=Obj()) as create:
            with mock.patch.object(adapter, 'triangles_of', return_value=triangles):
                with mock.patch.object(adapter, 'native_basis', return_value=(
                        (1, 0, 0), (0, 1, 0), (0, 0, 1))):
                    result = adapter.probe(doc, symbol, item, None, db, None, log)
        create.assert_called_once()
        return result

    return Obj(run=run, events=events, messages=messages, item=item, symbol=symbol)


class ConnectorProbeDiagnosticsTests(unittest.TestCase):
    def test_actual_manufacturer_family_name_selects_h25a_and_probe_rolls_back(self):
        probe = probe_harness('C_H25A_3d_Cad_MULT_Prod', h25a_fixture(),
                              item_overrides=dict(model='custom', family_name='custom'))
        original = geometry.tie_profile
        with mock.patch.object(adapter.geo, 'tie_profile', wraps=original) as fit:
            profile = probe.run()
        self.assertEqual(fit.call_args.kwargs['model'], 'H2.5A')
        self.assertEqual(profile['details']['model'], 'H2.5A')
        self.assertEqual(profile['details']['plate_line_from_lower_in'], 2.1875)
        self.assertEqual(profile['native_basis'], ((1, 0, 0), (0, 1, 0), (0, 0, 1)))
        self.assertEqual(probe.events, ['start', 'regenerate', 'rollback'])
        self.assertTrue(any('Measured connector profile' in line for line in probe.messages))

    def test_custom_family_cannot_use_requested_h25a_name_and_failure_rolls_back(self):
        probe = probe_harness('Custom overlapping tie', h25a_fixture(),
                              item_overrides=dict(model='H2.5A', family_name='C_H25A_3d_Cad_MULT_Prod'))
        original = geometry.tie_profile
        with mock.patch.object(adapter.geo, 'tie_profile', wraps=original) as fit:
            with self.assertRaisesRegex(ValueError, 'model-specific plate-line datum'):
                probe.run()
        self.assertIsNone(fit.call_args.kwargs['model'])
        self.assertEqual(probe.events, ['start', 'regenerate', 'rollback'])
        self.assertTrue(any('major_planes=' in line for line in probe.messages))

    def test_malformed_known_family_saves_round_trip_replay_mesh_in_feet(self):
        triangles = [tuple((x, y, z * 1.05) for x, y, z in tri)
                     for tri in h25a_fixture()]
        with replay_folder() as folder:
            probe = probe_harness('C_H25A_3d_Cad_MULT_Prod', triangles, folder)
            with self.assertRaisesRegex(ValueError, 'must measure 6 inches overall'):
                probe.run()
            files = list(Path(folder).glob('connector_probe_HURRICANE_STRAP_*.json'))
            self.assertEqual(len(files), 1)
            payload = json.loads(files[0].read_text(encoding='utf-8'))
            self.assertEqual(payload['triangles'], json.loads(json.dumps(triangles)))
            self.assertEqual(payload['units'], 'feet')
            self.assertEqual(payload['coordinates'], 'temporary probe instance at project origin')
            self.assertEqual(payload['model'], 'H2.5A')
            self.assertEqual(payload['family_name'], probe.symbol.Family.Name)
            self.assertEqual(payload['symbol_uid'], probe.symbol.UniqueId)
            self.assertEqual(payload['role'], 'HURRICANE_STRAP')
            self.assertEqual(payload['width_in'], 1.5)
            self.assertEqual(payload['depth_in'], 9.25)
            self.assertTrue(any('replay mesh saved locally' in line for line in probe.messages))
        self.assertEqual(probe.events, ['start', 'regenerate', 'rollback'])

    def test_diagnostic_write_failure_keeps_original_probe_error_and_rolls_back(self):
        triangles = [tuple((x, y, z * 1.05) for x, y, z in tri)
                     for tri in h25a_fixture()]
        with replay_folder() as folder:
            missing_folder = Path(folder) / 'missing-report-folder'
            probe = probe_harness('C_H25A_3d_Cad_MULT_Prod', triangles, missing_folder)
            with self.assertRaisesRegex(ValueError, 'must measure 6 inches overall'):
                probe.run()
            self.assertFalse(missing_folder.exists())
        self.assertTrue(any('diagnostic unavailable' in line for line in probe.messages))
        self.assertEqual(probe.events, ['start', 'regenerate', 'rollback'])


if __name__ == '__main__':
    unittest.main()
