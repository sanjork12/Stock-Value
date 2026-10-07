"""Conservative Chinese fact extraction from the supplied publisher summary.

No body fetching, financial estimates, or ungrounded numeric completion. Unsupported
sentences remain evidence only; they are never presented as translated facts.
"""
import re

INSUFFICIENT = '原始摘要信息不足，建议阅读原文'
COMPANIES = {
 'AAPL': ('苹果', r'Apple|iPhone|MacBook'), 'MSFT': ('微软', r'Microsoft|Azure'),
 'GOOG': ('谷歌', r'Google|Alphabet'), 'AMZN': ('亚马逊', r'Amazon|AWS'),
 'NVDA': ('英伟达', r'Nvidia'), 'META': ('Meta', r'Meta|Facebook'),
 'TSLA': ('特斯拉', r'Tesla'), 'MU': ('美光', r'Micron'),
 'AVGO': ('博通', r'Broadcom'), 'ORCL': ('甲骨文', r'Oracle'),
 'PLTR': ('Palantir', r'Palantir'), 'JPM': ('摩根大通', r'JPMorgan|JP Morgan'),
 'NFLX': ('奈飞', r'Netflix'), 'UBER': ('优步', r'Uber'),
 'BABA': ('阿里巴巴', r'Alibaba'), 'ANET': ('Arista', r'Arista'),
}


def canonical(ticker):
    return 'GOOG' if str(ticker).upper() == 'GOOGL' else str(ticker).upper()


def mentions(text):
    return [t for t, (name, pattern) in COMPANIES.items()
            if re.search(r'\b(?:' + pattern + '|' + t + ('|GOOGL' if t == 'GOOG' else '') + r')\b', text, re.I)
            or name in text]


def ticker_roles(headline, summary, related):
    related = {canonical(t) for t in re.findall(r'[A-Z0-9.\-]+', str(related).upper())}
    primary = mentions(headline)
    if not primary:
        # Only a leading named subject can establish relevance without a title mention.
        primary = mentions(re.split(r'[.!?。]', summary)[0][:160])
    for t in mentions(summary):
        if t not in primary:
            pattern = COMPANIES[t][1]
            count = len(re.findall(r'\b(?:'+pattern+'|'+t+r')\b', summary, re.I))
            if count >= 2 and re.search(r'compar|versus|\bvs\b|competitor|rival', summary, re.I):
                primary.append(t)
    secondary = sorted((set(mentions(summary)) | related) - set(primary))
    return primary, secondary


def chinese_title(headline, primary, kind):
    names = '与'.join(COMPANIES.get(t, (t, ''))[0] for t in primary)
    if re.search(r'[\u4e00-\u9fff]', headline):
        return headline
    if re.search(r'earnings.*test.*(?:cloud|infrastructure)', headline, re.I):
        return f'{names}财报将检验AI云基础设施需求是否持续强劲'
    upcoming = bool(re.search(r'\b(?:to|will|preview|ahead|expected)\b', headline, re.I))
    labels = {'earnings': '将公布财报' if upcoming else '公布财报进展',
              'guidance': '更新业绩指引', 'capex': '资本开支出现新进展',
              'partnership': '披露合作或合同进展', 'regulation': '面临监管新进展',
              'legal': '法律事项出现新进展', 'product': '披露产品进展',
              'management': '管理层出现变动', 'M&A': '并购事项出现新进展',
              'competition': '竞争格局出现新进展'}
    return names + labels.get(kind, '业务动态')


