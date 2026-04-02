// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Header } from "./Header";

afterEach(() => {
  cleanup();
});

describe("Header", () => {
  it("renders user info, balance, and top-up action", () => {
    render(
      <Header
        user={{ name: "Alice" }}
        balance={1250}
        onTopUp={vi.fn()}
      />,
    );

    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText(/1.?250 ₽/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Пополнить" }),
    ).toBeInTheDocument();
  });

  it("shows notification badge and calls both header actions", () => {
    const onTopUp = vi.fn();
    const onOpenNotifications = vi.fn();

    render(
      <Header
        user={{ name: "Alice" }}
        balance={500}
        onTopUp={onTopUp}
        onOpenNotifications={onOpenNotifications}
        unreadNotificationsCount={120}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Открыть уведомления" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Пополнить" }));

    expect(screen.getByText("99+")).toBeInTheDocument();
    expect(onOpenNotifications).toHaveBeenCalledTimes(1);
    expect(onTopUp).toHaveBeenCalledTimes(1);
  });
});
