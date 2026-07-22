import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import { ChatPanel } from './ChatPanel'


vi.mock('../api/client', () => ({
  api: {
    conversations: vi.fn(),
    createConversation: vi.fn(),
    conversation: vi.fn(),
    streamMessage: vi.fn(),
    confirmTool: vi.fn(),
  },
}))

const conversation = {
  id: 'conversation-1',
  title: '新对话',
  created_at: '2026-07-17T00:00:00Z',
  updated_at: '2026-07-17T00:00:00Z',
  messages: [],
}


describe('ChatPanel', () => {
  beforeEach(() => {
    vi.mocked(api.conversations).mockResolvedValue([conversation])
    vi.mocked(api.conversation).mockResolvedValue(conversation)
    vi.mocked(api.streamMessage).mockImplementation(async (_token, _id, _content, onEvent) => {
      const message = {
        id: 'assistant-1', role: 'assistant', content: '**完成**', tool_name: null,
        tool_payload: null, created_at: '2026-07-17T00:00:00Z',
      }
      onEvent({ event: 'planning', data: { id: 'planning', phase: 'planning', status: 'running' } })
      onEvent({ event: 'tool_started', data: { id: 'call-1', phase: 'tool_started', status: 'running', tool_name: 'market_quote' } })
      onEvent({ event: 'tool_completed', data: { id: 'call-1', phase: 'tool_completed', status: 'completed', tool_name: 'market_quote', result: { ok: true, code: '600519' }, duration_ms: 12 } })
      onEvent({ event: 'token', data: { content: '**完成**' } })
      onEvent({ event: 'message', data: message })
      return message
    })
    vi.mocked(api.confirmTool).mockResolvedValue({
      id: 'assistant-2', role: 'assistant', content: '已保存', tool_name: 'portfolio.upsert',
      tool_payload: { status: 'completed' }, created_at: '2026-07-17T00:00:00Z',
    })
  })

  it('loads a conversation and sends natural language input', async () => {
    const user = userEvent.setup()
    render(<ChatPanel token="token" newChatRequest={0} onAction={vi.fn()} onOpenResearch={vi.fn()} />)

    const input = await screen.findByLabelText('输入投研需求')
    await user.type(input, '分析 600519')
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => expect(api.streamMessage).toHaveBeenCalledWith(
      'token', 'conversation-1', '分析 600519', expect.any(Function),
    ))
  })

  it('confirms a durable write action by message id', async () => {
    const pendingConversation = {
      ...conversation,
      messages: [{
        id: 'pending-message', role: 'assistant', content: '请确认',
        tool_name: 'portfolio.upsert', tool_payload: { status: 'pending_confirmation' },
        created_at: '2026-07-17T00:00:00Z',
      }],
    }
    vi.mocked(api.conversations).mockResolvedValue([pendingConversation])
    vi.mocked(api.conversation).mockResolvedValue(pendingConversation)
    const user = userEvent.setup()

    render(<ChatPanel token="token" newChatRequest={0} onAction={vi.fn()} onOpenResearch={vi.fn()} />)
    await user.click(await screen.findByRole('button', { name: '确认写入持仓' }))

    expect(api.confirmTool).toHaveBeenCalledWith('token', 'conversation-1', 'pending-message')
  })

  it('renders markdown only for assistant responses', async () => {
    const markdownConversation = {
      ...conversation,
      messages: [{
        id: 'markdown-message', role: 'assistant', content: '## 结论\n\n**谨慎观察**',
        tool_name: null, tool_payload: null, created_at: '2026-07-17T00:00:00Z',
      }],
    }
    vi.mocked(api.conversations).mockResolvedValue([markdownConversation])
    vi.mocked(api.conversation).mockResolvedValue(markdownConversation)

    render(<ChatPanel token="token" newChatRequest={0} onAction={vi.fn()} onOpenResearch={vi.fn()} />)

    expect(await screen.findByRole('heading', { name: '结论' })).toBeInTheDocument()
    expect(screen.getByText('谨慎观察').tagName).toBe('STRONG')
  })

  it('renders persisted tool activity and a structured quote card', async () => {
    const toolConversation = {
      ...conversation,
      messages: [{
        id: 'quote-message', role: 'assistant', content: '行情如下。', tool_name: 'market_quote',
        tool_payload: {
          status: 'completed',
          tool_results: [{
            name: 'market_quote', status: 'completed', duration_ms: 18, arguments: { code: '600519' },
            result: { ok: true, code: '600519', name: '贵州茅台', latest_price: 1500, change_pct: 1.2, open: 1488, high: 1510, low: 1480 },
          }],
        },
        created_at: '2026-07-17T00:00:00Z',
      }],
    }
    vi.mocked(api.conversations).mockResolvedValue([toolConversation])
    vi.mocked(api.conversation).mockResolvedValue(toolConversation)

    render(<ChatPanel token="token" newChatRequest={0} onAction={vi.fn()} onOpenResearch={vi.fn()} />)

    expect(await screen.findByText('贵州茅台 600519')).toBeInTheDocument()
    expect(screen.getByText('查询实时行情')).toBeInTheDocument()
    expect(screen.getByText('¥ 1,500')).toBeInTheDocument()
  })

  it('grows the composer until the maximum height then enables scrolling', async () => {
    render(<ChatPanel token="token" newChatRequest={0} onAction={vi.fn()} onOpenResearch={vi.fn()} />)
    const input = await screen.findByLabelText('输入投研需求')
    Object.defineProperty(input, 'scrollHeight', { configurable: true, value: 180 })

    fireEvent.change(input, { target: { value: '第一行\n第二行\n第三行' } })

    await waitFor(() => expect(input).toHaveStyle({ height: '128px', overflowY: 'auto' }))
  })
})
