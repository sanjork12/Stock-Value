"""Offline read-only V5 evidence completion from a captured production snapshot."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from enterprise_evidence import complete_report,export_report,export_csv
from financial_forensics import snapshot_json
from production_snapshot_admin import _public


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-json',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    report=json.loads(args.input_json.read_text(encoding='utf-8-sig'))
    completed=complete_report(_public(report))
    args.output_dir.mkdir(parents=True,exist_ok=True)
    (args.output_dir/'v50_enterprise_evidence_completion.json').write_bytes(snapshot_json(_public(export_report(completed))))
    (args.output_dir/'v50_enterprise_evidence_completion.csv').write_bytes(export_csv(completed))


if __name__=='__main__':main()
