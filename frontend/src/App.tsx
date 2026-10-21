import { FormEvent, useEffect, useMemo, useState } from 'react'

type Variant = { sku: string; label: string; unit_price: number; stock: number; color?: string; size?: string }
type Product = { product_id: number; name: string; category: string; description: string; price_from: number; price_to: number; in_stock: boolean; variants: Variant[] }
type Item = { item_id: string; sku: string; name: string; variant_label: string; quantity: number; unit_price: number; line_total: number; available_variants?: {sku: string; label: string}[] }
type Order = { order_id: string; status: string; editable?: boolean; shipping?: {recipient_name: string; phone: string; address: string}; items: Item[]; total: number }
type ChatMessage = { role: 'user' | 'assistant'; text: string; reply?: string; route?: string; missing_fields?: string[]; order?: Order; error?: string }

const images: Record<string, string[]> = {
  'Áo': [
    'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?auto=format&fit=crop&w=1000&q=85',
    'https://images.unsplash.com/photo-1556821840-3a63f95609a7?auto=format&fit=crop&w=1000&q=85',
  ],
  'Giày': [
    'https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=1000&q=85',
    'https://images.unsplash.com/photo-1525966222134-fcfa99b8ae77?auto=format&fit=crop&w=1000&q=85',
  ],
  'Phụ kiện': [
    'https://images.unsplash.com/photo-1553062407-98eeb64c6a62?auto=format&fit=crop&w=1000&q=85',
    'https://images.unsplash.com/photo-1588850561407-ed78c282e89b?auto=format&fit=crop&w=1000&q=85',
  ],
}
const formatMoney = (value: number) => new Intl.NumberFormat('vi-VN').format(value) + '₫'
const statusLabels: Record<string, string> = { pending_confirmation: 'Chờ xác nhận', confirmed: 'Đã xác nhận', cancelled: 'Đã hủy' }
const imageFor = (product: Product) => {
  const name = product.name.toLocaleLowerCase('vi')
  if (product.category === 'Phụ kiện') {
    if (name.includes('nón') || name.includes('mũ')) return images['Phụ kiện'][1]
    if (name.includes('balo')) return images['Phụ kiện'][0]
  }
  return images[product.category]?.[(product.product_id - 1) % (images[product.category]?.length || 1)] || images['Phụ kiện'][0]
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  const token = localStorage.getItem('lc-session')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(path, { ...init, headers })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data?.error?.message || 'Không thể kết nối máy chủ. Vui lòng thử lại.')
  return data as T
}

function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, React.ReactNode> = {
    search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
    bag: <><path d="M5 8h14l1 13H4L5 8Z"/><path d="M9 8a3 3 0 0 1 6 0"/></>,
    chat: <><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z"/></>,
    arrow: <><path d="M5 12h14M13 6l6 6-6 6"/></>,
    close: <><path d="m18 6-12 12M6 6l12 12"/></>,
    order: <><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></>,
    spark: <><path d="m12 3 1.9 5.8L20 11l-6.1 2.2L12 19l-2-5.8L4 11l6-2.2L12 3Z"/><path d="m19 14 1.2 2.8L23 18l-2.8 1.2L19 22l-1.2-2.8L15 18l2.8-1.2L19 14Z"/></>,
    back: <><path d="m15 18-6-6 6-6"/></>,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}

