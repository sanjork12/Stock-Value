"""Read-only V4.9 export from a captured eligible Cloud batch; never fetches data."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from enterprise_family_suitability import audit_export,csv_export
from financial_forensics import snapshot_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-json',required=True,type=Path)
    parser.add_argument('--output-dir',required=True,type=Path)
    args=parser.parse_args()
    report=json.loads(args.input_json.read_text(encoding='utf-8-sig'))
    args.output_dir.mkdir(parents=True,exist_ok=True)
    (args.output_dir/'v49_enterprise_family_suitability_audit.json').write_bytes(snapshot_json(audit_export(report)))
    (args.output_dir/'v49_enterprise_family_suitability_audit.csv').write_bytes(csv_export(report))


if __name__=='__main__':main()
