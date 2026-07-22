import { ChartLine, Newspaper, ShieldWarning, TrendUp, UserFocus } from '@phosphor-icons/react'
import type { ReactNode } from 'react'

import type { ResearchReport } from '../api/client'


const ACTIONS: Record<string, { label: string; summary: string }> = {
  buy: { label: '关注买入', summary: '当前证据整体偏积极，但仍需结合仓位和风险承受能力。' },
  watch: { label: '谨慎观察', summary: '多空证据尚未形成充分共识，建议等待更明确的确认信号。' },
  avoid: { label: '暂时回避', summary: '当前风险或负面证据占优，不建议在此时扩大风险暴露。' },
}

export function ReportModal({ report, onClose }: { report: ResearchReport; onClose: () => void }) {
  const payload = record(report.report_payload)
  const decision = record(payload.top_decision)
  const quant = record(decision.quant)
  const fundamental = record(decision.fundamental)
  const news = record(decision.news)
  const sentiment = record(decision.sentiment)
  const personal = record(payload.personal_context)
  const action = text(decision.action, report.action)
  const actionCopy = ACTIONS[action] || { label: action || '研究结论', summary: '请结合完整证据审慎判断。' }
  const code = text(decision.code)
  const name = text(decision.name)
  const confidence = percent(decision.confidence ?? report.confidence)
  const score = numeric(decision.rank_score) ?? report.rank_score
  const hasDecision = Boolean(code || name || Object.keys(decision).length)

  return <div className="modal-backdrop" role="presentation" onClick={onClose}>
    <section className="report-modal" role="dialog" aria-modal="true" aria-label="深度研究报告" onClick={(event) => event.stopPropagation()}>
      <button className="text-button close" aria-label="关闭研究报告" onClick={onClose}>关闭</button>

      <header className="report-header">
        <p className="eyebrow">DEEP RESEARCH REPORT</p>
        <div className="report-title-row">
          <div>
            <span className={`decision-badge ${action}`}>{actionCopy.label}</span>
            <h2>{code || '个股'} {name}</h2>
          </div>
          <div className="report-score"><strong>{score}</strong><span>综合评分</span></div>
        </div>
        <p className="report-lead">{text(decision.reason, hasDecision ? actionCopy.summary : report.summary || actionCopy.summary)}</p>
        <div className="report-metrics">
          <span>置信度 <strong>{confidence}</strong></span>
          <span>建议仓位 <strong>{text(decision.position_bias, '未给出')}</strong></span>
          <span>生成时间 <strong>{new Date(report.created_at).toLocaleString('zh-CN')}</strong></span>
        </div>
      </header>

      {hasDecision && <>
        <div className="report-two-columns">
          <ReportList title="核心依据" items={strings(decision.top_reasons)} empty="暂未生成核心依据。" />
          <ReportList title="主要风险" items={strings(decision.risk_flags)} tone="risk" empty="当前没有识别出额外风险标记。" />
        </div>

        <ReportList title="结论失效条件" items={strings(decision.invalidation_conditions)} tone="warning" empty="暂未提供明确的失效条件。" />

        <section className="report-section">
          <div className="report-section-title"><ChartLine size={18} /><div><h3>多维分析</h3><p>量化、基本面、新闻与市场情绪的独立证据</p></div></div>
          <div className="analyst-grid">
            <AnalystCard title="量化与技术面" icon={<TrendUp size={17} />} status={text(quant.status)} score={numeric(quant.quant_score)}>
              <Metrics items={[
                ['趋势', trendLabel(text(quant.trend))],
                ['最新收盘', money(quant.latest_close)],
                ['5日涨跌', signedPercent(quant.return_5d)],
                ['20日涨跌', signedPercent(quant.return_20d)],
                ['RSI(14)', decimal(quant.rsi_14)],
                ['波动率', percent(quant.volatility_20d)],
              ]} />
              <CompactFactors items={strings(quant.key_factors).map(factorLabel)} />
            </AnalystCard>

            <AnalystCard title="基本面" icon={<ChartLine size={17} />} status={text(fundamental.status)} score={numeric(fundamental.fundamental_score)}>
              <Metrics items={[
                ['估值水平', levelLabel(text(fundamental.valuation_level))],
                ['盈利能力', levelLabel(text(fundamental.profitability_level))],
                ['成长性', levelLabel(text(fundamental.growth_level))],
                ['市盈率 PE', decimal(fundamental.pe_ttm)],
                ['市净率 PB', decimal(fundamental.pb)],
                ['净资产收益率', percentPoint(fundamental.roe)],
                ['资产负债率', percentPoint(fundamental.debt_ratio)],
              ]} />
              <CompactFactors items={strings(fundamental.key_factors).map(factorLabel)} />
            </AnalystCard>

            <AnalystCard title="新闻与事件" icon={<Newspaper size={17} />} status={text(news.status)} score={numeric(news.news_score)}>
              <Metrics items={[
                ['新闻倾向', sentimentLabel(text(news.sentiment))],
                ['分析置信度', confidenceLabel(text(news.confidence))],
                ['原始新闻', `${numeric(news.raw_count) ?? 0} 条`],
                ['有效事件', `${records(news.events).length} 条`],
              ]} />
              <div className="report-events">{records(news.events).map((event, index) => {
                const url = safeUrl(event.source)
                return <article key={`${text(event.summary)}-${index}`}>
                  <div><strong>{text(event.event_type, '市场事件')}</strong><span>{sentimentLabel(text(event.sentiment))} · {severityLabel(text(event.severity))}</span></div>
                  <p>{text(event.summary)}</p>
                  <small>{text(event.published_at)}</small>
                  {url && <a href={url} target="_blank" rel="noreferrer noopener">查看来源</a>}
                </article>
              })}</div>
            </AnalystCard>

            <AnalystCard title="市场情绪" icon={<UserFocus size={17} />} status={text(sentiment.status)} score={numeric(sentiment.sentiment_score)}>
              <Metrics items={[
                ['情绪得分', decimal(sentiment.sentiment_score)],
                ['关注度', decimal(sentiment.attention_score)],
                ['拥挤风险', levelLabel(text(sentiment.crowding_risk))],
                ['主导情绪', strings(sentiment.dominant_emotions).map(sentimentLabel).join('、') || '未知'],
              ]} />
              <CompactFactors items={strings(sentiment.heat_sources)} />
            </AnalystCard>
          </div>
        </section>

        <PersonalContext context={personal} />
      </>}

      {!hasDecision && <section className="report-empty"><ShieldWarning size={22} /><p>{report.summary || '报告缺少可展示的研究结论。'}</p></section>}

      <details className="raw-report">
        <summary>开发调试：查看原始数据</summary>
        <pre>{JSON.stringify(report.report_payload, null, 2)}</pre>
      </details>
    </section>
  </div>
}

