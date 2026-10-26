// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { t } from '../../lib/i18n';
import { PendingPaymentsPage, type PendingPaymentView } from './PendingPaymentsPage';

afterEach(cleanup);

const payment: PendingPaymentView = {
  provider: 'yookassa', kind: 'plan', amount: 560, currency: 'RUB',
  providerPaymentId: 'one-payment', status: 'pending', expiresAt: null,
  createdAt: '2026-10-26T15:00:00Z',
  confirmationUrl: 'https://shop.test/checkout?payment_id=one-payment#checkout_token=ticket',
};

it('opens each mode of the same existing payment without creating another payment', () => {
  const item = { ...payment, sbpConfirmationUrl: 'https://shop.test/checkout?payment_id=one-payment&mode=sbp#checkout_token=ticket' };
  const onResume = vi.fn();
  render(<PendingPaymentsPage items={[item]} isLoading={false} onBack={vi.fn()} onResume={onResume} />);
  fireEvent.click(screen.getByRole('button', { name: 'Картой и другими способами' }));
  expect(onResume).toHaveBeenLastCalledWith(item);
  fireEvent.click(screen.getByRole('button', { name: 'СБП' }));
  expect(onResume).toHaveBeenLastCalledWith({ ...item, confirmationUrl: item.sbpConfirmationUrl });
  expect(onResume).toHaveBeenCalledTimes(2);
});

it('keeps the original continuation button for old redirect payments', () => {
  const onResume = vi.fn();
  render(<PendingPaymentsPage items={[payment]} isLoading={false} onBack={vi.fn()} onResume={onResume} />);
  expect(screen.queryByRole('button', { name: 'СБП' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: t('web.pendingPayments.resume') }));
  expect(onResume).toHaveBeenCalledWith(payment);
});
