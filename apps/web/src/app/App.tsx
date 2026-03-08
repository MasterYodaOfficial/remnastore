import React, { useEffect, useRef, useState } from 'react';
import { supabase } from '../../utils/supabase/client';
import { loadTelegramScript, getTelegramWebApp } from '../../utils/telegram';
import { LoginPage } from './components/LoginPage';
import { Header } from './components/Header';
import { HomePage } from './components/HomePage';
import { PlansPage } from './components/PlansPage';
import { ReferralPage } from './components/ReferralPage';
import { ReferralCard } from './components/ReferralCard';
import { SettingsPage } from './components/SettingsPage';
import { SubscriptionCard } from './components/SubscriptionCard';
import { ThemeToggle } from './components/ThemeToggle';
import { BottomNav } from './components/BottomNav';
import { TopUpModal } from './components/TopUpModal';
import { LoadingScreen } from './components/LoadingScreen';
import { toast, Toaster } from 'sonner';
import {
  CreditCard,
  Gift,
  LayoutDashboard,
  LogOut,
  Moon,
  Settings as SettingsIcon,
  Sparkles,
  Sun,
  Wallet,
} from 'lucide-react';

const BACKEND_API = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(
  /\/+$/,
  ""
);
const BROWSER_TOKEN_STORAGE_KEY = 'remnastore.browser_access_token';
const PASSWORD_RECOVERY_STORAGE_KEY = 'remnastore.password_recovery_active';
const THEME_STORAGE_KEY = 'remnastore.theme';
type AuthView = 'default' | 'recovery' | 'recovery-expired';

interface BackendAccount {
  id: string;
  telegram_id?: number | null;
  email?: string | null;
  display_name?: string | null;
  username?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  balance_cents: number;
  referral_code?: string | null;
  referral_earnings_cents: number;
  referrals_count: number;
}

interface User {
  id: string;
  name: string;
  email: string;
  balance: number;
  referralCode: string;
  referralsCount: number;
  earnings: number;
  hasUsedTrial: boolean;
  avatar?: string;
}

interface Subscription {
  isActive: boolean;
  startDate?: string;
  endDate?: string;
  isTrial?: boolean;
}

interface Plan {
  id: string;
  name: string;
  price: number;
  duration: number;
  features: string[];
  popular?: boolean;
}

function mapBackendAccountToUser(account: BackendAccount): User {
  const name =
    account.display_name ||
    account.first_name ||
    account.username ||
    account.email ||
    'Пользователь';

  return {
    id: account.id,
    name,
    email: account.email || '',
    balance: (account.balance_cents || 0) / 100,
    referralCode: account.referral_code || '',
    referralsCount: account.referrals_count || 0,
    earnings: (account.referral_earnings_cents || 0) / 100,
    hasUsedTrial: false,
  };
}

