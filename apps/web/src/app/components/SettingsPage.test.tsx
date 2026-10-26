// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { SettingsPage } from './SettingsPage';

afterEach(cleanup);

it('shows linked OAuth methods without requiring a contact email', () => {
  render(<SettingsPage theme="light" onThemeChange={() => {}} onLogout={() => {}} isTelegramWebApp onLinkBrowser={() => {}}
    user={{ authProviders: ['vk', 'yandex', 'supabase'] }} />);
  expect(screen.getByText('VK ID')).toBeVisible();
  expect(screen.getByText('Яндекс ID')).toBeVisible();
  expect(screen.queryByText('Google')).not.toBeInTheDocument();
  expect(screen.queryByText('Контактный email')).not.toBeInTheDocument();
  expect(screen.queryByText('Привязать браузерный вход')).not.toBeInTheDocument();
});
