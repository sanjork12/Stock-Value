"""Offline real Streamlit widget check; no Cloud credentials required."""
from pathlib import Path
from tempfile import TemporaryDirectory
from streamlit.testing.v1 import AppTest


def main():
    root = Path(__file__).resolve().parents[1]
    source = f'''
import sys
sys.path.insert(0, {str(root)!r})
import streamlit as st
from tests.test_last_reliable_valuation import LastReliableTests
from last_reliable_valuation import render_cache_notice
test = LastReliableTests()
test.setUp()
render_cache_notice(st, test.fallback())
'''
    with TemporaryDirectory() as directory:
        path = Path(directory) / 'cache_ui.py'
        path.write_text(source, encoding='utf-8')
        app = AppTest.from_file(str(path)).run()
        assert not app.exception, 'Streamlit rendering failed'
        assert len(app.warning) == 1
        assert '实时财务输入暂不完整，当前显示最近一次可靠估值。' in app.warning[0].value
        assert '上次可靠更新：' in app.caption[0].value
    print('Last reliable valuation UI: PASS')


if __name__ == '__main__':
    main()
