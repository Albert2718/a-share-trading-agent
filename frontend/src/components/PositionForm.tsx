import { useState } from 'react'

import { api } from '../api/client'

export function PositionForm({ token, onSaved }: { token: string; onSaved: () => void }) {
  const [stockCode, setStockCode] = useState('')
  const [stockName, setStockName] = useState('')
  const [quantity, setQuantity] = useState('')
  const [averageCost, setAverageCost] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      await api.savePosition(token, {
        stock_code: stockCode,
        stock_name: stockName,
        quantity: Number(quantity),
        average_cost: averageCost,
      })
      setStockCode('')
      setStockName('')
      setQuantity('')
      setAverageCost('')
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '持仓保存失败')
    } finally {
      setSaving(false)
    }
  }

  return <form className="position-form" onSubmit={submit}>
    <label>代码<input value={stockCode} onChange={(event) => setStockCode(event.target.value)} placeholder="600519" pattern="\\d{6}" required /></label>
    <label>名称<input value={stockName} onChange={(event) => setStockName(event.target.value)} placeholder="贵州茅台" /></label>
    <label>持仓股数<input value={quantity} onChange={(event) => setQuantity(event.target.value)} type="number" min="0" step="1" required /></label>
    <label>平均成本<input value={averageCost} onChange={(event) => setAverageCost(event.target.value)} type="number" min="0" step="0.01" required /></label>
    <button className="secondary" disabled={saving}>{saving ? '保存中…' : '保存持仓'}</button>
    {error && <p className="form-error">{error}</p>}
  </form>
}