function App() {
  const [products, setProducts] = useState<Product[]>([])
  const [cart, setCart] = useState<Order | null>(null)
  const [orders, setOrders] = useState<Order[]>([])
  const [page, setPage] = useState<'shop' | 'cart' | 'checkout' | 'orders'>('shop')
  const [selected, setSelected] = useState<Product | null>(null)
  const [variant, setVariant] = useState<Variant | null>(null)
  const [quantity, setQuantity] = useState(1)
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('Tất cả')
  const [chatOpen, setChatOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([{ role: 'assistant', text: 'Xin chào! Mình có thể giúp bạn tìm sản phẩm, kiểm tra giá và tồn kho, hoặc tạo đơn hàng.' }])
  const [chatInput, setChatInput] = useState('')
  const [pendingChat, setPendingChat] = useState<{ message: string; key: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [checkoutError, setCheckoutError] = useState('')
  const [shipping, setShipping] = useState({ recipient_name: '', phone: '', address: '' })
  const [activeOrder, setActiveOrder] = useState<Order | null>(null)
  const [orderDrafts, setOrderDrafts] = useState<Record<string, { sku: string; quantity: number }>>({})

  const load = async () => {
    setError('')
    try {
      if (!localStorage.getItem('lc-session')) {
        const session = await request<{ token: string }>('/api/session', { method: 'POST' })
        localStorage.setItem('lc-session', session.token)
      }
      const [catalog, currentCart] = await Promise.all([
        request<{ products: Product[] }>('/api/products'), request<Order>('/api/cart'),
      ])
      setProducts(catalog.products)
      setCart(currentCart)
    } catch (e) { setError((e as Error).message) } finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [])

  const categories = useMemo(() => ['Tất cả', ...new Set(products.map(p => p.category))], [products])
  const shown = useMemo(() => products.filter(p => (category === 'Tất cả' || p.category === category) && p.name.toLocaleLowerCase('vi').includes(query.toLocaleLowerCase('vi'))), [products, category, query])
  const cartCount = cart?.items?.reduce((sum, item) => sum + item.quantity, 0) || 0
  const flash = (text: string) => { setNotice(text); window.setTimeout(() => setNotice(''), 2800) }

  const addToCart = async () => {
    if (!variant) return
    setBusy(true)
    try {
      const updated = await request<Order>('/api/cart/items', { method: 'POST', body: JSON.stringify({ sku: variant.sku, quantity }) })
      setCart(updated); setSelected(null); flash('Đã thêm sản phẩm vào giỏ hàng.')
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const updateCartItem = async (item: Item, next: number) => {
    try { setCart(await request<Order>(`/api/cart/items/${encodeURIComponent(item.item_id)}`, { method: 'PATCH', body: JSON.stringify({ quantity: next }) })) }
    catch (e) { setError((e as Error).message) }
  }
  const removeCartItem = async (item: Item) => {
    try { setCart(await request<Order>(`/api/cart/items/${encodeURIComponent(item.item_id)}`, { method: 'DELETE' })); flash('Đã xóa sản phẩm khỏi giỏ.') }
    catch (e) { setError((e as Error).message) }
  }
  const submitCheckout = async (event: FormEvent) => {
    event.preventDefault(); setCheckoutError('')
    const phone = shipping.phone.replace(/[\s()-]/g, '')
    const errors = [shipping.recipient_name.trim().length < 2 && 'Vui lòng nhập tên người nhận.', !/^(0\d{9}|\+84\d{9})$/.test(phone) && 'Số điện thoại chưa đúng định dạng.', shipping.address.trim().length < 10 && 'Địa chỉ cần ít nhất 10 ký tự.'].filter(Boolean)
    if (errors.length) { setCheckoutError(errors.join(' ')); return }
    setBusy(true)
    try {
      const key = sessionStorage.getItem('lc-checkout-key') || crypto.randomUUID()
      sessionStorage.setItem('lc-checkout-key', key)
      const order = await request<Order>('/api/orders', { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify({ shipping: { ...shipping, phone } }) })
      sessionStorage.removeItem('lc-checkout-key'); setCart({ ...order, items: [], total: 0 }); setActiveOrder(order); setPage('orders'); flash(`Đã tạo đơn ${order.order_id}.`)
    } catch (e) { setCheckoutError((e as Error).message) } finally { setBusy(false) }
  }
  const openOrders = async () => {
    setPage('orders')
    try { const result = await request<{ orders: Order[] }>('/api/orders'); setOrders(result.orders); if (result.orders[0]) setActiveOrder(result.orders[0]) }
    catch (e) { setError((e as Error).message) }
  }
  const saveOrderItem = async (item: Item) => {
    if (!activeOrder) return
    const draft = orderDrafts[item.item_id] || { sku: item.sku, quantity: item.quantity }
    const changes: Record<string, string | number> = {}
    if (draft.sku !== item.sku) changes.sku = draft.sku
    if (draft.quantity !== item.quantity) changes.quantity = draft.quantity
    if (!Object.keys(changes).length) return
    try {
      const updated = await request<Order>(`/api/orders/${encodeURIComponent(activeOrder.order_id)}/items/${encodeURIComponent(item.item_id)}`, { method: 'PATCH', body: JSON.stringify(changes) })
      setActiveOrder(updated); setOrders(current => current.map(order => order.order_id === updated.order_id ? updated : order))
      setOrderDrafts({}); flash('Đã cập nhật đơn hàng.')
    } catch (e) { setError((e as Error).message) }
  }
  const sendChat = async (event: FormEvent) => {
    event.preventDefault(); const text = chatInput.trim(); if (!text || busy) return
    setMessages(prev => [...prev, { role: 'user', text }]); setChatInput(''); setBusy(true)
    const pending = pendingChat?.message === text ? pendingChat : { message: text, key: crypto.randomUUID() }
    setPendingChat(pending)
    try {
      const response = await request<ChatMessage>('/api/chat', { method: 'POST', headers: { 'Idempotency-Key': pending.key }, body: JSON.stringify({ message: text }) })
      setMessages(prev => [...prev, { role: 'assistant', text: response.reply || response.text || '', route: response.route, missing_fields: response.missing_fields, order: response.order }])
      setPendingChat(null)
      if (response.order) setActiveOrder(response.order)
      void request<Order>('/api/cart').then(setCart).catch(e => setError((e as Error).message))
    } catch (e) { setChatInput(text); setMessages(prev => [...prev, { role: 'assistant', text: `${(e as Error).message} Bạn có thể gửi lại tin nhắn này.`, error: 'true' }]) } finally { setBusy(false) }
  }

  return <div className="app-shell">
    <div className="announcement"><span>Giao hàng miễn phí cho đơn từ 500.000₫</span><span>Hỗ trợ mỗi ngày · 09:00 – 21:00</span></div>
    <header className="header wrap">
      <button className="brand" onClick={() => setPage('shop')} aria-label="Trang chủ"><span className="brand-mark">l.</span><span>live<span className="brand-light">commerce</span></span></button>
      <nav className="main-nav"><button className={page === 'shop' ? 'nav-active' : ''} onClick={() => setPage('shop')}>Cửa hàng</button><button onClick={openOrders}>Đơn hàng</button></nav>
      <div className="header-actions">
        <label className="header-search"><Icon name="search" size={18}/><input value={query} onChange={e => { setQuery(e.target.value); setPage('shop') }} placeholder="Tìm sản phẩm..." /></label>
        <button className="icon-button chat-shortcut" aria-label="Chat với trợ lý" onClick={() => setChatOpen(true)}><Icon name="chat"/><span className="online-dot"/></button>
        <button className="cart-button" onClick={() => setPage('cart')}><Icon name="bag"/><span>Giỏ hàng</span><b>{cartCount}</b></button>
      </div>
    </header>

    {error && <div className="toast toast-error" role="alert">{error}<button onClick={() => setError('')}><Icon name="close" size={16}/></button></div>}
    {notice && <div className="toast">{notice}</div>}

    {page === 'shop' && <main>
      <section className="hero wrap">
        <div className="hero-copy"><span className="eyebrow"><span className="eyebrow-dot"/> BỘ SƯU TẬP MỚI</span><h1>Những món đồ<br/>làm nên <em>chất riêng.</em></h1><p>Tuyển chọn những thiết kế tối giản, chất lượng bền lâu — dành cho nhịp sống mỗi ngày.</p><button className="button button-dark" onClick={() => document.getElementById('catalog')?.scrollIntoView({ behavior: 'smooth' })}>Khám phá ngay <Icon name="arrow" size={17}/></button><div className="hero-proof"><div className="avatar-stack"><span>H</span><span>M</span><span>A</span></div><span>Được yêu thích bởi <b>2.000+</b> khách hàng</span></div></div>
        <div className="hero-visual"><img src="https://images.unsplash.com/photo-1529139574466-a303027c1d8b?auto=format&fit=crop&w=1500&q=90" alt="Bộ sưu tập thời trang phong cách tối giản"/><div className="hero-sticker"><span>CURATED FOR</span><strong>everyday.</strong><i>✳</i></div><div className="hero-index">01 <span>/</span> 04</div></div>
        <div className="hero-side-note">LỰA CHỌN CÓ CHỦ ĐÍCH&nbsp; · &nbsp;SỐNG ĐẸP MỖI NGÀY</div>
      </section>
      <section className="benefits wrap"><div><span className="benefit-icon">✳</span><span><b>Chọn lọc kỹ lưỡng</b><small>Chất lượng trong từng chi tiết</small></span></div><div><span className="benefit-icon">↗</span><span><b>Giao hàng toàn quốc</b><small>Nhận hàng trong 2–4 ngày</small></span></div><div><span className="benefit-icon">♡</span><span><b>Đổi trả dễ dàng</b><small>Hỗ trợ đổi trong vòng 7 ngày</small></span></div></section>
      <section id="catalog" className="catalog wrap"><div className="section-heading"><div><span className="eyebrow">THE EVERYDAY EDIT</span><h2>Món đồ đáng để giữ lâu.</h2></div><span className="product-count">{shown.length.toString().padStart(2, '0')} sản phẩm</span></div>
        <div className="catalog-toolbar"><div className="category-tabs">{categories.map(c => <button key={c} onClick={() => setCategory(c)} className={category === c ? 'category-active' : ''}>{c}</button>)}</div><div className="sort-label">SẮP XẾP <span>↕</span></div></div>
        {loading ? <div className="loading-grid">{[1,2,3,4].map(x => <div className="skeleton" key={x}/>)}</div> : <div className="product-grid">{shown.map((product, index) => <article className="product-card" key={product.product_id}>
          <button className={`product-image image-tone-${index % 4}`} onClick={() => { setSelected(product); setVariant(product.variants.find(v => v.stock > 0) || product.variants[0]); setQuantity(1) }} aria-label={`Xem ${product.name}`}><img src={imageFor(product)} alt={product.name} loading="lazy"/><span className="image-badge">{index === 0 ? 'BESTSELLER' : product.in_stock ? 'CURATED' : 'TẠM HẾT'}</span><span className="quick-view">Xem sản phẩm <Icon name="arrow" size={15}/></span><span className="product-plus">+</span></button>
          <div className="product-info"><div><span className="product-category">{product.category}</span><h3>{product.name}</h3></div><b>{product.price_from === product.price_to ? formatMoney(product.price_from) : `${formatMoney(product.price_from)} – ${formatMoney(product.price_to)}`}</b></div><div className="product-subline"><span>{product.variants.length} lựa chọn</span><span className={product.in_stock ? 'stock-ok' : 'stock-out'}>{product.in_stock ? '● Còn hàng' : '● Hết hàng'}</span></div>
        </article>)}</div>}
        {!loading && !shown.length && <div className="empty-state"><span>⌕</span><h3>Chưa tìm thấy món đồ phù hợp</h3><p>Thử một từ khóa khác hoặc chọn danh mục khác nhé.</p></div>}
      </section>
      <section className="editorial wrap"><div className="editorial-image"><img src="https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&w=1300&q=85" alt="Chất liệu và chi tiết sản phẩm"/></div><div className="editorial-copy"><span className="eyebrow">MUA ÍT HƠN, CHỌN TỐT HƠN</span><h2>Tốt hơn mỗi ngày.<br/><em>Bền lâu theo năm tháng.</em></h2><p>Chúng mình tin rằng những món đồ bạn dùng thường xuyên nên được làm thật tốt. Từ chất liệu đến phom dáng, mọi lựa chọn đều hướng đến sự thoải mái và bền bỉ.</p><button className="text-link" onClick={() => setChatOpen(true)}>Hỏi trợ lý mua sắm <Icon name="arrow" size={16}/></button></div></section>
    </main>}

    {page === 'cart' && <main className="inner-page wrap"><button className="back-link" onClick={() => setPage('shop')}><Icon name="back" size={16}/> Tiếp tục mua sắm</button><div className="inner-heading"><span className="eyebrow">YOUR SELECTION</span><h1>Giỏ hàng <small>({cartCount})</small></h1></div>{cart?.items?.length ? <div className="cart-layout"><div className="cart-list">{cart.items.map(item => <div className="cart-row" key={item.item_id}><div className="cart-thumb"><img src={imageFor(products.find(p => p.name === item.name) || { product_id: 1, category: 'Áo' } as Product)} alt=""/></div><div className="cart-product"><span>{item.name}</span><small>{item.variant_label} · {formatMoney(item.unit_price)}</small><button className="remove-link" onClick={() => void removeCartItem(item)}>Xóa</button></div><div className="quantity-control"><button onClick={() => void updateCartItem(item, Math.max(1,item.quantity-1))}>−</button><span>{item.quantity}</span><button onClick={() => void updateCartItem(item, item.quantity+1)}>+</button></div><strong className="line-total">{formatMoney(item.line_total)}</strong></div>)}</div><aside className="summary-card"><h3>Tóm tắt đơn hàng</h3><div><span>Tạm tính</span><b>{formatMoney(cart.total)}</b></div><div><span>Phí vận chuyển</span><span>Tính ở bước sau</span></div><hr/><div className="summary-total"><span>Tổng cộng</span><b>{formatMoney(cart.total)}</b></div><button className="button button-dark full-button" onClick={() => setPage('checkout')}>Tiến hành đặt hàng <Icon name="arrow" size={17}/></button><p>Giá được xác nhận ở thời điểm đặt hàng.</p></aside></div> : <div className="empty-state"><span>◯</span><h3>Giỏ hàng đang trống</h3><p>Hãy chọn vài món đồ bạn yêu thích nhé.</p><button className="button button-dark" onClick={() => setPage('shop')}>Đi xem sản phẩm <Icon name="arrow" size={16}/></button></div>}</main>}

    {page === 'checkout' && <main className="inner-page wrap"><button className="back-link" onClick={() => setPage('cart')}><Icon name="back" size={16}/> Quay lại giỏ hàng</button><div className="inner-heading"><span className="eyebrow">ALMOST YOURS</span><h1>Thông tin giao nhận</h1></div><div className="checkout-layout"><form className="checkout-form" onSubmit={submitCheckout}><h2>Thông tin người nhận</h2><label>Họ và tên<input required maxLength={100} value={shipping.recipient_name} onChange={e => setShipping({...shipping,recipient_name:e.target.value})} placeholder="Tên người nhận"/></label><label>Số điện thoại<input required value={shipping.phone} onChange={e => setShipping({...shipping,phone:e.target.value})} placeholder="0912 345 678"/></label><label>Địa chỉ giao hàng<textarea required maxLength={300} rows={3} value={shipping.address} onChange={e => setShipping({...shipping,address:e.target.value})} placeholder="Số nhà, đường, phường/xã, quận/huyện, tỉnh/thành"/></label>{checkoutError && <div className="inline-error">{checkoutError}</div>}<button className="button button-dark full-button" disabled={busy}>{busy ? 'Đang gửi...' : 'Gửi yêu cầu đặt hàng'} <Icon name="arrow" size={17}/></button><p className="form-note">Đơn hàng sẽ ở trạng thái chờ xác nhận. Bạn có thể kiểm tra và chỉnh sửa trong mục Đơn hàng.</p></form><aside className="summary-card"><h3>Đơn hàng của bạn</h3>{cart?.items?.map(i => <div className="checkout-item" key={i.item_id}><span>{i.name} <small>× {i.quantity}</small></span><b>{formatMoney(i.line_total)}</b></div>)}<hr/><div className="summary-total"><span>Tổng cộng</span><b>{formatMoney(cart?.total || 0)}</b></div></aside></div></main>}

    {page === 'orders' && <main className="inner-page wrap"><div className="inner-heading"><span className="eyebrow">YOUR ORDERS</span><h1>Đơn hàng</h1></div>{(orders.length || activeOrder) ? <div className="orders-layout"><div className="order-selector">{[...(activeOrder && !orders.some(o => o.order_id === activeOrder.order_id) ? [activeOrder] : []), ...orders].map(o => <button key={o.order_id} className={activeOrder?.order_id === o.order_id ? 'order-selected' : ''} onClick={() => setActiveOrder(o)}><Icon name="order"/><span><b>{o.order_id}</b><small>{statusLabels[o.status] || o.status}</small></span><Icon name="arrow" size={16}/></button>)}</div>{activeOrder && <div className="order-detail"><div className="order-detail-head"><div><span className="eyebrow">ORDER DETAILS</span><h2>{activeOrder.order_id}</h2></div><span className="status-pill">{statusLabels[activeOrder.status] || activeOrder.status}</span></div>{activeOrder.items.map(i => { const draft = orderDrafts[i.item_id] || { sku: i.sku, quantity: i.quantity }; return <div className="order-line order-edit-line" key={i.item_id}><div className="order-edit-fields"><span>{i.name}<small>{i.variant_label}</small></span>{activeOrder.editable && <div className="order-edit-controls"><select aria-label="Phân loại" value={draft.sku} onChange={e => setOrderDrafts(current => ({...current,[i.item_id]:{...draft,sku:e.target.value}}))}>{(i.available_variants || [{sku:i.sku,label:i.variant_label}]).map(v => <option key={v.sku} value={v.sku}>{v.label}</option>)}</select><input aria-label="Số lượng" type="number" min="1" max="99" value={draft.quantity} onChange={e => setOrderDrafts(current => ({...current,[i.item_id]:{...draft,quantity:Math.max(1,Number(e.target.value))}}))}/><button className="save-edit" onClick={() => void saveOrderItem(i)}>Lưu</button></div>}</div><b>{formatMoney(i.line_total)}</b></div>})}<div className="summary-total"><span>Tổng cộng</span><b>{formatMoney(activeOrder.total)}</b></div>{activeOrder.shipping && <div className="shipping-details"><b>Giao đến</b><span>{activeOrder.shipping.recipient_name} · {activeOrder.shipping.phone}</span><small>{activeOrder.shipping.address}</small></div>}<button className="text-link" onClick={() => void openOrders()}>Tải lại đơn hàng ↻</button></div>}</div> : <div className="empty-state"><span>▤</span><h3>Bạn chưa có đơn hàng nào</h3><p>Những món đồ bạn đặt sẽ xuất hiện ở đây.</p><button className="button button-dark" onClick={() => setPage('shop')}>Khám phá cửa hàng</button></div>}</main>}

    <footer className="footer"><div className="wrap footer-inner"><button className="brand footer-brand" onClick={() => setPage('shop')}><span className="brand-mark">l.</span><span>live<span className="brand-light">commerce</span></span></button><span>Những lựa chọn tốt cho cuộc sống thường ngày.</span><span>© 2025 Live Commerce</span></div></footer>
    <button className="assistant-fab" onClick={() => setChatOpen(true)}><Icon name="spark"/><span>Trợ lý mua sắm</span><span className="fab-dot"/></button>

    {selected && <div className="overlay" onMouseDown={e => { if (e.target === e.currentTarget) setSelected(null) }}><section className="product-modal"><button className="modal-close" onClick={() => setSelected(null)} aria-label="Đóng"><Icon name="close"/></button><div className="modal-photo"><img src={imageFor(selected)} alt={selected.name}/><span className="image-badge">{selected.category.toUpperCase()}</span></div><div className="modal-details"><span className="eyebrow">{selected.category} · EVERYDAY EDIT</span><h2>{selected.name}</h2><p>{selected.description}</p><strong className="modal-price">{formatMoney(variant?.unit_price || selected.price_from)}</strong><label className="variant-label">Phân loại</label><div className="variant-list">{selected.variants.map(v => <button key={v.sku} className={`${variant?.sku === v.sku ? 'variant-selected' : ''} ${v.stock === 0 ? 'variant-sold' : ''}`} disabled={v.stock === 0} onClick={() => { setVariant(v); setQuantity(1) }}>{v.label}{v.stock === 0 && ' · Hết hàng'}</button>)}</div>{variant && <div className="stock-note">{variant.stock ? `Còn ${variant.stock} sản phẩm` : 'Tạm hết hàng'}</div>}<div className="add-row"><div className="quantity-control"><button onClick={() => setQuantity(Math.max(1,quantity-1))}>−</button><span>{quantity}</span><button onClick={() => setQuantity(Math.min(99,variant?.stock || 99,quantity+1))}>+</button></div><button className="button button-dark" disabled={!variant?.stock || busy} onClick={() => void addToCart()}>{busy ? 'Đang thêm...' : 'Thêm vào giỏ'} <Icon name="bag" size={17}/></button></div><div className="modal-promise">↗ Giao hàng toàn quốc <span>♡ Đổi trả trong 7 ngày</span></div></div></section></div>}

    {chatOpen && <div className="chat-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) setChatOpen(false) }}><section className="chat-panel"><div className="chat-head"><div className="assistant-avatar"><Icon name="spark"/></div><div><b>Trợ lý mua sắm</b><small><span className="online-dot"/> Đang trực tuyến</small></div><button onClick={() => setChatOpen(false)} aria-label="Đóng chat"><Icon name="close"/></button></div><div className="chat-intro"><span className="eyebrow">LIVE COMMERCE ASSISTANT</span><h3>Mình có thể giúp gì cho bạn?</h3><p>Tìm sản phẩm, kiểm tra giá và tồn kho, hay bắt đầu đặt hàng.</p><div className="suggestions"><button onClick={() => setChatInput('Cửa hàng bán những gì?')}>Cửa hàng bán gì?</button><button onClick={() => setChatInput('Cho xem giày dưới 800k còn hàng')}>Tìm giày dưới 800k</button></div></div><div className="chat-messages">{messages.map((m,i) => <div key={i} className={`message ${m.role === 'user' ? 'message-user' : ''}`}><span className="message-avatar">{m.role === 'assistant' ? 'l.' : 'bạn'}</span><div><p>{m.text}</p>{m.missing_fields?.length ? <small>Cần bổ sung: {m.missing_fields.join(', ')}</small> : null}{m.order && <button className="message-order" onClick={() => { setActiveOrder(m.order!); setChatOpen(false); void openOrders() }}>Xem đơn {m.order.order_id} →</button>}</div></div>)}</div><form className="chat-compose" onSubmit={sendChat}><input maxLength={500} value={chatInput} onChange={e => setChatInput(e.target.value)} placeholder="Nhập câu hỏi của bạn..."/><button disabled={busy || !chatInput.trim()} aria-label="Gửi"><Icon name="arrow"/></button></form><div className="chat-footnote">Câu trả lời được hỗ trợ bởi trợ lý AI.</div></section></div>}
  </div>
}

export default App
