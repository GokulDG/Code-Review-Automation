export function addItem(items, product) {
  const existing = items.find((item) => item.id === product.id);
  if (!existing) {
    return [...items, { ...product, quantity: 1 }];
  }
  return items.map((item) =>
    item.id === product.id ? { ...item, quantity: item.quantity + 1 } : item,
  );
}

export function removeItem(items, id) {
  return items.filter((item) => item.id !== id);
}