function getInitialTheme(): 'light' | 'dark' {
  if (typeof window === 'undefined') {
    return 'light';
  }

  const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (storedTheme === 'light' || storedTheme === 'dark') {
    return storedTheme;
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isTelegramWebApp, setIsTelegramWebApp] = useState(false);
  const [authView, setAuthView] = useState<AuthView>('default');
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [activeTab, setActiveTab] = useState('home');
  const [theme, setTheme] = useState<'light' | 'dark'>(getInitialTheme);
  const [referralCopied, setReferralCopied] = useState(false);
  const [isTopUpModalOpen, setIsTopUpModalOpen] = useState(false);
  const [isDesktopBrowser, setIsDesktopBrowser] = useState(
    () => typeof window !== 'undefined' && window.innerWidth >= 1200
  );
  const lastLoadedBrowserTokenRef = useRef<string | null>(null);
  const inFlightBrowserTokenRef = useRef<string | null>(null);
  const currentBrowserTokenRef = useRef<string | null>(null);
  const manualLogoutRef = useRef(false);
  const authViewRef = useRef<AuthView>('default');

  const setAuthViewMode = (view: AuthView) => {
    authViewRef.current = view;
    setAuthView(view);
  };

  const isPasswordRecoveryRequested = () => {
    const url = new URL(window.location.href);
    return url.searchParams.get('auth_action') === 'reset-password';
  };

  const clearAuthActionParam = () => {
    const url = new URL(window.location.href);
    url.searchParams.delete('auth_action');
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
  };

  const applyTelegramTheme = (nextTheme: 'light' | 'dark') => {
    const tg = getTelegramWebApp();
    if (!tg) {
      return;
    }

    try {
      tg.setHeaderColor?.(nextTheme === 'dark' ? '#0f172a' : '#ffffff');
    } catch (err) {
      console.error('Telegram header theme update error:', err);
    }

    try {
      tg.setBottomBarColor?.(nextTheme === 'dark' ? '#0f172a' : '#ffffff');
    } catch (err) {
      console.error('Telegram bottom bar theme update error:', err);
    }
  };

  const getRecoveryCallbackState = () => {
    const url = new URL(window.location.href);
    const hashValue = window.location.hash.startsWith('#')
      ? window.location.hash.slice(1)
      : window.location.hash;
    const hashParams = new URLSearchParams(hashValue);

    return {
      code: url.searchParams.get('code'),
      tokenHash: url.searchParams.get('token_hash') || hashParams.get('token_hash'),
      type: url.searchParams.get('type') || hashParams.get('type'),
      accessToken: hashParams.get('access_token'),
      refreshToken: hashParams.get('refresh_token'),
    };
  };

  const clearRecoveryCallbackState = (options: { clearHash?: boolean } = {}) => {
    const url = new URL(window.location.href);
    url.searchParams.delete('code');
    url.searchParams.delete('token_hash');
    url.searchParams.delete('type');

    if (options.clearHash) {
      url.hash = '';
    }

    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
  };

  const markPasswordRecoveryActive = () => {
    window.sessionStorage.setItem(PASSWORD_RECOVERY_STORAGE_KEY, '1');
  };

  const clearPasswordRecoveryActive = () => {
    window.sessionStorage.removeItem(PASSWORD_RECOVERY_STORAGE_KEY);
  };

  const hasPasswordRecoveryActive = () =>
    window.sessionStorage.getItem(PASSWORD_RECOVERY_STORAGE_KEY) === '1';

  // Check if running in Telegram WebApp
  useEffect(() => {
    const initApp = async () => {
      // Load Telegram script first
      await loadTelegramScript();
      
      const tg = getTelegramWebApp();
      if (tg && tg.initData) {
        setIsTelegramWebApp(true);
        setAuthViewMode('default');
        // Apply Telegram theme
        if (tg.colorScheme === 'dark') {
          setTheme('dark');
        } else if (tg.colorScheme === 'light') {
          setTheme('light');
        }
        // Expand the WebApp to full height
        tg.expand();
        // Auto-authenticate Telegram users
        handleTelegramAuth(tg);
      } else {
        setIsTelegramWebApp(false);
        if (isPasswordRecoveryRequested()) {
          setAuthViewMode('recovery');
          preparePasswordRecovery();
        } else {
          setAuthViewMode('default');
          checkSupabaseAuth();
        }
      }
    };

    initApp();
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const root = window.document.documentElement;
    root.classList.toggle('dark', theme === 'dark');
    root.classList.toggle('theme-dark', theme === 'dark');
    root.classList.toggle('theme-light', theme === 'light');
    root.style.colorScheme = theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);

    if (isTelegramWebApp) {
      applyTelegramTheme(theme);
    }
  }, [theme, isTelegramWebApp]);

  useEffect(() => {
    if (!isTelegramWebApp) {
      return;
    }

    const tg = getTelegramWebApp();
    if (!tg?.onEvent) {
      return;
    }

    const handleThemeChanged = () => {
      if (tg.colorScheme === 'dark' || tg.colorScheme === 'light') {
        setTheme(tg.colorScheme);
        applyTelegramTheme(tg.colorScheme);
      }
    };

    tg.onEvent('themeChanged', handleThemeChanged);

    return () => {
      tg.offEvent?.('themeChanged', handleThemeChanged);
    };
  }, [isTelegramWebApp]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const mediaQuery = window.matchMedia('(min-width: 1200px)');
    const updateDesktopLayout = (matches: boolean) => {
      setIsDesktopBrowser(!isTelegramWebApp && matches);
    };

    updateDesktopLayout(mediaQuery.matches);

    const listener = (event: MediaQueryListEvent) => {
      updateDesktopLayout(event.matches);
    };

    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', listener);
      return () => mediaQuery.removeEventListener('change', listener);
    }

    mediaQuery.addListener(listener);
    return () => mediaQuery.removeListener(listener);
  }, [isTelegramWebApp]);

  const handleTelegramAuth = async (tg: any) => {
    try {
      const telegramUser = tg.initDataUnsafe?.user;
      if (!telegramUser) {
        setIsLoading(false);
        return;
      }

      let accountUser = mapBackendAccountToUser({
        id: String(telegramUser.id),
        email: `telegram_${telegramUser.id}@vpn.service`,
        display_name: telegramUser.first_name,
        username: telegramUser.username,
        first_name: telegramUser.first_name,
        last_name: telegramUser.last_name,
        balance_cents: 0,
        referral_earnings_cents: 0,
        referrals_count: 0,
      });

      try {
        const authResponse = await fetch(`${BACKEND_API}/api/v1/auth/telegram/webapp`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ init_data: tg.initData }),
        });

        if (authResponse.ok) {
          const authData = await authResponse.json();
          accountUser = mapBackendAccountToUser(authData.account as BackendAccount);
        }
      } catch {
        /* ignore */
      }

      setUser({
        ...accountUser,
        avatar: telegramUser.photo_url,
      });
      setIsAuthenticated(true);
      setAccessToken(null);
    } catch (err) {
      console.error('Telegram auth error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const checkSupabaseAuth = async () => {
    let restored = false;

    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (session?.access_token) {
        restored = await syncBrowserAuth(session.access_token);
      } else {
        const cachedToken = window.localStorage.getItem(BROWSER_TOKEN_STORAGE_KEY);
        if (cachedToken) {
          restored = await syncBrowserAuth(cachedToken);
        }
      }
    } catch (err) {
      console.error('Auth check error:', err);
    } finally {
      setIsLoading(false);
    }

    return restored;
  };

  const preparePasswordRecovery = async () => {
    clearBrowserAuthState();
    const recoveryCallbackState = getRecoveryCallbackState();
    const hasRecoveryCallback =
      Boolean(recoveryCallbackState.code) ||
      Boolean(recoveryCallbackState.tokenHash) ||
      Boolean(recoveryCallbackState.accessToken && recoveryCallbackState.refreshToken);
    let lastError: unknown = null;

    try {
      const initializeResult = await supabase.auth.initialize();
      if (initializeResult.error) {
        lastError = initializeResult.error;
      }

      let {
        data: { session },
      } = await supabase.auth.getSession();

      if (!session?.access_token && recoveryCallbackState.code) {
        const { data, error } = await supabase.auth.exchangeCodeForSession(recoveryCallbackState.code);
        if (error) {
          lastError = error;
        } else {
          session = data.session;
          clearRecoveryCallbackState();
        }
      }

      if (
        !session?.access_token &&
        recoveryCallbackState.accessToken &&
        recoveryCallbackState.refreshToken
      ) {
        const { data, error } = await supabase.auth.setSession({
          access_token: recoveryCallbackState.accessToken,
          refresh_token: recoveryCallbackState.refreshToken,
        });
        if (error) {
          lastError = error;
        } else {
          session = data.session;
          clearRecoveryCallbackState({ clearHash: true });
        }
      }

      if (
        !session?.access_token &&
        recoveryCallbackState.tokenHash &&
        recoveryCallbackState.type === 'recovery'
      ) {
        const { data, error } = await supabase.auth.verifyOtp({
          token_hash: recoveryCallbackState.tokenHash,
          type: 'recovery',
        });
        if (error) {
          lastError = error;
        } else {
          session = data.session;
          clearRecoveryCallbackState();
        }
      }

      if (session?.access_token && (hasRecoveryCallback || hasPasswordRecoveryActive())) {
        markPasswordRecoveryActive();
        setAuthViewMode('recovery');
        return;
      }

      if (lastError) {
        console.error('Password recovery preparation error:', lastError);
      }

      clearPasswordRecoveryActive();
      clearAuthActionParam();
      const restored = await checkSupabaseAuth();
      setAuthViewMode(restored ? 'default' : 'recovery-expired');
    } catch (err) {
      console.error('Password recovery preparation error:', err);
      clearPasswordRecoveryActive();
      clearAuthActionParam();
      const restored = await checkSupabaseAuth();
      setAuthViewMode(restored ? 'default' : 'recovery-expired');
    } finally {
      setIsLoading(false);
    }
  };

  // Listen for auth changes
  useEffect(() => {
    const { data: authListener } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        if (event === 'PASSWORD_RECOVERY') {
          setAuthViewMode('recovery');
          clearBrowserAuthState();
          markPasswordRecoveryActive();
          setIsLoading(false);
          return;
        }

        if (authViewRef.current === 'recovery') {
          if (event === 'SIGNED_OUT') {
            if (manualLogoutRef.current) {
              manualLogoutRef.current = false;
            }
            clearBrowserAuthState();
          }
          return;
        }

        if ((event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED') && session?.access_token) {
          await syncBrowserAuth(session.access_token);
        } else if (event === 'SIGNED_OUT') {
          if (manualLogoutRef.current) {
            manualLogoutRef.current = false;
            clearBrowserAuthState();
            return;
          }

          if (currentBrowserTokenRef.current || lastLoadedBrowserTokenRef.current) {
            return;
          }

          clearBrowserAuthState();
        }
      }
    );

    return () => {
      authListener.subscription.unsubscribe();
    };
  }, []);

  const clearBrowserAuthState = () => {
    setIsAuthenticated(false);
    setUser(null);
    setAccessToken(null);
    currentBrowserTokenRef.current = null;
    lastLoadedBrowserTokenRef.current = null;
    inFlightBrowserTokenRef.current = null;
    window.localStorage.removeItem(BROWSER_TOKEN_STORAGE_KEY);
  };

  const syncBrowserAuth = async (token: string) => {
    if (!token) {
      return false;
    }

    setAccessToken(token);
    currentBrowserTokenRef.current = token;
    window.localStorage.setItem(BROWSER_TOKEN_STORAGE_KEY, token);

    if (lastLoadedBrowserTokenRef.current === token) {
      setIsAuthenticated(true);
      return true;
    }

    if (inFlightBrowserTokenRef.current === token) {
      return false;
    }

    inFlightBrowserTokenRef.current = token;
    const loaded = await loadUserData(token);
    if (loaded) {
      lastLoadedBrowserTokenRef.current = token;
      setIsAuthenticated(true);
    } else if (currentBrowserTokenRef.current === token) {
      currentBrowserTokenRef.current = null;
      window.localStorage.removeItem(BROWSER_TOKEN_STORAGE_KEY);
    }
    inFlightBrowserTokenRef.current = null;
    return loaded;
  };

  const loadUserData = async (token: string) => {
    try {
      const accountResponse = await fetch(`${BACKEND_API}/api/v1/accounts/me`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!accountResponse.ok) {
        throw new Error('Failed to load account from backend');
      }

      const accountData: BackendAccount = await accountResponse.json();
      setUser(mapBackendAccountToUser(accountData));
      setSubscription(null);
      setPlans([]);

      return true;
    } catch (err) {
      console.error('Error loading user data:', err);
      return false;
    }
  };

  const handleTopUp = async () => {
    setIsTopUpModalOpen(true);
  };

  const handleTopUpAmount = async (amount: number) => {
    if (!accessToken) return;

    toast.error('Пополнение пока не перенесено на новый API.');
  };

  const handleActivateTrial = async () => {
    if (!accessToken) return;
    toast.error('Пробный период пока не перенесен на новый API.');
  };

  const handleBuyPlan = async (planId: string) => {
    if (!accessToken) return;
    void planId;
    toast.error('Покупка тарифа пока не перенесена на новый API.');
  };

  const handleCopyReferral = () => {
    if (user?.referralCode) {
      const referralLink = `${window.location.origin}?ref=${user.referralCode}`;
      navigator.clipboard.writeText(referralLink);
      setReferralCopied(true);
      toast.success('Реферальная ссылка скопирована!');
      setTimeout(() => setReferralCopied(false), 2000);
    }
  };

  const handleWithdraw = async () => {
    if (!accessToken) return;
    toast.error('Вывод пока не перенесен на новый API.');
  };

  const handleLogout = async () => {
    manualLogoutRef.current = true;
    clearPasswordRecoveryActive();
    await supabase.auth.signOut();
    clearBrowserAuthState();
  };

  const handlePasswordRecoveryComplete = async () => {
    setAuthViewMode('default');
    clearPasswordRecoveryActive();
    clearAuthActionParam();
    setIsLoading(true);

    try {
      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (session?.access_token) {
        const loaded = await syncBrowserAuth(session.access_token);
        if (!loaded) {
          toast.success('Пароль обновлен. Войдите с новым паролем.');
        }
      } else {
        toast.success('Пароль обновлен. Войдите с новым паролем.');
      }
    } catch (err) {
      console.error('Password recovery completion error:', err);
      toast.success('Пароль обновлен. Войдите с новым паролем.');
    } finally {
      setIsLoading(false);
    }
  };

  const handlePasswordRecoveryCancel = async () => {
    setAuthViewMode('default');
    clearPasswordRecoveryActive();
    clearAuthActionParam();
    clearBrowserAuthState();
    manualLogoutRef.current = true;

    try {
      await supabase.auth.signOut();
    } catch (err) {
      console.error('Password recovery cancel error:', err);
      manualLogoutRef.current = false;
    }
  };

  const handleAuthViewReset = () => {
    clearPasswordRecoveryActive();
    clearAuthActionParam();
    setAuthViewMode('default');
  };

  const getSubscriptionData = () => {
    if (!subscription) {
      return {
        isActive: false,
        hasTrial: true,
        hasUsedTrial: user?.hasUsedTrial || false,
      };
    }

    const now = new Date();
    const endDate = subscription.endDate ? new Date(subscription.endDate) : null;
    const startDate = subscription.startDate ? new Date(subscription.startDate) : null;

    if (!endDate || !startDate) {
      return {
        isActive: false,
        hasTrial: true,
        hasUsedTrial: user?.hasUsedTrial || false,
      };
    }

    const isActive = now < endDate;
    const totalDays = Math.ceil((endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24));
    const daysLeft = Math.ceil((endDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));

    return {
      isActive,
      daysLeft: isActive ? Math.max(0, daysLeft) : undefined,
      totalDays: isActive ? totalDays : undefined,
      hasTrial: !user?.hasUsedTrial,
      hasUsedTrial: user?.hasUsedTrial || false,
    };
  };

  if (isLoading) {
    return (
      <>
        <Toaster position="top-center" />
        <LoadingScreen />
      </>
    );
  }

  if (!isAuthenticated) {
    return (
      <>
        <Toaster position="top-center" />
        <LoginPage
          view={authView}
          onRecoveryComplete={handlePasswordRecoveryComplete}
          onRecoveryCancel={handlePasswordRecoveryCancel}
          onAuthViewReset={handleAuthViewReset}
        />
      </>
    );
  }

  if (!user) {
    return (
      <>
        <Toaster position="top-center" />
        <div className="min-h-screen flex items-center justify-center bg-[var(--tg-theme-bg-color,#ffffff)]">
          <div className="text-[var(--tg-theme-text-color,#000000)]">Загрузка профиля...</div>
        </div>
      </>
    );
  }

  const subscriptionData = getSubscriptionData();

  const renderContent = () => {
    switch (activeTab) {
      case 'home':
        return (
          <HomePage
            subscription={subscriptionData}
            referralData={{
              referralCode: user.referralCode || '',
              referralsCount: user.referralsCount || 0,
              earnings: user.earnings || 0,
            }}
            onActivateTrial={handleActivateTrial}
            onRenew={() => setActiveTab('plans')}
            onBuy={() => setActiveTab('plans')}
            onCopyReferral={handleCopyReferral}
            onWithdraw={handleWithdraw}
            referralCopied={referralCopied}
          />
        );
      case 'plans':
        return (
          <PlansPage
            plans={plans}
            balance={user.balance}
            onBuyPlan={handleBuyPlan}
            onTopUp={handleTopUp}
          />
        );
      case 'referral':
        return (
          <ReferralPage
            referrals={[]}
            totalEarnings={user.earnings || 0}
            availableForWithdraw={user.earnings || 0}
            onWithdraw={handleWithdraw}
          />
        );
      case 'settings':
        return (
          <SettingsPage
            theme={theme}
            onThemeChange={setTheme}
            onLogout={handleLogout}
            showLogout={!isTelegramWebApp}
          />
        );
      default:
        return null;
    }
  };

  const scrollToSection = (sectionId: string) => {
    document.getElementById(sectionId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const desktopSections = [
    { id: 'overview', label: 'Обзор', icon: LayoutDashboard },
    { id: 'plans', label: 'Тарифы', icon: CreditCard },
    { id: 'referrals', label: 'Рефералы', icon: Gift },
    { id: 'settings', label: 'Настройки', icon: SettingsIcon },
  ];

  const renderDesktopPlans = () => {
    if (!plans.length) {
      return (
        <div className="rounded-[28px] border border-dashed border-slate-300 bg-slate-50/70 p-6 dark:border-slate-700 dark:bg-slate-900/70">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-900 text-white dark:bg-sky-500 dark:text-slate-950">
              <Sparkles className="h-6 w-6" />
            </div>
            <div className="space-y-3">
              <div>
                <h3 className="text-xl font-semibold text-slate-900 dark:text-slate-50">
                  Каталог тарифов переносится
                </h3>
                <p className="mt-2 max-w-xl text-sm leading-6 text-slate-500 dark:text-slate-300">
                  В browser dashboard уже работает новая авторизация, а тарифы и подписки
                  догружаем следующим этапом с вашего `FastAPI`.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  onClick={handleTopUp}
                  className="rounded-2xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
                >
                  Пополнить баланс
                </button>
                <button
                  onClick={() => scrollToSection('overview')}
                  className="rounded-2xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900"
                >
                  Вернуться к обзору
                </button>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="grid gap-4 xl:grid-cols-2">
        {plans.map((plan) => (
          <div
            key={plan.id}
            className={`relative rounded-[28px] border border-slate-200 bg-slate-50/70 p-6 dark:border-slate-800 dark:bg-slate-900/80 ${
              plan.popular ? 'ring-2 ring-sky-400/60' : ''
            }`}
          >
            {plan.popular && (
              <div className="absolute -top-3 left-6 rounded-full bg-slate-950 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-white dark:bg-sky-500 dark:text-slate-950">
                Лучший выбор
              </div>
            )}
            <div className="space-y-4">
              <div>
                <div className="text-sm font-medium uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                  {plan.duration} дней доступа
                </div>
                <h3 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-slate-50">
                  {plan.name}
                </h3>
                <div className="mt-3 flex items-end gap-2">
                  <span className="text-4xl font-bold text-slate-900 dark:text-slate-50">
                    {plan.price}
                  </span>
                  <span className="pb-1 text-sm text-slate-500 dark:text-slate-400">₽</span>
                </div>
              </div>
              <div className="space-y-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                {plan.features.map((feature, index) => (
                  <div key={index} className="flex items-start gap-3">
                    <span className="mt-1.5 h-2 w-2 rounded-full bg-sky-500" />
                    <span>{feature}</span>
                  </div>
                ))}
              </div>
              <button
                onClick={() => {
                  if (user.balance >= plan.price) {
                    handleBuyPlan(plan.id);
                    return;
                  }
                  handleTopUp();
                }}
                className={`w-full rounded-2xl px-4 py-3 text-sm font-semibold transition ${
                  user.balance >= plan.price
                    ? 'bg-slate-900 text-white hover:bg-slate-800 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400'
                    : 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900'
                }`}
              >
                {user.balance >= plan.price ? 'Купить тариф' : 'Пополнить для покупки'}
              </button>
            </div>
          </div>
        ))}
      </div>
    );
  };

  const renderDesktopBrowserLayout = () => (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,#dbeafe_0%,#eff6ff_24%,#f8fafc_58%,#eef2ff_100%)] px-8 py-8 dark:bg-[radial-gradient(circle_at_top_left,#0f172a_0%,#111827_28%,#020617_100%)]">
      <Toaster position="top-center" />
      <TopUpModal
        isOpen={isTopUpModalOpen}
        onClose={() => setIsTopUpModalOpen(false)}
        onTopUp={handleTopUpAmount}
      />

      <div className="mx-auto flex max-w-[1520px] gap-6">
        <aside className="sticky top-8 h-[calc(100vh-4rem)] w-[310px] shrink-0 rounded-[32px] border border-white/70 bg-white/82 p-6 shadow-[0_32px_80px_rgba(15,23,42,0.14)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_32px_80px_rgba(2,6,23,0.55)]">
          <div className="flex h-full flex-col">
            <div className="space-y-6">
              <div className="space-y-3">
                <span className="inline-flex items-center rounded-full bg-sky-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-sky-700 dark:bg-sky-500/15 dark:text-sky-200">
                  Browser Workspace
                </span>
                <div>
                  <h1 className="text-2xl font-semibold text-slate-950 dark:text-slate-50">RemnaStore</h1>
                  <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                    Широкий desktop dashboard вместо мобильного контейнера по центру экрана.
                  </p>
                </div>
              </div>

              <div className="rounded-[28px] bg-slate-950 p-5 text-white shadow-[0_24px_48px_rgba(15,23,42,0.28)] dark:border dark:border-slate-800 dark:bg-slate-900/90 dark:shadow-[0_24px_48px_rgba(2,6,23,0.45)]">
                <div className="flex items-center gap-4">
                  <div className="flex h-14 w-14 items-center justify-center overflow-hidden rounded-2xl bg-white/10 text-lg font-semibold">
                    {user.avatar ? (
                      <img
                        src={user.avatar}
                        alt={user.name}
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      user.name.charAt(0).toUpperCase()
                    )}
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-lg font-semibold">{user.name}</div>
                    <div className="truncate text-sm text-slate-300">
                      {user.email || 'Browser account'}
                    </div>
                  </div>
                </div>
                <div className="mt-5 rounded-2xl bg-white/8 p-4 dark:bg-white/5">
                  <div className="text-xs uppercase tracking-[0.16em] text-slate-300">Баланс</div>
                  <div className="mt-2 text-3xl font-semibold">{user.balance.toFixed(2)} ₽</div>
                </div>
              </div>

              <nav className="space-y-2">
                {desktopSections.map((section) => {
                  const Icon = section.icon;
                  return (
                    <button
                      key={section.id}
                      onClick={() => scrollToSection(section.id)}
                      className="flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left text-sm font-semibold text-slate-700 transition hover:bg-white/70 hover:text-slate-950 dark:text-slate-300 dark:hover:bg-slate-900 dark:hover:text-slate-50"
                    >
                      <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-100 text-slate-900 dark:border dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100">
                        <Icon className="h-5 w-5" />
                      </span>
                      <span>{section.label}</span>
                    </button>
                  );
                })}
              </nav>

              <div className="rounded-[24px] border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-900/80">
                <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">Desktop quick note</div>
                <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                  Основные разделы собраны на одной странице. Скролл нужен только если контента
                  станет больше.
                </p>
              </div>
            </div>

            <button
              onClick={handleLogout}
              className="mt-auto flex items-center justify-center gap-2 rounded-2xl bg-red-500 px-4 py-3 text-sm font-semibold text-white transition hover:bg-red-600"
            >
              <LogOut className="h-4 w-4" />
              Выйти из аккаунта
            </button>
          </div>
        </aside>

        <main className="min-w-0 flex-1 space-y-6">
          <section
            id="overview"
            className="rounded-[32px] border border-white/70 bg-white/82 p-8 shadow-[0_28px_72px_rgba(15,23,42,0.12)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_28px_72px_rgba(2,6,23,0.55)]"
          >
            <div className="flex flex-wrap items-start justify-between gap-6">
              <div className="max-w-3xl space-y-3">
                <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate-600 dark:bg-slate-900 dark:text-slate-300">
                  Управление доступом
                </span>
                <h2 className="text-4xl font-semibold tracking-tight text-slate-950 dark:text-slate-50">
                  Вся работа с аккаунтом собрана в одном desktop dashboard
                </h2>
                <p className="text-base leading-7 text-slate-500 dark:text-slate-300">
                  Без имитации экрана телефона: обзор аккаунта, тарифы, реферальные метрики и
                  быстрые настройки теперь живут в одном широком рабочем пространстве.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <button
                  onClick={() => scrollToSection('plans')}
                  className="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900"
                >
                  Открыть тарифы
                </button>
                <button
                  onClick={handleTopUp}
                  className="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 dark:bg-sky-500 dark:text-slate-950 dark:hover:bg-sky-400"
                >
                  Пополнить баланс
                </button>
              </div>
            </div>

            <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-[26px] bg-slate-950 p-5 text-white dark:border dark:border-slate-800 dark:bg-slate-900/90">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-[0.16em] text-slate-300">
                    Баланс
                  </span>
                  <Wallet className="h-5 w-5 text-slate-300" />
                </div>
                <div className="mt-4 text-3xl font-semibold">{user.balance.toFixed(2)} ₽</div>
                <div className="mt-2 text-sm text-slate-300">Доступно для покупок и продления</div>
              </div>

              <div className="rounded-[26px] bg-white p-5 shadow-[0_20px_40px_rgba(15,23,42,0.06)] dark:bg-slate-900 dark:shadow-[0_20px_40px_rgba(2,6,23,0.35)]">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                    Статус
                  </span>
                  <LayoutDashboard className="h-5 w-5 text-slate-400 dark:text-slate-500" />
                </div>
                <div className="mt-4 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                  {subscriptionData.isActive
                    ? `${subscriptionData.daysLeft ?? 0} дней`
                    : subscriptionData.hasTrial && !subscriptionData.hasUsedTrial
                      ? 'Trial доступен'
                      : 'Без подписки'}
                </div>
                <div className="mt-2 text-sm text-slate-500 dark:text-slate-300">
                  {subscriptionData.isActive
                    ? 'Подписка активна'
                    : 'Можно активировать пробный доступ или выбрать тариф'}
                </div>
              </div>

              <div className="rounded-[26px] bg-white p-5 shadow-[0_20px_40px_rgba(15,23,42,0.06)] dark:bg-slate-900 dark:shadow-[0_20px_40px_rgba(2,6,23,0.35)]">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                    Рефералы
                  </span>
                  <Gift className="h-5 w-5 text-slate-400 dark:text-slate-500" />
                </div>
                <div className="mt-4 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                  {user.referralsCount || 0}
                </div>
                <div className="mt-2 text-sm text-slate-500 dark:text-slate-300">Активных приглашений в системе</div>
              </div>

              <div className="rounded-[26px] bg-white p-5 shadow-[0_20px_40px_rgba(15,23,42,0.06)] dark:bg-slate-900 dark:shadow-[0_20px_40px_rgba(2,6,23,0.35)]">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                    Доход
                  </span>
                  <Sparkles className="h-5 w-5 text-slate-400 dark:text-slate-500" />
                </div>
                <div className="mt-4 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                  {user.earnings.toFixed(2)} ₽
                </div>
                <div className="mt-2 text-sm text-slate-500 dark:text-slate-300">Начислено по реферальной программе</div>
              </div>
            </div>
          </section>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
            <section
              className="rounded-[32px] border border-white/70 bg-white/82 shadow-[0_28px_72px_rgba(15,23,42,0.12)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_28px_72px_rgba(2,6,23,0.55)]"
            >
              <div className="border-b border-slate-200/80 px-6 py-5 dark:border-slate-800/80">
                <h3 className="text-xl font-semibold text-slate-950 dark:text-slate-50">Подписка и доступ</h3>
                <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                  Ключевой статус аккаунта и действия по доступу находятся здесь.
                </p>
              </div>
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
                <div className="min-w-0">
                  <SubscriptionCard
                    subscription={subscriptionData}
                    onActivateTrial={handleActivateTrial}
                    onRenew={() => scrollToSection('plans')}
                    onBuy={() => scrollToSection('plans')}
                  />
                </div>
                <div className="p-6">
                  <div className="rounded-[28px] bg-slate-50 p-5 dark:bg-slate-900">
                    <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">Что изменилось</div>
                    <ul className="mt-4 space-y-3 text-sm leading-6 text-slate-500 dark:text-slate-300">
                      <li>Google и email живут в одном browser auth flow.</li>
                      <li>Telegram Mini App остается отдельным полноэкранным сценарием.</li>
                      <li>Desktop теперь использует нормальную панель, а не мобильный shell.</li>
                    </ul>
                  </div>
                </div>
              </div>
            </section>

            <section
              id="plans"
              className="rounded-[32px] border border-white/70 bg-white/82 p-6 shadow-[0_28px_72px_rgba(15,23,42,0.12)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_28px_72px_rgba(2,6,23,0.55)]"
            >
              <div className="mb-6 flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-xl font-semibold text-slate-950 dark:text-slate-50">Тарифы</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                    Здесь будет коммерческий каталог после переноса subscription API.
                  </p>
                </div>
                <button
                  onClick={handleTopUp}
                  className="rounded-2xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900"
                >
                  Пополнить
                </button>
              </div>
              {renderDesktopPlans()}
            </section>
          </div>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
            <section
              id="referrals"
              className="rounded-[32px] border border-white/70 bg-white/82 shadow-[0_28px_72px_rgba(15,23,42,0.12)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_28px_72px_rgba(2,6,23,0.55)]"
            >
              <div className="border-b border-slate-200/80 px-6 py-5 dark:border-slate-800/80">
                <h3 className="text-xl font-semibold text-slate-950 dark:text-slate-50">Реферальная программа</h3>
                <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                  Код, начисления и быстрые действия собраны в одном блоке.
                </p>
              </div>
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_280px]">
                <div className="min-w-0">
                  <ReferralCard
                    referralCode={user.referralCode || ''}
                    referralsCount={user.referralsCount || 0}
                    earnings={user.earnings || 0}
                    onCopy={handleCopyReferral}
                    onWithdraw={handleWithdraw}
                    copied={referralCopied}
                  />
                </div>
                <div className="p-6">
                  <div className="grid gap-4">
                    <div className="rounded-[24px] bg-slate-50 p-4 dark:bg-slate-900">
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
                        Приглашено
                      </div>
                      <div className="mt-3 text-3xl font-semibold text-slate-950 dark:text-slate-50">
                        {user.referralsCount || 0}
                      </div>
                    </div>
                    <div className="rounded-[24px] bg-slate-950 p-4 text-white dark:border dark:border-slate-800 dark:bg-slate-900">
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-300">
                        Доступно к выводу
                      </div>
                      <div className="mt-3 text-3xl font-semibold">{user.earnings.toFixed(2)} ₽</div>
                    </div>
                    <div className="rounded-[24px] border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
                      Детальный список рефералов появится автоматически, когда переведем
                      оставшийся referral backend на новый API.
                    </div>
                  </div>
                </div>
              </div>
            </section>

            <section
              id="settings"
              className="rounded-[32px] border border-white/70 bg-white/82 p-6 shadow-[0_28px_72px_rgba(15,23,42,0.12)] backdrop-blur dark:border-slate-800/80 dark:bg-slate-950/76 dark:shadow-[0_28px_72px_rgba(2,6,23,0.55)]"
            >
              <div className="mb-6">
                <h3 className="text-xl font-semibold text-slate-950 dark:text-slate-50">Быстрые настройки</h3>
                <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-300">
                  Главное вынесено в отдельный блок, без ухода на отдельный экран.
                </p>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between rounded-[24px] bg-slate-50 px-4 py-4 dark:bg-slate-900">
                  <div className="flex items-center gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100">
                      {theme === 'dark' ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">Тема интерфейса</div>
                      <div className="text-sm text-slate-500 dark:text-slate-300">Переключение локального режима</div>
                    </div>
                  </div>
                  <ThemeToggle
                    theme={theme}
                    onToggle={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                  />
                </div>

                <div className="flex items-center justify-between rounded-[24px] bg-slate-50 px-4 py-4 dark:bg-slate-900">
                  <div className="flex items-center gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100">
                      <SettingsIcon className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-slate-900 dark:text-slate-50">Язык интерфейса</div>
                      <div className="text-sm text-slate-500 dark:text-slate-300">Текущая локаль браузера</div>
                    </div>
                  </div>
                  <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">Русский</div>
                </div>

                <div className="rounded-[24px] border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
                  Следующий логичный этап здесь: настройки уведомлений, помощь и управление
                  безопасностью аккаунта.
                </div>

                <button
                  onClick={handleLogout}
                  className="flex w-full items-center justify-center gap-2 rounded-2xl bg-red-500 px-4 py-3 text-sm font-semibold text-white transition hover:bg-red-600"
                >
                  <LogOut className="h-4 w-4" />
                  Выйти из аккаунта
                </button>
              </div>
            </section>
          </div>
        </main>
      </div>
    </div>
  );

  if (isDesktopBrowser) {
    return renderDesktopBrowserLayout();
  }

  const isCompactBrowserLayout = !isTelegramWebApp;

  return (
    <div
      className={`min-h-screen ${
        isCompactBrowserLayout
          ? 'bg-[linear-gradient(180deg,#eef4ff_0%,#f8fafc_45%,#eef2f7_100%)] sm:px-4 sm:py-6 md:px-6 md:py-8 dark:bg-[linear-gradient(180deg,#0f172a_0%,#111827_45%,#020617_100%)]'
          : 'bg-[var(--tg-theme-bg-color,#ffffff)]'
      }`}
    >
      <Toaster position="top-center" />
      <TopUpModal
        isOpen={isTopUpModalOpen}
        onClose={() => setIsTopUpModalOpen(false)}
        onTopUp={handleTopUpAmount}
      />

      <div
        className={`${
          isCompactBrowserLayout
            ? 'relative flex min-h-screen w-full flex-col bg-[var(--tg-theme-bg-color,#ffffff)] sm:mx-auto sm:min-h-[calc(100vh-3rem)] sm:max-w-[440px] sm:overflow-hidden sm:rounded-[30px] sm:border sm:border-white/70 sm:shadow-[0_28px_80px_rgba(15,23,42,0.16)] sm:backdrop-blur'
            : 'min-h-screen bg-[var(--tg-theme-bg-color,#ffffff)]'
        }`}
      >
        <Header
          user={{ name: user.name, avatar: user.avatar }}
          balance={user.balance}
          onTopUp={handleTopUp}
        />
        <main className="flex-1 pb-24">{renderContent()}</main>
        <BottomNav activeTab={activeTab} onTabChange={setActiveTab} compact={isCompactBrowserLayout} />
      </div>
    </div>
  );
}
