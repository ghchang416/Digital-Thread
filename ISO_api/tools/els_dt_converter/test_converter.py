"""Run with: python -m unittest discover -s ISO_api/tools/els_dt_converter -p 'test_*.py'."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import convert as c

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / 'outputs/els_dt_converter/가상예제.xlsx'
BLANK = ROOT / 'outputs/els_dt_converter/업체입력_빈양식.xlsx'


class ConverterTests(unittest.TestCase):
    def read(self):
        inp = c.Input()
        inp.read(EXAMPLE)
        self.assertEqual(inp.errors, [])
        return inp

    def build(self, inp, **kw):
        return c.build(inp, EXAMPLE, kw.get('part'), kw.get('rev'), 'urn:test', kw.get('mode', 'local'))

    def test_end_to_end_five_assets_roundtrip_and_local_files(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / 'result'
            report = c.run(EXAMPLE, dest)
            self.assertTrue(report['ok'])
            self.assertEqual({a['type'] for a in report['assets']}, {'DtMaterial','DtProject','DtMachineTool','DtCuttingTool13399','DtFile'})
            self.assertEqual(len(list(dest.glob('*.xml'))), 5)
            self.assertFalse(report['machine_ready'])
            self.assertEqual(json.loads((dest/'report.json').read_text())['errors'], [])
            manifest = json.loads((dest/'file_manifest.json').read_text())
            self.assertTrue((dest/manifest[0]['path']).is_file())
            self.assertTrue(manifest[0]['upload_required'])
            for path in dest.glob('*.xml'):
                asset = c.XmlParser().parse(path, c.m.DtAsset)
                self.assertEqual(c.required_errors(asset), [])
                if isinstance(asset.dt_elements[0], c.m.DtFile):
                    self.assertTrue(asset.dt_elements[0].value.startswith('pending-upload:'))

    def test_refs_units_false_and_explicit_axis_path(self):
        inp = self.read()
        assets, _, _ = self.build(inp)
        uris = {f'{a.asset_global_id}/{a.id}/{a.dt_elements[0].element_id}' for a in assets}
        project = next(a.dt_elements[0] for a in assets if isinstance(a.dt_elements[0], c.m.DtProject))
        plan = project.main_workplan.its_elements[0]
        op = plan.its_elements[0].its_operation
        self.assertEqual(op.its_technology.spindle, 100)
        self.assertEqual(op.its_technology.feedrate, .01)
        self.assertIs(op.its_technology.inhibit_feedrate_override, False)
        self.assertIn(op.ref_dt_cutting_tool.keys[0].value, uris)
        self.assertIn(plan.ref_dt_machine_tool.keys[0].value, uris)
        self.assertIn(project.its_workpieces[0].ref_dt_material.keys[0].value, uris)
        self.assertEqual(op.its_toolpath.its_list[0].its_toolaxis.points[1].coordinates, [.6,0,.8])
        self.assertEqual(inp.data['Part_Info']['P1']['Part_Rev'], '01')
        self.assertEqual(inp.data['Operation_Info']['OP1']['Op_No'], '010')

    def test_blank_reports_cells_and_emits_no_xml(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / 'result'
            report = c.run(BLANK, dest)
            self.assertFalse(report['ok'])
            self.assertTrue(any(e['cell']=='업체입력!D5' for e in report['errors']))
            self.assertEqual(list(dest.glob('*.xml')), [])

    def test_duplicate_master_keys(self):
        inp = self.read()
        inp.data['Tool_Milling']['T2'] = copy.deepcopy(inp.data['Tool_Milling']['T1'])
        self.build(inp)
        self.assertTrue(any('복합키' in e['message'] for e in inp.errors))

    def test_missing_tool_join(self):
        inp = self.read()
        inp.data['Operation_Machining']['WS1']['공구사양'] = 'missing'
        self.build(inp)
        self.assertTrue(any('Tool_Milling 연결' in e['message'] for e in inp.errors))

    def test_duplicate_order(self):
        inp = self.read()
        row = copy.deepcopy(inp.data['Operation_Machining']['WS1'])
        row['SEQNO'] = 20
        inp.data['Operation_Machining']['WS2'] = row
        self.build(inp)
        self.assertTrue(any('실행 순서' in e['message'] for e in inp.errors))

    def test_missing_selected_spindle_value(self):
        inp = self.read()
        inp.data['Operation_Machining']['WS1']['spindle_source'] = 'SPINDLE_02'
        self.build(inp)
        self.assertTrue(any(e.get('column')=='SPINDLE_02' for e in inp.errors))

    def test_explicit_source_selection_and_signed_spindle(self):
        inp = self.read()
        row = inp.data['Operation_Machining']['WS1']
        row.update(spindle_source='SPINDLE_02', SPINDLE_02=-50, spindle_unit='1/s', feed_source='FEED_04', FEED_04=.05, feed_unit='m/s')
        assets, _, _ = self.build(inp)
        project = next(a.dt_elements[0] for a in assets if isinstance(a.dt_elements[0], c.m.DtProject))
        tech = project.main_workplan.its_elements[0].its_elements[0].its_operation.its_technology
        self.assertEqual((tech.spindle, tech.feedrate), (-50, .05))

    def test_bad_plane_directions(self):
        inp = self.read()
        inp.data['Operation_Machining']['WS1']['security_ref_direction'] = [0,0,1]
        self.build(inp)
        self.assertTrue(any('직교' in e['message'] for e in inp.errors))

    def test_empty_path_is_reported_not_fabricated(self):
        inp = self.read()
        inp.paths = {}
        assets, _, warnings = self.build(inp)
        self.assertFalse(inp.errors)
        self.assertTrue(any('경로·공구축 미입력' in w for w in warnings))
        project = next(a.dt_elements[0] for a in assets if isinstance(a.dt_elements[0], c.m.DtProject))
        self.assertIsNone(project.main_workplan.its_elements[0].its_elements[0].its_operation.its_toolpath)

    def test_unknown_path_and_duplicate_points(self):
        for mutate in ('unknown', 'duplicate'):
            inp = self.read()
            if mutate == 'unknown':
                inp.paths['missing'] = inp.paths.pop('WS1')
            else:
                inp.paths['WS1'].append(inp.paths['WS1'][0])
            self.build(inp)
            self.assertTrue(inp.errors)

    def test_missing_file_and_invalid_gridfs(self):
        inp = self.read()
        self.build(inp, mode='gridfs')
        self.assertTrue(any(e.get('column')=='gridfs_id' for e in inp.errors))
        inp = self.read()
        inp.data['Files']['F1']['File_Path'] = 'missing.nc'
        self.build(inp)
        self.assertTrue(any(e.get('column')=='File_Path' for e in inp.errors))

    def test_file_targets_tool_machine_and_workplan(self):
        for source, target in [('Tool_File','T1'),('Machine_File','M1'),('Part_File','OP1')]:
            inp = self.read()
            inp.data['Files']['F1'].update(source_table=source, target_record=target)
            assets, staged, _ = self.build(inp)
            self.assertFalse(inp.errors)
            self.assertEqual(len(staged), 1)
            f = next(a.dt_elements[0] for a in assets if isinstance(a.dt_elements[0], c.m.DtFile))
            if target == 'OP1':
                self.assertEqual(f.reference[0].keys[1].key, c.m.DtKeyType.WORKPLAN)

    def test_part_selection_required_and_no_unrelated_assets(self):
        inp = self.read()
        inp.data['Part_Info']['P2'] = dict(inp.data['Part_Info']['P1'], Part_No='OTHER')
        self.build(inp)
        self.assertTrue(inp.errors)
        inp.errors.clear()
        assets, _, _ = self.build(inp, part='DEMO-P001', rev='01')
        self.assertFalse(inp.errors)
        self.assertEqual(len(assets), 5)

    def test_no_overwrite_and_idempotent_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            a = c.run(EXAMPLE, Path(temp)/'a')
            b = c.run(EXAMPLE, Path(temp)/'b')
            self.assertEqual(a['xml_files'], b['xml_files'])
            with self.assertRaises(c.InputError):
                c.run(EXAMPLE, Path(temp)/'a')

    def test_strict_input_types(self):
        for value, kind in [(True,'number'), ('nan','number'), ('inf','positive'), (-1,'positive'),(1.5,'integer'),(1,'text'),('yes','bool'),('0,0,0','unitvector'),('1,2','vector'),('inch/min','mm/min|m/s')]:
            with self.subTest(value=value, kind=kind), self.assertRaises((ValueError, TypeError)):
                c.parse_value(value, kind)
        self.assertIs(c.parse_value('false','bool'), False)
        self.assertEqual(c.parse_value('001','text'), '001')

    def test_formula_is_rejected_at_cell(self):
        # In-memory reader fixture only; never rewrites the deliverable workbook.
        wb = c.openpyxl.load_workbook(EXAMPLE)
        wb['업체입력']['D5'] = '=1+1'
        with patch.object(c.openpyxl, 'load_workbook', return_value=wb):
            inp = c.Input()
            inp.read(EXAMPLE)
        self.assertTrue(any(e['cell']=='업체입력!D5' and '수식' in e['message'] for e in inp.errors))

    def test_missing_boolean_is_not_defaulted(self):
        wb = c.openpyxl.load_workbook(EXAMPLE)
        ws = wb['필수보완']
        target = next(row[3] for row in ws.iter_rows(min_row=5) if row[2].value=='coolant')
        address = '필수보완!' + target.coordinate
        target.value = None
        with patch.object(c.openpyxl, 'load_workbook', return_value=wb):
            inp = c.Input()
            inp.read(EXAMPLE)
        self.assertTrue(any(e['cell']==address and '필수값' in e['message'] for e in inp.errors))

    def test_unsupported_column_is_reported(self):
        wb = c.openpyxl.load_workbook(EXAMPLE)
        ws = wb['업체입력']
        ws.append(['Part_Info','P1','원가',5000,'선택','미사용'])
        with patch.object(c.openpyxl, 'load_workbook', return_value=wb):
            inp = c.Input()
            inp.read(EXAMPLE)
        self.assertFalse(inp.errors)
        self.assertEqual(inp.unmapped[0]['column'], '원가')

    def test_required_model_check_accepts_false_but_catches_missing(self):
        obj = c.m.MillingMachineFunctions(coolant=False, through_spindle_coolant=False, chip_removal=False)
        self.assertEqual(c.required_errors(obj), [])
        obj.chip_removal = None
        self.assertEqual(c.required_errors(obj), ['dt_asset.chip_removal'])


if __name__ == '__main__':
    unittest.main()
