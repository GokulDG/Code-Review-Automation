import { useMemo, useState } from 'react';
import Cart from './components/Cart.jsx';
import ProductList from './components/ProductList.jsx';
import SearchBar from './components/SearchBar.jsx';
import { products } from './lib/products.js';
import { addItem, removeItem } from './lib/cart.js';

export default function App() {
  const [query, setQuery] = useState('');
  const [items, setItems] = useState([]);

  const visibleProducts = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return products.filter((product) => product.name.toLowerCase().includes(needle));
  }, [query]);

  return (
    <main className="shop">
      <h1>Sample Shop</h1>
      <SearchBar value={query} onChange={setQuery} />
      <div className="layout">
        <ProductList
          products={visibleProducts}
          onAdd={(product) => setItems((current) => addItem(current, product))}
        />
        <Cart
          items={items}
          onRemove={(id) => setItems((current) => removeItem(current, id))}
        />
      </div>
    </main>
  );
}
