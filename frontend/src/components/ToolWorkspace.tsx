import {
  Briefcase,
  ChartLineUp,
  ClockCounterClockwise,
  Database,
} from '@phosphor-icons/react'

import type { Position, ResearchJob } from '../api/client'
import { JobTable } from './JobTable'
import { PositionForm } from './PositionForm'
import { ResearchPanel } from './ResearchPanel'

export type ToolView = 'research' | 'portfolio' | 'jobs'

export function ToolWorkspace({
  view,
  token,
  jobs,
  positions,
  memoriesCount,
  documentsCount,
  onChanged,
  onOpenReport,
}: {
  view: ToolView
  token: string
  jobs: ResearchJob[]
  positions: Position[]
  memoriesCount: number
  documentsCount: number
  onChanged: () => void
  onOpenReport: (job: ResearchJob) => void
}) {
  return <div className="tool-workspace">
    {view === 'research' && <section className="utility-section card">
      <div className="utility-title"><span><ChartLineUp size={20} /></span><div><h3>发起深度研究</h3><p>生成基本面、技术面与风险结论</p></div></div>
      <ResearchPanel token={token} onCreated={onChanged} />
      <div className="context-note"><Database size={17} /><p>Agent 对话可读取 <strong>{memoriesCount}</strong> 条记忆，并可检索 <strong>{documentsCount}</strong> 份知识库文档。</p></div>
      {jobs[0] && <div className="latest-job">
        <small>最近任务</small>
        <div><strong>{jobs[0].stock_code}</strong><span className={`status ${jobs[0].status}`}>{jobLabel(jobs[0].status)}</span></div>
        <div className="progress"><i style={{ width: `${jobs[0].progress}%` }} /></div>
        {jobs[0].status === 'completed' && <button className="secondary" onClick={() => onOpenReport(jobs[0])}>查看最新报告</button>}
      </div>}
    </section>}

    {view === 'portfolio' && <section className="utility-section card">
      <div className="utility-title"><span><Briefcase size={20} /></span><div><h3>我的持仓</h3><p>实时行情与未实现盈亏</p></div><button className="text-button portfolio-refresh" onClick={onChanged}>刷新行情</button></div>
      {positions.length ? <div className="utility-positions">{positions.map((item) => <article key={item.id}>
        <div><strong>{item.stock_code}</strong><span>{item.stock_name || '未命名标的'}</span></div>
        <p>{item.quantity.toLocaleString()} 股 · {item.market_price ? `现价 ¥${formatMoney(item.market_price)}` : '行情不可用'}</p>
        <small className={Number(item.unrealized_pnl) >= 0 ? 'profit' : 'loss'}>
          {item.unrealized_pnl !== null ? `盈亏 ${formatSigned(item.unrealized_pnl)} (${formatSigned(item.pnl_pct)}%)` : `成本 ¥${formatMoney(item.average_cost)}`}
        </small>
      </article>)}</div> : <div className="empty-state"><Briefcase size={24} /><p>还没有持仓，可以手动录入，也可以直接告诉 Agent。</p></div>}
      <details className="utility-form-drawer" open={!positions.length}>
        <summary>手动录入持仓</summary>
        <PositionForm token={token} onSaved={onChanged} />
      </details>
    </section>}

    {view === 'jobs' && <section className="utility-section card">
      <div className="utility-title"><span><ClockCounterClockwise size={20} /></span><div><h3>研究任务</h3><p>查看执行进度与历史报告</p></div></div>
      <JobTable jobs={jobs} onOpenReport={onOpenReport} />
    </section>}
  </div>
}

function jobLabel(status: string) {
  return ({ pending: '等待中', running: '分析中', completed: '已完成', failed: '失败' } as Record<string, string>)[status] || status
}

function formatMoney(value: string | null) {
  return Number(value || 0).toFixed(2)
}

function formatSigned(value: string | null) {
  const number = Number(value || 0)
  return `${number >= 0 ? '+' : ''}${number.toFixed(2)}`
}
