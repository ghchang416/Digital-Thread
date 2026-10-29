"""Original source-column fidelity and natural-key converter integration."""
import io
from pathlib import Path
import unittest
from unittest.mock import patch

import convert as c
from schema import SOURCE, SUPPLEMENT
from original_reader import SPEC, KEYS, DT_SHEETS, record_key

ROOT=Path(__file__).resolve().parents[3]
TEMPLATE=ROOT/'outputs/els_dt_converter/업체DB_원본컬럼_빈양식.xlsx'


class OriginalWorkbookTests(unittest.TestCase):
    def write_row(self, wb, sheet, n, values):
        # In-memory reader fixture. Deliverables are never authored by openpyxl.
        for i,cell in enumerate(wb[sheet][1],1):
            if cell.value in values:
                wb[sheet].cell(n,i,values[cell.value])

    def sample(self):
        wb=c.openpyxl.load_workbook(TEMPLATE)
        for t,defs in SOURCE.items():
            row={d[0]:d[4] for d in defs}
            if t=='Operation_Machining':
                row['Operation_Machining_SN']=101
            self.write_row(wb,t,2,row)
        for sheet,(t,defs) in DT_SHEETS.items():
            row={d[0]:d[4] for d in SOURCE[t]+defs}
            row['Operation_Machining_SN']=101
            self.write_row(wb,sheet,2,row)
        tool={d[0]:d[4] for d in SOURCE['Tool_Milling']}
        tool.update(공구번호='TOOL-002',공구사양='DEMO-D6')
        self.write_row(wb,'Tool_Milling',3,tool)
        for n,tool_no in [(3,'TOOL-002'),(4,'TOOL-001')]:
            step={d[0]:d[4] for d in SOURCE['Operation_Machining']+SUPPLEMENT['Operation_Machining']}
            step.update(Operation_Machining_SN=99+n,SEQNO=(n-1)*10,execution_order=n-1,공구번호=tool_no,공구사양='DEMO-D6' if n==3 else 'DEMO-D10')
            self.write_row(wb,'Operation_Machining',n,step)
            self.write_row(wb,'DT_가공',n,step)
        self.write_row(wb,'Part_File',2,{'Part_File_SN':1,'Part_No':'DEMO-P001','Part_Rev':'01','File_Name':'demo.nc','File_Path':'demo.nc','File_Type':'NC','Doc_Type':'NC'})
        self.write_row(wb,'DT_파일',2,{'source_table':'Part_File','File_SN':1,'content_type':'text/plain'})
        return wb

    def read(self,wb):
        inp=c.Input()
        with patch.object(c.openpyxl,'load_workbook',return_value=wb):
            inp.read(TEMPLATE)
        return inp

    def test_all_236_headers_match_original_document_in_order(self):
        template=c.openpyxl.load_workbook(TEMPLATE,read_only=True)
        original=c.openpyxl.load_workbook(ROOT/SPEC['source'],read_only=True)
        count=0
        for table,meta in SPEC['tables'].items():
            ws=original[meta['sheet']]
            source=[ws.cell(d['source_row'],meta['start_column']).value for d in meta['columns']]
            actual=[cell.value for cell in template[table][1]]
            self.assertEqual(actual,source,table)
            self.assertNotIn('Record_ID',actual)
            count+=len(actual)
        self.assertEqual(count,236)
        template.close();original.close()

    def test_natural_keys_multiple_tools_and_roundtrip(self):
        inp=self.read(self.sample())
        self.assertEqual(inp.errors,[])
        assets,staged,_=c.build(inp,TEMPLATE,None,None,'urn:test','local')
        self.assertEqual(inp.errors,[])
        self.assertEqual(len(assets),6)
        self.assertEqual(len(staged),1)
        project=next(a.dt_elements[0] for a in assets if isinstance(a.dt_elements[0],c.m.DtProject))
        refs=[s.its_operation.ref_dt_cutting_tool.keys[0].value for s in project.main_workplan.its_elements[0].its_elements]
        self.assertEqual(refs[0],refs[2]);self.assertNotEqual(refs[0],refs[1])
        for asset in assets:
            xml=c.XmlSerializer().render(asset)
            self.assertEqual(c.XmlParser().parse(io.BytesIO(xml.encode()),c.m.DtAsset),asset)
        f=next(a.dt_elements[0] for a in assets if isinstance(a.dt_elements[0],c.m.DtFile))
        self.assertEqual(f.content_type,'text/plain')

    def test_changed_column_order_is_rejected(self):
        wb=self.sample()
        ws=wb['Part_Info']
        ws['A1'],ws['B1']=ws['B1'].value,ws['A1'].value
        inp=self.read(wb)
        self.assertTrue(any(e['cell']=='Part_Info!1' for e in inp.errors))

    def test_missing_supplement_is_reported_by_original_sn(self):
        wb=self.sample();wb['DT_가공'].delete_rows(3)
        inp=self.read(wb)
        self.assertTrue(any('102' in e.get('record','') and '필수값' in e['message'] for e in inp.errors))

    def test_duplicate_original_sn_rejected(self):
        wb=self.sample();wb['Operation_Machining']['A3']=101
        inp=self.read(wb)
        self.assertTrue(any(e['cell']=='Operation_Machining!3' and '중복' in e['message'] for e in inp.errors))

    def test_machine_file_number_spelling_is_joined_without_header_change(self):
        wb=self.sample()
        self.write_row(wb,'Machine_File',2,{'Machine_File_SN':2,'설비코드':'MC','번호':'001','File_Name':'demo.nc','File_Path':'demo.nc','File_Type':'NC','Doc_Type':'NC'})
        self.write_row(wb,'DT_파일',3,{'source_table':'Machine_File','File_SN':2,'content_type':'text/plain'})
        inp=self.read(wb)
        self.assertEqual(inp.errors,[])
        assets,staged,_=c.build(inp,TEMPLATE,None,None,'urn:test','local')
        self.assertEqual(inp.errors,[])
        self.assertEqual(len(staged),2)

    def test_unused_cost_is_reported_not_mapped(self):
        wb=self.sample()
        self.write_row(wb,'Part_Info',2,{'자재비':1234})
        inp=self.read(wb)
        self.assertEqual(inp.errors,[])
        self.assertTrue(any(x.get('column')=='자재비' for x in inp.unmapped))
        self.assertFalse(any('자재비' in r for r in inp.data['Part_Info'].values()))

    def test_blank_returns_missing_rows(self):
        inp=c.Input();inp.read(TEMPLATE)
        self.assertTrue(any(e['cell']=='Part_Info!A2' for e in inp.errors))


if __name__=='__main__':
    unittest.main()
