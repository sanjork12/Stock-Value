"""Local public-input capture and trusted exported-snapshot comparison.

Writes only to the requested local directory. Never commits or uploads reports.
Cloud snapshots are downloaded separately through the verified admin UI.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from financial_forensics import TICKERS,capture_financial_diagnostic,compare_financial_snapshots,snapshot_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ticker',choices=TICKERS)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'output/financial_input_forensics')
    parser.add_argument('--local',type=Path)
    parser.add_argument('--cloud',type=Path)
    args=parser.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    if args.local or args.cloud:
        if not args.local or not args.cloud:parser.error('Both --local and --cloud are required for comparison.')
        local=json.loads(args.local.read_text(encoding='utf-8-sig'))
        cloud=json.loads(args.cloud.read_text(encoding='utf-8-sig'))
        rows=compare_financial_snapshots(local,cloud)
        path=args.output_dir/f"comparison_{cloud['ticker']}.json"
        path.write_text(json.dumps(rows,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        print('Comparison saved:',path)
        return
    summary=[]
    for ticker in [args.ticker] if args.ticker else TICKERS:
        try:
            snapshot=capture_financial_diagnostic(ticker)
            (args.output_dir/f'local_financial_diagnostic_{ticker}.json').write_bytes(snapshot_json(snapshot))
            trace=snapshot['valuation_failure_trace']
            summary.append({'ticker':ticker,'status':'CAPTURED','availability':trace['valuation_mode'],
                            'reason':trace['internal_reason']})
            print(ticker,'captured:',trace['valuation_mode'],flush=True)
        except Exception:
            # Request exception text can contain URL parameters or auth material.
            summary.append({'ticker':ticker,'status':'CAPTURE_FAILED','reason':'See local network/provider availability; no exception text retained.'})
            print(ticker,'capture failed; no request or exception details retained',flush=True)
    (args.output_dir/'capture_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
