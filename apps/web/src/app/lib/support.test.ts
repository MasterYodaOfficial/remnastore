import { describe, expect, it } from 'vitest';

import { buildSupportEmailDraft, buildSupportMailtoUrl } from './support';

describe('buildSupportEmailDraft', () => {
  it('includes user and subscription details in the preset email body', () => {
    const draft = buildSupportEmailDraft({
      browserBrandName: 'QuickCloud',
      user: {
        id: 'acc-123',
        name: 'Иван Иванов',
        email: 'ivan@example.com',
        telegramId: 123456789,
      },
      subscription: {
        status: 'ACTIVE',
        isTrial: false,
        expiresAt: '2026-04-22T15:30:00Z',
      },
    });

    expect(draft.subject).toBe('QuickCloud: обращение в поддержку');
    expect(draft.body).toContain('Пользователь: Иван Иванов');
    expect(draft.body).toContain('Email аккаунта: ivan@example.com');
    expect(draft.body).toContain('Telegram ID: 123456789');
    expect(draft.body).toContain('ID аккаунта: acc-123');
    expect(draft.body).toContain('Статус подписки: Активна');
    expect(draft.body).toContain('Подписка действует до: 22.04.2026, 15:30 UTC');
    expect(draft.body).toContain('Опишите, пожалуйста, проблему:');
  });

  it('falls back to placeholders when account details are missing', () => {
    const draft = buildSupportEmailDraft({});

    expect(draft.subject).toBe('QuickCloud: обращение в поддержку');
    expect(draft.body).toContain('Пользователь: Не указано');
    expect(draft.body).toContain('Статус подписки: Не указано');
  });
});

describe('buildSupportMailtoUrl', () => {
  it('builds a mailto link with encoded draft params', () => {
    const url = buildSupportMailtoUrl({
      supportEmail: 'support+web@example.com',
      browserBrandName: 'QuickCloud',
      user: {
        name: 'Иван Иванов',
      },
    });

    const [target, query = ''] = url.split('?');
    const params = new URLSearchParams(query);

    expect(target).toBe('mailto:support+web@example.com');
    expect(query).toContain('%20');
    expect(query).not.toContain('+');
    expect(params.get('subject')).toBe('QuickCloud: обращение в поддержку');
    expect(params.get('body')).toContain('Пользователь: Иван Иванов');
  });

  it('returns an empty string when support email is not configured', () => {
    expect(buildSupportMailtoUrl({ supportEmail: '   ' })).toBe('');
  });
});
