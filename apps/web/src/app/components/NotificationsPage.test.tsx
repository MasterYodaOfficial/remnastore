// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NotificationsPage, type NotificationItemView } from "./NotificationsPage";

afterEach(() => {
  cleanup();
});

function createNotification(id: number): NotificationItemView {
  return {
    id,
    type: "payment_succeeded",
    title: `Уведомление ${id}`,
    body: `Тело уведомления ${id}`,
    priority: "info",
    isRead: id % 2 === 0,
    createdAt: `2026-06-${String((id % 28) + 1).padStart(2, "0")}T10:00:00Z`,
  };
}

describe("NotificationsPage", () => {
  it("shows only the latest 20 notifications by default and expands buffered items locally", () => {
    const onLoadMore = vi.fn();
    const items = Array.from({ length: 25 }, (_, index) => createNotification(index + 1));
    const { container } = render(
      <NotificationsPage
        items={items}
        total={25}
        unreadCount={13}
        isLoading={false}
        onMarkRead={vi.fn()}
        onMarkAllRead={vi.fn()}
        onLoadMore={onLoadMore}
      />,
    );

    expect(container.querySelectorAll("article")).toHaveLength(20);
    expect(screen.queryByText("Уведомление 21")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Показать ещ[её]/ }));

    expect(container.querySelectorAll("article")).toHaveLength(25);
    expect(screen.getByText("Уведомление 21")).toBeInTheDocument();
    expect(onLoadMore).not.toHaveBeenCalled();
  });

  it("requests the next page when only the first chunk is loaded", () => {
    const onLoadMore = vi.fn();
    render(
      <NotificationsPage
        items={Array.from({ length: 20 }, (_, index) => createNotification(index + 1))}
        total={45}
        unreadCount={12}
        isLoading={false}
        onMarkRead={vi.fn()}
        onMarkAllRead={vi.fn()}
        onLoadMore={onLoadMore}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Показать ещ[её]/ }));

    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });
});
