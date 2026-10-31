const COUPONS = {
  SAVE10: 0.1,
  SAVE25: 0.25,
};

export function formatPrice(cents) {
  return `$${(cents / 100).toFixed(2)}`;
}

export function calculateTotals(items, couponCode = '') {
  const subtotalCents = items.reduce(
    (sum, item) => sum + item.priceCents * item.quantity,
    0,
  );
  const rate = COUPONS[couponCode.trim().toUpperCase()] ?? 0;
  const discountCents = Math.round(subtotalCents * rate);
  return {
    subtotalCents,
    discountCents,
    totalCents: subtotalCents - discountCents,
  };
}
