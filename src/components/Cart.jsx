import { useState } from 'react';
import { calculateTotals, formatPrice } from '../lib/pricing.js';

export default function Cart({ items, onRemove }) {
  const [couponCode, setCouponCode] = useState('');
  const totals = calculateTotals(items, couponCode);

  if (items.length === 0) {
    return (
      <aside className="cart">
        <h2>Cart</h2>
        <p className="empty">Your cart is empty.</p>
      </aside>
    );
  }

  return (
    <aside className="cart">
      <h2>Cart</h2>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            {item.name} x {item.quantity}
            <button type="button" onClick={() => onRemove(item.id)}>
              Remove {item.name}
            </button>
          </li>
        ))}
      </ul>
      <label>
        Coupon code
        <input value={couponCode} onChange={(event) => setCouponCode(event.target.value)} />
      </label>
      <dl>
        <dt>Subtotal</dt>
        <dd>{formatPrice(totals.subtotalCents)}</dd>
        <dt>Discount</dt>
        <dd>{formatPrice(totals.discountCents)}</dd>
        <dt>Total</dt>
        <dd>{formatPrice(totals.totalCents)}</dd>
      </dl>
    </aside>
  );
}
