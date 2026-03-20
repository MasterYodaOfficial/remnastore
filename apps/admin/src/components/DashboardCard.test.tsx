// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DashboardCard } from "./DashboardCard";

afterEach(() => {
  cleanup();
});

describe("DashboardCard", () => {
  it("renders the label, value, and hint for a dashboard metric", () => {
    render(
      <DashboardCard
        label="Пользователи"
        value={128}
        hint="всего локальных аккаунтов"
      />,
    );

    expect(screen.getByText("Пользователи")).toBeInTheDocument();
    expect(screen.getByText("128")).toBeInTheDocument();
    expect(screen.getByText("всего локальных аккаунтов")).toBeInTheDocument();
  });
});
