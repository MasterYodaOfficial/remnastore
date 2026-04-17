import { describe, expect, it } from "vitest";

import { parseAdminApiErrorPayload } from "./api-errors";

describe("parseAdminApiErrorPayload", () => {
  it("maps invalid credentials to a stable message", () => {
    expect(
      parseAdminApiErrorPayload(
        {
          detail: "invalid admin credentials",
          error_code: "admin_invalid_credentials",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Неверный логин или пароль.",
      errorCode: "admin_invalid_credentials",
    });
  });

  it("collapses invalid session codes into a relogin message", () => {
    expect(
      parseAdminApiErrorPayload(
        {
          detail: "invalid token",
          error_code: "admin_invalid_token",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Сессия администратора недействительна. Войдите заново.",
      errorCode: "admin_invalid_token",
    });
  });

  it("falls back to backend detail for unknown codes", () => {
    expect(
      parseAdminApiErrorPayload(
        {
          detail: "custom backend detail",
          error_code: "custom_code",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "custom backend detail",
      errorCode: "custom_code",
    });
  });

  it("maps admin account errors to stable operator messages", () => {
    expect(
      parseAdminApiErrorPayload(
        {
          detail: "account not found",
          error_code: "admin_account_not_found",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Аккаунт не найден.",
      errorCode: "admin_account_not_found",
    });

    expect(
      parseAdminApiErrorPayload(
        {
          detail: "insufficient funds",
          error_code: "insufficient_funds",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Недостаточно средств.",
      errorCode: "insufficient_funds",
    });

    expect(
      parseAdminApiErrorPayload(
        {
          detail: "status conflict",
          error_code: "admin_account_status_conflict",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Не удалось изменить статус аккаунта. Обновите данные и попробуйте снова.",
      errorCode: "admin_account_status_conflict",
    });
  });

  it("maps admin promo errors to stable operator messages", () => {
    expect(
      parseAdminApiErrorPayload(
        {
          detail: "promo campaign not found",
          error_code: "admin_promo_campaign_not_found",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Промокампания не найдена.",
      errorCode: "admin_promo_campaign_not_found",
    });

    expect(
      parseAdminApiErrorPayload(
        {
          detail: "validation failed",
          error_code: "admin_promo_validation_failed",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Проверьте параметры промокампании или промокода и попробуйте снова.",
      errorCode: "admin_promo_validation_failed",
    });

    expect(
      parseAdminApiErrorPayload(
        {
          detail: "promo code already exists",
          error_code: "admin_promo_code_conflict",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Промокод с таким значением уже существует.",
      errorCode: "admin_promo_code_conflict",
    });

    expect(
      parseAdminApiErrorPayload(
        {
          detail: "invalid account_id",
          error_code: "admin_promo_invalid_account_id",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Некорректный идентификатор аккаунта.",
      errorCode: "admin_promo_invalid_account_id",
    });
  });

  it("maps admin broadcast not-found errors to stable operator messages", () => {
    expect(
      parseAdminApiErrorPayload(
        {
          detail: "broadcast not found",
          error_code: "admin_broadcast_not_found",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Рассылка не найдена.",
      errorCode: "admin_broadcast_not_found",
    });

    expect(
      parseAdminApiErrorPayload(
        {
          detail: "broadcast run not found",
          error_code: "admin_broadcast_run_not_found",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Запуск рассылки не найден.",
      errorCode: "admin_broadcast_run_not_found",
    });

    expect(
      parseAdminApiErrorPayload(
        {
          detail: "preset not found",
          error_code: "admin_broadcast_audience_preset_not_found",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Сохранённая аудитория рассылки не найдена.",
      errorCode: "admin_broadcast_audience_preset_not_found",
    });
  });

  it("maps admin broadcast runtime conflict errors to stable operator messages", () => {
    expect(
      parseAdminApiErrorPayload(
        {
          detail: "generic validation",
          error_code: "admin_broadcast_validation_failed",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Проверьте параметры рассылки и попробуйте снова.",
      errorCode: "admin_broadcast_validation_failed",
    });

    expect(
      parseAdminApiErrorPayload(
        {
          detail: "only draft broadcasts can be deleted",
          error_code: "broadcast_delete_requires_draft",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Удалить можно только черновик рассылки.",
      errorCode: "broadcast_delete_requires_draft",
    });

    expect(
      parseAdminApiErrorPayload(
        {
          detail: "scheduled_at must be in the future",
          error_code: "broadcast_schedule_in_past",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Дата и время запуска должны быть в будущем.",
      errorCode: "broadcast_schedule_in_past",
    });

    expect(
      parseAdminApiErrorPayload(
        {
          detail: "only paused broadcasts can be resumed",
          error_code: "broadcast_resume_invalid_state",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Возобновить можно только рассылку на паузе.",
      errorCode: "broadcast_resume_invalid_state",
    });
  });

  it("maps admin subscription grant errors to stable operator messages", () => {
    expect(
      parseAdminApiErrorPayload(
        {
          detail: "unknown plan",
          error_code: "unknown_plan",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Тариф не найден.",
      errorCode: "unknown_plan",
    });

    expect(
      parseAdminApiErrorPayload(
        {
          detail: "comment conflict",
          error_code: "idempotency_comment_conflict",
        },
        "fallback",
      ),
    ).toEqual({
      detail: "Этот ключ уже используется с другим комментарием.",
      errorCode: "idempotency_comment_conflict",
    });
  });
});
