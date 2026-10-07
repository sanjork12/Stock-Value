"""Repeatable five-stock comparison; credentials never enter reports.

Without configured Finnhub credentials no live financial loader is called.
Reference benchmarks are optional external report inputs, never model inputs.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from finnhub_service import get_finnhub_provider
from mag7_monitor import fill_fundamental_fallbacks, get_live_fundamentals
from peer_comparable import calculate_peer_comparable
from valuation_engine import infer_valuation_class, valuate

SAMPLES = ['NVDA','ORCL','MSFT','GOOG','AMZN']


def build_report(*, provider=None, financial_loader=get_live_fundamentals, references=None):
    provider = provider or get_finnhub_provider()
    configured = provider.configured()
    rows, details = [], []
    for ticker in SAMPLES:
        financials = {}
        status = 'NOT_CONFIGURED'
        internal = None
        if configured:
            try:
                financials = fill_fundamental_fallbacks(financial_loader(ticker) or {})
                internal = valuate(ticker,financials).get('fair')
                status = 'AVAILABLE' if financials else 'NO_TARGET_FINANCIALS'
            except Exception:
                status = 'TARGET_FINANCIALS_UNAVAILABLE'
        peer = calculate_peer_comparable(ticker,financials,infer_valuation_class(ticker,financials),provider=provider)
        context = (references or {}).get(ticker,{})
        benchmark = context.get('external_benchmark')
        direction = 'UNAVAILABLE'
        if peer.valid and internal is not None and benchmark is not None:
            delta = abs(peer.mid-benchmark)-abs(internal-benchmark)
            direction = 'CLOSER' if delta < 0 else 'FURTHER' if delta > 0 else 'UNCHANGED'
        rows.append(dict(ticker=ticker, target_data_status=status, current_internal_mid=internal,
            peer_low=peer.low,peer_mid=peer.mid,peer_high=peer.high,confidence=peer.confidence,
            selected_multiple=peer.selected_multiple,peers_included=';'.join(peer.peers_included),
            external_benchmark=benchmark,benchmark_direction=direction,
            user_supplied_internal_context=context.get('internal_context'),
            warnings=';'.join(peer.warnings)))
        details.append(peer.to_dict())
    return dict(generated_at=datetime.now(timezone.utc).isoformat(),mode='diagnostic',
                live_finnhub_configured=configured,
                caveat='User-supplied internal context is not a current recalculation. Unavailable values are not inferred.',
                comparison=rows,peer_results=details)


def write_report(report, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/'v44_peer_comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (output_dir/'v44_peer_comparison.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        rows=report['comparison']; writer=csv.DictWriter(handle,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',default=str(ROOT/'output'/'peer_comparable'))
    parser.add_argument('--reference-file',type=Path)
    args=parser.parse_args()
    references=json.loads(args.reference_file.read_text(encoding='utf-8')) if args.reference_file else {}
    report=build_report(references=references)
    write_report(report,args.output_dir)
    print('Comparison saved; live Finnhub configured:',report['live_finnhub_configured'])
