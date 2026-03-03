// Load Telegram WebApp script dynamically
export const loadTelegramScript = (): Promise<void> => {
  return new Promise((resolve) => {
    if (typeof window !== 'undefined') {
      // @ts-ignore
      if (window.Telegram?.WebApp) {
        resolve();
        return;
      }

      const script = document.createElement('script');
      script.src = 'https://telegram.org/js/telegram-web-app.js';
      script.async = true;
      script.onload = () => resolve();
      document.head.appendChild(script);
    } else {
      resolve();
    }
  });
};

// Get Telegram WebApp instance
export const getTelegramWebApp = () => {
  if (typeof window !== 'undefined') {
    // @ts-ignore
    return window.Telegram?.WebApp;
  }
  return null;
};
