# V4.4 Peer Comparable Diagnostic Review

审查对象：`1726299fd0af36beb0988bffc7d7406273220ef6`。本轮不 commit、不 push；生产参数、估值、normalization、fallback、Auth/RLS 均未修改。

**状态：PENDING_CLOUD_EVIDENCE。代码审查和本地隔离验证已完成，真实五股纠偏效果尚未验证。**

本地 `configured_api_key()` 仅检查是否配置，结果为 false；未读取、打印或保存密钥。既有 `reports/v44_peer_comparison.json` 同样是 `live_finnhub_configured=false`，不能当作 Cloud 观测。合成测试只证明算法行为，不是市场结果。

五股结果表和逐股完整字段见 [可读报告](v44_peer_diagnostic_review.html)，机器可读数据见 [JSON](v44_peer_diagnostic_review.json)。`null` 表示未观测；不是零，也不是 Cloud 模型一定不可用。

## A. Files changed

- `scripts/report_peer_comparable.py`：增强已有只读报告工具，记录逐个 peer 的倍数、growth、margin、market cap、来源时间、纳入/排除原因及比较字段。只允许 profile2/metric 两个 Finnhub endpoint，重复 peer 复用同一份观测，全局 rate limit 后停止后续取数。默认不重新请求 Yahoo 或 estimates；目标输入由已捕获的 normalized snapshot 注入，可通过 `--target-input-file` 指定按 ticker 索引的输入 JSON。
- `tests/test_peer_review_report.py`：报告透明性、benchmark 隔离、endpoint 白名单、Alphabet 去重、限流和高 dispersion 审查测试。
- 本报告、HTML、JSON：本地缺少 Cloud 数据的真实状态及结构审查结论。

没有修改 `peer_comparable.py`、`valuation_engine.py`、`analysis_service.py`、`financial_normalization.py`、`last_reliable_valuation.py` 或生产配置。

## B. Data freshness / source

本轮实际 Finnhub 网络请求为零。所有 live multiple、growth、margin、market cap、Q1/median/Q3、peer fair、fetched_at、data_age 都未观测，不能填入猜测值。数据来源标签为计划使用的 Finnhub Company Profile / Basic Financials，不代表已经成功取得。

现有模型拒绝未知取数时间、超过 72 小时或未来超过约 6 分钟的数据。provider 的 profile TTL 为 24 小时，metrics TTL 为 8 小时。**这些是 retrieval/cache 时效，不是财务报表期或 forward EPS 估计期**；不能据此宣称基本面“最新”。

目标 forward EPS 来自已有 normalized target financials；同行 Forward PE 来自 Finnhub 显式 `forwardPE` 映射。来源/估计期可能不同，应在真实审查中单独披露。不得把 TTM PE 改名作为 Forward PE。网页/年报仅用于业务结构核对，不替代 Finnhub multiple 数据。

## C. Five-stock data and multiple selection

五只股票当前重新观测的 internal fair/range 和 Peer 数值均未取得。用户提供的约数仅保存在 `reference_context`，没有写入 `current_internal_fair/low/high`。报告保留所有要求的字段和完整候选组成，未知值明确为空。

当前选择机制是 **first valid multiple**：依次尝试，首个合格结果立即 `break`。不是 Forward PE/EV-EBITDA/EV-Revenue 的加权组合。`selection_attempts` 是备选尝试记录；不存在另一个 peer combined blend。

- NVDA：Forward P/E → EV/EBITDA；target revenue growth >=20% 时追加 EV/Revenue。
- ORCL、MSFT：enterprise_software 路径，Forward P/E → EV/EBITDA → EV/Revenue。
- GOOG、AMZN：Forward P/E → EV/EBITDA。
- 本次五只不采用 P/B；P/B/TTM PE 是 bank 路径，不能套到这五只。

## D. Peer composition and group quality

### NVDA — REVISE（结构建议，尚无 live 数值验证）

候选仅 AVGO、AMD、MRVL；peer-only class 都为 semiconductor_growth。不是三家公司“保证被纳入”，必须各自通过 growth/margin/正盈利/倍数和 outlier gate。

AMD/AVGO 的业务相关性使其可作为研究候选，但整个公司并非 NVIDIA 的同质复制。Broadcom 同时经营 semiconductor 和 infrastructure software；Marvell 是 data infrastructure semiconductor，不能只因为缺第三家就将其视为完全可比。池子仅三家，任何一家缺失或被剔除，就不足三家而不可用。**不要为凑足三家放松既有 gate。**

