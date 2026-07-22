import { useState } from 'react'

import { api, type MemoryItem } from '../api/client'


const TYPE_LABELS: Record<string, string> = {
  profile: '用户画像',
  preference: '投资偏好',
  constraint: '投资约束',
  watchlist: '关注方向',
}


export function MemoryPanel({
  token,
  memories,
  onChanged,
}: {
  token: string
  memories: MemoryItem[]
  onChanged: () => void
}) {
  const [memoryType, setMemoryType] = useState('preference')
  const [memoryKey, setMemoryKey] = useState('')
  const [memoryValue, setMemoryValue] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function save(event: React.FormEvent) {
    event.preventDefault()
    if (!memoryKey.trim() || !memoryValue.trim()) return
    setSaving(true)
    setError('')
    try {
      await api.saveMemory(token, {
        memory_type: memoryType,
        memory_key: memoryKey.trim(),
        memory_value: parseValue(memoryValue),
      })
      setMemoryKey('')
      setMemoryValue('')
      onChanged()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '保存记忆失败')
    } finally {
      setSaving(false)
    }
  }

  async function remove(id: string) {
    try {
      await api.deleteMemory(token, id)
      onChanged()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '删除记忆失败')
    }
  }

  return <section className="knowledge-workspace">
    <section className="card">
      <div className="section-title"><div><p className="eyebrow">STRUCTURED MEMORY</p><h2>Agent 长期记忆</h2></div><span>可查看、可编辑、可删除</span></div>
      <p className="panel-copy">这里保存风险偏好、投资风格和明确约束。持仓与实时行情不会被当作模糊记忆保存。</p>
      <form className="memory-form" onSubmit={save}>
        <label>类型<select value={memoryType} onChange={(event) => setMemoryType(event.target.value)}>{Object.entries(TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>字段<input value={memoryKey} onChange={(event) => setMemoryKey(event.target.value)} placeholder="例如 investment_style" /></label>
        <label className="wide">内容<input value={memoryValue} onChange={(event) => setMemoryValue(event.target.value)} placeholder="例如 高股息, 长期持有" /></label>
        <button className="primary" disabled={saving}>{saving ? '保存中…' : '保存记忆'}</button>
      </form>
      {error && <p className="form-error">{error}</p>}
    </section>
    <section className="card">
      <div className="section-title"><div><p className="eyebrow">MEMORY RECORDS</p><h2>已保存记忆</h2></div><strong className="count-pill">{memories.length}</strong></div>
      {memories.length ? <div className="memory-list">{memories.map((item) => <article key={item.id} className={item.status !== 'active' ? 'inactive' : ''}>
        <div><span>{TYPE_LABELS[item.memory_type] || item.memory_type}</span><strong>{item.memory_key}</strong></div>
        <p>{formatValue(item.memory_value)}</p>
        <button className="danger-link" onClick={() => void remove(item.id)}>删除</button>
      </article>)}</div> : <div className="empty">还没有长期记忆。你也可以直接对 Agent 说：“记住我偏好长期高股息投资”。</div>}
    </section>
  </section>
}


function parseValue(value: string): unknown {
  const trimmed = value.trim()
  if (trimmed.includes(',')) return trimmed.split(',').map((item) => item.trim()).filter(Boolean)
  if (trimmed.includes('，')) return trimmed.split('，').map((item) => item.trim()).filter(Boolean)
  if (trimmed === 'true') return true
  if (trimmed === 'false') return false
  const numeric = Number(trimmed)
  return Number.isNaN(numeric) ? trimmed : numeric
}


function formatValue(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value)
}