function ReportList({ title, items, tone = '', empty }: { title: string; items: string[]; tone?: string; empty: string }) {
  return <section className={`report-list ${tone}`}><h3>{title}</h3>{items.length
    ? <ul>{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
    : <p>{empty}</p>}</section>
}

function AnalystCard({ title, icon, status, score, children }: { title: string; icon: ReactNode; status: string; score: number | null; children: ReactNode }) {
  return <article className="analyst-card">
    <header><span>{icon}</span><div><h4>{title}</h4><small>{statusLabel(status)}</small></div>{score != null && <strong>{score}</strong>}</header>
    {children}
  </article>
}

function Metrics({ items }: { items: [string, string][] }) {
  return <dl className="report-data-grid">{items.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
}

function CompactFactors({ items }: { items: string[] }) {
  if (!items.length) return null
  return <ul className="compact-factors">{items.slice(0, 5).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
}

function PersonalContext({ context }: { context: Record<string, unknown> }) {
  const target = record(context.target_position)
  const memories = records(context.memories)
  const sources = records(context.knowledge_sources)
  const codes = strings(context.portfolio_codes)
  if (!Object.keys(context).length) return null
  return <section className="report-section personal-report-context">
    <div className="report-section-title"><UserFocus size={18} /><div><h3>与你的投资上下文</h3><p>本次结论参考的持仓、长期记忆和个人资料</p></div></div>
    <dl className="report-data-grid">
      <div><dt>目标持仓</dt><dd>{text(target.stock_code, '未持有')} {text(target.stock_name)}</dd></div>
      <div><dt>持仓数量</dt><dd>{target.quantity != null ? `${decimal(target.quantity)} 股` : '—'}</dd></div>
      <div><dt>平均成本</dt><dd>{money(target.average_cost)}</dd></div>
      <div><dt>组合股票</dt><dd>{codes.length ? codes.join('、') : '暂无'}</dd></div>
      <div><dt>长期记忆</dt><dd>{memories.length} 条</dd></div>
      <div><dt>知识库来源</dt><dd>{sources.length} 条</dd></div>
    </dl>
  </section>
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(record).filter((item) => Object.keys(item).length) : []
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && Boolean(item.trim())) : []
}

function text(value: unknown, fallback = ''): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : fallback
}

function numeric(value: unknown): number | null {
  const parsed = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : NaN
  return Number.isFinite(parsed) ? parsed : null
}

function decimal(value: unknown, digits = 2): string {
  const parsed = numeric(value)
  return parsed == null ? '—' : parsed.toLocaleString('zh-CN', { maximumFractionDigits: digits })
}

function money(value: unknown): string {
  const parsed = numeric(value)
  return parsed == null ? '—' : `¥ ${parsed.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
}

function percent(value: unknown): string {
  const parsed = numeric(value)
  return parsed == null ? '—' : `${(parsed * 100).toFixed(1)}%`
}

function percentPoint(value: unknown): string {
  const parsed = numeric(value)
  return parsed == null ? '—' : `${parsed.toFixed(2)}%`
}

function signedPercent(value: unknown): string {
  const parsed = numeric(value)
  return parsed == null ? '—' : `${parsed >= 0 ? '+' : ''}${(parsed * 100).toFixed(2)}%`
}

function safeUrl(value: unknown): string | null {
  const url = text(value)
  return /^https?:\/\//i.test(url) ? url : null
}

function trendLabel(value: string): string {
  return ({ bullish: '偏多', bearish: '偏空', neutral: '震荡' } as Record<string, string>)[value] || value || '未知'
}

function levelLabel(value: string): string {
  return ({ reasonable: '合理', expensive: '偏贵', cheap: '偏低', neutral: '中性', strong: '较强', weak: '较弱', unknown: '数据不足', low: '低', medium: '中等', high: '高' } as Record<string, string>)[value] || value || '未知'
}

function sentimentLabel(value: string): string {
  return ({ positive: '积极', negative: '消极', neutral: '中性', divided: '分歧' } as Record<string, string>)[value] || value || '未知'
}

function confidenceLabel(value: string): string {
  return ({ high: '高', medium: '中等', low: '低' } as Record<string, string>)[value] || value || '未知'
}

function severityLabel(value: string): string {
  return ({ critical: '极高影响', high: '高影响', medium: '中等影响', low: '低影响' } as Record<string, string>)[value] || value || '影响未知'
}

function statusLabel(value: string): string {
  return ({ ok: '数据可用', unavailable: '数据不可用', error: '分析失败', data_insufficient: '数据不足' } as Record<string, string>)[value] || value || '状态未知'
}

function factorLabel(value: string): string {
  return value
    .replace('MA bullish alignment', '均线呈多头排列')
    .replace('MACD histogram positive', 'MACD 柱线为正')
    .replace(/reasonable PE/i, '市盈率处于合理区间')
    .replace(/(\d+)d return/gi, '$1 日收益率')
    .replace(/14d LSTM expected return/i, 'LSTM 14 日预期收益')
}