判断 358.45 是否向 300 收敛所需的 peer median、target forward EPS 和实际 surviving peers 尚缺；目前不能给 KEEP 或宣称改善。

### ORCL — REVISE（结构建议，尚无 live 数值验证）

候选 MSFT、CRM、NOW、SAP、IBM。MSFT 的 peer class 为 mega_cap_tech；CRM/SAP/IBM 为 mature_growth；NOW 为 high_growth_software。它们通过 enterprise_software 兼容集合进入候选，这不等同业务完全同质。

Oracle 的 cloud/software、hardware、services 组合与纯应用 SaaS 有差异。建议后续分别审视 enterprise database/cloud infrastructure 与 enterprise application SaaS，而非只缩短名单。MSFT/SAP/IBM 与 CRM/NOW 的组合差异可能令同一个 median 没有清晰经济含义；应先验证规模、growth、margin 和盈利口径，再谈进入 blend。不能根据 180 benchmark 选择名单。

### MSFT — REVISE（结构建议，尚无 live 数值验证）

实际候选 ORCL、CRM、NOW、SAP、IBM。**当前没有把 AAPL/AMZN/GOOG/META 混入一个 mega-cap peer median**；`group_for()` 先按 ticker 的 business family 选择 enterprise_software。

问题是该企业软件组能否代表 MSFT 的整体业务，而非“mega-cap 池太宽”。官方披露显示微软覆盖企业应用/基础设施及消费者业务；因此仅用 enterprise software 同行并不能自动代表全部 cash flows。建议将其作为子业务诊断，而不是直接修正整家公司内部 fair。

### GOOG — REVISE（结构建议，尚无 live 数值验证）

实际候选 META、TTD、PINS、SNAP。没有 AAPL、AMZN、MSFT，也没有把 GOOGL 当成第二家公司。GOOGL 在候选、请求和报告中 canonicalize 为 GOOG。

因此不能归因于“mega-cap peer 把 GOOG 压低”；真实风险是广告组在规模、广告模式及 Cloud 占比上的差异。现有 market cap gate 仅要求正值，没有 target/peer 规模比筛选；growth/margin 绝对差阈值也不衡量 Search 与社交/广告工具业务组合差异。Alphabet 披露 Services、Cloud、Other Bets；广告 peer median 不等价整体估值。254 是否应向 345 上移，尚无实际 Peer 数值证据。

### AMZN — REVISE（整体公司单倍数路线暂不建议纳入）

候选 BABA、JD、MELI、EBAY。当前组为 commerce_platform，模型已明确标记 heterogeneous_business_mix，并将 confidence 设为 LOW，但仍可能 valid=true。

Amazon 包含零售与 AWS；跨公司整体 PE/EV-EBITDA 会混合 cloud、零售、广告、物流、地理和平台差异。增长与 operating margin 两个 gate 不能解决全部 mix 问题。建议后续按业务分部研究，再决定是否有可用的 peer 校验；本轮不新建 SOTP，也不改变内部估值。不能声称当前 Peer 能保持在 285–300。

## E–G. Internal / Peer / external benchmark

仅按用户提供的约数计算（不是实时重新估值）：

- NVDA：internal 358.45，benchmark 300，Internal Error **+19.48%**。
- ORCL：internal 237.71，benchmark 180，Internal Error **+32.06%**。
- AMZN：internal 290.44，benchmark 285，Internal Error **+1.91%**。
- MSFT：internal 657.04，benchmark 544，Internal Error **+20.78%**。
- GOOG：internal 253.81，GOOGL/同公司 benchmark 345，Internal Error **−26.43%**。

Peer Mid、Difference $/%、Peer Error、Peer Direction 和改善/变差均 **未验证**。目前既没有证据证明哪只明显改善，也没有证据证明哪只反而更差。不得把数据缺失理解为“模型已经证实无价值”。用户 benchmark 本身不是已验证 fair value，只是人工比较基准。

数学上方向正确也不等于改善：例如 NVDA 下降过度、GOOG 上升过度都可能扩大 absolute error；AMZN 起点已接近 benchmark，轻微偏移也可能变差。真实比较必须同时保留 signed error 和 absolute deviation。

## H. Important model/review gaps

