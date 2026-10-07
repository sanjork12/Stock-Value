"""Compact read-only external reference panel for the continuous stock page."""
import pandas as pd
import streamlit as st
from finnhub_service import get_finnhub_provider, external_sanity_warnings, STATUS_TEXT, number


def recommendation_summary(rows):
    if not rows:return ''
    latest=rows[0];positive=sum(latest.get(k) or 0 for k in ('Strong Buy','Buy'))
    negative=sum(latest.get(k) or 0 for k in ('Sell','Strong Sell'))
    hold=latest.get('Hold') or 0
    stance='整体偏积极' if positive>max(negative,hold) else '整体偏谨慎' if negative>max(positive,hold) else '观点较为分散'
    change=''
    if len(rows)>1 and latest.get('Hold') is not None and rows[1].get('Hold') is not None:
        delta=latest['Hold']-rows[1]['Hold']
        change='，最新一期持有评级增加' if delta>0 else '，最新一期持有评级减少' if delta<0 else '，最新一期持有评级数量持平'
    return f'分析师{stance}{change}。评级数量是外部观点参考。'


def quote_reference(internal_price,result):
    primary=number(internal_price);data=result.get('data') or {};external=number(data.get('c'))
    if primary is not None and primary>0:return {'price':primary,'source':'Yahoo / 现有行情','fallback':False}
    if external and external>0:return {'price':external,'source':'Finnhub 参考报价（行情缺失时备用）','fallback':True}
    return {'price':None,'source':None,'fallback':False}


def render_external_reference(ticker,internal):
    provider=get_finnhub_provider()
    if not provider.configured():return
    st.markdown('#### 外部市场参考')
    st.caption('独立外部参考，不参与内部估值加权。')
    # Each module fails independently; the provider handles retries and caching.
    results={}
    for key,method in [('公司资料',provider.get_company_profile),('报价',provider.get_quote),
                       ('财务指标',provider.get_basic_financials),('分析师观点',provider.get_recommendation_trends),
                       ('EPS 预期差',provider.get_earnings_surprises)]:
        try:results[key]=method(ticker)
        except Exception:results[key]={'source':'Finnhub','status':'NETWORK_ERROR','data':None,'fetched_at':None}
    profile=results['公司资料'].get('data') or {}
    if profile:
        st.caption(' · '.join(str(profile[k]) for k in ('name','country','exchange','finnhubIndustry') if profile.get(k)))
        values=[]
        if number(profile.get('marketCapitalization')) is not None:values.append(f"市值：{profile['marketCapitalization']:,.0f} 百万 {profile.get('currency') or ''}")
        if number(profile.get('shareOutstanding')) is not None:values.append(f"发行在外股数：{profile['shareOutstanding']:,.2f} 百万股")
        if values:st.caption(' · '.join(values))
    quote=results['报价'];data=quote.get('data') or {}
    if data:
        st.caption(f"Finnhub 参考报价：${data['c']:,.2f} · 报价时间戳：{int(data['t'])}")
        fallback=quote_reference(internal.get('price'),quote)
        if fallback['fallback']:st.info(f"现有行情缺失，备用参考报价 ${fallback['price']:,.2f}；历史指标和估值保持原结果。")
    for warning in external_sanity_warnings(internal,quote,results['财务指标']):st.warning(warning)
    with st.expander('外部财务参考',expanded=False):
        metrics=results['财务指标'].get('data') or {}
        if metrics:st.dataframe(pd.DataFrame([{'指标':k,'Finnhub':v} for k,v in metrics.items()]),hide_index=True,width='stretch')
        else:st.caption(STATUS_TEXT.get(results['财务指标']['status'],'暂无数据'))
        st.caption('ROE、利润率、同比增速单位为百分比；Forward PE 缺失时不以其他 PE 冒充。')
    with st.expander('分析师观点趋势（最近4期）',expanded=False):
        rows=results['分析师观点'].get('data') or []
        if rows:
            st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
            st.caption(recommendation_summary(rows))
        else:st.caption(STATUS_TEXT.get(results['分析师观点']['status'],'暂无数据'))
    with st.expander('EPS 预期差（最近4季）',expanded=False):
        rows=results['EPS 预期差'].get('data') or []
        if rows:
            st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
            beats=sum(row['Beat/Miss']=='Beat' for row in rows)
            st.caption(f'最近 {len(rows)} 季 EPS {beats} 次超预期；不推导未来股价。')
        else:st.caption(STATUS_TEXT.get(results['EPS 预期差']['status'],'暂无数据'))
    failures=[f'{name}：{STATUS_TEXT.get(r["status"],r["status"])}' for name,r in results.items() if r['status'] not in ('AVAILABLE','NO_DATA')]
    if failures:st.caption(' · '.join(failures))
    updated=max((r.get('fetched_at') or '' for r in results.values()),default='')
    st.caption(f'Finnhub · Updated {updated or "—"}（数据获取时间，各模块独立缓存）')
