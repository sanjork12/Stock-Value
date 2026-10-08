"""Metadata-only change: frozen V4.6 payloads retain all behavioral fields."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import unittest
from production_reliability_governance import APPLIED_METADATA,VERSION
from production_snapshot_admin import governance_audit_rows
from tests.test_last_reliable_valuation import analyze,NOW
from scripts.verify_peer_isolation import internal_snapshot
from last_reliable_valuation import reliable_snapshot,apply_last_reliable
from valuation_engine import reconstruct_blend_from_snapshot
from analysis_service import build_snapshot_record


def behavioral_payload(value):
    if isinstance(value,dict):
        return {k:behavioral_payload(v) for k,v in value.items()
            if k not in {'governance_scope','fair_value_effect','production_effect',
                'governance_input_source','reliability_governance_version','governance_status'}
            and not (k=='status' and v in ('DIAGNOSTIC_ONLY','APPLIED_TO_PRODUCTION_RELIABILITY'))}
    if isinstance(value,list):return [behavioral_payload(v) for v in value]
    return value


class GovernanceMetadataTests(unittest.TestCase):
    def test_new_applied_status_and_effects(self):
        g=analyze('AMZN')['blend']['structural_governance']
        for key,value in APPLIED_METADATA.items():self.assertEqual(g[key],value)
        self.assertEqual(g['reliability_governance_version'],'v4.6.1')

    def test_new_snapshot_metadata_and_model_version(self):
        r=analyze('AMZN');row=build_snapshot_record('u',r)
        self.assertEqual(row['raw']['reliability_governance_version'],VERSION)
        self.assertEqual(row['model_version'],r['model_version'])
        self.assertEqual(row['raw']['structural_governance']['status'],'APPLIED_TO_PRODUCTION_RELIABILITY')

    def test_old_diagnostic_snapshot_loads_without_rewrite(self):
        r=analyze('AMZN');row=build_snapshot_record('u',r)
        g=row['raw']['reliability_json']['structural_governance']
        g['status']='DIAGNOSTIC_ONLY';g['reliability_governance_version']='v4.6'
        for key in APPLIED_METADATA:
            if key!='status':g.pop(key,None)
        before=deepcopy(row)
        out=reconstruct_blend_from_snapshot(row)
        self.assertEqual(out['structural_governance']['status'],'DIAGNOSTIC_ONLY')
        self.assertEqual(out['reliability']['reliability_score'],r['reliability_score'])
        self.assertEqual(row,before)

    def test_v46_behavioral_hashes_all_tickers(self):
        baseline=json.loads((Path(__file__).parent/'fixtures/v46_metadata_behavioral_hashes.json').read_text())
        for ticker,expected in baseline['tickers'].items():
            with self.subTest(ticker=ticker):
                payload=behavioral_payload(internal_snapshot(analyze(ticker)))
                digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
                self.assertEqual(digest,expected)

    def test_new_admin_export_metadata(self):
        r=analyze('AMZN');b=r['blend']
        row=governance_audit_rows({'stocks':[{'ticker':'AMZN','source_status':'live',
            'structural_governance':b['structural_governance'],'reliability_governance_audit':b['reliability_governance_audit']}]})[0]
        self.assertEqual(row['governance_status'],'APPLIED_TO_PRODUCTION_RELIABILITY')
        self.assertEqual(row['governance_scope'],'RELIABILITY_CONFIDENCE_AND_EXIT')
        self.assertEqual(row['fair_value_effect'],'NONE')
        self.assertEqual(row['production_effect'],'RELIABILITY_CONFIDENCE_PRECISE_EXIT')
        self.assertEqual(row['reliability_governance_version'],'v4.6.1')

    def test_legacy_admin_export_preserves_version(self):
        s={'ticker':'OLD','source_status':'cached_last_reliable','structural_governance':{
            'status':'DIAGNOSTIC_ONLY','reliability_governance_version':'v4.6','severity':'CRITICAL'}}
        before=deepcopy(s);row=governance_audit_rows({'stocks':[s]})[0]
        self.assertEqual(row['governance_status'],'DIAGNOSTIC_ONLY')
        self.assertEqual(row['reliability_governance_version'],'v4.6')
        self.assertEqual(s,before)

    def test_last_reliable_legacy_metadata_not_recomputed(self):
        r=analyze();saved=reliable_snapshot(r,NOW)
        saved['valuation']['blend']['structural_governance']['status']='DIAGNOSTIC_ONLY'
        saved['valuation']['blend']['reliability_governance_version']='v4.6'
        saved['valuation']['reliability_governance_version']='v4.6'
        before=deepcopy(saved)
        missing=analyze(book_value_per_share=None,tangible_book_value_per_share=None)
        out=apply_last_reliable(missing,{'raw':{'last_reliable':saved}},NOW+timedelta(hours=1))
        self.assertEqual(out['source_status'],'cached_last_reliable')
        self.assertEqual(out['blend'],saved['valuation']['blend'])
        self.assertEqual(out['calculated_at'],saved['calculated_at'])
        self.assertEqual(saved,before)