1. **High dispersion 并不使当前模型 invalid。** `IQR/median >0.6` 仅将 confidence 设为 LOW，仍可能输出 precise range。合成测试可复现三个倍数 10/25/50 得到 dispersion=0.8、model valid=true。本轮按审查要求把此类结果设为 `review_eligible=false`，明确区别于原始 `peer_valid`，不修改模型参数。
2. Commerce 异质性同样只是 LOW/warning，不是 hard invalid gate。审查不把该精确价格当作可激活的正式 fair。
3. 没有 market-cap ratio gate，也没有逐分部 comparability gate。代码中的 peer-only class 标签不是独立证据。
4. Outlier removal 后重新算分位数是正确的，但 NVDA 三候选池对任何剔除极敏感。真实报告应保留 removal 前后的 multiples，不能只看最终 median。
5. 现有单股 JSON 有纳入名单、多个尝试、倍数及时间，但**没有完整逐 peer growth/margin/market cap**；只靠旧 JSON 无法完成全部组成审查。增强报告工具对此进行只读旁录，原始输入不改写。

如果真实 Peer 与内部差异超过 20%，需区分：目标 EPS 与内部 blended metric 差异、peer multiple 差异、EV-to-equity cash/debt/shares 转换、名单筛选及 outlier 前后变化。**不能把 peer-vs-blended-fair 差异全部解释成 target PE 的差异。** 当前没有真实数据，故不臆造哪项主导。

## I. Activation recommendation

五只的结构性建议暂定均为 **REVISE**，不是 live performance verdict。没有股票达到有证据支持的 KEEP；在少于三家、高 dispersion 或明显不可比的实际运行中，应按本次审查要求拒绝正式 precise fair/activation。

**现阶段不建议任何一个 valuation class 正式激活。保持 diagnostic。** 完成真实数据和分组复核后，优先考虑较同质的 semiconductor_growth 子组和 mature_growth 中的 enterprise-software 子组，小范围逐 ticker 验证；不是按整个 class 一键启用。MSFT/GOOG/AMZN 这类混合业务不宜因为“mega_cap_tech”同标签就统一启用。

## J. Tests / isolation

完整测试命令：`python -m unittest discover -s tests -v`。

结果：**414 PASS，0 FAIL，0 ERROR**。

本轮覆盖五股报告、benchmark 不进入选组/倍数/模型、只调用两个 endpoint、GOOG 去重、跨股票复用观测、全局限流停止、缺 key 不请求目标财务数据、不编造当前值、旁录器不改变模型输出以及 high-dispersion 审查拒绝。

既有强制 diagnostic isolation 测试继续验证 internal fair/range、confidence、valuation_mode、reliability、dispersion、buy/exit zones 和所有内部模型输出不变。真实 Cloud session/config 未被本地观察；不能把 fixture 隔离验证说成 Cloud 实测。

## K. Commit / remaining evidence

当前 HEAD：`1726299fd0af36beb0988bffc7d7406273220ef6`。本轮没有新 commit、没有 push。

完成实际 B/C（改善/变差）及最终 KEEP/REJECT 所需：Cloud 当前五只 internal range 和 Peer diagnostics，以及两个 Finnhub endpoint 的公开字段/时间旁录。旧报告里的 NOT_CONFIGURED 不是有效替代。应在能读取 Streamlit Secrets 的可信运行环境直接调用增强报告函数；不能把 API key 粘贴到聊天、导出 JSON 或报告。CLI 本地启动不会自动继承 Cloud secrets。

## Public business-structure sources（不参与计算）

- [NVIDIA 2026 annual report](https://s201.q4cdn.com/141608511/files/doc_financials/2026/ar/2026-annual-report-web-Hyperlinks.pdf)
- [Broadcom company](https://www.broadcom.com/company)
- [Marvell company](https://www.marvell.com/company.html)
- [AMD 2025 annual report](https://ir.amd.com/financial-information/sec-filings/content/0001193125-26-129106/0001193125-26-129106.pdf)
- [Oracle FY2026 results](https://investor.oracle.com/investor-news/news-details/2026/Oracle-Announces-Record-Q4-and-FY-2026-Results-Driven-by-Cloud-Infrastructure--Cloud-Applications/default.aspx)
- [Microsoft FY27 reporting update](https://www.sec.gov/Archives/edgar/data/789019/000119312526380280/d291965dex991.htm)
- [Alphabet 2025 10-K](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000018/goog-20251231.htm)
- [Amazon 2025 10-K](https://www.sec.gov/Archives/edgar/data/1018724/000101872426000004/amzn-20251231.htm)

由以上业务披露推断 peer comparability 风险；它们不证明某个 peer median 的数值方向，也没有替换规定的 Finnhub 数据源。
