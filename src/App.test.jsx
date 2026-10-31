import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App.jsx';

describe('App', () => {
  it('filters products by search text', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText('Search products'), 'mug');

    expect(screen.getByRole('button', { name: 'Add Ceramic Mug' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add Steel Bottle' })).not.toBeInTheDocument();
  });

  it('shows a message when nothing matches', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText('Search products'), 'zzz');

    expect(screen.getByText('No products match your search.')).toBeInTheDocument();
  });

  it('adds to the cart, applies a coupon and removes the item', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', { name: 'Add Ceramic Mug' }));
    await user.click(screen.getByRole('button', { name: 'Add Ceramic Mug' }));
    await user.type(screen.getByLabelText('Coupon code'), 'SAVE10');

    const cart = screen.getByRole('complementary');
    expect(within(cart).getByText('Ceramic Mug x 2')).toBeInTheDocument();
    expect(within(cart).getByText('$21.60')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Remove Ceramic Mug' }));

    expect(screen.getByText('Your cart is empty.')).toBeInTheDocument();
  });
});
