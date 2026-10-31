import { formatPrice } from '../lib/pricing.js';

export default function ProductList({ products, onAdd }) {
  if (products.length === 0) {
    return <p className="empty">No products match your search.</p>;
  }

  return (
    <ul className="products">
      {products.map((product) => (
        <li key={product.id} className="product">
          <span>{product.name}</span>
          <span>{formatPrice(product.priceCents)}</span>
          <button type="button" onClick={() => onAdd(product)}>
            Add {product.name}
          </button>
        </li>
      ))}
    </ul>
  );
}
