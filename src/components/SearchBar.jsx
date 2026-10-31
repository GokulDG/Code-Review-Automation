export default function SearchBar({ value, onChange }) {
  return (
    <label className="search">
      Search products
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
