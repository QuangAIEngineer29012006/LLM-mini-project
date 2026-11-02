import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, ensureSession, request } from './api'
import { Dialog } from './Dialog'
import { ChatPurchaseForm, type Purchase } from './ChatPurchaseForm'
import { KnowledgeBlock, SourceDialog, type Knowledge } from './Knowledge'
import { AdminPage } from './AdminPage'

type Variant = { sku: string; label: string; unit_price: number; stock: number; color?: string; size?: string }
type Product = { product_id: number; name: string; category: string; description: string; price_from: number; price_to: number; in_stock: boolean; variants: Variant[] }
type Item = { item_id: string; sku: string; name: string; variant_label: string; quantity: number; unit_price: number; line_total: number; available_variants?: {sku: string; label: string}[] }
type Order = { order_id: string; status: string; editable?: boolean; shipping?: {recipient_name: string; phone: string; address: string}; items: Item[]; total: number }
type ChatMessage = { role: 'user' | 'assistant'; text: string; reply?: string; route?: string; intent?: string; missing_fields?: string[]; order?: Order; purchase?: Purchase; knowledge?: Knowledge; error?: string }

const images: Record<string, string[]> = {
  'Áo': [
    'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?auto=format&fit=crop&w=1000&q=85',
    'https://images.unsplash.com/photo-1556905055-8f358a7a47b2?auto=format&fit=crop&w=1000&q=85',
  ],
  'Giày': [
    'https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=1000&q=85',
    'https://images.unsplash.com/photo-1603808033192-082d6919d3e1?auto=format&fit=crop&w=1000&q=85',
  ],
  'Phụ kiện': [
    'https://images.unsplash.com/photo-1553062407-98eeb64c6a62?auto=format&fit=crop&w=1000&q=85',
    'https://images.unsplash.com/photo-1588850561407-ed78c282e89b?auto=format&fit=crop&w=1000&q=85',
  ],
}

const specificImages: Record<string, string> = {
  'áo thun': 'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?auto=format&fit=crop&w=1000&q=85',
  'hoodie': 'https://images.unsplash.com/photo-1556905055-8f358a7a47b2?auto=format&fit=crop&w=1000&q=85',
  'sneaker': 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=1000&q=85',
  'dép': 'https://images.unsplash.com/photo-1603808033192-082d6919d3e1?auto=format&fit=crop&w=1000&q=85',
  'nón': 'https://images.unsplash.com/photo-1588850561407-ed78c282e89b?auto=format&fit=crop&w=1000&q=85',
  'mũ': 'https://images.unsplash.com/photo-1588850561407-ed78c282e89b?auto=format&fit=crop&w=1000&q=85',
  'balo': 'https://images.unsplash.com/photo-1553062407-98eeb64c6a62?auto=format&fit=crop&w=1000&q=85',
}

const formatMoney = (value: number) => new Intl.NumberFormat('vi-VN').format(value) + '₫'
const fieldLabels: Record<string, string> = { recipient_name: 'tên người nhận', phone: 'số điện thoại', address: 'địa chỉ', product: 'sản phẩm', quantity: 'số lượng', variant: 'màu/size', order_reference: 'mã đơn' }
type Page = 'shop' | 'cart' | 'checkout' | 'orders' | 'admin'
const pageFrom = (value: string): Page => (['cart', 'checkout', 'orders', 'admin'] as string[]).includes(value) ? value as Page : 'shop'
const statusLabels: Record<string, string> = { pending_confirmation: 'Chờ xác nhận', confirmed: 'Đã xác nhận', cancelled: 'Đã hủy' }

const imageFor = (product: Product | null | undefined): string => {
  if (!product) return images['Áo'][0]
  const name = (product.name || '').toLocaleLowerCase('vi')
  for (const [key, url] of Object.entries(specificImages)) {
    if (name.includes(key)) return url
  }
  const categoryImages = images[product.category]
  if (categoryImages && categoryImages.length > 0) {
    const id = product.product_id || 1
    return categoryImages[(id - 1) % categoryImages.length]
  }
  return images['Phụ kiện'][0]
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
    check: <><path d="M20 6 9 17l-5-5"/></>,
    shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></>,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.arrow}</svg>
}

