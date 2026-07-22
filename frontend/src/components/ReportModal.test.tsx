import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ReportModal } from './ReportModal'


const report = {
  id: 'report-1',
  job_id: 'job-1',
  action: 'watch',
  confidence: 0.65,
  rank_score: 58,
  summary: 'legacy english summary',
  created_at: '2026-07-22T08:00:00Z',
  report_payload: {
    top_decision: {
      code: '600519', name: '贵州茅台', action: 'watch', confidence: 0.65, rank_score: 58,
      position_bias: '5%', reason: '技术面偏强，但短期接近超买。',
      top_reasons: ['均线呈多头排列'], risk_flags: ['RSI 接近超买区域'],
      invalidation_conditions: ['若价格跌破趋势支撑位，需要重新评估'],
      quant: { status: 'ok', quant_score: 92, trend: 'bullish', latest_close: 1308, return_5d: 0.07, rsi_14: 72.6 },
      fundamental: { status: 'ok', fundamental_score: 64, valuation_level: 'reasonable', pe_ttm: 19.77 },
      news: { status: 'ok', news_score: 35, sentiment: 'positive', confidence: 'medium', events: [] },
      sentiment: { status: 'ok', sentiment_score: -24, attention_score: 45, crowding_risk: 'low' },
    },
    personal_context: { portfolio_codes: ['600519'], memories: [], knowledge_sources: [] },
  },
}

describe('ReportModal', () => {
  it('renders a readable Chinese research report instead of leading with JSON', () => {
    render(<ReportModal report={report} onClose={vi.fn()} />)

    expect(screen.getByText('谨慎观察')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '600519 贵州茅台' })).toBeInTheDocument()
    expect(screen.getByText('技术面偏强，但短期接近超买。')).toBeInTheDocument()
    expect(screen.getByText('核心依据')).toBeInTheDocument()
    expect(screen.getByText('量化与技术面')).toBeInTheDocument()
    expect(screen.getByText('结论失效条件')).toBeInTheDocument()
    expect(screen.getByText('开发调试：查看原始数据')).toBeInTheDocument()
  })

  it('closes from the accessible close button', async () => {
    const onClose = vi.fn()
    render(<ReportModal report={report} onClose={onClose} />)

    await userEvent.click(screen.getByRole('button', { name: '关闭研究报告' }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
