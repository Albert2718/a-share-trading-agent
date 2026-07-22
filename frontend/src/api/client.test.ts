import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from './client'


describe('api client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('returns the backend detail for a failed request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: '邮箱或密码错误' }),
      { status: 401, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(api.login({ email: 'a@example.com', password: 'bad' }))
      .rejects.toThrow('邮箱或密码错误')
  })

  it('adds a bearer token to authenticated requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('[]', {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await api.positions('token-123')

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer token-123')
  })

  it('parses streamed agent tokens and final message', async () => {
    const payload = [
      'event: planning\ndata: {"id":"planning","phase":"planning","status":"running"}\n\n',
      'event: tool_started\ndata: {"id":"call-1","phase":"tool_started","status":"running","tool_name":"market_quote"}\n\n',
      'event: tool_completed\ndata: {"id":"call-1","phase":"tool_completed","status":"completed","tool_name":"market_quote","result":{"ok":true,"code":"600519"}}\n\n',
      'event: token\ndata: {"content":"## 结论"}\n\n',
      'event: message\ndata: {"id":"m1","role":"assistant","content":"## 结论","tool_name":null,"tool_payload":null,"created_at":"2026-07-22T00:00:00Z"}\n\n',
    ].join('')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(payload, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    })))
    const events: string[] = []

    const message = await api.streamMessage('token', 'conversation-1', '分析', (event) => events.push(event.event))

    expect(events).toEqual(['planning', 'tool_started', 'tool_completed', 'token', 'message'])
    expect(message.content).toBe('## 结论')
  })
})
