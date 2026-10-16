"""Frozen figure inputs retain exact scientific counts and family identity."""
import csv
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.figure_data import ROOT, data

class FigureDataTests(unittest.TestCase):
    def test_retained_inputs_match_the_paper(self):
        counts,timing=data()
        self.assertEqual(counts,[(4,9,6,2),(8,12,11,6),(12,14,13,12)])
        self.assertEqual(len(timing),5)

    def test_changed_denominator_or_certificate_family_is_rejected(self):
        for relative,field in [('results/summary/sensitivity.csv','cases'),
                               ('results/microbenchmark/summary.csv','local_records')]:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                for name in ['results/summary/sensitivity.csv','results/microbenchmark/summary.csv']:
                    target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(ROOT/name,target)
                target=root/relative
                with target.open(encoding='utf-8',newline='') as stream:
                    records=list(csv.DictReader(stream))
                if field=='local_records':
                    row=next(r for r in records if int(r['d'])==4)
                else:
                    row=records[0]
                row[field]=str(int(row[field])+1)
                with target.open('w',encoding='utf-8',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=list(records[0]))
                    writer.writeheader();writer.writerows(records)
                with self.assertRaises(ValueError):
                    data(root)
