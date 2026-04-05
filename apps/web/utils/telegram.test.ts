// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getTelegramWebApp, hasTelegramLaunchParams, loadTelegramScript } from './telegram';

const TELEGRAM_SCRIPT_URL = 'https://telegram.org/js/telegram-web-app.js';
const TELEGRAM_FALLBACK_SCRIPT_URL = '/vendor/telegram-web-app.js';

describe('telegram utils', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/');
    delete window.Telegram;
    delete (
      globalThis as typeof globalThis & {
        __REMNASTORE_RUNTIME_CONFIG__?: Record<string, string>;
      }
    ).__REMNASTORE_RUNTIME_CONFIG__;
    document
      .querySelectorAll('script')
      .forEach((element) => element.remove());
    vi.restoreAllMocks();
  });

  it('detects Telegram launch params in the URL hash', () => {
    expect(hasTelegramLaunchParams()).toBe(false);

    window.location.hash = '#tgWebAppPlatform=ios&tgWebAppData=user%3D%257B%2522id%2522%253A1%257D';

    expect(hasTelegramLaunchParams()).toBe(true);
  });

  it('builds a fallback Telegram WebApp object from launch params', () => {
    window.location.hash =
      '#tgWebAppPlatform=ios&tgWebAppData=user%3D%257B%2522id%2522%253A123%252C%2522photo_url%2522%253A%2522https%253A%252F%252Fexample.com%252Fphoto.jpg%2522%257D&tgWebAppThemeParams=%7B%22bg_color%22%3A%22%23000000%22%7D';

    expect(getTelegramWebApp()).toEqual({
      initData: 'user=%7B%22id%22%3A123%2C%22photo_url%22%3A%22https%3A%2F%2Fexample.com%2Fphoto.jpg%22%7D',
      initDataUnsafe: {
        user: {
          id: 123,
          photo_url: 'https://example.com/photo.jpg',
        },
      },
      platform: 'ios',
      colorScheme: 'dark',
      expand: expect.any(Function),
      onEvent: expect.any(Function),
      offEvent: expect.any(Function),
    });
  });

  it('returns false when the Telegram script fails to load', async () => {
    const originalAppendChild = document.head.appendChild.bind(document.head);

    vi.spyOn(document.head, 'appendChild').mockImplementation((node) => {
      const appendedNode = originalAppendChild(node);
      setTimeout(() => {
        node.dispatchEvent(new Event('error'));
      }, 0);
      return appendedNode;
    });

    await expect(loadTelegramScript()).resolves.toBe(false);
  });

  it('falls back to the self-hosted Telegram script when the primary URL fails', async () => {
    const appendedScriptUrls: string[] = [];
    const originalAppendChild = document.head.appendChild.bind(document.head);

    vi.spyOn(document.head, 'appendChild').mockImplementation((node) => {
      const appendedNode = originalAppendChild(node);
      if (node instanceof HTMLScriptElement) {
        appendedScriptUrls.push(node.src);
        setTimeout(() => {
          if (node.src === TELEGRAM_SCRIPT_URL) {
            node.dispatchEvent(new Event('error'));
            return;
          }

          window.Telegram = {
            WebApp: {
              initData: 'tg-init-data',
            },
          };
          node.dispatchEvent(new Event('load'));
        }, 0);
      }
      return appendedNode;
    });

    await expect(loadTelegramScript()).resolves.toBe(true);
    expect(appendedScriptUrls).toEqual([
      TELEGRAM_SCRIPT_URL,
      `${window.location.origin}${TELEGRAM_FALLBACK_SCRIPT_URL}`,
    ]);
    expect(window.Telegram?.WebApp?.initData).toBe('tg-init-data');
  });
});
