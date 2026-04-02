import React, { FormEvent, useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Loader2, Lock, Mail } from 'lucide-react';
import { toast } from 'sonner';
import { supabase } from '../../../utils/supabase/client';
import { getActiveReferralCode, buildTelegramReferralBotUrl } from '../lib/referrals';
import { t } from '../../lib/i18n';
import { AppLogo } from './AppLogo';

type LoginFormMode = 'signin' | 'signup' | 'forgot';
type OAuthProviderState = 'google';
type SupabaseOAuthProvider = Parameters<typeof supabase.auth.signInWithOAuth>[0]['provider'];

interface LoginPageProps {
  view?: 'default' | 'recovery' | 'recovery-expired';
  onRecoveryComplete?: () => Promise<void> | void;
  onRecoveryCancel?: () => Promise<void> | void;
  onAuthViewReset?: () => Promise<void> | void;
}

function buildAuthRedirectUrl(extraParams: Record<string, string> = {}): string {
  const url = new URL(window.location.origin + window.location.pathname);

  for (const [key, value] of Object.entries(extraParams)) {
    url.searchParams.set(key, value);
  }

  return url.toString();
}

function TelegramIcon() {
  return (
    <svg className="h-[18px] w-[18px] shrink-0" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#229ED9"
        d="M21.9 4.6c.3-.9-.6-1.7-1.5-1.4L3.5 9.3c-1 .3-1 1.7 0 2l4 1.2 1.5 4.8c.3 1 .1 1.1.5 1.1.4 0 .6-.2.9-.5l2.3-2.2 4.4 3.2c.8.6 1.9.2 2.1-.8L21.9 4.6zm-3 1.8-7.7 6.9a.9.9 0 0 0-.3.5l-.6 2.8-1-3.1a.9.9 0 0 0-.6-.6l-3.1-.9 13.3-5.6z"
      />
    </svg>
  );
}

function loginT(
  key: string,
  params: Record<string, string | number | boolean | null | undefined> = {}
) {
  return t(`web.login.${key}`, params);
}

