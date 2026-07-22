import { useEffect, useState } from 'react'

import { api, type KnowledgeDocument, type KnowledgeSourceType, type RagAnswer } from '../api/client'

const SOURCE_TYPES: Array<{ value: KnowledgeSourceType; label: string }> = [
  { value: 'financial_report', label: '财务报告' },
  { value: 'announcement', label: '公司公告' },
  { value: 'news', label: '新闻资料' },
  { value: 'analysis', label: '分析文章' },
  { value: 'personal_note', label: '个人笔记' },
  { value: 'other', label: '其他资料' },
]


export function KnowledgePanel({
  token,
  documents,
  onChanged,
}: {
  token: string
  documents: KnowledgeDocument[]
  onChanged: () => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [stockCode, setStockCode] = useState('')
  const [sourceType, setSourceType] = useState<KnowledgeSourceType>('other')
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<RagAnswer | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!documents.some((item) => item.status === 'pending' || item.status === 'processing')) return
    const timer = window.setInterval(onChanged, 2000)
    return () => window.clearInterval(timer)
  }, [documents, onChanged])

  async function upload(event: React.FormEvent) {
    event.preventDefault()
    if (!file) return
    setBusy(true)
    setError('')
    try {
      await api.uploadDocument(token, file, title, stockCode, sourceType)
      setFile(null)
      setTitle('')
      setStockCode('')
      setSourceType('other')
      onChanged()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '上传失败')
    } finally {
      setBusy(false)
    }
  }

  async function query(event: React.FormEvent) {
    event.preventDefault()
    if (!question.trim()) return
    setBusy(true)
    setError('')
    try {
      setAnswer(await api.queryKnowledge(token, { question: question.trim(), top_k: 5 }))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '知识库查询失败')
    } finally {
      setBusy(false)
    }
  }

  async function remove(id: string) {
    try {
      await api.deleteDocument(token, id)
      onChanged()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '删除文档失败')
    }
  }

  return <section className="knowledge-workspace">
    <section className="card">
      <div className="section-title"><div><p className="eyebrow">VECTOR KNOWLEDGE</p><h2>上传并建立向量索引</h2></div><span>PDF / Markdown / TXT · 最大 20MB</span></div>
      <p className="panel-copy">文档会被递归切块，使用中文 BGE Embedding 写入 Qdrant。SQLite 只保存文档和 chunk 元数据。</p>
      <form className="upload-form" onSubmit={upload}>
        <label className="file-drop">选择文档<input type="file" accept=".pdf,.md,.txt" onChange={(event) => setFile(event.target.files?.[0] || null)} /><span>{file?.name || '点击选择 PDF、Markdown 或 TXT'}</span></label>
        <label>显示标题<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="可选" /></label>
        <label>资料类型<select value={sourceType} onChange={(event) => setSourceType(event.target.value as KnowledgeSourceType)}>{SOURCE_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
        <label>关联股票<input value={stockCode} onChange={(event) => setStockCode(event.target.value)} placeholder="可选，6 位代码" maxLength={6} /></label>
        <button className="primary" disabled={busy || !file}>{busy ? '处理中…' : '上传并索引'}</button>
      </form>
      {error && <p className="form-error">{error}</p>}
    </section>
    <section className="card">
      <div className="section-title"><div><p className="eyebrow">DOCUMENT LIBRARY</p><h2>知识库文档</h2></div><strong className="count-pill">{documents.length}</strong></div>
      {documents.length ? <div className="document-list">{documents.map((item) => <article key={item.id}>
        <div><strong>{item.title}</strong><span>{sourceTypeLabel(item.source_type)} · {item.filename}{item.stock_code ? ` · ${item.stock_code}` : ''}</span></div>
        <div><b className={`status ${item.status}`}>{statusLabel(item.status)}</b><small>{item.chunk_count} chunks · {formatBytes(item.file_size)}</small></div>
        {item.error && <p>{item.error}</p>}
        <button className="danger-link" onClick={() => void remove(item.id)}>删除</button>
      </article>)}</div> : <div className="empty">尚未上传文档。</div>}
    </section>
    <section className="card">
      <div className="section-title"><div><p className="eyebrow">RAG QUERY</p><h2>检索增强问答</h2></div><span>回答附带来源片段</span></div>
      <form className="rag-form" onSubmit={query}><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="例如：根据我上传的年报，这家公司最大的经营风险是什么？" /><button className="primary" disabled={busy}>{busy ? '检索中…' : '检索回答'}</button></form>
      {answer && <div className="rag-answer"><p>{answer.answer}</p><div className="source-list">{answer.sources.map((source, index) => <details key={`${source.document_id}-${source.chunk_index}`}><summary>[{index + 1}] {source.title}{source.page_number ? ` · 第 ${source.page_number} 页` : ''} · 相似度 {source.score.toFixed(3)}</summary><p>{source.content}</p></details>)}</div></div>}
    </section>
  </section>
}


function statusLabel(status: string) {
  return ({ pending: '等待处理', processing: '切块索引中', ready: '可检索', failed: '处理失败' } as Record<string, string>)[status] || status
}

function sourceTypeLabel(sourceType: KnowledgeSourceType) {
  return SOURCE_TYPES.find((item) => item.value === sourceType)?.label || '其他资料'
}


function formatBytes(value: number) {
  return value < 1024 * 1024 ? `${(value / 1024).toFixed(1)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`
}
