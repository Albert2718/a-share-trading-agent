import { FormEvent, useState } from 'react'

import { api, type AuthResult } from '../api/client'

export function AuthPanel({ onAuthenticated }: { onAuthenticated: (value: AuthResult) => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const email = String(data.get('email') || '')
    const password = String(data.get('password') || '')
    const username = String(data.get('username') || '')
    setLoading(true)
    setError('')
    try {
      const result = mode === 'login'
        ? await api.login({ email, password })
        : await api.register({ email, username, password })
      onAuthenticated(result)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '认证失败')
    } finally {
      setLoading(false)
    }
  }

  return <main className="auth-shell">
    <section className="auth-intro">
      <p className="eyebrow">RESEARCH OS / A-SHARE</p>
      <h1>把市场信息，变成可追溯的研究判断。</h1>
      <p>一个面向个人投资者的 AI 研究工作台。研究任务、持仓与结论都由你的账户独立保存。</p>
    </section>
    <form className="auth-card" onSubmit={submit}>
      <div className="tabs">
        <button type="button" className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>登录</button>
        <button type="button" className={mode === 'register' ? 'active' : ''} onClick={() => setMode('register')}>创建账户</button>
      </div>
      {mode === 'register' && <label>用户名<input name="username" required minLength={3} placeholder="例如 albert_ai" /></label>}
      <label>邮箱<input name="email" required type="email" placeholder="you@example.com" /></label>
      <label>密码<input name="password" required type="password" minLength={8} placeholder="至少 8 位" /></label>
      {error && <p className="form-error">{error}</p>}
      <button className="primary" disabled={loading}>{loading ? '处理中…' : mode === 'login' ? '进入工作台' : '创建并进入'}</button>
    </form>
  </main>
}