export function LoginPage({
  view = 'default',
  onRecoveryComplete,
  onRecoveryCancel,
  onAuthViewReset,
}: LoginPageProps) {
  const [formMode, setFormMode] = useState<LoginFormMode>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeProvider, setActiveProvider] = useState<OAuthProviderState | 'email' | 'recovery' | null>(
    null
  );
  const telegramBotUrl = useMemo(
    () => buildTelegramReferralBotUrl(getActiveReferralCode()),
    []
  );

  useEffect(() => {
    if (view === 'recovery') {
      setPassword('');
      setConfirmPassword('');
      return;
    }

    if (view === 'recovery-expired') {
      setFormMode('forgot');
      setPassword('');
      setConfirmPassword('');
      return;
    }

    setFormMode('signin');
  }, [view]);

  const requestPasswordReset = async (normalizedEmail: string) => {
    const { error } = await supabase.auth.resetPasswordForEmail(normalizedEmail, {
      redirectTo: buildAuthRedirectUrl({ auth_action: 'reset-password' }),
    });

    if (error) {
      throw error;
    }
  };

  const startOAuthLogin = async ({
    provider,
    state,
    errorToastKey,
    errorLogLabel,
  }: {
    provider: SupabaseOAuthProvider;
    state: OAuthProviderState;
    errorToastKey: string;
    errorLogLabel: string;
  }) => {
    try {
      setActiveProvider(state);
      const { error } = await supabase.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo: buildAuthRedirectUrl(),
        },
      });

      if (error) {
        throw error;
      }
    } catch (err) {
      console.error(`${errorLogLabel} login error:`, err);
      toast.error(loginT(errorToastKey));
    } finally {
      setActiveProvider(null);
    }
  };

  const handleGoogleLogin = async () =>
    startOAuthLogin({
      provider: 'google',
      state: 'google',
      errorToastKey: 'toasts.googleStartError',
      errorLogLabel: 'Google',
    });

  const handleEmailSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail) {
      toast.error(loginT('toasts.emailRequired'));
      return;
    }

    if (formMode === 'forgot') {
      setIsSubmitting(true);
      setActiveProvider('email');

      try {
        await requestPasswordReset(normalizedEmail);

        toast.success(loginT('toasts.resetSent'));
        setFormMode('signin');
        setPassword('');
        setConfirmPassword('');
      } catch (err) {
        const message =
          err instanceof Error && err.message ? err.message : loginT('toasts.resetSendError');
        console.error('Password reset request error:', err);
        toast.error(message);
      } finally {
        setIsSubmitting(false);
        setActiveProvider(null);
      }

      return;
    }

    if (!password) {
      toast.error(loginT('toasts.passwordRequired'));
      return;
    }

    if (formMode === 'signup') {
      if (password.length < 8) {
        toast.error(loginT('toasts.passwordTooShort'));
        return;
      }

      if (password !== confirmPassword) {
        toast.error(loginT('toasts.passwordsMismatch'));
        return;
      }
    }

    setIsSubmitting(true);
    setActiveProvider('email');

    try {
      if (formMode === 'signin') {
        const { error } = await supabase.auth.signInWithPassword({
          email: normalizedEmail,
          password,
        });

        if (error) {
          throw error;
        }

        toast.success(loginT('toasts.signInSuccess'));
        return;
      }

      const { data, error } = await supabase.auth.signUp({
        email: normalizedEmail,
        password,
        options: {
          emailRedirectTo: buildAuthRedirectUrl(),
        },
      });

      if (error) {
        throw error;
      }

      if (data.session) {
        toast.success(loginT('toasts.signUpAndSignIn'));
      } else {
        toast.success(loginT('toasts.signUpConfirmEmail'));
        setFormMode('signin');
      }

      setPassword('');
      setConfirmPassword('');
    } catch (err) {
      const message =
        err instanceof Error && err.message ? err.message : loginT('toasts.authFallbackError');
      console.error('Email auth error:', err);
      toast.error(message);
    } finally {
      setIsSubmitting(false);
      setActiveProvider(null);
    }
  };

  const handleRecoverySubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!password || !confirmPassword) {
      toast.error(loginT('toasts.recoveryFieldsRequired'));
      return;
    }

    if (password.length < 8) {
      toast.error(loginT('toasts.passwordTooShort'));
      return;
    }

    if (password !== confirmPassword) {
      toast.error(loginT('toasts.passwordsMismatch'));
      return;
    }

    setIsSubmitting(true);
    setActiveProvider('recovery');

    try {
      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (!session?.access_token) {
        throw new Error(loginT('toasts.recoverySessionMissing'));
      }

      const { error } = await supabase.auth.updateUser({ password });

      if (error) {
        throw error;
      }

      toast.success(loginT('toasts.recoverySuccess'));
      setPassword('');
      setConfirmPassword('');
      await onRecoveryComplete?.();
    } catch (err) {
      const message =
        err instanceof Error && err.message ? err.message : loginT('toasts.recoveryError');
      console.error('Password recovery update error:', err);
      toast.error(message);
    } finally {
      setIsSubmitting(false);
      setActiveProvider(null);
    }
  };

  const renderDefaultForm = () => (
    <>
      <div className="space-y-3">
        <button
          onClick={handleGoogleLogin}
          disabled={isSubmitting || activeProvider === 'google'}
          className="flex w-full items-center justify-center gap-3 rounded-2xl border border-slate-200 bg-white px-5 py-4 text-sm font-semibold text-slate-800 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {activeProvider === 'google' ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : (
            <svg className="h-5 w-5" viewBox="0 0 24 24" aria-hidden="true">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
          )}
          {loginT('googleAction')}
        </button>

        <a
          href={telegramBotUrl || '#'}
          target="_blank"
          rel="noreferrer"
          aria-disabled={!telegramBotUrl}
          className={`flex w-full items-center justify-center gap-3 rounded-2xl border px-5 py-4 text-sm font-semibold transition ${
            telegramBotUrl
              ? 'border-sky-200 bg-sky-50 text-sky-900 hover:bg-sky-100'
              : 'pointer-events-none cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400'
          }`}
        >
          <TelegramIcon />
          {loginT('telegramAction')}
        </a>
      </div>

      <div className="flex items-center gap-3 text-xs font-medium uppercase tracking-[0.24em] text-slate-400">
        <span className="h-px flex-1 bg-slate-200" />
        {loginT('divider')}
        <span className="h-px flex-1 bg-slate-200" />
      </div>

      <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-2">
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => setFormMode('signin')}
            className={`rounded-xl px-4 py-3 text-sm font-semibold transition ${
              formMode === 'signin'
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            {loginT('emailSignInTab')}
          </button>
          <button
            type="button"
            onClick={() => setFormMode('signup')}
            className={`rounded-xl px-4 py-3 text-sm font-semibold transition ${
              formMode === 'signup'
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            {loginT('signUpTab')}
          </button>
        </div>
      </div>

      <form className="space-y-4" onSubmit={handleEmailSubmit}>
        <label className="block space-y-2">
          <span className="text-sm font-medium text-slate-700">{loginT('emailLabel')}</span>
          <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 focus-within:border-slate-400">
            <Mail className="h-5 w-5 text-slate-400" />
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder={loginT('emailPlaceholder')}
              autoComplete="email"
              className="w-full bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
            />
          </div>
        </label>

        {formMode !== 'forgot' && (
          <label className="block space-y-2">
            <span className="text-sm font-medium text-slate-700">{loginT('passwordLabel')}</span>
            <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 focus-within:border-slate-400">
              <Lock className="h-5 w-5 text-slate-400" />
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder={formMode === 'signup' ? loginT('passwordMinPlaceholder') : loginT('passwordPlaceholder')}
                autoComplete={formMode === 'signup' ? 'new-password' : 'current-password'}
                className="w-full bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
              />
            </div>
          </label>
        )}

        {formMode === 'signup' && (
          <label className="block space-y-2">
            <span className="text-sm font-medium text-slate-700">
              {loginT('passwordRepeatLabel')}
            </span>
            <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 focus-within:border-slate-400">
              <Lock className="h-5 w-5 text-slate-400" />
              <input
                type="password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                placeholder={loginT('passwordRepeatPlaceholder')}
                autoComplete="new-password"
                className="w-full bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
              />
            </div>
          </label>
        )}

        <button
          type="submit"
          disabled={isSubmitting || activeProvider === 'google'}
          className="flex w-full items-center justify-center gap-2 rounded-2xl bg-slate-900 px-5 py-4 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="h-5 w-5 animate-spin" />
              {loginT('submitting')}
            </>
          ) : formMode === 'signin' ? (
            loginT('submitSignIn')
          ) : formMode === 'signup' ? (
            loginT('submitSignUp')
          ) : (
            loginT('submitForgot')
          )}
        </button>

        {formMode === 'signin' ? (
          <button
            type="button"
            onClick={() => setFormMode('forgot')}
            className="w-full text-center text-sm font-medium text-slate-500 transition hover:text-slate-900"
          >
            {loginT('forgotPassword')}
          </button>
        ) : formMode === 'forgot' ? (
          <button
            type="button"
            onClick={() => setFormMode('signin')}
            className="flex w-full items-center justify-center gap-2 text-center text-sm font-medium text-slate-500 transition hover:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4" />
            {loginT('backToSignIn')}
          </button>
        ) : null}
      </form>

      <div className="space-y-2 text-center text-xs leading-5 text-slate-500">
        <p>{loginT('browserHint')}</p>
        <p>{loginT('confirmEmailHint')}</p>
      </div>
    </>
  );

  const renderRecoveryForm = () => (
    <>
      <div className="space-y-2 text-center">
        <h2 className="text-xl font-semibold text-slate-900">{loginT('recoveryTitle')}</h2>
        <p className="text-sm leading-6 text-slate-500">
          {loginT('recoverySubtitle')}
        </p>
      </div>

      <form className="space-y-4" onSubmit={handleRecoverySubmit}>
        <label className="block space-y-2">
          <span className="text-sm font-medium text-slate-700">
            {loginT('recoveryNewPasswordLabel')}
          </span>
          <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 focus-within:border-slate-400">
            <Lock className="h-5 w-5 text-slate-400" />
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={loginT('recoveryNewPasswordPlaceholder')}
              autoComplete="new-password"
              className="w-full bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
            />
          </div>
        </label>

        <label className="block space-y-2">
          <span className="text-sm font-medium text-slate-700">
            {loginT('recoveryRepeatLabel')}
          </span>
          <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 focus-within:border-slate-400">
            <Lock className="h-5 w-5 text-slate-400" />
            <input
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder={loginT('recoveryRepeatPlaceholder')}
              autoComplete="new-password"
              className="w-full bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
            />
          </div>
        </label>

        <button
          type="submit"
          disabled={isSubmitting}
          className="flex w-full items-center justify-center gap-2 rounded-2xl bg-slate-900 px-5 py-4 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {activeProvider === 'recovery' ? (
            <>
              <Loader2 className="h-5 w-5 animate-spin" />
              {loginT('recoverySaving')}
            </>
          ) : (
            loginT('recoverySave')
          )}
        </button>

        <button
          type="button"
          onClick={() => void onRecoveryCancel?.()}
          className="w-full text-center text-sm font-medium text-slate-500 transition hover:text-slate-900"
        >
          {loginT('cancel')}
        </button>
      </form>
    </>
  );

  const renderRecoveryExpiredForm = () => (
    <>
      <div className="space-y-4 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-amber-100 text-amber-700">
          <Mail className="h-8 w-8" />
        </div>
        <div className="space-y-2">
          <h2 className="text-xl font-semibold text-slate-900">{loginT('expiredTitle')}</h2>
          <p className="text-sm leading-6 text-slate-500">
            {loginT('expiredDescription')}
          </p>
        </div>
      </div>

      <form
        className="space-y-4"
        onSubmit={async (event) => {
          event.preventDefault();

          const normalizedEmail = email.trim().toLowerCase();
          if (!normalizedEmail) {
            toast.error(loginT('toasts.emailRequired'));
            return;
          }

          setIsSubmitting(true);
          setActiveProvider('email');

          try {
            await requestPasswordReset(normalizedEmail);
            toast.success(loginT('toasts.resetSentAgain'));
            await onAuthViewReset?.();
            setFormMode('signin');
          } catch (err) {
            const message =
              err instanceof Error && err.message ? err.message : loginT('toasts.resetSendError');
            console.error('Recovery link refresh error:', err);
            toast.error(message);
          } finally {
            setIsSubmitting(false);
            setActiveProvider(null);
          }
        }}
      >
        <label className="block space-y-2">
          <span className="text-sm font-medium text-slate-700">{loginT('emailLabel')}</span>
          <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 focus-within:border-slate-400">
            <Mail className="h-5 w-5 text-slate-400" />
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder={loginT('emailPlaceholder')}
              autoComplete="email"
              className="w-full bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
            />
          </div>
        </label>

        <button
          type="submit"
          disabled={isSubmitting}
          className="flex w-full items-center justify-center gap-2 rounded-2xl bg-slate-900 px-5 py-4 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {activeProvider === 'email' ? (
            <>
              <Loader2 className="h-5 w-5 animate-spin" />
              {loginT('resendLoading')}
            </>
          ) : (
            loginT('resend')
          )}
        </button>

        <button
          type="button"
          onClick={() => void onAuthViewReset?.()}
          className="flex w-full items-center justify-center gap-2 text-center text-sm font-medium text-slate-500 transition hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" />
          {loginT('backToSignIn')}
        </button>
      </form>
    </>
  );

  return (
    <div className="min-h-screen bg-[linear-gradient(180deg,#eef4ff_0%,#f8fafc_42%,#eef2f7_100%)] px-4 py-6 md:px-6 md:py-8">
      <div className="mx-auto flex min-h-[calc(100vh-3rem)] w-full max-w-[440px] items-center">
        <div className="w-full overflow-hidden rounded-[30px] border border-white/70 bg-[var(--tg-theme-bg-color,#ffffff)] p-6 shadow-[0_28px_80px_rgba(15,23,42,0.16)] backdrop-blur md:p-8">
          <div className="space-y-6">
            <div className="space-y-4 text-center">
              <div className="flex justify-center">
                <AppLogo
                  shape="card"
                  className="h-[88px] w-[176px] shadow-[0_14px_32px_rgba(51,144,236,0.18)]"
                  imageClassName="p-[12px]"
                />
              </div>
              <div className="space-y-2">
                <h1 className="text-3xl font-bold text-[var(--tg-theme-text-color,#000000)]">
                  {loginT('heroTitle')}
                </h1>
                <p className="text-sm leading-6 text-[var(--tg-theme-hint-color,#6b7280)]">
                  {view === 'recovery'
                    ? loginT('heroRecoverySubtitle')
                    : view === 'recovery-expired'
                      ? loginT('heroRecoveryExpiredSubtitle')
                      : loginT('heroDefaultSubtitle')}
                </p>
              </div>
            </div>

            {view === 'recovery'
              ? renderRecoveryForm()
              : view === 'recovery-expired'
                ? renderRecoveryExpiredForm()
                : renderDefaultForm()}
          </div>
        </div>
      </div>
    </div>
  );
}
