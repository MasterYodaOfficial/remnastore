// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PromoRedeemCard } from "./PromoRedeemCard";

afterEach(() => {
  cleanup();
});

describe("PromoRedeemCard", () => {
  it("renders localized copy and keeps submit disabled for blank input", () => {
    const onCodeChange = vi.fn();

    render(
      <PromoRedeemCard
        code=""
        onCodeChange={onCodeChange}
        onRedeem={vi.fn()}
      />,
    );

    expect(screen.getByText("Активировать промокод")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Если код подходит, доступ или баланс обновятся сразу без отдельной оплаты.",
      ),
    ).toBeInTheDocument();

    const input = screen.getByPlaceholderText("Введите код");
    const button = screen.getByRole("button", { name: "Активировать" });

    expect(button).toBeDisabled();

    fireEvent.change(input, { target: { value: " spring20 " } });

    expect(onCodeChange).toHaveBeenCalledWith(" spring20 ");
  });

  it("renders a custom message and allows redeem when a code is present", () => {
    const onRedeem = vi.fn();

    render(
      <PromoRedeemCard
        code="SPRING20"
        onCodeChange={vi.fn()}
        onRedeem={onRedeem}
        message={{ tone: "success", text: "Код применен." }}
      />,
    );

    const button = screen.getByRole("button", { name: "Активировать" });

    expect(button).toBeEnabled();
    expect(screen.getByText("Код применен.")).toBeInTheDocument();

    fireEvent.click(button);

    expect(onRedeem).toHaveBeenCalledTimes(1);
  });

  it("shows submitting state with the loading label", () => {
    render(
      <PromoRedeemCard
        code="SPRING20"
        onCodeChange={vi.fn()}
        onRedeem={vi.fn()}
        isSubmitting
      />,
    );

    expect(
      screen.getByRole("button", { name: "Активируем код..." }),
    ).toBeDisabled();
  });
});
