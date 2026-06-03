// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BalanceHistoryPage, type BalanceHistoryItemView } from "./BalanceHistoryPage";

afterEach(() => {
  cleanup();
});

function createLedgerEntry(id: number): BalanceHistoryItemView {
  return {
    id,
    entryType: id % 2 === 0 ? "topup_payment" : "subscription_debit",
    amount: id % 2 === 0 ? 100 : -100,
    balanceAfter: 10_000 - id * 100,
    createdAt: `2026-05-${String((id % 28) + 1).padStart(2, "0")}T10:00:00Z`,
  };
}

describe("BalanceHistoryPage", () => {
  it("shows only the first 20 balance history items by default and expands buffered items locally", () => {
    const onLoadMore = vi.fn();
    const { container } = render(
      <BalanceHistoryPage
        items={Array.from({ length: 24 }, (_, index) => createLedgerEntry(index + 1))}
        total={24}
        isLoading={false}
        onBack={vi.fn()}
        onLoadMore={onLoadMore}
      />,
    );

    expect(container.querySelectorAll("article")).toHaveLength(20);

    fireEvent.click(screen.getByRole("button", { name: /Показать ещ[её]/ }));

    expect(container.querySelectorAll("article")).toHaveLength(24);
    expect(onLoadMore).not.toHaveBeenCalled();
  });

  it("requests the next balance history page when only the first chunk is loaded", () => {
    const onLoadMore = vi.fn();
    render(
      <BalanceHistoryPage
        items={Array.from({ length: 20 }, (_, index) => createLedgerEntry(index + 1))}
        total={41}
        isLoading={false}
        onBack={vi.fn()}
        onLoadMore={onLoadMore}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Показать ещ[её]/ }));

    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });
});
