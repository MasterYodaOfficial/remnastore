import { describe, expect, it } from "vitest";

import {
  formatAccountIdentity,
  formatCompactId,
  parseManualAudienceTargetsInput,
  parseOptionalIntegerInput,
} from "./admin-helpers";

describe("parseOptionalIntegerInput", () => {
  it("returns null for blank input", () => {
    expect(parseOptionalIntegerInput("   ", 1, "Поле")).toBeNull();
  });

  it("parses an integer that satisfies the minimum", () => {
    expect(parseOptionalIntegerInput("42", 1, "Поле")).toBe(42);
  });

  it("throws a readable validation error for invalid input", () => {
    expect(() => parseOptionalIntegerInput("0.5", 1, "Лимит")).toThrow(
      "Лимит должно быть целым числом не меньше 1",
    );
  });
});

describe("parseManualAudienceTargetsInput", () => {
  it("normalizes and deduplicates supported target kinds", () => {
    const parsed = parseManualAudienceTargetsInput(`
      account_id
      6F9619FF-8B86-D011-B42D-00CF4FC964FF
      "6f9619ff-8b86-d011-b42d-00cf4fc964ff"
      EMAIL
      User@Example.COM
      user@example.com
      telegram_id
      123456
      123456
      -777
    `);

    expect(parsed).toEqual({
      manualAccountIds: ["6f9619ff-8b86-d011-b42d-00cf4fc964ff"],
      manualEmails: ["user@example.com"],
      manualTelegramIds: [123456, -777],
    });
  });

  it("throws when an unsupported token appears in the manual list", () => {
    expect(() => parseManualAudienceTargetsInput("not-an-identifier")).toThrow(
      "Не удалось распознать идентификатор из списка: not-an-identifier. Используйте account_id, email или telegram_id.",
    );
  });
});

describe("formatCompactId", () => {
  it("shortens long identifiers", () => {
    expect(formatCompactId("1234567890abcdef")).toBe("12345678...cdef");
  });

  it("returns a dash for missing identifiers", () => {
    expect(formatCompactId(null)).toBe("-");
  });
});

describe("formatAccountIdentity", () => {
  it("prefers human-friendly fields in order", () => {
    expect(
      formatAccountIdentity({
        display_name: "Иван",
        username: "ivan",
        email: "ivan@example.com",
        account_id: "acc-1",
      }),
    ).toBe("Иван");

    expect(
      formatAccountIdentity({
        username: "ivan",
        email: "ivan@example.com",
      }),
    ).toBe("ivan");
  });

  it("falls back to a placeholder when identity is empty", () => {
    expect(formatAccountIdentity({})).toBe("Пользователь без имени");
  });
});
