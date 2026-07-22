import { useCallback, useEffect, useState } from 'react'
import {
  Brain,
  Briefcase,
  ChartLineUp,
  ChatCircleDots,
  ClockCounterClockwise,
  Database,
  Plus,
  SignOut,
  Sparkle,
} from '@phosphor-icons/react'

import {
  api,
  type AuthResult,
  type KnowledgeDocument,
  type MemoryItem,
  type Position,
  type ResearchJob,
  type ResearchReport,
} from './api/client'
import { AuthPanel } from './components/AuthPanel'
import { ChatPanel } from './components/ChatPanel'
import { KnowledgePanel } from './components/KnowledgePanel'
import { MemoryPanel } from './components/MemoryPanel'
import { ReportModal } from './components/ReportModal'
import { ToolWorkspace, type ToolView } from './components/ToolWorkspace'

type WorkspaceView = 'assistant' | 'research' | 'portfolio' | 'jobs' | 'memory' | 'knowledge'

export default function App() {
  const [auth, setAuth] = useState<AuthResult | null>(null)
  const [jobs, setJobs] = useState<ResearchJob[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [memories, setMemories] = useState<MemoryItem[]>([])
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([])
  const [view, setView] = useState<WorkspaceView>('assistant')
  const [error, setError] = useState('')
  const [report, setReport] = useState<ResearchReport | null>(null)
  const [newChatRequest, setNewChatRequest] = useState(0)

  const refresh = useCallback(async () => {
    if (!auth) return
    try {
      const [nextJobs, nextPositions, nextMemories, nextDocuments] = await Promise.all([
        api.jobs(auth.access_token),
        api.positions(auth.access_token),
        api.memories(auth.access_token),
        api.documents(auth.access_token),
      ])
      setJobs(nextJobs)
      setPositions(nextPositions)
      setMemories(nextMemories)
      setDocuments(nextDocuments)
      setError('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法获取工作台数据')
    }
  }, [auth])

  const refreshJobs = useCallback(async () => {
    if (!auth) return
    try {
      setJobs(await api.jobs(auth.access_token))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法刷新研究任务')
    }
  }, [auth])

  useEffect(() => { void refresh() }, [refresh])
  useEffect(() => {
    if (!auth || !jobs.some((job) => job.status === 'pending' || job.status === 'running')) return
    const timer = window.setInterval(() => void refreshJobs(), 2000)
    return () => window.clearInterval(timer)
  }, [auth, jobs, refreshJobs])

  if (!auth) return <AuthPanel onAuthenticated={setAuth} />
  const token = auth.access_token
  const readyDocuments = documents.filter((item) => item.status === 'ready').length
  async function openReport(job: ResearchJob) {
    try {
      setReport(await api.report(token, job.id))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法读取报告')
    }
  }

  function startNewChat() {
    setView('assistant')
    setNewChatRequest((value) => value + 1)
  }

  return <main className={`terminal-layout ${view === 'assistant' ? '' : 'detail-view'}`}>
    <aside className="left-rail">
      <div className="console-logo">
        <span className="logo-mark"><Sparkle size={21} weight="fill" /></span>
        <div><strong>克劳德老师</strong><small>A-share Intelligence</small></div>
      </div>

      <button className="new-chat" onClick={startNewChat}>
        <Plus size={18} weight="bold" /><span>新对话</span>
      </button>

      <nav aria-label="工作区导航">
        <button className={view === 'assistant' ? 'active' : ''} onClick={() => setView('assistant')}>
          <ChatCircleDots size={19} /><span>投资助手</span>
        </button>
        <button className={view === 'research' ? 'active' : ''} onClick={() => setView('research')}>
          <ChartLineUp size={19} /><span>深度研究</span>
        </button>
        <button className={view === 'portfolio' ? 'active' : ''} onClick={() => setView('portfolio')}>
          <Briefcase size={19} /><span>我的持仓</span>
        </button>
        <button className={view === 'jobs' ? 'active' : ''} onClick={() => setView('jobs')}>
          <ClockCounterClockwise size={19} /><span>研究任务</span>
        </button>
        <button className={view === 'memory' ? 'active' : ''} onClick={() => setView('memory')}>
          <Brain size={19} /><span>长期记忆</span>
        </button>
        <button className={view === 'knowledge' ? 'active' : ''} onClick={() => setView('knowledge')}>
          <Database size={19} /><span>知识库</span>
        </button>
      </nav>

      <div className="rail-context">
        <p><span className="online-dot" /> Agent 在线</p>
      </div>

      <div className="rail-user">
        <span className="user-avatar">{auth.user.username.slice(0, 1).toUpperCase()}</span>
        <div><strong>{auth.user.username}</strong><small>{auth.user.risk_profile || '个人投资者'}</small></div>
        <button title="退出登录" aria-label="退出登录" onClick={() => setAuth(null)}><SignOut size={18} /></button>
      </div>
    </aside>

    <section className="workspace">
      <header className="workspace-header">
        <div>
          <p className="workspace-kicker">{viewKicker(view)}</p>
          <h1>{viewTitle(view)}</h1>
        </div>
        <div className="header-actions">
          <span className="model-status"><span className="online-dot" /> Agent 已连接</span>
        </div>
      </header>

      {error && <p className="banner-error">{error}</p>}

      <div className={`workspace-body ${view === 'assistant' ? 'chat-workspace' : 'detail-workspace'}`}>
        {view === 'assistant' && <ChatPanel
          token={token}
          newChatRequest={newChatRequest}
          jobs={jobs}
          onAction={() => void refresh()}
          onOpenResearch={() => setView('research')}
          onOpenReport={(job) => void openReport(job)}
        />}
        {isToolView(view) && <ToolWorkspace
          view={view}
          token={token}
          jobs={jobs}
          positions={positions}
          memoriesCount={memories.length}
          documentsCount={readyDocuments}
          onChanged={() => void refresh()}
          onOpenReport={(job) => void openReport(job)}
        />}
        {view === 'memory' && <MemoryPanel token={token} memories={memories} onChanged={() => void refresh()} />}
        {view === 'knowledge' && <KnowledgePanel token={token} documents={documents} onChanged={() => void refresh()} />}
      </div>
    </section>

    {report && <ReportModal report={report} onClose={() => setReport(null)} />}
  </main>
}

function viewTitle(view: WorkspaceView) {
  return ({
    assistant: 'AI 投资助手',
    research: '深度研究',
    portfolio: '我的持仓',
    jobs: '研究任务',
    memory: '结构化长期记忆',
    knowledge: 'RAG 向量知识库',
  } as const)[view]
}

function viewKicker(view: WorkspaceView) {
  return ({
    assistant: 'Agent Desk',
    research: 'Research',
    portfolio: 'Portfolio',
    jobs: 'Tasks',
    memory: 'Memory',
    knowledge: 'Knowledge',
  } as const)[view]
}

function isToolView(view: WorkspaceView): view is ToolView {
  return view === 'research' || view === 'portfolio' || view === 'jobs'
}