function App() {
  const [products, setProducts] = useState<Product[]>([])
  const [cart, setCart] = useState<Order | null>(null)
  const [orders, setOrders] = useState<Order[]>([])
  const [page, setPage] = useState<Page>(() => pageFrom(location.hash.slice(1)))
  const [selected, setSelected] = useState<Product | null>(null)
  const [variant, setVariant] = useState<Variant | null>(null)
  const [quantity, setQuantity] = useState(1)
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('Tất cả')
  const [chatOpen, setChatOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([{ role: 'assistant', text: 'Xin chào! Mình là trợ lý Live Commerce. Bạn có thể hỏi tìm sản phẩm, kiểm tra giá, chính sách bảo hành hoặc đặt hàng nhanh chóng!' }])
  const [chatInput, setChatInput] = useState('')
  const [pendingChat, setPendingChat] = useState<{ message: string; key: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [checkoutError, setCheckoutError] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [shipping, setShipping] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('lc-customer-shipping') || '{}')
      return {
        recipient_name: saved.recipient_name || '',
        phone: saved.phone || '',
        address: saved.address || ''
      }
    } catch {
      return { recipient_name: '', phone: '', address: '' }
    }
  })
  const [activeOrder, setActiveOrder] = useState<Order | null>(null)
  const [sourceId, setSourceId] = useState<string | null>(null)
  const mutation = useRef(false)
  const loadInProgress = useRef(false)
  const messagesEnd = useRef<HTMLDivElement>(null)
  const chatInputRef = useRef<HTMLInputElement>(null)
  const [sort, setSort] = useState('default')
  const [orderDrafts, setOrderDrafts] = useState<Record<string, { sku: string; quantity: number }>>({})

  const load = async () => {
    if (loadInProgress.current) return
    loadInProgress.current = true
    setError(''); setLoading(true)
    try {
      await ensureSession()
      try { await request<Order>('/api/cart') }
      catch (e) {
        if (!(e instanceof ApiError) || e.status !== 401) throw e
        localStorage.removeItem('lc-session'); sessionStorage.removeItem('lc-checkout-key')
        await ensureSession()
        setOrders([]); setActiveOrder(null); setMessages([{ role: 'assistant', text: 'Phiên cũ đã hết hạn. Đã mở phiên mua sắm mới; đơn cũ không chuyển sang phiên này.' }])
        setPendingChat(null); setShipping({ recipient_name: '', phone: '', address: '' })
        setSelected(null); setOrderDrafts({}); setFieldErrors({})
        flash('Phiên cũ đã hết hạn. Đã mở phiên mua sắm mới; đơn cũ không chuyển sang phiên này.')
      }
      const [catalog, currentCart] = await Promise.all([
        request<{ products: Product[] }>('/api/products'), request<Order>('/api/cart'),
      ])
      setProducts(catalog.products)
      setCart(currentCart)
    } catch (e) { setError((e as Error).message) } finally { loadInProgress.current = false; setLoading(false) }
  }
  useEffect(() => { void load() }, [])
  useEffect(() => {
    const onHash = () => setPage(pageFrom(location.hash.slice(1)))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  useEffect(() => { if (location.hash !== `#${page}`) location.hash = page }, [page])
  useEffect(() => { if (page === 'orders' && !loading && !error) void openOrders() }, [page, loading])
  useEffect(() => { messagesEnd.current?.scrollIntoView({ block: 'end', behavior: 'smooth' }) }, [messages, busy, chatOpen])
  const normalize = (text: string) => text.toLocaleLowerCase('vi').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd')

  const categories = useMemo(() => ['Tất cả', ...new Set(products.map(p => p.category))], [products])
  const shown = useMemo(() => products.filter(p => (category === 'Tất cả' || p.category === category) && normalize(p.name).includes(normalize(query))).sort((a, b) => sort === 'price-asc' ? a.price_from - b.price_from : sort === 'price-desc' ? b.price_from - a.price_from : a.product_id - b.product_id), [products, category, query, sort])
  const cartCount = cart?.items?.reduce((sum, item) => sum + item.quantity, 0) || 0
  const flash = (text: string) => { setNotice(text); window.setTimeout(() => setNotice(''), 3000) }

  const addToCart = async () => {
    if (!variant || mutation.current) return
    mutation.current = true; setBusy(true)
    try {
      const updated = await request<Order>('/api/cart/items', { method: 'POST', body: JSON.stringify({ sku: variant.sku, quantity }) })
      setCart(updated); setSelected(null); flash('Đã thêm sản phẩm vào giỏ hàng.')
    } catch (e) { setError((e as Error).message) } finally { mutation.current = false; setBusy(false) }
  }
  const updateCartItem = async (item: Item, next: number) => {
    if (mutation.current) return
    mutation.current = true; setBusy(true)
    try { setCart(await request<Order>(`/api/cart/items/${encodeURIComponent(item.item_id)}`, { method: 'PATCH', body: JSON.stringify({ quantity: next }) })) }
    catch (e) { setError((e as Error).message) } finally { mutation.current = false; setBusy(false) }
  }
  const removeCartItem = async (item: Item) => {
    if (mutation.current) return
    mutation.current = true; setBusy(true)
    try { setCart(await request<Order>(`/api/cart/items/${encodeURIComponent(item.item_id)}`, { method: 'DELETE' })); flash('Đã xóa sản phẩm khỏi giỏ.') }
    catch (e) { setError((e as Error).message) } finally { mutation.current = false; setBusy(false) }
  }
  const submitCheckout = async (event: FormEvent) => {
    event.preventDefault(); if (mutation.current) return; setCheckoutError('')
    const phone = shipping.phone.replace(/[\s()-]/g, '')
    const errors = {
      recipient_name: shipping.recipient_name.trim().length < 2 ? 'Vui lòng nhập tên người nhận (ít nhất 2 ký tự).' : '',
      phone: !/^(0\d{9}|\+84\d{9})$/.test(phone) ? 'Số điện thoại chưa đúng định dạng.' : '',
      address: shipping.address.trim().length < 10 ? 'Địa chỉ cần ít nhất 10 ký tự.' : '',
    }
    setFieldErrors(errors)
    if (Object.values(errors).some(Boolean)) return
    mutation.current = true; setBusy(true)
    try {
      const key = sessionStorage.getItem('lc-checkout-key') || crypto.randomUUID()
      sessionStorage.setItem('lc-checkout-key', key)
      const order = await request<Order>('/api/orders', { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify({ shipping: { ...shipping, phone } }) })
      sessionStorage.removeItem('lc-checkout-key')
      try {
        localStorage.setItem('lc-customer-shipping', JSON.stringify({ recipient_name: shipping.recipient_name, phone, address: shipping.address }))
      } catch {}
      setCart({ ...order, items: [], total: 0 }); setActiveOrder(order); setPage('orders'); flash(`Đã tạo đơn ${order.order_id}.`)
    } catch (e) { setCheckoutError((e as Error).message) } finally { mutation.current = false; setBusy(false) }
  }
  const openOrders = async (preferred?: string) => {
    setPage('orders')
    try {
      const result = await request<{ orders: Order[] }>('/api/orders')
      setOrders(result.orders)
      setActiveOrder(current => result.orders.find(order => order.order_id === (preferred || current?.order_id)) || result.orders[0] || null)
      setOrderDrafts({})
    } catch (e) { setError((e as Error).message) }
  }
  const saveOrderItem = async (item: Item) => {
    if (!activeOrder || mutation.current) return
    const draft = orderDrafts[item.item_id] || { sku: item.sku, quantity: item.quantity }
    const changes: Record<string, string | number> = {}
    if (draft.sku !== item.sku) changes.sku = draft.sku
    if (draft.quantity !== item.quantity) changes.quantity = draft.quantity
    if (!Object.keys(changes).length) return
    if (!Number.isInteger(draft.quantity) || draft.quantity < 1 || draft.quantity > 99) { setError('Số lượng phải là số nguyên từ 1 đến 99.'); return }
    mutation.current = true; setBusy(true)
    try {
      const updated = await request<Order>(`/api/orders/${encodeURIComponent(activeOrder.order_id)}/items/${encodeURIComponent(item.item_id)}`, { method: 'PATCH', body: JSON.stringify(changes) })
      setActiveOrder(updated); setOrders(current => current.map(order => order.order_id === updated.order_id ? updated : order))
      setOrderDrafts({}); flash('Đã cập nhật đơn hàng.')
    } catch (e) { setError((e as Error).message) } finally { mutation.current = false; setBusy(false) }
  }
  const submitChatText = async (message: string) => {
    const text = message.trim(); if (!text || mutation.current) return
    setMessages(prev => [...prev, { role: 'user', text }]); setChatInput(''); mutation.current = true; setBusy(true)
    const pending = pendingChat?.message === text ? pendingChat : { message: text, key: crypto.randomUUID() }
    setPendingChat(pending)
    try {
      const response = await request<ChatMessage>('/api/chat', { method: 'POST', headers: { 'Idempotency-Key': pending.key }, body: JSON.stringify({ message: text }) })
      setMessages(prev => [...prev, { role: 'assistant', text: response.reply || response.text || '', route: response.route, intent: response.intent, missing_fields: response.missing_fields, order: response.order, purchase: response.purchase, knowledge: response.knowledge }])
      setPendingChat(null)
      if (response.order) setActiveOrder(response.order)
      void request<Order>('/api/cart').then(setCart).catch(e => setError((e as Error).message))
    } catch (e) { setChatInput(text); setMessages(prev => [...prev, { role: 'assistant', text: `${(e as Error).message} Bạn có thể gửi lại tin nhắn này.`, error: 'true' }]) } finally { mutation.current = false; setBusy(false) }
  }

  const sendChat = async (event: FormEvent) => { event.preventDefault(); await submitChatText(chatInput) }
  const handleSuggestionClick = (text: string) => {
    setChatInput(text)
    chatInputRef.current?.focus()
  }
  const openProductFromSource = (productId: number | null, sku?: string) => {
    const product = products.find(p => sku ? p.variants.some(v => v.sku === sku) : p.product_id === productId)
    if (!product) { setError('Sản phẩm này hiện không có trong catalog đang bán.'); return }
    setSourceId(null); setChatOpen(false); setPage('shop'); setSelected(product); setQuantity(1)
    setVariant(product.variants.find(v => v.sku === sku) || product.variants.find(v => v.stock > 0) || product.variants[0])
  }
  const activePurchaseIndex = messages.reduce((active, message, index) => {
    if (message.purchase) return index
    return message.intent === 'create_order' || (message.route && ['draft_created', 'order_updated', 'handoff', 'out_of_stock'].includes(message.route)) ? -1 : active
  }, -1)

  return <div className="app-shell">
    <div className="announcement">
      <span className="announcement-item"><span className="pulse-dot"/> Trợ lý AI sẵn sàng tư vấn &amp; hỗ trợ tạo đơn 24/7</span>
      <span className="announcement-item">Miễn phí giao hàng cho đơn từ 500.000₫ · Đổi trả 7 ngày</span>
    </div>

    <header className="header wrap">
      <div className="header-left">
        <button className="brand" onClick={() => setPage('shop')} aria-label="Trang chủ">
          <span className="brand-mark">l.</span>
          <span className="brand-name">live<span className="brand-light">commerce</span></span>
        </button>
        <nav className="main-nav">
          <button className={page === 'shop' ? 'nav-active' : ''} onClick={() => setPage('shop')}>Cửa hàng</button>
          <button className={page === 'orders' ? 'nav-active' : ''} onClick={() => void openOrders()}>Đơn hàng</button>
          <button className={page === 'cart' ? 'nav-active mobile-only-nav' : 'mobile-only-nav'} onClick={() => setPage('cart')}>Giỏ ({cartCount})</button>
        </nav>
      </div>

      <div className="header-actions">
        <label className="header-search">
          <Icon name="search" size={17}/>
          <input
            value={query}
            onChange={e => { setQuery(e.target.value); setPage('shop') }}
            aria-label="Tìm sản phẩm"
            placeholder="Tìm theo tên, loại đồ..."
          />
          {query && <button className="search-clear" type="button" onClick={() => setQuery('')} aria-label="Xóa tìm kiếm">×</button>}
        </label>
        <button className="icon-button chat-shortcut" aria-label="Chat với trợ lý" onClick={() => setChatOpen(true)}>
          <Icon name="chat"/>
          <span className="online-dot"/>
        </button>
        <button className="cart-button" onClick={() => setPage('cart')} aria-label={`Giỏ hàng ${cartCount}`}>
          <Icon name="bag"/>
          <span>Giỏ hàng</span>
          <b className={cartCount > 0 ? 'cart-badge-active' : ''}>{cartCount}</b>
        </button>
      </div>
    </header>

    <div className="toast-container">
      {error && (
        <div className="toast toast-error" role="alert">
          <span className="toast-text">{error}</span>
          <div className="toast-actions">
            <button className="toast-retry-btn" onClick={() => void load()}>Tải lại dữ liệu</button>
            <button className="toast-close-btn" aria-label="Đóng thông báo" onClick={() => setError('')}><Icon name="close" size={16}/></button>
          </div>
        </div>
      )}
      {notice && (
        <div className="toast toast-notice" role="status">
          <Icon name="check" size={16}/>
          <span>{notice}</span>
        </div>
      )}
    </div>

    {page === 'shop' && <main>
      <section className="hero wrap">
        <div className="hero-copy">
          <span className="eyebrow"><span className="eyebrow-dot"/> BỘ SƯU TẬP MỚI · THIẾT KẾ TỐI GIẢN</span>
          <h1>Những món đồ<br/>làm nên <em>chất riêng.</em></h1>
          <p>Tuyển chọn những thiết kế tối giản, chất lượng bền lâu — dành cho nhịp sống hiện đại mỗi ngày.</p>
          <div className="hero-cta-group">
            <button className="button button-dark hero-btn" onClick={() => document.getElementById('catalog')?.scrollIntoView({ behavior: 'smooth' })}>
              Khám phá ngay <Icon name="arrow" size={17}/>
            </button>
            <button className="button button-secondary hero-chat-btn" onClick={() => setChatOpen(true)}>
              <Icon name="spark" size={16}/> Hỏi trợ lý AI
            </button>
          </div>
          <div className="hero-proof">
            <div className="hero-proof-item"><span>✳</span> 100% hình ảnh &amp; mô tả thực tế</div>
            <div className="hero-proof-item"><span>⚡</span> Tồn kho &amp; giá cập nhật trực tiếp</div>
          </div>
        </div>
        <div className="hero-visual">
          <img src="https://images.unsplash.com/photo-1529139574466-a303027c1d8b?auto=format&fit=crop&w=1500&q=90" alt="Bộ sưu tập thời trang phong cách tối giản"/>
          <div className="hero-sticker">
            <span>CURATED FOR</span>
            <strong>everyday.</strong>
            <i>✳</i>
          </div>
          <div className="hero-card-floating">
            <span className="card-floating-badge">TRỢ LÝ MUA SẮM</span>
            <p>Hỏi giá, size và đặt hàng tự động trong vài giây</p>
          </div>
        </div>
      </section>

      <section className="benefits wrap">
        <div>
          <span className="benefit-icon">✳</span>
          <div>
            <b>Chọn lọc kỹ lưỡng</b>
            <small>Chất lượng bền vững trong từng đường kim mũi chỉ</small>
          </div>
        </div>
        <div>
          <span className="benefit-icon">⚡</span>
          <div>
            <b>Đặt hàng qua Chat</b>
            <small>Tư vấn chọn size, kiểm tra tồn kho và tạo đơn tức thì</small>
          </div>
        </div>
        <div>
          <span className="benefit-icon">↺</span>
          <div>
            <b>Chỉnh sửa linh hoạt</b>
            <small>Đổi phân loại, số lượng đơn hàng trước khi xác nhận</small>
          </div>
        </div>
      </section>

      <section id="catalog" className="catalog wrap">
        <div className="section-heading">
          <div>
            <span className="eyebrow">THE EVERYDAY EDIT</span>
            <h2>Danh mục sản phẩm</h2>
          </div>
          <span className="product-count">{shown.length.toString().padStart(2, '0')} sản phẩm</span>
        </div>

        <div className="catalog-toolbar">
          <div className="category-tabs">
            {categories.map(c => (
              <button key={c} onClick={() => setCategory(c)} className={category === c ? 'category-active' : ''}>
                {c}
              </button>
            ))}
          </div>
          <label className="sort-label">
            <span>Sắp xếp</span>
            <select aria-label="Sắp xếp sản phẩm" value={sort} onChange={e => setSort(e.target.value)}>
              <option value="default">Mặc định</option>
              <option value="price-asc">Giá: Thấp đến cao</option>
              <option value="price-desc">Giá: Cao đến thấp</option>
            </select>
          </label>
        </div>

        {loading ? (
          <div className="loading-grid">
            {[1, 2, 3, 4].map(x => <div className="skeleton" key={x}/>)}
          </div>
        ) : (
          <div className="product-grid">
            {shown.map((product, index) => (
              <article className="product-card" key={product.product_id}>
                <button
                  className={`product-image image-tone-${index % 4}`}
                  onClick={() => { setSelected(product); setVariant(product.variants.find(v => v.stock > 0) || product.variants[0]); setQuantity(1) }}
                  aria-label={`Xem ${product.name}`}
                >
                  <img src={imageFor(product)} alt={product.name} loading="lazy"/>
                  <small className="illustration-note">Ảnh minh họa</small>
                  <span className={`image-badge ${!product.in_stock ? 'badge-sold-out' : ''}`}>
                    {product.in_stock ? product.category : 'TẠM HẾT'}
                  </span>
                  <span className="quick-view">Xem chi tiết <Icon name="arrow" size={15}/></span>
                  <span className="product-plus">+</span>
                </button>
                <div
                  className="product-info"
                  onClick={() => { setSelected(product); setVariant(product.variants.find(v => v.stock > 0) || product.variants[0]); setQuantity(1) }}
                >
                  <div>
                    <span className="product-category">{product.category}</span>
                    <h3>{product.name}</h3>
                  </div>
                  <b>{product.price_from === product.price_to ? formatMoney(product.price_from) : `${formatMoney(product.price_from)} – ${formatMoney(product.price_to)}`}</b>
                </div>
                <div className="product-subline">
                  <span>{product.variants.length} lựa chọn phân loại</span>
                  <span className={product.in_stock ? 'stock-ok' : 'stock-out'}>
                    {product.in_stock ? '● Còn hàng' : '● Tạm hết'}
                  </span>
                </div>
              </article>
            ))}
          </div>
        )}

        {!loading && !shown.length && (
          <div className="empty-state">
            <span className="empty-icon">⌕</span>
            <h3>Chưa tìm thấy món đồ phù hợp</h3>
            <p>Thử tìm với từ khóa khác hoặc chuyển sang danh mục Tất cả nhé.</p>
            <button className="button button-secondary" onClick={() => { setQuery(''); setCategory('Tất cả') }}>Xóa bộ lọc</button>
          </div>
        )}
      </section>

      <section className="editorial wrap">
        <div className="editorial-image">
          <img src="https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&w=1300&q=85" alt="Chất liệu và chi tiết sản phẩm"/>
        </div>
        <div className="editorial-copy">
          <span className="eyebrow">CHẤT LIỆU &amp; PHOM DÁNG</span>
          <h2>Tốt hơn mỗi ngày.<br/><em>Bền lâu theo năm tháng.</em></h2>
          <p>Mỗi sản phẩm đều được chọn lọc từ chất liệu tự nhiên, phom dáng chuẩn chỉ, tạo cảm giác thoải mái tối đa trong mọi hoạt động hàng ngày.</p>
          <button className="text-link" onClick={() => setChatOpen(true)}>
            Hỏi trợ lý mua sắm AI <Icon name="arrow" size={16}/>
          </button>
        </div>
      </section>
    </main>}

    {page === 'cart' && <main className="inner-page wrap">
      <button className="back-link" onClick={() => setPage('shop')}><Icon name="back" size={16}/> Tiếp tục mua sắm</button>
      <div className="inner-heading">
        <span className="eyebrow">SELECTION</span>
        <h1>Giỏ hàng <small>({cartCount} món)</small></h1>
      </div>

      {cart?.items?.length ? (
        <div className="cart-layout">
          <div className="cart-list">
            {cart.items.map(item => (
              <div className="cart-row" key={item.item_id}>
                <div className="cart-thumb">
                  <img src={imageFor(products.find(p => p.name === item.name))} alt={item.name}/>
                </div>
                <div className="cart-product">
                  <span>{item.name}</span>
                  <small>{item.variant_label} · {formatMoney(item.unit_price)}</small>
                  <button className="remove-link" disabled={busy} onClick={() => void removeCartItem(item)}>Xóa khỏi giỏ</button>
                </div>
                <div className="quantity-control">
                  <button aria-label={`Giảm số lượng ${item.name}`} disabled={busy || item.quantity <= 1} onClick={() => void updateCartItem(item, Math.max(1, item.quantity - 1))}>−</button>
                  <span>{item.quantity}</span>
                  <button aria-label={`Tăng số lượng ${item.name}`} disabled={busy || item.quantity >= 99} onClick={() => void updateCartItem(item, item.quantity + 1)}>+</button>
                </div>
                <strong className="line-total">{formatMoney(item.line_total)}</strong>
              </div>
            ))}
          </div>

          <aside className="summary-card">
            <h3>Tóm tắt đơn hàng</h3>
            <div>
              <span>Tạm tính</span>
              <b>{formatMoney(cart.total)}</b>
            </div>
            <div>
              <span>Phí vận chuyển</span>
              <span className="text-free">Miễn phí</span>
            </div>
            <hr/>
            <div className="summary-total">
              <span>Tổng cộng</span>
              <b>{formatMoney(cart.total)}</b>
            </div>
            <button className="button button-dark full-button" disabled={busy || loading} onClick={() => setPage('checkout')}>
              Tiến hành đặt hàng <Icon name="arrow" size={17}/>
            </button>
            <p className="summary-note">Đơn hàng được lưu nháp và kiểm tra tồn kho tại thời điểm xác nhận.</p>
          </aside>
        </div>
      ) : (
        <div className="empty-state">
          <span className="empty-icon">🛍️</span>
          <h3>Giỏ hàng đang trống</h3>
          <p>Khám phá các sản phẩm trong bộ sưu tập mới và thêm vào giỏ nhé.</p>
          <button className="button button-dark" onClick={() => setPage('shop')}>Đi xem sản phẩm <Icon name="arrow" size={16}/></button>
        </div>
      )}
    </main>}

    {page === 'checkout' && <main className="inner-page wrap">
      <button className="back-link" onClick={() => setPage('cart')}><Icon name="back" size={16}/> Quay lại giỏ hàng</button>
      <div className="inner-heading">
        <span className="eyebrow">CHECKOUT</span>
        <h1>Thông tin giao nhận</h1>
      </div>

      <div className="checkout-layout">
        <form className="checkout-form" noValidate onSubmit={submitCheckout}>
          <h2>Địa chỉ nhận hàng</h2>

          <label>
            Họ và tên
            <input
              aria-label="Họ và tên"
              autoComplete="name"
              aria-invalid={!!fieldErrors.recipient_name}
              aria-describedby="recipient-error"
              required
              maxLength={100}
              value={shipping.recipient_name}
              onChange={e => {
                setShipping({ ...shipping, recipient_name: e.target.value })
                if (fieldErrors.recipient_name) setFieldErrors(prev => ({ ...prev, recipient_name: '' }))
              }}
              placeholder="Ví dụ: Nguyễn Văn A"
            />
            {fieldErrors.recipient_name && <small id="recipient-error" role="alert" className="inline-error">{fieldErrors.recipient_name}</small>}
          </label>

          <label>
            Số điện thoại
            <input
              aria-label="Số điện thoại"
              type="tel"
              autoComplete="tel"
              aria-invalid={!!fieldErrors.phone}
              aria-describedby="phone-error"
              required
              value={shipping.phone}
              onChange={e => {
                setShipping({ ...shipping, phone: e.target.value })
                if (fieldErrors.phone) setFieldErrors(prev => ({ ...prev, phone: '' }))
              }}
              placeholder="Ví dụ: 0912345678"
            />
            {fieldErrors.phone && <small id="phone-error" role="alert" className="inline-error">{fieldErrors.phone}</small>}
          </label>

          <label>
            Địa chỉ giao hàng
            <textarea
              aria-label="Địa chỉ giao hàng"
              autoComplete="street-address"
              aria-invalid={!!fieldErrors.address}
              aria-describedby="address-error"
              required
              maxLength={200}
              rows={3}
              value={shipping.address}
              onChange={e => {
                setShipping({ ...shipping, address: e.target.value })
                if (fieldErrors.address) setFieldErrors(prev => ({ ...prev, address: '' }))
              }}
              placeholder="Số nhà, tên đường, phường/xã, quận/huyện, tỉnh/thành phố"
            />
            {fieldErrors.address && <small id="address-error" role="alert" className="inline-error">{fieldErrors.address}</small>}
          </label>

          {checkoutError && <div className="inline-error" role="alert">{checkoutError}</div>}

          <button className="button button-dark full-button" disabled={busy || loading || !cart?.items?.length}>
            {busy ? 'Đang gửi...' : 'Gửi yêu cầu đặt hàng'} <Icon name="arrow" size={17}/>
          </button>
          <p className="form-note">Đơn hàng sẽ được tạo ở trạng thái Chờ xác nhận. Bạn có thể kiểm tra và chỉnh sửa phân loại hoặc số lượng trong mục Đơn hàng.</p>
        </form>

        <aside className="summary-card">
          <h3>Đơn hàng của bạn</h3>
          {cart?.items?.map(i => (
            <div className="checkout-item" key={i.item_id}>
              <span>{i.name} <small>× {i.quantity} ({i.variant_label})</small></span>
              <b>{formatMoney(i.line_total)}</b>
            </div>
          ))}
          <hr/>
          <div className="summary-total">
            <span>Tổng cộng</span>
            <b>{formatMoney(cart?.total || 0)}</b>
          </div>
        </aside>
      </div>
    </main>}

    {page === 'orders' && <main className="inner-page wrap">
      <div className="orders-toolbar">
        <button className="back-link" onClick={() => setPage('shop')}><Icon name="back" size={16}/> Quay lại cửa hàng</button>
      </div>
      <div className="inner-heading">
        <span className="eyebrow">TRACKING</span>
        <h1>Quản lý đơn hàng</h1>
      </div>

      {(orders.length || activeOrder) ? (
        <div className="orders-layout">
          <div className="order-selector">
            {[...(activeOrder && !orders.some(o => o.order_id === activeOrder.order_id) ? [activeOrder] : []), ...orders].map(o => (
              <button
                key={o.order_id}
                className={activeOrder?.order_id === o.order_id ? 'order-selected' : ''}
                onClick={() => { setActiveOrder(o); setOrderDrafts({}) }}
              >
                <Icon name="order"/>
                <span>
                  <b>{o.order_id}</b>
                  <small className={`order-status-tag status-${o.status}`}>{statusLabels[o.status] || o.status}</small>
                </span>
                <Icon name="arrow" size={16}/>
              </button>
            ))}
          </div>

          {activeOrder && (
            <div className="order-detail">
              <div className="order-detail-head">
                <div>
                  <span className="eyebrow">CHI TIẾT ĐƠN HÀNG</span>
                  <h2>{activeOrder.order_id}</h2>
                </div>
                <span className={`status-pill status-${activeOrder.status}`}>
                  {statusLabels[activeOrder.status] || activeOrder.status}
                </span>
              </div>

              <div className="order-items-list">
                {activeOrder.items.map(i => {
                  const draft = orderDrafts[i.item_id] || { sku: i.sku, quantity: i.quantity }
                  return (
                    <div className="order-line order-edit-line" key={i.item_id}>
                      <div className="order-edit-fields">
                        <span>{i.name} <small className="order-item-variant">{i.variant_label}</small></span>
                        {activeOrder.editable && (
                          <div className="order-edit-controls">
                            <select
                              aria-label="Phân loại"
                              value={draft.sku}
                              onChange={e => setOrderDrafts(current => ({ ...current, [i.item_id]: { ...draft, sku: e.target.value } }))}
                            >
                              {(i.available_variants || [{ sku: i.sku, label: i.variant_label }]).map(v => (
                                <option key={v.sku} value={v.sku}>{v.label}</option>
                              ))}
                            </select>
                            <input
                              aria-label="Số lượng"
                              type="number"
                              min="1"
                              max="99"
                              value={draft.quantity}
                              onChange={e => setOrderDrafts(current => ({ ...current, [i.item_id]: { ...draft, quantity: Math.max(1, Number(e.target.value)) } }))}
                            />
                            <button className="save-edit" disabled={busy} onClick={() => void saveOrderItem(i)}>Lưu</button>
                          </div>
                        )}
                      </div>
                      <b>{formatMoney(i.line_total)}</b>
                    </div>
                  )
                })}
              </div>

              <div className="summary-total">
                <span>Tổng cộng tiền hàng</span>
                <b>{formatMoney(activeOrder.total)}</b>
              </div>

              {activeOrder.shipping && (
                <div className="shipping-details">
                  <b>Thông tin giao nhận</b>
                  <span>{activeOrder.shipping.recipient_name} · {activeOrder.shipping.phone}</span>
                  <small>{activeOrder.shipping.address}</small>
                </div>
              )}

              <button className="text-link reload-orders-btn" onClick={() => void openOrders()}>Tải lại đơn hàng ↻</button>
            </div>
          )}
        </div>
      ) : (
        <div className="empty-state">
          <span className="empty-icon">📦</span>
          <h3>Bạn chưa có đơn hàng nào</h3>
          <p>Các đơn hàng bạn tạo sẽ hiển thị tại đây để bạn tiện theo dõi và chỉnh sửa.</p>
          <button className="button button-dark" onClick={() => setPage('shop')}>Khám phá cửa hàng</button>
        </div>
      )}
    </main>}

    {page === 'admin' && <AdminPage/>}

    <footer className="footer">
      <div className="wrap footer-inner">
        <button className="brand footer-brand" onClick={() => setPage('shop')}>
          <span className="brand-mark">l.</span>
          <span className="brand-name">live<span className="brand-light">commerce</span></span>
        </button>
        <span className="footer-tagline">Nền tảng mua sắm tích hợp Trợ lý AI &amp; Tra cứu tài liệu chính sách.</span>
        <div className="footer-links">
          <button className="text-link" onClick={() => setPage('admin')}>Trang quản trị (Demo)</button>
        </div>
        <span className="footer-copy">© {new Date().getFullYear()} Live Commerce</span>
      </div>
    </footer>

    <button className="assistant-fab" onClick={() => setChatOpen(true)} aria-label="Mở trợ lý mua sắm AI">
      <Icon name="spark"/>
      <span>Trợ lý mua sắm</span>
      <span className="fab-dot"/>
    </button>

    {selected && (
      <Dialog label={selected.name} backdrop="overlay" className="product-modal" onClose={() => setSelected(null)}>
        <button className="modal-close" onClick={() => setSelected(null)} aria-label="Đóng"><Icon name="close"/></button>
        <div className="modal-photo">
          <img src={imageFor(selected)} alt={selected.name}/>
          <span className="image-badge">{selected.category.toUpperCase()}</span>
        </div>
        <div className="modal-details">
          <span className="eyebrow">{selected.category} · EVERYDAY ESSENTIALS</span>
          <h2>{selected.name}</h2>
          <p>{selected.description}</p>
          <strong className="modal-price">{formatMoney(variant?.unit_price || selected.price_from)}</strong>

          <label className="variant-label">Chọn phân loại (Màu / Size)</label>
          <div className="variant-list">
            {selected.variants.map(v => (
              <button
                key={v.sku}
                className={`${variant?.sku === v.sku ? 'variant-selected' : ''} ${v.stock === 0 ? 'variant-sold' : ''}`}
                disabled={v.stock === 0}
                onClick={() => { setVariant(v); setQuantity(1) }}
              >
                {v.label}{v.stock === 0 && ' · Hết hàng'}
              </button>
            ))}
          </div>

          {variant && (
            <div className={`stock-note ${variant.stock > 0 ? 'stock-in' : 'stock-out-note'}`}>
              {variant.stock > 0 ? `● Còn lại ${variant.stock} sản phẩm trong kho` : '● Tạm thời hết hàng'}
            </div>
          )}

          <div className="add-row">
            <div className="quantity-control">
              <button onClick={() => setQuantity(Math.max(1, quantity - 1))}>−</button>
              <span>{quantity}</span>
              <button onClick={() => setQuantity(Math.min(99, variant?.stock || 99, quantity + 1))}>+</button>
            </div>
            <button className="button button-dark add-to-cart-btn" disabled={!variant?.stock || busy} onClick={() => void addToCart()}>
              {busy ? 'Đang thêm...' : 'Thêm vào giỏ'} <Icon name="bag" size={17}/>
            </button>
          </div>
          <div className="modal-promise">Ảnh minh họa · Giá và tồn kho được kiểm tra trực tiếp từ hệ thống.</div>
        </div>
      </Dialog>
    )}

    {chatOpen && (
      <Dialog label="Trợ lý mua sắm" backdrop="chat-backdrop" className="chat-panel" onClose={() => setChatOpen(false)}>
        <div className="chat-head">
          <div className="assistant-avatar"><Icon name="spark"/></div>
          <div className="chat-head-info">
            <b>Trợ lý mua sắm AI</b>
            <small><span className="online-dot"/> Hỏi đáp sản phẩm, tra cứu chính sách &amp; đặt hàng</small>
          </div>
          <button className="chat-close-btn" onClick={() => setChatOpen(false)} aria-label="Đóng chat"><Icon name="close"/></button>
        </div>

        <div className="chat-messages">
          <div className="chat-intro">
            <span className="eyebrow">LIVE COMMERCE ASSISTANT</span>
            <h3>Mình có thể giúp gì cho bạn?</h3>
            <p>Tìm sản phẩm theo nhu cầu, kiểm tra giá &amp; tồn kho, tra cứu chính sách đổi trả/bảo hành có trích dẫn, hoặc hỗ trợ đặt hàng ngay.</p>
            <div className="suggestions">
              <button type="button" onClick={() => handleSuggestionClick('Cửa hàng bán những gì?')}>Cửa hàng bán gì?</button>
              <button type="button" onClick={() => handleSuggestionClick('Cho xem giày dưới 800k còn hàng')}>Tìm giày dưới 800k</button>
              <button type="button" onClick={() => handleSuggestionClick('Đặt cho tôi balo laptop xám, 15inch')}>Đặt balo xám 15 inch</button>
              <button type="button" onClick={() => handleSuggestionClick('Balo laptop bảo hành bao lâu?')}>Bảo hành balo</button>
              <button type="button" onClick={() => handleSuggestionClick('Báo thiếu hàng sau khi nhận cần làm gì?')}>Báo thiếu hàng</button>
            </div>
          </div>

          {messages.map((m, i) => (
            <div key={i} className={`message ${m.role === 'user' ? 'message-user' : ''}`}>
              <span className="message-avatar">{m.role === 'assistant' ? 'l.' : 'bạn'}</span>
              <div className="message-bubble">
                {(m.route === 'knowledge' || m.knowledge) && (
                  <span className="route-tag">
                    {m.route === 'knowledge' ? 'Tra cứu tài liệu' : 'Tài liệu + đơn hàng'}
                  </span>
                )}
                <p>{m.text}</p>
                {m.knowledge && <KnowledgeBlock knowledge={m.knowledge} onOpenSource={setSourceId}/>}
                {m.missing_fields?.length ? (
                  <small className="missing-fields-note">
                    Cần bổ sung: {m.missing_fields.map(field => fieldLabels[field] || field).join(', ')}
                  </small>
                ) : null}
                {m.purchase && (
                  <ChatPurchaseForm
                    purchase={m.purchase}
                    missing={m.missing_fields || []}
                    busy={busy}
                    active={i === activePurchaseIndex}
                    onSubmit={submitChatText}
                  />
                )}
                {m.order && (
                  <div className="chat-order-summary">
                    <strong>Đơn {m.order.order_id} · {statusLabels[m.order.status] || m.order.status}</strong>
                    {m.order.items.map(item => (
                      <span key={item.item_id}>{item.name} · {item.variant_label} × {item.quantity}</span>
                    ))}
                    <b>Tổng tiền sản phẩm: {formatMoney(m.order.total)}</b>
                  </div>
                )}
                {m.order && (
                  <button className="message-order" onClick={() => { setActiveOrder(m.order!); setChatOpen(false); void openOrders(m.order!.order_id) }}>
                    Xem đơn {m.order.order_id} →
                  </button>
                )}
              </div>
            </div>
          ))}

          {busy && (
            <div className="chat-typing-container">
              <span className="message-avatar">l.</span>
              <div className="chat-typing-row" role="status">
                <span className="typing-dots">
                  <span></span><span></span><span></span>
                </span>
                <span className="typing-label">Đang xử lý yêu cầu...</span>
              </div>
            </div>
          )}
          <div ref={messagesEnd}/>
        </div>

        <form className="chat-compose" onSubmit={sendChat}>
          <input
            ref={chatInputRef}
            aria-label="Tin nhắn"
            maxLength={500}
            value={chatInput}
            onChange={e => setChatInput(e.target.value)}
            placeholder="Nhập câu hỏi hoặc yêu cầu đặt hàng..."
          />
          <button type="submit" disabled={busy || !chatInput.trim()} aria-label="Gửi">
            <Icon name="arrow"/>
          </button>
        </form>
        <div className="chat-footnote">Câu trả lời được hỗ trợ bởi mô hình AI &amp; cơ sở dữ liệu chính sách.</div>
      </Dialog>
    )}

    {sourceId && <SourceDialog chunkId={sourceId} onClose={() => setSourceId(null)} onOpenProduct={openProductFromSource}/>}
  </div>
}

export default App
