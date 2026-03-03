import React from 'react';
import { Shield, Chrome } from 'lucide-react';
import { supabase } from '../../../utils/supabase/client';

export function LoginPage() {
  const handleGoogleLogin = async () => {
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: window.location.origin,
        },
      });
      if (error) {
        console.error('Google login error:', error);
      }
    } catch (err) {
      console.error('Failed to initiate Google login:', err);
    }
  };

  const handleYandexLogin = async () => {
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'yandex',
        options: {
          redirectTo: window.location.origin,
        },
      });
      if (error) {
        console.error('Yandex login error:', error);
      }
    } catch (err) {
      console.error('Failed to initiate Yandex login:', err);
    }
  };

  const handleVKLogin = async () => {
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'vk',
        options: {
          redirectTo: window.location.origin,
        },
      });
      if (error) {
        console.error('VK login error:', error);
      }
    } catch (err) {
      console.error('Failed to initiate VK login:', err);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--tg-theme-bg-color,#ffffff)] px-4">
      <div className="w-full max-w-md space-y-8">
        <div className="text-center space-y-4">
          <div className="flex justify-center">
            <div className="w-20 h-20 rounded-full bg-[var(--tg-theme-button-color,#3390ec)] flex items-center justify-center">
              <Shield className="w-12 h-12 text-white" />
            </div>
          </div>
          <h1 className="text-3xl font-bold text-[var(--tg-theme-text-color,#000000)]">
            VPN Service
          </h1>
          <p className="text-[var(--tg-theme-hint-color,#999999)]">
            Войдите, чтобы управлять вашими подписками
          </p>
        </div>

        <div className="space-y-4">
          <button
            onClick={handleGoogleLogin}
            className="w-full flex items-center justify-center gap-3 px-6 py-4 bg-white border-2 border-gray-200 rounded-xl hover:bg-gray-50 transition-colors text-gray-800 font-medium"
          >
            <svg className="w-6 h-6" viewBox="0 0 24 24">
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
            Продолжить с Google
          </button>

          <button
            onClick={handleYandexLogin}
            className="w-full flex items-center justify-center gap-3 px-6 py-4 bg-[#ffcc00] hover:bg-[#f5c400] rounded-xl transition-colors text-black font-medium"
          >
            <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="11" fill="#FC3F1D" />
              <path
                d="M13.5 6.5h-2.8c-2.3 0-3.5 1.2-3.5 3.2 0 1.7.8 2.7 2.3 3.3l-2.8 4.5h2.4l2.5-4.2h-.9c-1.5 0-2.4-.8-2.4-2.4 0-1.4.7-2.1 2.2-2.1h1.3v8.7h2.1V6.5h-.4z"
                fill="white"
              />
            </svg>
            Продолжить с Яндекс
          </button>

          <button
            onClick={handleVKLogin}
            className="w-full flex items-center justify-center gap-3 px-6 py-4 bg-[#0077FF] hover:bg-[#0066dd] rounded-xl transition-colors text-white font-medium"
          >
            <svg className="w-6 h-6" viewBox="0 0 24 24" fill="white">
              <path d="M12.785 16.241s.288-.032.436-.193c.136-.148.131-.425.131-.425s-.019-1.299.574-1.491c.586-.189 1.336 1.256 2.132 1.811.602.421 1.06.328 1.06.328l2.127-.03s1.112-.069.585-.96c-.043-.073-.308-.66-1.588-1.866-1.34-1.264-1.16-1.059.453-3.246.983-1.332 1.376-2.145 1.253-2.493-.117-.332-.841-.244-.841-.244l-2.396.015s-.178-.024-.309.056c-.128.078-.211.261-.211.261s-.378 1.024-.882 1.895c-1.062 1.838-1.487 1.936-1.661 1.821-.405-.267-.304-1.073-.304-1.646 0-1.786.266-2.532-.519-2.724-.261-.064-.453-.106-1.120-.113-.857-.009-1.583.003-1.994.208-.274.137-.485.442-.356.46.159.022.520.099.711.364.247.342.238 1.111.238 1.111s.142 2.104-.331 2.365c-.325.179-.770-.186-1.726-1.854-.489-.844-.859-1.778-.859-1.778s-.071-.177-.198-.272c-.154-.115-.37-.152-.37-.152l-2.276.015s-.342.010-.467.161c-.111.134-.009.411-.009.411s1.777 4.237 3.788 6.373c1.843 1.958 3.933 1.829 3.933 1.829h.949z" />
            </svg>
            Продолжить с VK
          </button>
        </div>

        <div className="text-center">
          <p className="text-xs text-[var(--tg-theme-hint-color,#999999)]">
            Нажимая кнопку входа, вы соглашаетесь с условиями использования
          </p>
        </div>
      </div>
    </div>
  );
}
