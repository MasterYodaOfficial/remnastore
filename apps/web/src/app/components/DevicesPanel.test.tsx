// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { DevicesPanel } from './DevicesPanel';
import { DeviceRenewalOptions } from './DeviceRenewalOptions';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('requires confirmation to remove a device and quotes before charging the wallet', async () => {
  const requests: string[] = [];
  const fetchMock = vi.fn(async (input: string) => {
    requests.push(input);
    if (input.endsWith('/remove')) return new Response(null, { status: 204 });
    if (input.endsWith('/quote')) return Response.json({ quantity: 1, amount_rub: 45, limit: 4, expires_at: '2027-01-01T00:00:00Z', quote_token: 'signed' });
    if (input.endsWith('/purchase')) return Response.json({ applied: true, refunded: false });
    return Response.json({ base_limit: 3, extra_count: 0, renewal_extra_count: 0, limit: 3, devices: [{ hwid: 'private-id', device_model: 'iPhone', platform: 'iOS' }], expires_at: '2027-01-01T00:00:00Z', can_purchase: true, sync_pending: false, is_active: true });
  });
  vi.stubGlobal('fetch', fetchMock);
  render(<DevicesPanel apiBase="https://api.test" accessToken="token" balance={100} onChanged={vi.fn().mockResolvedValue(undefined)} onConnect={vi.fn()} onTopUp={vi.fn()} />);
  expect(fetchMock).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: /Устройства/ }));
  expect(await screen.findByText('iPhone')).toBeInTheDocument();
  expect(screen.queryByText('private-id')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));
  expect(screen.getByRole('alertdialog')).toBeInTheDocument();
  expect(requests.some((url) => url.endsWith('/remove'))).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));
  await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  fireEvent.click(screen.getByRole('button', { name: 'Рассчитать стоимость' }));
  const payButton = await screen.findByRole('button', { name: 'Оплатить 45 ₽ с баланса' });
  expect(requests.some((url) => url.endsWith('/purchase'))).toBe(false);
  fireEvent.click(payButton);
  await waitFor(() => expect(requests.filter((url) => url.endsWith('/purchase'))).toHaveLength(1));
  const call = fetchMock.mock.calls.find(([url]) => url.endsWith('/purchase'));
  expect(call).toBeDefined();
});

it('shows the common expiry, total charge and downgrade refund before renewal', () => {
  const onCountChange = vi.fn();
  render(<DeviceRenewalOptions quote={{ extra_devices: 1, extra_device_price_rub: 50, extra_amount_rub: 50, base_amount_rub: 199, total_amount_rub: 249, refund_rub: 90, expires_at: '2027-01-01T00:00:00Z', base_limit: 3, limit: 4 }} error={null} onCountChange={onCountChange} />);
  expect(screen.getByText('Итого: 249 ₽')).toBeInTheDocument();
  expect(screen.getByText(/вернётся 90 ₽/)).toBeInTheDocument();
  expect(screen.getByText(/до 1 января 2027/)).toBeInTheDocument();
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '0' } });
  expect(onCountChange).toHaveBeenCalledWith(0);
});

it('keeps the confirmed limit during an outage without claiming the device list is empty', async () => {
  let offline = true;
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({
    base_limit: offline ? 3 : 5, extra_count: 1, renewal_extra_count: 1,
    limit: offline ? 4 : 6, devices: offline ? null : [{ hwid: 'phone', device_model: 'iPhone' }],
    expires_at: '2027-01-01T00:00:00Z', can_purchase: !offline, sync_pending: false, is_active: true,
    limit_sync_status: offline ? 'unavailable' : 'synced', panel_limit: offline ? null : 6,
  })));
  render(<DevicesPanel apiBase="https://api.test" accessToken="token" balance={100} onChanged={vi.fn().mockResolvedValue(undefined)} onConnect={vi.fn()} onTopUp={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: /Устройства/ }));
  expect(await screen.findByText(/последний подтверждённый лимит/)).toBeVisible();
  expect(screen.getByText('Лимит устройств: 4')).toBeVisible();
  expect(screen.queryByText(/Устройств пока нет/)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Рассчитать стоимость' })).not.toBeInTheDocument();
  expect(screen.getByRole('combobox')).toBeDisabled();
  offline = false;
  fireEvent.click(screen.getByRole('button', { name: 'Обновить' }));
  expect(await screen.findByText('Добавлено 1 из 6')).toBeVisible();
  expect(screen.queryByText(/последний подтверждённый лимит/)).not.toBeInTheDocument();
});

it('explains a panel limit conflict and prevents another purchase', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => Response.json({
    base_limit: 3, extra_count: 2, renewal_extra_count: 2, limit: 5,
    devices: [], expires_at: '2027-01-01T00:00:00Z', can_purchase: false,
    sync_pending: false, is_active: true, limit_sync_status: 'conflict', panel_limit: 1,
  })));
  render(<DevicesPanel apiBase="https://api.test" accessToken="token" balance={100} onChanged={vi.fn().mockResolvedValue(undefined)} onConnect={vi.fn()} onTopUp={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: /Устройства/ }));
  expect(await screen.findByRole('alert')).toHaveTextContent('В панели установлен лимит 1');
  expect(screen.getByRole('alert')).toHaveTextContent('Оплаченные права сохранены');
  expect(screen.queryByRole('button', { name: 'Рассчитать стоимость' })).not.toBeInTheDocument();
  expect(screen.getByRole('combobox')).toBeDisabled();
});
