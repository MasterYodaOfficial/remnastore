import React, { useEffect, useRef, useState } from 'react';
import { supabase } from '../../utils/supabase/client';
import { loadTelegramScript, getTelegramWebApp } from '../../utils/telegram';
import { LoginPage } from './components/LoginPage';
import { Header } from './components/Header';
import { HomePage } from './components/HomePage';
import { PlansPage } from './components/PlansPage';
import { ReferralPage } from './components/ReferralPage';
import { SettingsPage } from './components/SettingsPage';
import { BottomNav } from './components/BottomNav';
import { TopUpModal } from './components/TopUpModal';
import { LoadingScreen } from './components/LoadingScreen';
import { toast, Toaster } from 'sonner';

const BACKEND_API = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(
  /\/+$/,
  ""
);
const BROWSER_TOKEN_STORAGE_KEY = 'remnastore.browser_access_token';

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

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isTelegramWebApp, setIsTelegramWebApp] = useState(false);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [activeTab, setActiveTab] = useState('home');
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [referralCopied, setReferralCopied] = useState(false);
  const [isTopUpModalOpen, setIsTopUpModalOpen] = useState(false);
  const lastLoadedBrowserTokenRef = useRef<string | null>(null);
  const inFlightBrowserTokenRef = useRef<string | null>(null);
  const currentBrowserTokenRef = useRef<string | null>(null);
  const manualLogoutRef = useRef(false);

  // Check if running in Telegram WebApp
  useEffect(() => {
    const initApp = async () => {
      // Load Telegram script first
      await loadTelegramScript();
      
      const tg = getTelegramWebApp();
      if (tg && tg.initData) {
        setIsTelegramWebApp(true);
        // Apply Telegram theme
        if (tg.colorScheme === 'dark') {
          setTheme('dark');
        }
        // Expand the WebApp to full height
        tg.expand();
        // Auto-authenticate Telegram users
        handleTelegramAuth(tg);
      } else {
        setIsTelegramWebApp(false);
        checkSupabaseAuth();
      }
    };

    initApp();
  }, []);

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
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (session?.access_token) {
        await syncBrowserAuth(session.access_token);
      } else {
        const cachedToken = window.sessionStorage.getItem(BROWSER_TOKEN_STORAGE_KEY);
        if (cachedToken) {
          await syncBrowserAuth(cachedToken);
        }
      }
    } catch (err) {
      console.error('Auth check error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // Listen for auth changes
  useEffect(() => {
    const { data: authListener } = supabase.auth.onAuthStateChange(
      async (event, session) => {
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
    window.sessionStorage.removeItem(BROWSER_TOKEN_STORAGE_KEY);
  };

  const syncBrowserAuth = async (token: string) => {
    if (!token) {
      return false;
    }

    setAccessToken(token);
    currentBrowserTokenRef.current = token;
    window.sessionStorage.setItem(BROWSER_TOKEN_STORAGE_KEY, token);

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
      window.sessionStorage.removeItem(BROWSER_TOKEN_STORAGE_KEY);
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
    await supabase.auth.signOut();
    clearBrowserAuthState();
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
    return <LoadingScreen />;
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--tg-theme-bg-color,#ffffff)]">
        <div className="text-[var(--tg-theme-text-color,#000000)]">Загрузка профиля...</div>
      </div>
    );
  }

  const renderContent = () => {
    switch (activeTab) {
      case 'home':
        return (
          <HomePage
            subscription={getSubscriptionData()}
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
          />
        );
      default:
        return null;
    }
  };

  const isCompactBrowserLayout = !isTelegramWebApp;

  return (
    <div
      className={`min-h-screen ${
        isCompactBrowserLayout
          ? 'bg-[linear-gradient(180deg,#eef4ff_0%,#f8fafc_45%,#eef2f7_100%)] px-4 py-6 md:px-6 md:py-8'
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
            ? 'relative mx-auto flex min-h-[calc(100vh-3rem)] w-full max-w-[440px] flex-col overflow-hidden rounded-[30px] border border-white/70 bg-[var(--tg-theme-bg-color,#ffffff)] shadow-[0_28px_80px_rgba(15,23,42,0.16)] backdrop-blur'
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
