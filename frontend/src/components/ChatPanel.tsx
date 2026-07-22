import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import {
  ArrowUp,
  Brain,
  ChartLineUp,
  Database,
  Robot,
  Sparkle,
  Wallet,
} from '@phosphor-icons/react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { api, type AgentActivity, type ChatMessage, type Conversation, type ResearchJob } from '../api/client'
import { AgentActivityTimeline, PersistedToolResults } from './AgentExecution'

const STARTERS = [
  { icon: ChartLineUp, label: '分析股票', prompt: '分析 600519，结合近期走势给出保守建议' },
  { icon: Wallet, label: '查看持仓', prompt: '我目前有哪些持仓？请总结风险暴露' },
  { icon: Brain, label: '记录偏好', prompt: '记住我偏好长期、低波动和高股息投资' },
  { icon: Database, label: '查询资料', prompt: '根据我上传的资料，总结最重要的投资风险' },
]
const COMPOSER_MAX_HEIGHT = 128

export function ChatPanel({
  token,
  newChatRequest,
  onAction,
  onOpenResearch,
  jobs = [],
  onOpenReport = () => undefined,
}: {
  token: string
  newChatRequest: number
  onAction: () => void
  onOpenResearch: () => void
  jobs?: ResearchJob[]
  onOpenReport?: (job: ResearchJob) => void
}) {
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [content, setContent] = useState('')
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)
  const [activities, setActivities] = useState<AgentActivity[]>([])
  const [streamedContent, setStreamedContent] = useState('')
  const logRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const loadPromiseRef = useRef<{ key: string; promise: Promise<Conversation> } | null>(null)

  useEffect(() => {
    let active = true
    const key = `${token}:${newChatRequest}`
    if (loadPromiseRef.current?.key !== key) {
      loadPromiseRef.current = {
        key,
        promise: (async () => {
          const current = newChatRequest > 0
            ? await api.createConversation(token)
            : (await api.conversations(token))[0] || await api.createConversation(token)
          return api.conversation(token, current.id)
        })(),
      }
    }
    void loadPromiseRef.current.promise
      .then((next) => { if (active) setConversation(next) })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : '无法加载对话') })
    return () => { active = false }
  }, [token, newChatRequest])

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
  }, [conversation?.messages.length, sending, activities.length, streamedContent])

  useLayoutEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    const nextHeight = Math.min(Math.max(textarea.scrollHeight, 24), COMPOSER_MAX_HEIGHT)
    textarea.style.height = `${nextHeight}px`
    textarea.style.overflowY = textarea.scrollHeight > COMPOSER_MAX_HEIGHT ? 'auto' : 'hidden'
  }, [content])

  async function send(event: React.FormEvent) {
    event.preventDefault()
    if (!conversation || !content.trim()) return
    const prompt = content.trim()
    const temporaryUserId = `user-${Date.now()}`
    setContent('')
    setSending(true)
    setError('')
    setActivities([])
    setStreamedContent('')
    setConversation((current) => current ? {
      ...current,
      messages: [
        ...current.messages,
        temporaryMessage(temporaryUserId, 'user', prompt),
      ],
    } : current)
    try {
      await api.streamMessage(token, conversation.id, prompt, (streamEvent) => {
        if (streamEvent.event === 'token') {
          setStreamedContent((current) => current + streamEvent.data.content)
        }
        if (streamEvent.event === 'message') {
          setConversation((current) => current ? {
            ...current,
            messages: [...current.messages, streamEvent.data],
          } : current)
        }
        if (!['token', 'message'].includes(streamEvent.event)) {
          const activity = streamEvent.data as AgentActivity
          setActivities((current) => {
            const existing = current.findIndex((item) => item.id === activity.id)
            if (existing < 0) return [...current, activity]
            return current.map((item, index) => index === existing ? activity : item)
          })
        }
      })
      setConversation(await api.conversation(token, conversation.id))
      onAction()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '发送失败')
      setContent(prompt)
    } finally {
      setSending(false)
      setActivities([])
      setStreamedContent('')
    }
  }

  async function confirm(message: ChatMessage) {
    if (!conversation) return
    setSending(true)
    try {
      await api.confirmTool(token, conversation.id, message.id)
      setConversation(await api.conversation(token, conversation.id))
      onAction()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '确认失败')
    } finally { setSending(false) }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  const hasMessages = Boolean(conversation?.messages.length)

  return <section className="chat-stage">
    <div className="chat-log" ref={logRef}>
      {!hasMessages && <div className="chat-welcome">
        <span className="agent-orb"><Sparkle size={28} weight="fill" /></span>
        <p>你的个人 A 股研究伙伴</p>
        <h2>今天想研究什么？</h2>
        <p className="welcome-copy">直接描述目标，我会调用行情、研究、持仓、记忆和知识库工具完成任务。</p>
        <div className="starter-grid">{STARTERS.map(({ icon: Icon, label, prompt }) => <button key={label} onClick={() => setContent(prompt)}>
          <Icon size={19} /><span>{label}</span><small>{prompt}</small>
        </button>)}</div>
      </div>}

      {conversation?.messages.map((message) => <article key={message.id} className={`chat-message ${message.role}`}>
        {message.role !== 'user' && <span className="message-avatar"><Robot size={18} weight="duotone" /></span>}
        <div className="message-body">
          {message.role === 'assistant'
            ? <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{
              a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer noopener" />,
            }}>{message.content || (sending ? '正在思考…' : '')}</ReactMarkdown></div>
            : <p>{message.content}</p>}
          {message.tool_payload?.status === 'pending_confirmation' && <button className="confirmation-button" disabled={sending} onClick={() => void confirm(message)}>
            {message.tool_name === 'memory.upsert' ? '确认保存记忆' : '确认写入持仓'}
          </button>}
          <PersistedToolResults message={message} jobs={jobs} onOpenReport={onOpenReport} />
        </div>
      </article>)}
      {sending && <article className="chat-message assistant pending">
        <span className="message-avatar"><Robot size={18} /></span>
        <div className="message-body live-agent-message">
          <AgentActivityTimeline activities={activities} />
          {streamedContent
            ? <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{streamedContent}</ReactMarkdown></div>
            : !activities.length && <div className="thinking"><i /><i /><i /></div>}
        </div>
      </article>}
    </div>

    <div className="composer-wrap">
      {hasMessages && <div className="composer-actions">
        <button type="button" onClick={() => setContent('分析 600519，偏保守')}>分析股票</button>
        <button type="button" onClick={() => setContent('我有哪些持仓？')}>查看持仓</button>
        <button type="button" onClick={onOpenResearch}>深度研究</button>
      </div>}
      <form className="chat-input" onSubmit={send}>
        <textarea
          ref={textareaRef}
          value={content}
          rows={1}
          onKeyDown={handleKeyDown}
          onChange={(event) => setContent(event.target.value)}
          placeholder="输入你的投研需求，Shift + Enter 换行"
          aria-label="输入投研需求"
        />
        <button className="send-button" aria-label="发送消息" disabled={sending || !content.trim()}><ArrowUp size={20} weight="bold" /></button>
      </form>
      <p className="composer-note">AI 结论仅供研究参考 · 涉及持仓和记忆的写入会先征求你的确认</p>
      {error && <p className="form-error">{error}</p>}
    </div>
  </section>
}

function temporaryMessage(id: string, role: string, content: string): ChatMessage {
  return { id, role, content, tool_name: null, tool_payload: null, created_at: new Date().toISOString() }
}
