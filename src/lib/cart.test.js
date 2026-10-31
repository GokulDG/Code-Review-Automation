import { addItem, removeItem } from './cart.js';

const mug = { id: 'mug', name: 'Ceramic Mug', priceCents: 1200 };

describe('cart', () => {
  it('adds a new product with quantity 1', () => {
    expect(addItem([], mug)).toEqual([{ ...mug, quantity: 1 }]);
  });

  it('increments the quantity of a product already in the cart', () => {
    const items = addItem(addItem([], mug), mug);
    expect(items).toEqual([{ ...mug, quantity: 2 }]);
  });

  it('removes a product by id', () => {
    expect(removeItem([{ ...mug, quantity: 1 }], 'mug')).toEqual([]);
  });
});
