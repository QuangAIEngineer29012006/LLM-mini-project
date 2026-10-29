import { FormEvent, useState } from 'react'

export type PurchaseItem = { sku: string; name: string; variant_label: string; unit_price: number; stock: number; quantity: number | null }
export type Purchase = { items: PurchaseItem[] }
const money = (value: number) => new Intl.NumberFormat('vi-VN').format(value) + '₫'

export function ChatPurchaseForm({ purchase, missing, busy, active, onSubmit }: {
  purchase: Purchase; missing: string[]; busy: boolean; active: boolean; onSubmit: (text: string) => Promise<void>
}) {
  const [quantities, setQuantities] = useState(() => purchase.items.map(item => item.quantity ?? 1))
  const [delivery, setDelivery] = useState({ recipient_name: '', phone: '', address: '' })
  const [error, setError] = useState('')
  const labels = { recipient_name: 'Tên người nhận', phone: 'Số điện thoại', address: 'Địa chỉ giao hàng' }
  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (busy || !active) return
    setError('')
    if (quantities.some((qty, i) => !Number.isInteger(qty) || qty < 1 || qty > Math.min(99, purchase.items[i].stock))) {
      setError('Số lượng phải là số nguyên, từ 1 đến số lượng còn hàng.'); return
    }
    for (const field of Object.keys(labels) as (keyof typeof labels)[]) {
      if (!missing.includes(field)) continue
      const value = delivery[field].trim()
      if ((field === 'recipient_name' && value.length < 2) || (field === 'phone' && !/^(0\d{9}|\+84\d{9})$/.test(value.replace(/[\s()-]/g, ''))) || (field === 'address' && value.length < 10)) {
        setError(`Vui lòng kiểm tra ${labels[field].toLocaleLowerCase('vi')}.`); return
      }
    }
    const parts = ['Chốt ' + purchase.items.map((item, index) => `${quantities[index]} ${item.sku}`).join(' và ')]
    if (missing.includes('recipient_name')) parts.push('Tên ' + delivery.recipient_name.trim())
    if (missing.includes('phone')) parts.push('SĐT ' + delivery.phone.replace(/[\s()-]/g, ''))
    if (missing.includes('address')) parts.push('giao về ' + delivery.address.trim())
    const text = parts.join(', ')
    if (text.length > 500) { setError('Thông tin quá dài. Bạn có thể gửi từng phần trong ô chat.'); return }
    await onSubmit(text)
  }
  return <div className="chat-purchase">
    <h4>Sản phẩm đã chọn</h4>
    {purchase.items.map((item, index) => <div className="chat-purchase-item" key={`${item.sku}-${index}`}>
      <strong>{item.name}</strong><span>{item.variant_label}</span>
      <span>{money(item.unit_price)} / sản phẩm · Còn {item.stock}</span>
    </div>)}
    {active && <form aria-label="Thông tin đặt hàng qua bot" noValidate onSubmit={submit}>
      {purchase.items.map((item, index) => <label key={`${item.sku}-${index}`}>Số lượng {item.name}
        <input aria-label={`Số lượng ${item.name}`} type="number" min="1" max={Math.min(99, item.stock)} step="1" required disabled={busy}
          value={quantities[index]} onChange={event => setQuantities(current => current.map((qty, i) => i === index ? Number(event.target.value) : qty))}/>
      </label>)}
      {(Object.keys(labels) as (keyof typeof labels)[]).filter(field => missing.includes(field)).map(field => <label key={field}>{labels[field]}
        {field === 'address' ? <textarea aria-label={labels[field]} autoComplete="street-address" rows={2} maxLength={200} required disabled={busy}
          value={delivery[field]} onChange={event => setDelivery({ ...delivery, [field]: event.target.value })}/>
          : <input aria-label={labels[field]} type={field === 'phone' ? 'tel' : 'text'} autoComplete={field === 'phone' ? 'tel' : 'name'}
            maxLength={field === 'phone' ? 20 : 100} required disabled={busy} value={delivery[field]} onChange={event => setDelivery({ ...delivery, [field]: event.target.value })}/>}
      </label>)}
      <div className="chat-purchase-total">Tổng tiền sản phẩm <b>{money(purchase.items.reduce((total, item, index) => total + item.unit_price * quantities[index], 0))}</b></div>
      {error && <p className="inline-error" role="alert">{error}</p>}
      <button className="button button-dark" type="submit" disabled={busy}>{busy ? 'Đang gửi...' : 'Gửi thông tin đặt hàng'}</button>
      <small>Bạn cũng có thể nhắn thông tin trong chat. Bot sẽ tạo đơn chờ cửa hàng xác nhận.</small>
    </form>}
  </div>
}
