// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DetailFact } from "./DetailFact";

afterEach(() => {
  cleanup();
});

describe("DetailFact", () => {
  it("renders the label and value for a detail row", () => {
    render(<DetailFact label="Баланс" value="1 250 ₽" />);

    expect(screen.getByText("Баланс")).toBeInTheDocument();
    expect(screen.getByText("1 250 ₽")).toBeInTheDocument();
  });
});
