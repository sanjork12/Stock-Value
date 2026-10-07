"""Single-stock comparable diagnostics; no dashboard columns or side effects."""
import json
import streamlit as st


def render_peer_comparable(peer, mode="diagnostic", diagnostics=None):
    if peer is None:
        if (diagnostics or {}).get("status") == "UNAVAILABLE":
            st.caption("Peer Comparable: Unavailable（同行诊断暂不可用）")
        else:
            st.caption("同行可比估值：历史快照未保存同行数据。")
        return
    st.markdown("#### 同行可比估值 · Peer Comparable")
    st.caption("诊断模式：仅供参考，不改变内部 fair value 或买卖区。" if mode != "active"
               else "Active 模式：合格同行模型按保守权重参与估值。")
    st.write({"同行组": peer.get("peer_group"), "估值倍数": peer.get("selected_multiple"),
              "目标当前倍数": peer.get("target_multiple"), "Q1": peer.get("peer_q1"),
              "Median": peer.get("peer_median"), "Q3": peer.get("peer_q3"),
              "目标财务指标": peer.get("target_metric"), "指标值": peer.get("target_metric_value"),
              "Confidence": peer.get("confidence"), "Dispersion": peer.get("dispersion")})
    if peer.get("valid"):
        st.write(f"同行估值区间：{peer['low']:,.2f} / {peer['mid']:,.2f} / {peer['high']:,.2f}")
    else:
        st.info("同行估值不可用：至少需要三家合格同行和可信的目标财务指标。")
    st.write("纳入同行：", ", ".join(peer.get("peers_included") or []) or "无")
    exclusions = peer.get("exclusion_reasons") or {}
    if exclusions:
        st.dataframe([{"Ticker": t, "排除原因": reason} for t, reason in exclusions.items()], hide_index=True)
    for warning in peer.get("warnings") or []:
        st.caption(warning)
    with st.expander("同行数据来源与时效"):
        st.json(peer.get("provenance") or {})
    st.download_button("下载同行诊断 JSON", json.dumps(peer, ensure_ascii=False, indent=2),
                       file_name=f"peer_{peer['target_ticker']}.json", mime="application/json",
                       key=f"peer_download_{peer['target_ticker']}")
