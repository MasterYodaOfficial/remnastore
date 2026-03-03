import React, { useEffect, useState } from 'react';
import { supabase } from '../../utils/supabase/client';
import { projectId, publicAnonKey } from '../../utils/supabase/info';
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

const API_BASE = `https://${projectId}.supabase.co/functions/v1/make-server-0ad4a249`;
const BACKEND_API = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(
  /\/+$/,
  ""
);

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

      // upsert + fetch fresh data
      let apiUser: any = null;
      try {
        const upsertResp = await fetch(`${BACKEND_API}/api/v1/accounts/telegram`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            telegram_id: telegramUser.id,
            username: telegramUser.username,
            first_name: telegramUser.first_name,
            last_name: telegramUser.last_name,
            is_premium: Boolean(telegramUser.is_premium),
            locale: telegramUser.language_code,
            last_login_source: 'telegram_webapp',
          }),
        });
        if (upsertResp.ok) {
          const resp = await fetch(
            `${BACKEND_API}/api/v1/accounts/me?telegram_id=${telegramUser.id}`
          );
          if (resp.ok) {
            apiUser = await resp.json();
          }
        }
      } catch {
        /* ignore */
      }

      const balance = apiUser?.balance_cents ?? 0;
      const referralCode = apiUser?.referral_code || '';
      const referralsCount = apiUser?.referrals_count || 0;
      const earnings = apiUser?.referral_earnings_cents ?? 0;

      setUser({
        id: String(telegramUser.id),
        name: telegramUser.first_name || 'Telegram User',
        email: `telegram_${telegramUser.id}@vpn.service`,
        balance,
        referralCode,
        referralsCount,
        earnings,
        hasUsedTrial: false,
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
        setAccessToken(session.access_token);
        await loadUserData(session.access_token);
        setIsAuthenticated(true);
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
        if (event === 'SIGNED_IN' && session?.access_token) {
          setAccessToken(session.access_token);
          await loadUserData(session.access_token);
          setIsAuthenticated(true);
        } else if (event === 'SIGNED_OUT') {
          setIsAuthenticated(false);
          setUser(null);
          setAccessToken(null);
        }
      }
    );

    return () => {
      authListener.subscription.unsubscribe();
    };
  }, []);

  const loadUserData = async (token: string) => {
    try {
      // Load user profile
      const profileResponse = await fetch(`${API_BASE}/profile`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (profileResponse.ok) {
        const { user: userData } = await profileResponse.json();
        setUser(userData);
      }

      // Load subscription
      const subResponse = await fetch(`${API_BASE}/subscription`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (subResponse.ok) {
        const { subscription: subData } = await subResponse.json();
        setSubscription(subData);
      }

      // Load plans
      const plansResponse = await fetch(`${API_BASE}/plans`, {
        headers: {
          Authorization: `Bearer ${publicAnonKey}`,
        },
      });
      if (plansResponse.ok) {
        const { plans: plansData } = await plansResponse.json();
        setPlans(plansData);
      }
    } catch (err) {
      console.error('Error loading user data:', err);
    }
  };

  const handleTopUp = async () => {
    setIsTopUpModalOpen(true);
  };

  const handleTopUpAmount = async (amount: number) => {
    if (!accessToken) return;
    
    toast.promise(
      fetch(`${API_BASE}/balance/add`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ amount }),
      }).then(async (res) => {
        if (res.ok) {
          const { balance } = await res.json();
          setUser((prev) => prev ? { ...prev, balance } : null);
          return balance;
        }
        throw new Error('Failed to top up');
      }),
      {
        loading: 'Пополнение баланса...',
        success: (balance) => `Баланс пополнен! Новый баланс: ${balance} ₽`,
        error: 'Ошибка пополнения баланса',
      }
    );
  };

  const handleActivateTrial = async () => {
    if (!accessToken) return;

    toast.promise(
      fetch(`${API_BASE}/subscription/trial`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      }).then(async (res) => {
        if (res.ok) {
          await loadUserData(accessToken);
          return true;
        }
        const error = await res.json();
        throw new Error(error.error);
      }),
      {
        loading: 'Активация пробного периода...',
        success: 'Пробный период активирован на 7 дней!',
        error: (err) => err.message || 'Ошибка активации',
      }
    );
  };

  const handleBuyPlan = async (planId: string) => {
    if (!accessToken) return;

    toast.promise(
      fetch(`${API_BASE}/plans/buy`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ planId }),
      }).then(async (res) => {
        if (res.ok) {
          await loadUserData(accessToken);
          return true;
        }
        const error = await res.json();
        throw new Error(error.error);
      }),
      {
        loading: 'Покупка подписки...',
        success: 'Подписка успешно куплена!',
        error: (err) => err.message || 'Ошибка покупки',
      }
    );
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

    toast.promise(
      fetch(`${API_BASE}/referrals/withdraw`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      }).then(async (res) => {
        if (res.ok) {
          await loadUserData(accessToken);
          const { withdrawn } = await res.json();
          return withdrawn;
        }
        const error = await res.json();
        throw new Error(error.error);
      }),
      {
        loading: 'Вывод средств...',
        success: (amount) => `${amount} ₽ переведено на баланс!`,
        error: (err) => err.message || 'Ошибка вывода',
      }
    );
  };

  const handleLogout = async () => {
    await supabase.auth.signOut();
    setIsAuthenticated(false);
    setUser(null);
    setAccessToken(null);
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

  return (
    <div className="min-h-screen bg-[var(--tg-theme-bg-color,#ffffff)]">
      <Toaster position="top-center" />
      <TopUpModal
        isOpen={isTopUpModalOpen}
        onClose={() => setIsTopUpModalOpen(false)}
        onTopUp={handleTopUpAmount}
      />
      <Header user={{ name: user.name, avatar: user.avatar }} balance={user.balance} onTopUp={handleTopUp} />
      <main>{renderContent()}</main>
      <BottomNav activeTab={activeTab} onTabChange={setActiveTab} />
    </div>
  );
}