def summarize(headline, summary, primary, kind, area):
    title = chinese_title(headline, primary, kind)
    facts, evidence, areas = [], [], {}
    sentences = re.split(r'(?<=[。!?])\s*|(?<=\.)\s+(?=[A-Z])', summary.strip())
    metrics = [(r'(?:cloud\s+)?revenue|sales', '收入', '收入'),
               (r'operating margin|gross margin', '利润率', '利润率'),
               (r'capital expenditures?|capex', '资本开支', '资本开支'),
               (r'net income|net profit', '净利润', '估值逻辑'),
               (r'free cash flow', '自由现金流', '估值逻辑'),
               (r'contract|deal', '合同金额', '收入')]
    for sentence in sentences:
        if len(facts) >= 4:
            break
        if re.search(r'[\u4e00-\u9fff]', sentence) and len(sentence) >= 12:
            facts.append(sentence); evidence.append(sentence)
            continue
        if re.search(r'\b(?:not|never|denied|denies|no longer)\b', sentence, re.I):
            continue  # Unsupported negation must not be turned into an affirmative fact.
        # Extract the whole metric clause, with direction and units preserved.
        for pattern, label, impact_area in metrics:
            match = re.search(r'\b(' + pattern + r')\b([^;]*?)(?=\b(?:and|while|but)\b|\.(?!\d)|;|$)', sentence, re.I)
            if not match:
                continue
            clause = match.group(0)
            numbers = re.findall(r'(?:[-−]?[$€£]\s*[-−]?\d[\d,]*(?:\.\d+)?\s*(?:billion|million|trillion|bn|mn)?|[-−]?\d[\d,]*(?:\.\d+)?\s*(?:billion|million|trillion|bn|mn|%|percent))', match.group(2), re.I)
            if not numbers:
                continue
            # Use the nearest named company before the metric, avoiding attribution
            # of an Oracle figure to every company mentioned later in the sentence.
            prefix = sentence[:match.start()]
            named_positions = [(m.start(), t) for t in mentions(prefix) for m in re.finditer(r'\b(?:'+COMPANIES[t][1]+'|'+t+r')\b', prefix, re.I)]
            subjects = [max(named_positions)[1]] if named_positions else mentions(sentence) or primary
            subject = '、'.join(COMPANIES[t][0] for t in subjects)
            guidance = bool(re.search(r'expect|forecast|guidance|project|outlook|\bcould\b|\bmay\b|rumou?r|unconfirmed', sentence, re.I))
            direction = '下降' if re.search(r'fell|declin|decreas|down|drop', clause, re.I) else '增长' if re.search(r'grew|grow|increas|rose|up|rise', clause, re.I) else '披露'
            # Keep original units to avoid silently changing the reported magnitude.
            values = '；'.join(re.sub(r'\b(billion|million|trillion|percent|bn|mn)\b', lambda m: {'billion':'十亿','million':'百万','trillion':'万亿','percent':'%','bn':'十亿','mn':'百万'}[m[0].lower()], n.strip(), flags=re.I) for n in numbers)
            metric_label = '云收入' if re.search(r'cloud\s+revenue', match[1], re.I) else label
            qualifier = '预期（尚未实现）' if guidance else '报道数据'
            facts.append(f'{subject}：{metric_label}{direction}，{qualifier}为 {values}（按原摘要顺序）。')
            evidence.append(clause)
            areas[impact_area] = '不确定' if guidance else ('负面' if direction == '下降' else '正面' if direction == '增长' and impact_area == '收入' else '不确定')
            if len(facts) >= 4:
                break
        if len(facts) < 4 and re.search(r'(?:will|to|scheduled to)\s+(?:report|release|announce)|earnings.*(?:this week|next week)', sentence, re.I):
            names = '、'.join(COMPANIES[t][0] for t in mentions(sentence) or primary)
            facts.append(names+'即将公布财报；本文讨论的是业绩检验窗口，并非已实现的业绩结果。')
            evidence.append(sentence)
        business_topics = [(r'custom AI (?:chips|accelerators)', '定制AI芯片'),
                           (r'cloud infrastructure', '云基础设施'),
                           (r'AI.driven demand|AI demand', 'AI需求'),
                           (r'export (?:ban|restrictions?)', '出口限制')]
        topics = [zh for pattern,zh in business_topics if re.search(pattern,sentence,re.I)]
        if topics and len(facts) < 4:
            facts.append('报道具体涉及'+'、'.join(topics)+'，这些业务是本文讨论的对象。')
            evidence.append(sentence)
        if len(facts) < 4 and re.search(r'launch|unveil|introduc|roadmap', sentence, re.I):
            products = re.findall(r'\b(?:Blackwell|Rubin|iPhone(?:\s+\d+)?|MacBook|Gemini|Qwen|Megapack|Robotaxi|Trainium|Maia|Foundry|AIP)\b', sentence, re.I)
            if products:
                names = '、'.join(COMPANIES[t][0] for t in mentions(sentence) or primary)
                planned = bool(re.search(r'will|plans?|expects?|roadmap',sentence,re.I))
                facts.append(names+('计划推出' if planned else '披露')+'、'.join(dict.fromkeys(products))+'产品进展。')
                evidence.append(sentence)
                areas['竞争格局'] = '不确定'
    if len(summary.strip()) < 60 or not facts:
        facts = [INSUFFICIENT]; evidence = []; areas = {{'产品':'竞争格局','监管':'估值逻辑','竞争':'竞争格局','估值':'估值逻辑'}.get(area,area): '不确定'}
    names = '、'.join(COMPANIES.get(t, (t,''))[0] for t in primary)
    contexts = {
      'earnings': (f'{names}的收入兑现与利润转换是本次财报检验的核心；预告不能当作已公布业绩。', ['下一季度收入及同比增速', '营业利润率与自由现金流']),
      'guidance': (f'{names}更新的预期会改变未来增长假设，需区分管理层目标与已实现收入。', ['指引适用季度及收入区间', '下次财报与此次指引的差异']),
      'capex': (f'{names}投入增加会先占用现金；产能利用率和新增收入决定投入能否回收。', ['现金资本开支与经营现金流', '新增产能上线时间和利用率']),
      'partnership': (f'{names}的合同价值取决于约束性条款、交付与收入确认，不能把签约金额全部计为当期收入。', ['合同生效和交付里程碑', '已确认收入与剩余履约义务']),
      'product': (f'{names}的产品进展需要转化为客户采用和收入，发布本身不代表商业兑现。', ['产品交付时间', '客户采用与对应业务收入']),
    }
    why, watch = contexts.get(kind, (f'{names}此次事项涉及{area}；投资判断取决于事件是否改变经营条件及实际财务结果。', ['事项生效时间与适用范围', '下一次财报披露的相关成本及收入']))
    return dict(headline=title, conclusion=facts[0] if evidence else title+'。'+INSUFFICIENT,
                facts=facts, fact_evidence=evidence, why_it_matters=why,
                impact_summary=areas, watch_next=watch,
                summary_status=('GROUNDED' if len(evidence) >= 2 else 'PARTIAL_SUMMARY') if evidence else 'INSUFFICIENT_SUMMARY')
