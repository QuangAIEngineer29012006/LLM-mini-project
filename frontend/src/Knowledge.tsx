import { useEffect, useState } from 'react'
import { request } from './api'
import { Dialog } from './Dialog'

export type Citation = { chunk_id: string; doc_id: string; source: string; version: string; title?: string; section?: string }
export type Knowledge = { status: string; answer: string; citations: Citation[]; missing_information: string }
type Source = Citation & { text: string; skus: string[]; product_ids: number[] }

export const knowledgeStatus: Record<string, { label: string; tone: string }> = {
  answered: { label: 'Có trích dẫn nguồn', tone: 'ok' },
  insufficient_evidence: { label: 'Chưa đủ bằng chứng', tone: 'warn' },
  access_denied: { label: 'Không có quyền truy cập', tone: 'deny' },
  handoff: { label: 'Chuyển nhân viên', tone: 'warn' },
  error: { label: 'Lỗi kỹ thuật', tone: 'deny' },
}

export function KnowledgeBlock({ knowledge, onOpenSource }: { knowledge: Knowledge; onOpenSource: (chunkId: string) => void }) {
  const status = knowledgeStatus[knowledge.status] || { label: knowledge.status, tone: 'warn' }
  return <div className="knowledge-block">
    <span className={`knowledge-status knowledge-${status.tone}`}>{status.label}</span>
    {knowledge.missing_information && knowledge.status !== 'answered' && <small>{knowledge.missing_information}</small>}
    {knowledge.citations.length > 0 && <ol className="citation-list" aria-label="Nguồn trích dẫn">{knowledge.citations.map(c =>
      <li key={c.chunk_id}><button onClick={() => onOpenSource(c.chunk_id)}><b>{c.title || c.doc_id}</b><span>{c.section ? `${c.section} · ` : ''}{c.doc_id} · v{c.version}</span></button></li>)}</ol>}
  </div>
}

export function SourceDialog({ chunkId, token, onClose, onOpenProduct }: {
  chunkId: string; token?: string; onClose: () => void; onOpenProduct?: (productId: number | null, sku?: string) => void
}) {
  const [source, setSource] = useState<Source | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    request<Source>(`/api/knowledge/sources/${encodeURIComponent(chunkId)}`, {}, token).then(setSource).catch(e => setError((e as Error).message))
  }, [chunkId, token])
  return <Dialog label="Nguồn trích dẫn" backdrop="overlay" className="source-modal" onClose={onClose}>
    <button className="modal-close" onClick={onClose} aria-label="Đóng"><span aria-hidden="true">×</span></button>
    {error && <p className="inline-error" role="alert">{error}</p>}
    {!source && !error && <p role="status">Đang mở tài liệu...</p>}
    {source && <>
      <span className="eyebrow">{source.doc_id} · PHIÊN BẢN {source.version}</span>
      <h2>{source.title}</h2>
      <h3>{source.section}</h3>
      <p className="source-text">{source.text}</p>
      <small className="source-path">Nguồn: {source.source} · đoạn {source.chunk_id}</small>
      {onOpenProduct && source.product_ids.length > 0 && <div className="source-products">
        {source.skus.length ? source.skus.map(sku => <button key={sku} className="button button-dark" onClick={() => onOpenProduct(null, sku)}>Xem {sku}</button>)
          : source.product_ids.map(id => <button key={id} className="button button-dark" onClick={() => onOpenProduct(id)}>Xem sản phẩm</button>)}
      </div>}
    </>}
  </Dialog>
}
