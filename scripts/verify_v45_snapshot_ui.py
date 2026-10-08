"""Offline real-widget check of Cloud export with synthetic production inputs."""
from pathlib import Path
from tempfile import TemporaryDirectory
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
        assert all('calibration_eligibility_reasons' in s for s in report['stocks'])
        if report['batch_calibration_eligibility']=='INELIGIBLE':
            assert any('本批次仅用于输入降级诊断，不应用于估值校准。' in w.value for w in app.warning)
        assert len(app.get('download_button'))==2
        app.secrets['ADMIN_EMAIL']='ordinary@test.com'
        app.run();assert not app.exception
        assert len(app.get('download_button'))==0
        assert '_v45_export_result' not in app.session_state
    print('V4.5 snapshot UI: batch, downloads, access revocation PASS')


if __name__=='__main__':main()
