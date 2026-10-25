// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LoginPage } from './LoginPage';

const mocks = vi.hoisted(() => ({ enabled: true, signIn: vi.fn(), error: vi.fn() }));
vi.mock('../../../utils/runtime-config', () => ({
  get yandexAuthEnabled() { return mocks.enabled; },
}));
vi.mock('../../../utils/supabase/client', () => ({
  supabase: { auth: { signInWithOAuth: mocks.signIn } },
}));
vi.mock('../lib/referrals', () => ({
  getActiveReferralCode: () => null, buildTelegramReferralBotUrl: () => '',
}));
vi.mock('sonner', () => ({ toast: { error: mocks.error } }));

beforeEach(() => {
  mocks.enabled = true;
  mocks.signIn.mockReset().mockResolvedValue({ error: null });
  mocks.error.mockReset();
});
afterEach(cleanup);

describe('Yandex login', () => {
  it('is hidden until configured', () => {
    mocks.enabled = false;
    render(<LoginPage />);
    expect(screen.queryByRole('button', { name: 'Войти с Яндекс ID' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Продолжить через Google' })).toBeInTheDocument();
  });

  it('uses Supabase PKCE login and disables competing submissions', async () => {
    let finish!: (value: { error: null }) => void;
    mocks.signIn.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    render(<LoginPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Войти с Яндекс ID' }));
    expect(mocks.signIn).toHaveBeenCalledWith({
      provider: 'custom:yandex',
      options: { redirectTo: window.location.origin + window.location.pathname },
    });
    expect(screen.getByRole('button', { name: 'Продолжить через Google' })).toBeDisabled();
    finish({ error: null });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Войти с Яндекс ID' })).toBeEnabled());
  });

  it('shows a retryable failure', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    mocks.signIn.mockResolvedValue({ error: new Error('provider disabled') });
    render(<LoginPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Войти с Яндекс ID' }));
    await waitFor(() => expect(mocks.error).toHaveBeenCalledWith(
      'Не удалось начать вход через Яндекс ID. Попробуйте ещё раз.'
    ));
    expect(screen.getByRole('button', { name: 'Войти с Яндекс ID' })).toBeEnabled();
    vi.restoreAllMocks();
  });
});
