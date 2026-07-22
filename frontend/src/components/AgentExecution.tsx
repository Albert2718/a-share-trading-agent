import {
  Brain,
  ChartLine,
  CheckCircle,
  Clock,
  Database,
  FileMagnifyingGlass,
  Hourglass,
  SpinnerGap,
  Wallet,
  WarningCircle,
} from '@phosphor-icons/react'
import type { ReactNode } from 'react'

import type { AgentActivity, ChatMessage, ResearchJob, ToolExecution } from '../api/client'


const TOOL_LABELS: Record<string, string> = {
  market_quote: '查询实时行情',
  market_history: '读取历史走势',
  portfolio_list: '读取持仓',
  portfolio_upsert: '准备写入持仓',
  research_submit: '创建深度研究',
  memory_list: '读取长期记忆',
  memory_upsert: '准备保存记忆',
  knowledge_search: '检索知识库',
}

const PHASE_LABELS: Record<string, string> = {
  planning: '理解需求并规划工具',
  synthesizing: '整理工具结果并生成回答',
}

export function AgentActivityTimeline({ activities }: { activities: AgentActivity[] }) {
  if (!activities.length) return null
  return <section className="agent-activity" aria-label="Agent 执行过程">
    <div className="activity-heading"><SpinnerGap size={14} /><span>Agent 执行过程</span></div>
    <ol>{activities.map((activity) => {
      const running = activity.status === 'running'
      const failed = activity.status === 'failed'
      const label = activity.tool_name
        ? TOOL_LABELS[activity.tool_name] || activity.tool_name
        : PHASE_LABELS[activity.phase] || activity.phase
      return <li key={activity.id} className={`${running ? 'running' : ''} ${failed ? 'failed' : ''}`}>
        <span className="activity-icon">{running
          ? <SpinnerGap size={13} className="spin" />
          : failed ? <WarningCircle size={13} /> : <CheckCircle size={13} weight="fill" />}</span>
        <span>{label}</span>
        {activity.duration_ms != null && <small>{formatDuration(activity.duration_ms)}</small>}
        {activity.status === 'queued' && <small>已进入后台队列</small>}
        {activity.status === 'awaiting_confirmation' && <small>等待确认</small>}
      </li>
    })}</ol>
  </section>
}

export function PersistedToolResults({
  message,
  jobs = [],
  onOpenReport = () => undefined,
}: {
  message: ChatMessage
  jobs?: ResearchJob[]
  onOpenReport?: (job: ResearchJob) => void
}) {
  const executions = toolExecutions(message)
  if (!executions.length || message.tool_payload?.status === 'pending_confirmation') return null
  return <div className="tool-results">
    <AgentActivityTimeline activities={executions.map((item, index) => {
      const job = researchJob(item, jobs)
      return {
        id: `${message.id}-${index}`,
        phase: item.name === 'research_submit' ? 'background_task_created' : 'tool_completed',
        status: job?.status === 'pending' ? 'queued' : job?.status || item.status || (item.result.ok === false ? 'failed' : item.name === 'research_submit' ? 'queued' : 'completed'),
        tool_name: item.name,
        duration_ms: item.duration_ms,
      }
    })} />
    {executions.map((item, index) => <ToolResultCard
      key={`${item.name}-${index}`}
      execution={item}
      job={researchJob(item, jobs)}
      onOpenReport={onOpenReport}
    />)}
  </div>
}

