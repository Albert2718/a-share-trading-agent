import { FormEvent, useState } from 'react'

import { api } from '../api/client'

export function ResearchPanel({ token, onCreated }: { token: string; onCreated: () => void }) {
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    const stockCode = String(data.get('stock_code') || '').trim()
    setError('')
    if (!/^\d{6}$/.test(stockCode)) {
      setError('请输入 6 位 A 股代码。')
      return
    }
    setLoading(true)
    try {
      await api.submitResearch(token, {
        stock_code: stockCode,
        depth: 'standard',
        risk_profile: String(data.get('risk_profile') || 'balanced'),
      })
      form.reset()
      onCreated()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '提交失败')
    } finally {
      setLoading(false)
    }
  }

  return <form className="research-form" onSubmit={submit}>
    <div><label>股票代码<input name="stock_code" inputMode="numeric" placeholder="600519" /></label></div>
    <div><label>风险偏好<select name="risk_profile"><option value="conservative">保守</option><option value="balanced">平衡</option><option value="aggressive">进取</option></select></label></div>
    <button className="primary" disabled={loading}>{loading ? '已进入队列…' : '发起深度研究'}</button>
    {error && <p className="form-error">{error}</p>}
  </form>
}
