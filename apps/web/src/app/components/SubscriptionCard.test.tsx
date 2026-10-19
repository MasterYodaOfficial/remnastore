// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SubscriptionCard } from './SubscriptionCard';

const day = 86_400_000;
const start = Date.parse('2026-01-01T12:00:00Z');
const end = start + 365 * day;
const callbacks = {
  onActivateTrial: vi.fn(), onRenew: vi.fn(), onBuy: vi.fn(), onOpenAccess: vi.fn(),
};
const subscription = {
  isActive: true, hasTrial: false, hasUsedTrial: true,
  periodStartedAt: new Date(start).toISOString(), expiresAt: new Date(end).toISOString(),
};

afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('subscription remaining time', () => {
  it('decreases across days while the cabinet stays open', () => {
    vi.useFakeTimers();
    vi.setSystemTime(start + 100 * day);
    render(<SubscriptionCard subscription={subscription} {...callbacks} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '73');
    expect(screen.getByText('265 из 365 дн.')).toBeInTheDocument();
    act(() => { vi.setSystemTime(start + 101 * day); window.dispatchEvent(new Event('focus')); });
    expect(screen.getByText('264 из 365 дн.')).toBeInTheDocument();
    act(() => { vi.setSystemTime(start + 200 * day); vi.advanceTimersByTime(60_000); });
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45');
  });

  it('extends the same period on renewal and resets on a new period', () => {
    vi.useFakeTimers();
    vi.setSystemTime(start + 100 * day);
    const { rerender } = render(<SubscriptionCard subscription={subscription} {...callbacks} />);
    rerender(<SubscriptionCard subscription={{ ...subscription, expiresAt: new Date(end + 30 * day).toISOString() }} {...callbacks} />);
    expect(screen.getByText('295 из 395 дн.')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '75');
    rerender(<SubscriptionCard subscription={{ ...subscription, periodStartedAt: new Date(start + 100 * day).toISOString(), expiresAt: new Date(start + 130 * day).toISOString() }} {...callbacks} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
  });

  it('shows the expiration date without a false percentage for legacy subscriptions', () => {
    vi.useFakeTimers();
    vi.setSystemTime(start + 100 * day);
    render(<SubscriptionCard subscription={{ ...subscription, periodStartedAt: null }} {...callbacks} />);
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(screen.getByText(/^Действует до /)).toBeInTheDocument();
    expect(screen.getByText('265')).toBeInTheDocument();
  });

  it('warns at seven and three days and never produces a negative percentage', () => {
    vi.useFakeTimers();
    vi.setSystemTime(end - 7 * day);
    render(<SubscriptionCard subscription={subscription} {...callbacks} />);
    expect(screen.getByText('Подписка скоро закончится')).toBeInTheDocument();
    act(() => { vi.setSystemTime(end - 3 * day); window.dispatchEvent(new Event('focus')); });
    expect(screen.getByText('Пора продлить')).toBeInTheDocument();
    act(() => { vi.setSystemTime(end + day); window.dispatchEvent(new Event('focus')); });
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
  });

  it('supports short trial periods', () => {
    vi.useFakeTimers();
    vi.setSystemTime(start + day);
    render(<SubscriptionCard subscription={{ ...subscription, isTrial: true, expiresAt: new Date(start + 3 * day).toISOString() }} {...callbacks} />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '67');
    expect(screen.getByText('2 из 3 дн.')).toBeInTheDocument();
  });
});
