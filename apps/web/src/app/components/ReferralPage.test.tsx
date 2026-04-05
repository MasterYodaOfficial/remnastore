// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReferralPage } from "./ReferralPage";

afterEach(() => {
  cleanup();
});

describe("ReferralPage", () => {
  it("renders the overall count separately from the filtered feed total", () => {
    render(
      <ReferralPage
        referralCode="ALICE123"
        referrals={[
          {
            id: "ref-1",
            name: "alice@example.com",
            date: "2026-04-01T09:00:00Z",
            earned: 200,
            status: "active",
          },
        ]}
        referralsTotal={1200}
        filteredTotal={35}
        activeFilter="active"
        totalEarnings={340}
        availableForWithdraw={200}
        minimumWithdrawalAmount={300}
        rewardRate={20}
        withdrawals={[]}
        withdrawalsTotal={0}
        copied={false}
        onFilterChange={vi.fn()}
        onLoadMore={vi.fn()}
        onCopyLink={vi.fn()}
        onShareTelegram={vi.fn()}
        onWithdraw={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "Ваши рефералы (1200)" })).toBeInTheDocument();
    expect(screen.getByText("Показаны 1 из 35")).toBeInTheDocument();
  });

  it("calls the filter callback when the user switches tabs", () => {
    const onFilterChange = vi.fn();

    render(
      <ReferralPage
        referralCode="ALICE123"
        referrals={[]}
        referralsTotal={12}
        activeFilter="all"
        totalEarnings={340}
        availableForWithdraw={0}
        minimumWithdrawalAmount={300}
        rewardRate={20}
        withdrawals={[]}
        withdrawalsTotal={0}
        copied={false}
        onFilterChange={onFilterChange}
        onLoadMore={vi.fn()}
        onCopyLink={vi.fn()}
        onShareTelegram={vi.fn()}
        onWithdraw={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "С покупкой" }));

    expect(onFilterChange).toHaveBeenCalledWith("active");
  });

  it("shows the loading-more state for paginated feed actions", () => {
    render(
      <ReferralPage
        referralCode="ALICE123"
        referrals={[
          {
            id: "ref-1",
            name: "alice@example.com",
            date: "2026-04-01T09:00:00Z",
            earned: 0,
            status: "pending",
          },
        ]}
        referralsTotal={12}
        filteredTotal={24}
        activeFilter="all"
        totalEarnings={340}
        availableForWithdraw={0}
        minimumWithdrawalAmount={300}
        rewardRate={20}
        withdrawals={[]}
        withdrawalsTotal={0}
        copied={false}
        isLoadingMore
        hasMore
        onFilterChange={vi.fn()}
        onLoadMore={vi.fn()}
        onCopyLink={vi.fn()}
        onShareTelegram={vi.fn()}
        onWithdraw={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Загружаем еще..." })).toBeDisabled();
  });
});
