import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import App from './App'

const shirt = { product_id: 1, name: 'Áo thun basic cotton', category: 'Áo', description: 'Cotton', price_from: 150000, price_to: 150000, in_stock: true, variants: [
  { sku: 'TSH-BLK-M', label: 'Đen / M', unit_price: 150000, stock: 25 },
  { sku: 'TSH-WHT-M', label: 'Trắng / M', unit_price: 150000, stock: 0 },
] }
const item = { item_id: '1', sku: 'TSH-BLK-M', name: shirt.name, variant_label: 'Đen / M', quantity: 1, unit_price: 150000, line_total: 150000 }
const order = { order_id: 'DH000001', status: 'pending_confirmation', editable: true, items: [item], total: 150000 }
const json = (value: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(value), { status }))
let handler: (path: string, init: RequestInit) => Promise<Response> | undefined
let fetchMock: ReturnType<typeof vi.fn>
const storage = () => {
  const data = new Map<string, string>()
  return { getItem: (key: string) => data.get(key) ?? null, setItem: (key: string, value: string) => { data.set(key, value) },
    removeItem: (key: string) => { data.delete(key) }, clear: () => data.clear(), key: (index: number) => [...data.keys()][index] ?? null,
    get length() { return data.size } }
}

beforeEach(() => {
  vi.stubGlobal('localStorage', storage())
  vi.stubGlobal('sessionStorage', storage())
  localStorage.clear(); sessionStorage.clear(); history.replaceState(null, '', '/')
  Element.prototype.scrollIntoView = vi.fn()
  handler = () => undefined
  fetchMock = vi.fn((path: string, init: RequestInit = {}) => {
    const custom = handler(path, init)
    if (custom) return custom
    if (path === '/api/session') return json({ token: 'test-session' })
    if (path === '/api/products') return json({ products: [shirt] })
    if (path === '/api/cart') return json({ items: [], total: 0 })
    if (path === '/api/orders') return json({ orders: [] })
    throw new Error('Unhandled API: ' + path)
  })
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

async function ready() { await screen.findByRole('button', { name: `Xem ${shirt.name}` }) }

describe('React integration regressions', () => {
  it('creates one session under StrictMode and searches Vietnamese without accents', async () => {
    render(<React.StrictMode><App /></React.StrictMode>); await ready()
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/session')).toHaveLength(1)
    fireEvent.change(screen.getByLabelText('Tìm sản phẩm'), { target: { value: 'ao thun' } })
    expect(screen.getByRole('button', { name: `Xem ${shirt.name}` })).toBeTruthy()
  })

  it('automatically recovers an expired session without retrying writes', async () => {
    localStorage.setItem('lc-session', 'expired')
    handler = (path, init) => path === '/api/cart' && new Headers(init.headers).get('Authorization') === 'Bearer expired'
      ? json({ error: { message: 'Phiên hết hạn' } }, 401) : undefined
    render(<App />); await ready()
    expect(localStorage.getItem('lc-session')).toBe('test-session')
    expect(fetchMock.mock.calls.filter(([path, init]) => path === '/api/cart/items' && init.method === 'POST')).toHaveLength(0)
  })

  it('shows a retry action after API failure and recovers on retry', async () => {
    let offline = true
    handler = path => path === '/api/products' && offline ? Promise.reject(new TypeError('fetch failed')) : undefined
    render(<App />)
    await screen.findByRole('alert')
    offline = false
    fireEvent.click(screen.getByRole('button', { name: 'Tải lại dữ liệu' })); await ready()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('blocks sold-out variants and closes product dialog with Escape', async () => {
    render(<App />); await ready()
    fireEvent.click(screen.getByRole('button', { name: `Xem ${shirt.name}` }))
    const dialog = screen.getByRole('dialog', { name: shirt.name })
    expect((within(dialog).getByRole('button', { name: 'Trắng / M · Hết hàng' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('opens the order referenced by chat even when a newer order exists', async () => {
    handler = path => path === '/api/chat' ? json({ reply: 'Đã tạo đơn nháp', order }) : path === '/api/orders'
      ? json({ orders: [{ ...order, order_id: 'DH000002' }, order] }) : undefined
    render(<App />); await ready()
    fireEvent.click(screen.getByRole('button', { name: 'Chat với trợ lý' }))
    fireEvent.change(screen.getByLabelText('Tin nhắn'), { target: { value: 'Chốt áo' } })
    fireEvent.click(screen.getByRole('button', { name: 'Gửi' }))
    fireEvent.click(await screen.findByRole('button', { name: /Xem đơn DH000001/ }))
    await waitFor(() => expect(screen.getByRole('heading', { level: 2, name: 'DH000001' })).toBeTruthy())
    expect(screen.queryByRole('heading', { level: 2, name: 'DH000002' })).toBeNull()
  })

  it('releases the mutation lock after saving an order so further edits work', async () => {
    history.replaceState(null, '', '/#orders')
    handler = (path, init) => path === '/api/orders' ? json({ orders: [order] }) : path.includes('/items/') && init.method === 'PATCH'
      ? json({ ...order, items: [{ ...item, quantity: JSON.parse(init.body as string).quantity }] }) : undefined
    render(<App />)
    const quantity = await screen.findByLabelText('Số lượng')
    fireEvent.change(quantity, { target: { value: '2' } }); fireEvent.click(screen.getByRole('button', { name: 'Lưu' }))
    await waitFor(() => expect((screen.getByRole('button', { name: 'Lưu' }) as HTMLButtonElement).disabled).toBe(false))
    fireEvent.change(screen.getByLabelText('Số lượng'), { target: { value: '3' } }); fireEvent.click(screen.getByRole('button', { name: 'Lưu' }))
    await waitFor(() => expect(fetchMock.mock.calls.filter(([path, init]) => path.includes('/items/') && init.method === 'PATCH')).toHaveLength(2))
  })

  it('retains the chat idempotency key when retrying an ambiguous network failure', async () => {
    let tries = 0
    handler = path => path === '/api/chat' ? (++tries === 1 ? Promise.reject(new TypeError('network')) : json({ reply: 'Đã nhận', route: 'ask_missing' })) : undefined
    render(<App />); await ready()
    fireEvent.click(screen.getByRole('button', { name: 'Chat với trợ lý' }))
    fireEvent.change(screen.getByLabelText('Tin nhắn'), { target: { value: 'Chốt 1 áo' } })
    fireEvent.click(screen.getByRole('button', { name: 'Gửi' }))
    await screen.findByText(/Bạn có thể gửi lại tin nhắn này/)
    fireEvent.click(screen.getByRole('button', { name: 'Gửi' }))
    await screen.findByText('Đã nhận')
    const calls = fetchMock.mock.calls.filter(([path]) => path === '/api/chat')
    expect(new Headers(calls[0][1].headers).get('Idempotency-Key')).toBe(new Headers(calls[1][1].headers).get('Idempotency-Key'))
  })
  it('shows field errors for an empty checkout and never submits an order', async () => {
    handler = path => path === '/api/cart' ? json({ items: [item], total: 150000 }) : undefined
    render(<App />); await ready()
    fireEvent.click(screen.getByRole('button', { name: /Giỏ hàng\s*1/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Tiến hành đặt hàng' }))
    fireEvent.click(screen.getByRole('button', { name: 'Gửi yêu cầu đặt hàng' }))
    expect(screen.getAllByRole('alert')).toHaveLength(3)
    expect(fetchMock.mock.calls.filter(([path, init]) => path === '/api/orders' && init.method === 'POST')).toHaveLength(0)
  })

  it('does not send a second add-to-cart request while the first is pending', async () => {
    let finish!: (response: Response) => void
    handler = path => path === '/api/cart/items' ? new Promise<Response>(resolve => { finish = resolve }) : undefined
    render(<App />); await ready()
    fireEvent.click(screen.getByRole('button', { name: `Xem ${shirt.name}` }))
    const add = screen.getByRole('button', { name: 'Thêm vào giỏ' })
    fireEvent.click(add); fireEvent.click(add)
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/cart/items')).toHaveLength(1)
    finish(await json({ items: [item], total: 150000 }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('collects backpack quantity and shipping in chat then displays the created order', async () => {
    const bag = { sku: 'BAG-GRY-15', name: 'Balo laptop', variant_label: 'Xám / 15 inch', unit_price: 520000, stock: 4, quantity: null }
    let chatCalls = 0
    handler = (path) => path === '/api/chat' ? (++chatCalls === 1
      ? json({ reply: 'Đã chọn balo. Vui lòng bổ sung thông tin.', intent: 'create_order', route: 'ask_missing', missing_fields: ['quantity', 'recipient_name', 'phone', 'address'], purchase: { items: [bag] } })
      : json({ reply: 'Đã tạo đơn nháp', route: 'draft_created', order: { ...order, items: [{ ...item, ...bag, quantity: 2, line_total: 1040000 }], total: 1040000 } })) : undefined
    render(<App />); await ready()
    fireEvent.click(screen.getByRole('button', { name: 'Chat với trợ lý' }))
    fireEvent.change(screen.getByLabelText('Tin nhắn'), { target: { value: 'đặt cho tôi balo laptop Balo laptop xám, 15inch' } })
    fireEvent.click(screen.getByRole('button', { name: 'Gửi' }))
    const form = await screen.findByRole('form', { name: 'Thông tin đặt hàng qua bot' })
    expect(chatCalls).toBe(1)
    fireEvent.change(within(form).getByLabelText('Số lượng Balo laptop'), { target: { value: '2' } })
    fireEvent.change(within(form).getByLabelText('Tên người nhận'), { target: { value: 'Khách Demo' } })
    fireEvent.change(within(form).getByLabelText('Số điện thoại'), { target: { value: '0912345678' } })
    fireEvent.change(within(form).getByLabelText('Địa chỉ giao hàng'), { target: { value: '12 Đường Mẫu, Quận 7' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Gửi thông tin đặt hàng' }))
    await screen.findByText('Tổng tiền sản phẩm: 1.040.000₫')
    expect(screen.queryByRole('form', { name: 'Thông tin đặt hàng qua bot' })).toBeNull()
    const payload = JSON.parse(fetchMock.mock.calls.filter(([path]) => path === '/api/chat')[1][1].body as string)
    expect(payload.message).toContain('Chốt 2 BAG-GRY-15')
    expect(payload.message).toContain('Tên Khách Demo')
    expect(payload.message).not.toContain('520000')
  })

  it('does not submit the chat purchase form with count above current stock', async () => {
    handler = path => path === '/api/chat' ? json({ reply: 'Chọn số lượng', route: 'ask_missing', missing_fields: ['quantity'], purchase: { items: [{ sku: 'BAG-GRY-15', name: 'Balo laptop', variant_label: 'Xám / 15 inch', unit_price: 520000, stock: 4, quantity: null }] } }) : undefined
    render(<App />); await ready()
    fireEvent.click(screen.getByRole('button', { name: 'Chat với trợ lý' }))
    fireEvent.change(screen.getByLabelText('Tin nhắn'), { target: { value: 'Đặt balo xám' } })
    fireEvent.click(screen.getByRole('button', { name: 'Gửi' }))
    const form = await screen.findByRole('form', { name: 'Thông tin đặt hàng qua bot' })
    fireEvent.change(within(form).getByLabelText('Số lượng Balo laptop'), { target: { value: '5' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Gửi thông tin đặt hàng' }))
    expect(within(form).getByRole('alert')).toBeTruthy()
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/chat')).toHaveLength(1)
  })

  it('closes the old purchase form when the customer requests a different unresolved variant', async () => {
    let calls = 0
    handler = path => path === '/api/chat' ? (++calls === 1
      ? json({ reply: 'Đã chọn balo', intent: 'create_order', route: 'ask_missing', missing_fields: ['quantity'], purchase: { items: [{ sku: 'BAG-GRY-15', name: 'Balo laptop', variant_label: 'Xám / 15 inch', unit_price: 520000, stock: 4, quantity: null }] } })
      : json({ reply: 'Không có size 16 inch', intent: 'create_order', route: 'ask_missing', missing_fields: ['variant'] })) : undefined
    render(<App />); await ready()
    fireEvent.click(screen.getByRole('button', { name: 'Chat với trợ lý' }))
    fireEvent.change(screen.getByLabelText('Tin nhắn'), { target: { value: 'Đặt balo xám' } })
    fireEvent.click(screen.getByRole('button', { name: 'Gửi' }))
    await screen.findByRole('form', { name: 'Thông tin đặt hàng qua bot' })
    fireEvent.change(screen.getByLabelText('Tin nhắn'), { target: { value: 'Đặt balo xám 16inch' } })
    fireEvent.click(screen.getByRole('button', { name: 'Gửi' }))
    await screen.findByText('Không có size 16 inch')
    expect(screen.queryByRole('form', { name: 'Thông tin đặt hàng qua bot' })).toBeNull()
  })

  it('shows knowledge status and citations, opens the source and links it to the product', async () => {
    const backpack = { product_id: 6, name: 'Balo laptop', category: 'Phụ kiện', description: 'Balo', price_from: 520000, price_to: 520000, in_stock: true, variants: [{ sku: 'BAG-GRY-15', label: 'Xám / 15 inch', unit_price: 520000, stock: 4 }] }
    handler = path => path === '/api/products' ? json({ products: [shirt, backpack] })
      : path === '/api/chat' ? json({ reply: 'Balo được bảo hành 12 tháng.', route: 'knowledge', intent: 'knowledge_query', knowledge: { status: 'answered', answer: 'Balo được bảo hành 12 tháng.', missing_information: '', citations: [{ chunk_id: 'DOC-POL-WARRANTY@1.0#03', doc_id: 'DOC-POL-WARRANTY', source: 'data_config/corpus/policies/pol_bao_hanh.md', version: '1.0', title: 'Chính sách bảo hành', section: 'Bảo hành Balo laptop' }] } })
      : path.startsWith('/api/knowledge/sources/') ? json({ chunk_id: 'DOC-POL-WARRANTY@1.0#03', doc_id: 'DOC-POL-WARRANTY', source: 'data_config/corpus/policies/pol_bao_hanh.md', version: '1.0', title: 'Chính sách bảo hành', section: 'Bảo hành Balo laptop', text: 'Thời hạn bảo hành 12 tháng.', skus: ['BAG-GRY-15'], product_ids: [6] })
      : undefined
    render(<App />); await ready()
    fireEvent.click(screen.getByRole('button', { name: 'Chat với trợ lý' }))
    fireEvent.change(screen.getByLabelText('Tin nhắn'), { target: { value: 'Balo laptop bảo hành bao lâu?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Gửi' }))
    expect(await screen.findByText('Có trích dẫn nguồn')).toBeTruthy()
    expect(screen.getByText('Tra cứu tài liệu')).toBeTruthy()
    fireEvent.click(within(screen.getByRole('list', { name: 'Nguồn trích dẫn' })).getByRole('button'))
    let source = await screen.findByRole('dialog', { name: 'Nguồn trích dẫn' })
    expect(await within(source).findByText('Thời hạn bảo hành 12 tháng.')).toBeTruthy()
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Nguồn trích dẫn' })).toBeNull())
    expect(screen.getByRole('dialog', { name: 'Trợ lý mua sắm' })).toBeTruthy()
    fireEvent.click(within(screen.getByRole('list', { name: 'Nguồn trích dẫn' })).getByRole('button'))
    source = await screen.findByRole('dialog', { name: 'Nguồn trích dẫn' })
    fireEvent.click(await within(source).findByRole('button', { name: 'Xem BAG-GRY-15' }))
    expect(await screen.findByRole('dialog', { name: 'Balo laptop' })).toBeTruthy()
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(document.body.style.overflow).toBe('')
  })

  it('shows refusal states without citations', async () => {
    handler = path => path === '/api/chat' ? json({ reply: 'Nội dung này thuộc tài liệu nội bộ.', route: 'knowledge', intent: 'knowledge_query', knowledge: { status: 'access_denied', answer: 'Nội dung này thuộc tài liệu nội bộ.', missing_information: 'Cần quyền admin.', citations: [] } }) : undefined
    render(<App />); await ready()
    fireEvent.click(screen.getByRole('button', { name: 'Chat với trợ lý' }))
    fireEvent.change(screen.getByLabelText('Tin nhắn'), { target: { value: 'Phụ cấp ca đêm bao nhiêu?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Gửi' }))
    expect(await screen.findByText('Không có quyền truy cập')).toBeTruthy()
    expect(screen.queryByRole('list', { name: 'Nguồn trích dẫn' })).toBeNull()
  })

  it('opens a demo staff session with its own token and shows index status', async () => {
    handler = (path, init) => {
      if (path === '/api/session' && new Headers(init.headers).get('X-Demo-Role') === 'staff') return json({ token: 'staff-token', role: 'staff' })
      if (path === '/api/admin/index') {
        expect(new Headers(init.headers).get('Authorization')).toBe('Bearer staff-token')
        return json({ role: 'staff', index: { ready: true, problem: null, index_id: '1.1.0-fake-143be753', corpus_release: '1.1.0', chunk_count: 86, chunks_by_access: { public: 64, staff: 13, admin: 9 }, embedding: { provider: 'fake', model: 'hashed-ngram-v1' }, generator: 'fake-extractive-v1', cache_entries: 0 }, corpus: { active_release: '1.1.0', synced_at: null, documents_by_access: { public: 12, staff: 3, admin: 0 } }, documents: [{ doc_id: 'DOC-INT-PROMO-RULES', title: 'Hạn mức hỗ trợ', doc_type: 'sop_internal', access_level: 'staff', version: '1.0', author: 'TV1' }], releases: null })
      }
      return undefined
    }
    history.replaceState(null, '', '/#admin')
    render(<App />)
    await screen.findByLabelText('Khóa demo')
    fireEvent.change(screen.getByLabelText('Khóa demo'), { target: { value: 'staff-demo-key' } })
    fireEvent.click(screen.getByRole('button', { name: 'Mở phiên' }))
    expect(await screen.findByText('1.1.0-fake-143be753')).toBeTruthy()
    expect(screen.getByText('DOC-INT-PROMO-RULES')).toBeTruthy()
    expect(localStorage.getItem('lc-session')).toBe('test-session')
  })
})
