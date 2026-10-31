import { calculateTotals, formatPrice } from './pricing.js';

const items = [
  { id: 'mug', priceCents: 1200, quantity: 2 },
  { id: 'tote', priceCents: 1500, quantity: 1 },
];

describe('formatPrice', () => {
  it('formats cents as dollars', () => {
    expect(formatPrice(850)).toBe('$8.50');
  });
});

describe('calculateTotals', () => {
  it('sums price times quantity', () => {
    expect(calculateTotals(items)).toEqual({
      subtotalCents: 3900,
      discountCents: 0,
      totalCents: 3900,
    });
  });

  it('applies a coupon regardless of case and whitespace', () => {
    expect(calculateTotals(items, ' save10 ').discountCents).toBe(390);
  });

  it('ignores unknown coupons', () => {
    expect(calculateTotals(items, 'FREE').totalCents).toBe(3900);
  });

  it('does not treat inherited object keys as coupons', () => {
    expect(calculateTotals(items, 'constructor').discountCents).toBe(0);
  });
});
