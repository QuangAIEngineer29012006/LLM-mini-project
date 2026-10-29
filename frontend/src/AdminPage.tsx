import { FormEvent, useEffect, useState } from 'react'
import { request } from './api'
import { KnowledgeBlock, SourceDialog, type Knowledge } from './Knowledge'

type Retrieval = { rank: number; score: number; chunk_id: string; access_level: string; section: string }
type Answer = Knowledge & { debug?: { retrieval?: Retrieval[]; context?: string[]; index_id?: string; cache?: string } }
type Bundle = { index_id: string; chunk_count: number; built_at: string }
type Status = {
  role: string
  index: { ready: boolean; problem: string | null; index_id: string | null; corpus_release: string | null; chunk_count: number | null
    chunks_by_access: Record<string, number> | null; embedding: { provider: string; model: string } | null; generator: string; cache_entries: number }
  corpus: { active_release: string | null; synced_at: string | null; documents_by_access: Record<string, number> }
  documents: { doc_id: string; title: string; doc_type: string; access_level: string; version: string; author: string }[]
  releases: Record<string, { manifest_path: string; bundle: Bundle | null }> | null
}

const STORAGE_KEY = 'lc-staff-session'

export function AdminPage() {
  const [session, setSession] = useState<{ token: string; role: string } | null>(() => {
    try { return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null') } catch { return null }
  })
  const [login, setLogin] = useState({ role: 'staff', key: '' })
  const [status, setStatus] = useState<Status | null>(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<Answer | null>(null)
  const [sourceId, setSourceId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const run = async (task: () => Promise<void>) => {
    setBusy(true); setError('')
    try { await task() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const loadStatus = (token = session?.token) => token ? run(async () => setStatus(await request<Status>('/api/admin/index', {}, token))) : Promise.resolve()
  useEffect(() => { void loadStatus() }, [session?.token])

  const signIn = (event: FormEvent) => {
    event.preventDefault()
    void run(async () => {
      const created = await request<{ token: string; role: string }>('/api/session', { method: 'POST', headers: { 'X-Demo-Role': login.role, 'X-Demo-Key': login.key } }, '')
      const next = { token: created.token, role: created.role }
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next)); setSession(next); setLogin({ ...login, key: '' })
    })
  }
  const signOut = () => {
    if (session) void request('/api/session', { method: 'DELETE' }, session.token).catch(() => undefined)
    sessionStorage.removeItem(STORAGE_KEY); setSession(null); setStatus(null); setAnswer(null)
  }
  const ask = (event: FormEvent) => {
    event.preventDefault()
    if (!session || !question.trim()) return
    void run(async () => setAnswer(await request<Answer>('/api/knowledge', { method: 'POST', body: JSON.stringify({ question }) }, session.token)))
  }
  const reindex = (action: 'build' | 'activate', release: string) => session && run(async () => {
    await request('/api/admin/reindex', { method: 'POST', body: JSON.stringify({ action, release }) }, session.token)
    setStatus(await request<Status>('/api/admin/index', {}, session.token))
  })

  if (!session) return <main className="inner-page wrap admin-page">
    <div className="inner-heading"><span className="eyebrow">STAFF · ADMIN (DEMO)</span><h1>Kiến thức nội bộ</h1></div>
    <form className="checkout-form" onSubmit={signIn}>
      <h2>Mở phiên nhân viên mô phỏng</h2>
      <label>Vai trò<select aria-label="Vai trò" value={login.role} onChange={e => setLogin({ ...login, role: e.target.value })}><option value="staff">Nhân viên (staff)</option><option value="admin">Quản trị (admin)</option></select></label>
      <label>Khóa demo<input aria-label="Khóa demo" type="password" autoComplete="off" value={login.key} onChange={e => setLogin({ ...login, key: e.target.value })} placeholder="DEMO_STAFF_KEY hoặc DEMO_ADMIN_KEY trong .env"/></label>
      {error && <div className="inline-error" role="alert">{error}</div>}
      <button className="button button-dark full-button" disabled={busy || !login.key}>Mở phiên</button>
      <p className="form-note">Đây là role mô phỏng cho demo, không phải hệ thống đăng nhập thật. Phiên khách hàng ở cửa hàng không bị ảnh hưởng.</p>
    </form>
  </main>

  const index = status?.index
  return <main className="inner-page wrap admin-page">
    <div className="inner-heading admin-heading"><div><span className="eyebrow">PHIÊN {session.role.toUpperCase()}</span><h1>Kiến thức nội bộ</h1></div><button className="text-link" onClick={signOut}>Đóng phiên</button></div>
    {error && <div className="inline-error" role="alert">{error}</div>}
    <section className="admin-grid">
      <div className="admin-card">
        <h2>Index đang dùng</h2>
        {index ? <dl>
          <dt>Trạng thái</dt><dd><span className={`knowledge-status knowledge-${index.ready ? 'ok' : 'deny'}`}>{index.ready ? 'Sẵn sàng' : 'Degraded'}</span>{index.problem && <small>{index.problem}</small>}</dd>
          <dt>Index</dt><dd>{index.index_id || '—'}</dd>
          <dt>Corpus release</dt><dd>index {index.corpus_release || '—'} · DB {status?.corpus.active_release || '—'}</dd>
          <dt>Embedding</dt><dd>{index.embedding ? `${index.embedding.provider} / ${index.embedding.model}` : '—'}</dd>
          <dt>Sinh câu trả lời</dt><dd>{index.generator}</dd>
          <dt>Chunk</dt><dd>{index.chunk_count ?? '—'} {index.chunks_by_access && `(public ${index.chunks_by_access.public}, staff ${index.chunks_by_access.staff}, admin ${index.chunks_by_access.admin})`}</dd>
          <dt>Cache</dt><dd>{index.cache_entries} câu trả lời</dd>
        </dl> : <p role="status">Đang tải...</p>}
        <button className="text-link" disabled={busy} onClick={() => void loadStatus()}>Tải lại ↻</button>
      </div>
      {status?.releases && <div className="admin-card">
        <h2>Release và re-index</h2>
        <table className="admin-table"><thead><tr><th>Release</th><th>Bundle</th><th></th></tr></thead><tbody>
          {Object.entries(status.releases).map(([release, info]) => <tr key={release}>
            <td>{release}{release === index?.corpus_release && <b> · active</b>}</td>
            <td>{info.bundle ? `${info.bundle.index_id} (${info.bundle.chunk_count} chunk)` : 'Chưa build'}</td>
            <td className="admin-actions"><button disabled={busy} onClick={() => void reindex('build', release)}>Build</button><button disabled={busy || !info.bundle || release === index?.corpus_release} onClick={() => void reindex('activate', release)}>Activate</button></td>
          </tr>)}
        </tbody></table>
        <p className="form-note">Activate đồng bộ metadata DB và con trỏ index cùng một lúc, rồi xóa cache. Rollback = activate release cũ.</p>
      </div>}
    </section>
    <section className="admin-card">
      <h2>Hỏi đáp theo quyền {session.role}</h2>
      <form className="admin-ask" onSubmit={ask}><input aria-label="Câu hỏi nội bộ" maxLength={500} value={question} onChange={e => setQuestion(e.target.value)} placeholder="Ví dụ: Hạn mức hỗ trợ phí vận chuyển nội bộ là bao nhiêu?"/><button className="button button-dark" disabled={busy || !question.trim()}>Hỏi</button></form>
      {answer && <div className="admin-answer">
        <p>{answer.answer}</p>
        <KnowledgeBlock knowledge={answer} onOpenSource={setSourceId}/>
        {answer.debug?.retrieval && <table className="admin-table"><caption>Retrieval (điểm không phải độ chắc chắn){answer.debug.cache === 'hit' ? ' · từ cache' : ''}</caption><thead><tr><th>#</th><th>Điểm</th><th>Chunk</th><th>Quyền</th><th>Trong context</th></tr></thead><tbody>
          {answer.debug.retrieval.map(r => <tr key={r.chunk_id}><td>{r.rank}</td><td>{r.score.toFixed(3)}</td><td>{r.chunk_id}<small>{r.section}</small></td><td>{r.access_level}</td><td>{answer.debug?.context?.includes(r.chunk_id) ? 'Có' : '—'}</td></tr>)}
        </tbody></table>}
      </div>}
    </section>
    {status && <section className="admin-card">
      <h2>Tài liệu được phép xem ({status.documents.length})</h2>
      <table className="admin-table"><thead><tr><th>Doc ID</th><th>Tiêu đề</th><th>Loại</th><th>Quyền</th><th>Phiên bản</th></tr></thead><tbody>
        {status.documents.map(d => <tr key={d.doc_id}><td>{d.doc_id}</td><td>{d.title}</td><td>{d.doc_type}</td><td>{d.access_level}</td><td>{d.version}</td></tr>)}
      </tbody></table>
    </section>}
    {sourceId && <SourceDialog chunkId={sourceId} token={session.token} onClose={() => setSourceId(null)}/>}
  </main>
}
