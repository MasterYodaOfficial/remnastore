// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LoginPage } from './LoginPage';

const mocks = vi.hoisted(() => ({ enabled: true, vkEnabled: false, signIn: vi.fn(), error: vi.fn(), success: vi.fn(), recoverySession: vi.fn(), updateUser: vi.fn() }));
vi.mock('../../../utils/runtime-config', () => ({
  get yandexAuthEnabled() { return mocks.enabled; },
  get vkAuthEnabled() { return mocks.vkEnabled; },
}));
vi.mock('../../../utils/supabase/client', () => ({
  supabase: { auth: { signInWithOAuth: mocks.signIn, updateUser: mocks.updateUser } },
  getPasswordRecoverySession: mocks.recoverySession,
}));
vi.mock('../lib/referrals', () => ({
  getActiveReferralCode: () => null, buildTelegramReferralBotUrl: () => '',
}));
vi.mock('sonner', () => ({ toast: { error: mocks.error, success: mocks.success } }));

beforeEach(() => {
  mocks.enabled = true;
  mocks.vkEnabled = false;
  mocks.signIn.mockReset().mockResolvedValue({ error: null });
  mocks.error.mockReset();
  mocks.success.mockReset();
  mocks.recoverySession.mockReset().mockResolvedValue({ access_token: 'recovery-token', user: { id: 'user' } });
  mocks.updateUser.mockReset().mockResolvedValue({ error: null });
});
afterEach(cleanup);

describe('VK login', () => {
  it('is hidden until configured', () => {
    render(<LoginPage />);
    expect(screen.queryByRole('button', { name: 'Войти с VK ID' })).not.toBeInTheDocument();
  });

  it('uses the custom provider and blocks competing login methods', async () => {
    mocks.vkEnabled = true;
    let finish!: (value: { error: null }) => void;
    mocks.signIn.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    render(<LoginPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Войти с VK ID' }));
    expect(mocks.signIn).toHaveBeenCalledWith({
      provider: 'custom:vk', options: { redirectTo: window.location.origin + window.location.pathname },
    });
    expect(screen.getByRole('button', { name: 'Продолжить через Google' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Войти с Яндекс ID' })).toBeDisabled();
    finish({ error: null });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Войти с VK ID' })).toBeEnabled());
  });

  it('offers another attempt after a provider failure', async () => {
    mocks.vkEnabled = true;
    const logging = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      mocks.signIn.mockResolvedValue({ error: new Error('VK unavailable') });
      render(<LoginPage />);
      fireEvent.click(screen.getByRole('button', { name: 'Войти с VK ID' }));
      await waitFor(() => expect(mocks.error).toHaveBeenCalledWith(
        'Не удалось начать вход через VK ID. Попробуйте ещё раз.'
      ));
      expect(screen.getByRole('button', { name: 'Войти с VK ID' })).toBeEnabled();
    } finally {
      logging.mockRestore();
    }
  });
});

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

describe('password recovery', () => {
  const fill = (password: string, confirmation: string) => {
    fireEvent.change(screen.getByPlaceholderText('Минимум 8 символов'), { target: { value: password } });
    fireEvent.change(screen.getByPlaceholderText('Повторите новый пароль'), { target: { value: confirmation } });
  };

  it('validates both password fields before trying to update', () => {
    render(<LoginPage view="recovery" />);
    fill('short', 'short');
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить новый пароль' }));
    expect(mocks.updateUser).not.toHaveBeenCalled();
    fill('long-enough-password', 'another-password');
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить новый пароль' }));
    expect(mocks.updateUser).not.toHaveBeenCalled();
  });

  it('does not update an ordinary session when recovery proof is missing', async () => {
    const expired = vi.fn();
    const logging = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      mocks.recoverySession.mockResolvedValue(null);
      render(<LoginPage view="recovery" onRecoveryExpired={expired} />);
      fill('new-valid-password', 'new-valid-password');
      fireEvent.click(screen.getByRole('button', { name: 'Сохранить новый пароль' }));
      await waitFor(() => expect(expired).toHaveBeenCalledOnce());
      expect(mocks.updateUser).not.toHaveBeenCalled();
    } finally { logging.mockRestore(); }
  });

  it('keeps the form after a save failure and completes only after success', async () => {
    const completed = vi.fn();
    const logging = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      mocks.updateUser.mockResolvedValueOnce({ error: Object.assign(new Error('Try again'), { status: 503 }) });
      render(<LoginPage view="recovery" onRecoveryComplete={completed} />);
      fill('new-valid-password', 'new-valid-password');
      fireEvent.click(screen.getByRole('button', { name: 'Сохранить новый пароль' }));
      await waitFor(() => expect(mocks.error).toHaveBeenCalledWith('Try again'));
      expect(completed).not.toHaveBeenCalled();
      expect(screen.getByRole('button', { name: 'Сохранить новый пароль' })).toBeEnabled();
      fireEvent.click(screen.getByRole('button', { name: 'Сохранить новый пароль' }));
      await waitFor(() => expect(completed).toHaveBeenCalledOnce());
      expect(mocks.updateUser).toHaveBeenLastCalledWith({ password: 'new-valid-password' });
    } finally { logging.mockRestore(); }
  });
});
