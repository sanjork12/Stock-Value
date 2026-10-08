"""Offline real-widget check of Cloud export with synthetic production inputs."""
from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
from unittest.mock import patch
from streamlit.testing.v1 import AppTest


def main():
    root=Path(__file__).resolve().parents[1]
    source=f'''
import sys
sys.path.insert(0,{str(root)!r})
sys.path.insert(0,{str(root/'tests')!r})
import streamlit as st
from test_v45_snapshot_export import SnapshotExportTests
import production_snapshot_admin as admin
from scripts.verify_peer_isolation import history
test=SnapshotExportTests()
test.setUp()
admin.render_snapshot_export(st,test.client,'u',history_loader=history,
    fundamentals_loader=lambda t:test.financials[t])
'''
    with TemporaryDirectory() as directory:
        path=Path(directory)/'app.py';path.write_text(source,encoding='utf-8')
        app=AppTest.from_file(str(path),default_timeout=20)
        app.secrets['ADMIN_EMAIL']='admin@test.com'
        app.run();assert not app.exception
        next(b for b in app.button if b.label=='运行五股生产分析快照').click().run()
        assert not app.exception
        report=app.session_state['_v45_export_result']['report']
        assert len(report['stocks'])==5
        assert all(s['capture_status']=='COMPLETE' for s in report['stocks'])
        assert report['batch_calibration_eligibility'] in ('ELIGIBLE','INELIGIBLE')
        assert any('Calibration Batch Status' in element.value for element in app.markdown)
        assert any('Correlation & Cross-Family Governance' in element.value for element in app.markdown)
        assert all('correlation_cross_family_governance' in s for s in report['stocks'])
        assert any('Family-Level Blend Experiment' in element.value for element in app.markdown)
        assert all('experimental_family_blend' in s for s in report['stocks'])
        assert any('Independent Evidence & Family Suppression' in element.value for element in app.markdown)
        assert all('independent_evidence_governance' in s for s in report['stocks'])
        assert any('Capital Structure Overlay' in element.value for element in app.markdown)
        assert all('capital_structure_overlay' in s for s in report['stocks'])
        assert any('Enterprise-Aware Valuation Experiment' in element.value for element in app.markdown)
        assert all('enterprise_aware_experiment' in s for s in report['stocks'])
        assert all('calibration_eligibility_reasons' in s for s in report['stocks'])
        if report['batch_calibration_eligibility']=='INELIGIBLE':
            assert any('本批次仅用于输入降级诊断，不应用于估值校准。' in w.value for w in app.warning)
        assert all('enterprise_family_suitability' in s for s in report['stocks'])
        assert any('V4.9 Enterprise Family Suitability Audit' in e.value for e in app.markdown)
        assert len(app.get('download_button'))==5
        assert any('V4.6 Reliability Governance Audit' in element.value for element in app.markdown)
        import production_snapshot_admin as admin
        legacy=deepcopy(app.session_state['_v45_export_result'])
        original_batch=legacy['report']['batch_id']
        original_stamp=legacy['report']['generated_at']
        for stock in legacy['report']['stocks']:
            stock.pop('enterprise_aware_experiment',None)
        app.session_state['_v45_export_result']=legacy
        with patch.object(admin,'capture_analysis',side_effect=AssertionError('Legacy rerender must not fetch')):
            app.run()
        assert not app.exception
        repaired=app.session_state['_v45_export_result']['report']
        assert len(repaired['enterprise_experiment_wiring']['repaired_tickers'])==5
        assert repaired['batch_id']==original_batch and repaired['generated_at']==original_stamp
        for stock in repaired['stocks']:
            experiment=stock['enterprise_aware_experiment']
            assert experiment['production_fair']==stock['production_analysis_fair']
            assert isinstance(experiment['enterprise_evidence_status'],str)
            assert isinstance(experiment['production_readiness'],str)
            assert 'input_snapshot' in experiment
        admin._LAST_RUN.clear()
        next(b for b in app.button if b.label=='V4.6 Reliability Governance Audit').click().run()
        assert not app.exception
        governance_report=app.session_state['_v45_export_result']['report']
        assert len(governance_report['stocks'])==5
        for stock in governance_report['stocks']:
            audit=stock.get('reliability_governance_audit')
            if audit:
                assert audit['fair_unchanged'] and all(audit['invariants'].values())
        app.secrets['ADMIN_EMAIL']='ordinary@test.com'
        app.run();assert not app.exception
        assert len(app.get('download_button'))==0
        assert '_v45_export_result' not in app.session_state
    print('V4.5 snapshot UI: batch, downloads, access revocation PASS')


if __name__=='__main__':main()
