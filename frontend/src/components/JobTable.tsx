import type { ResearchJob } from '../api/client'

const labels: Record<string, string> = { pending: '等待中', running: '分析中', completed: '已完成', failed: '失败' }

export function JobTable({ jobs, onOpenReport }: { jobs: ResearchJob[]; onOpenReport: (job: ResearchJob) => void }) {
  if (!jobs.length) return <div className="empty">还没有研究任务。提交一只股票开始第一份报告。</div>
  return <div className="job-list">
    {jobs.map((job) => <article className="job-row" key={job.id}>
      <div><strong>{job.stock_code}</strong><span>{job.depth} · {job.risk_profile}</span></div>
      <div className={`status ${job.status}`}>{labels[job.status] || job.status}</div>
      <div className="progress"><i style={{ width: `${job.progress}%` }} /><span>{job.progress}%</span></div>
      <small>{new Date(job.created_at).toLocaleString('zh-CN')}</small>
      {job.status === 'completed' && <button className="text-button report-button" onClick={() => onOpenReport(job)}>查看报告</button>}
      {job.error && <p className="form-error">{job.error}</p>}
    </article>)}
  </div>
}
