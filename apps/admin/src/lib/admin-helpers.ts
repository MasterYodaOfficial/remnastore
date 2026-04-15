import { t } from "./i18n";

export type AccountIdentityLike = {
  account_id?: string | null;
  id?: string | null;
  display_name?: string | null;
  username?: string | null;
  email?: string | null;
};

export type ParsedManualAudienceTargets = {
  manualAccountIds: string[];
  manualEmails: string[];
  manualTelegramIds: number[];
};

const MANUAL_AUDIENCE_HEADER_TOKENS = new Set([
  "account_id",
  "accountid",
  "email",
  "telegram_id",
  "telegramid",
  "tg_id",
  "tgid",
]);

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/i;

export function formatCompactId(value: string | null): string {
  if (!value) {
    return "-";
  }
  if (value.length <= 14) {
    return value;
  }
  return `${value.slice(0, 8)}...${value.slice(-4)}`;
}

export function parseOptionalIntegerInput(
  value: string,
  minimum: number,
  fieldLabel: string,
): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  const parsed = Number(trimmed);
  if (!Number.isInteger(parsed) || parsed < minimum) {
    throw new Error(t("admin.helpers.integerMin", { fieldLabel, minimum }));
  }
  return parsed;
}

export function parseManualAudienceTargetsInput(value: string): ParsedManualAudienceTargets {
  const tokens = value
    .split(/[\s,;]+/g)
    .map((item) => item.trim().replace(/^["']+|["']+$/g, ""))
    .filter(Boolean)
    .filter((item) => !MANUAL_AUDIENCE_HEADER_TOKENS.has(item.toLowerCase()));

  const manualAccountIds: string[] = [];
  const manualEmails: string[] = [];
  const manualTelegramIds: number[] = [];
  const seenAccountIds = new Set<string>();
  const seenEmails = new Set<string>();
  const seenTelegramIds = new Set<number>();

  for (const token of tokens) {
    if (UUID_PATTERN.test(token)) {
      const normalized = token.toLowerCase();
      if (!seenAccountIds.has(normalized)) {
        seenAccountIds.add(normalized);
        manualAccountIds.push(normalized);
      }
      continue;
    }
    if (EMAIL_PATTERN.test(token)) {
      const normalized = token.toLowerCase();
      if (!seenEmails.has(normalized)) {
        seenEmails.add(normalized);
        manualEmails.push(normalized);
      }
      continue;
    }
    if (/^-?\d+$/.test(token)) {
      const normalized = Number.parseInt(token, 10);
      if (!seenTelegramIds.has(normalized)) {
        seenTelegramIds.add(normalized);
        manualTelegramIds.push(normalized);
      }
      continue;
    }
    throw new Error(
      t("admin.helpers.manualAudienceTokenInvalid", { token }),
    );
  }

  return {
    manualAccountIds,
    manualEmails,
    manualTelegramIds,
  };
}

export function formatAccountIdentity(account: AccountIdentityLike): string {
  return (
    account.display_name ||
    account.username ||
    account.email ||
    account.account_id ||
    account.id ||
    t("admin.helpers.unnamedAccount")
  );
}