function ToolResultCard({ execution, job, onOpenReport }: { execution: ToolExecution; job?: ResearchJob; onOpenReport: (job: ResearchJob) => void }) {
  const result = execution.result
  if (result.ok === false) return <ResultShell icon={<WarningCircle />} title={TOOL_LABELS[execution.name] || execution.name} tone="warning">
    <p>{text(result.error, '工具执行失败')}</p>
  </ResultShell>

  if (execution.name === 'market_quote') {
    const change = number(result.change_pct)
    return <ResultShell icon={<ChartLine />} title={`${text(result.name)} ${text(result.code)}`.trim() || '行情快照'}>
      <div className="quote-summary">
        <strong>¥ {formatNumber(result.latest_price)}</strong>
        {change != null && <span className={change >= 0 ? 'up' : 'down'}>{change >= 0 ? '+' : ''}{change.toFixed(2)}%</span>}
      </div>
      <dl className="metric-grid">
        <Metric label="开盘" value={formatNumber(result.open)} />
        <Metric label="最高" value={formatNumber(result.high)} />
        <Metric label="最低" value={formatNumber(result.low)} />
        <Metric label="数据时间" value={text(result.quote_time, '—')} />
      </dl>
      {!result.is_realtime && <p className="card-note">实时行情不可用，当前展示最近交易日数据。</p>}
    </ResultShell>
  }

  if (execution.name === 'market_history') {
    const records = recordsOf(result.records)
    const latest = records.at(-1)
    return <ResultShell icon={<ChartLine />} title={`${text(result.code)} 历史走势`}>
      <dl className="metric-grid">
        <Metric label="交易日数" value={String(records.length)} />
        <Metric label="最新收盘" value={formatNumber(latest?.close)} />
        <Metric label="区间最高" value={formatNumber(extreme(records, 'high', Math.max))} />
        <Metric label="区间最低" value={formatNumber(extreme(records, 'low', Math.min))} />
      </dl>
    </ResultShell>
  }

  if (execution.name === 'portfolio_list') {
    const positions = recordsOf(result.positions)
    return <ResultShell icon={<Wallet />} title={`持仓概览 · ${positions.length} 项`}>
      {positions.length ? <div className="compact-list">{positions.slice(0, 6).map((position, index) => <div key={`${text(position.stock_code)}-${index}`}>
        <span><strong>{text(position.stock_code)}</strong>{text(position.stock_name)}</span>
        <span>{formatNumber(position.quantity)} 股</span>
        <small className={number(position.unrealized_pnl) != null && number(position.unrealized_pnl)! >= 0 ? 'up' : 'down'}>
          盈亏 {formatSigned(position.unrealized_pnl)}
        </small>
      </div>)}</div> : <p className="card-note">当前没有已记录持仓。</p>}
    </ResultShell>
  }

  if (execution.name === 'knowledge_search') {
    const sources = recordsOf(result.sources)
    return <ResultShell icon={<FileMagnifyingGlass />} title={`知识库检索 · ${sources.length} 个来源`}>
      <div className="source-cards">{sources.slice(0, 5).map((source, index) => <details key={`${text(source.document_id)}-${index}`}>
        <summary><span>[{index + 1}] {text(source.title, text(source.filename, '未命名资料'))}</span><small>{formatScore(source.score)}</small></summary>
        <p>{text(source.content, '无可展示片段')}</p>
      </details>)}</div>
    </ResultShell>
  }

  if (execution.name === 'research_submit') return <ResultShell icon={<Hourglass />} title={jobStatusLabel(job?.status)}>
    <dl className="metric-grid">
      <Metric label="股票代码" value={text(result.stock_code)} />
      <Metric label="任务状态" value={jobStatusText(job?.status)} />
      <Metric label="进度" value={job ? `${job.progress}%` : '等待同步'} />
      <Metric label="任务编号" value={shortId(result.job_id)} />
    </dl>
    {job?.status === 'completed' && <button className="report-card-button" onClick={() => onOpenReport(job)}>打开研究报告</button>}
    {job?.error && <p className="card-note">{job.error}</p>}
  </ResultShell>

  if (execution.name === 'memory_list') {
    const memories = recordsOf(result.memories)
    return <ResultShell icon={<Brain />} title={`长期记忆 · ${memories.length} 条`}>
      {memories.length ? <div className="memory-chips">{memories.slice(0, 8).map((memory, index) => <span key={`${text(memory.key)}-${index}`}>{text(memory.key, text(memory.type))}</span>)}</div> : <p className="card-note">尚未保存长期记忆。</p>}
    </ResultShell>
  }

  return <ResultShell icon={<Database />} title={TOOL_LABELS[execution.name] || execution.name}>
    <p className="card-note">工具已完成执行。</p>
  </ResultShell>
}

function ResultShell({ icon, title, tone = '', children }: { icon: ReactNode; title: string; tone?: string; children: ReactNode }) {
  return <section className={`tool-result-card ${tone}`}>
    <header><span>{icon}</span><strong>{title}</strong></header>
    {children}
  </section>
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>
}

function toolExecutions(message: ChatMessage): ToolExecution[] {
  const payload = message.tool_payload
  if (!payload || !message.tool_name) return []
  const toolName = message.tool_name
  if (Array.isArray(payload.tool_results)) {
    return payload.tool_results.filter(isRecord).map((item) => ({
      name: text(item.name, toolName),
      arguments: isRecord(item.arguments) ? item.arguments : undefined,
      result: isRecord(item.result) ? item.result : {},
      status: text(item.status) || undefined,
      duration_ms: number(item.duration_ms) ?? undefined,
    }))
  }
  const legacyResult = isRecord(payload.result) ? payload.result : payload
  return [{ name: toolName.replace('.', '_'), result: legacyResult }]
}

function researchJob(execution: ToolExecution, jobs: ResearchJob[]): ResearchJob | undefined {
  if (execution.name !== 'research_submit') return undefined
  const jobId = text(execution.result.job_id)
  return jobs.find((job) => job.id === jobId)
}

function jobStatusText(status?: string): string {
  return ({ pending: '等待执行', running: '正在分析', completed: '已完成', failed: '执行失败' } as Record<string, string>)[status || ''] || '已进入队列'
}

function jobStatusLabel(status?: string): string {
  return status === 'completed' ? '深度研究报告已完成' : status === 'failed' ? '深度研究任务失败' : status === 'running' ? '深度研究执行中' : '深度研究已进入后台'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function recordsOf(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter(isRecord) : []
}

function text(value: unknown, fallback = ''): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : fallback
}

function number(value: unknown): number | null {
  const parsed = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : NaN
  return Number.isFinite(parsed) ? parsed : null
}

function formatNumber(value: unknown): string {
  const parsed = number(value)
  return parsed == null ? '—' : parsed.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function formatSigned(value: unknown): string {
  const parsed = number(value)
  return parsed == null ? '—' : `${parsed >= 0 ? '+' : ''}${parsed.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
}

function extreme(records: Record<string, unknown>[], key: string, reducer: (...values: number[]) => number): number | null {
  const values = records.map((item) => number(item[key])).filter((item): item is number => item != null)
  return values.length ? reducer(...values) : null
}

function formatScore(value: unknown): string {
  const parsed = number(value)
  return parsed == null ? '' : `${Math.round(parsed * 100)}%`
}

function shortId(value: unknown): string {
  const id = text(value, '—')
  return id.length > 12 ? `${id.slice(0, 8)}…` : id
}

function formatDuration(value: number): string {
  return value < 1000 ? `${value}ms` : `${(value / 1000).toFixed(1)}s`
}
