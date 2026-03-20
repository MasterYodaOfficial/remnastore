type AdminApiErrorPayload = {
  detail?: string;
  error_code?: string;
};

function mapAdminErrorCodeToMessage(errorCode: string | null, fallback: string): string {
  switch (errorCode) {
    case "admin_invalid_credentials":
      return "Неверный логин или пароль.";
    case "admin_missing_credentials":
      return "Требуется авторизация администратора.";
    case "admin_invalid_token":
    case "admin_invalid_scope":
    case "admin_token_missing_subject":
    case "admin_not_found":
      return "Сессия администратора недействительна. Войдите заново.";
    case "admin_disabled":
      return "Учетная запись администратора отключена.";
    case "admin_request_validation_failed":
      return "Проверьте заполнение формы и попробуйте снова.";
    case "admin_superuser_required":
      return "Для этого действия нужны права суперпользователя.";
    case "admin_account_not_found":
      return "Аккаунт не найден.";
    case "admin_comment_required":
    case "admin_account_status_comment_required":
      return "Комментарий администратора обязателен.";
    case "insufficient_funds":
      return "Недостаточно средств.";
    case "admin_account_status_conflict":
      return "Не удалось изменить статус аккаунта из-за конфликта состояния. Обновите данные и попробуйте снова.";
    case "admin_promo_campaign_not_found":
      return "Промокампания не найдена.";
    case "admin_promo_code_not_found":
      return "Промокод не найден.";
    case "admin_promo_validation_failed":
      return "Проверьте параметры промокампании или промокода и попробуйте снова.";
    case "admin_promo_code_conflict":
      return "Промокод с таким значением уже существует.";
    case "admin_promo_batch_conflict":
      return "Не удалось выпустить пакет промокодов из-за конфликта значений. Попробуйте еще раз.";
    case "admin_promo_import_conflict":
      return "Один или несколько импортируемых промокодов уже существуют.";
    case "admin_promo_invalid_account_id":
      return "Некорректный идентификатор аккаунта.";
    case "admin_broadcast_not_found":
      return "Рассылка не найдена.";
    case "admin_broadcast_run_not_found":
      return "Запуск рассылки не найден.";
    case "admin_broadcast_audience_preset_not_found":
      return "Сохраненная аудитория рассылки не найдена.";
    case "admin_broadcast_conflict":
      return "Операцию с рассылкой не удалось выполнить из-за конфликта состояния. Обновите данные и попробуйте снова.";
    case "admin_broadcast_validation_failed":
      return "Проверьте параметры рассылки и попробуйте снова.";
    case "broadcast_edit_requires_draft":
      return "Редактировать можно только черновик рассылки.";
    case "broadcast_delete_requires_draft":
      return "Удалить можно только черновик рассылки.";
    case "broadcast_launch_requires_draft":
      return "Запустить сразу можно только черновик рассылки.";
    case "broadcast_schedule_requires_draft":
      return "Запланировать можно только черновик рассылки.";
    case "broadcast_schedule_in_past":
      return "Дата и время запуска должны быть в будущем.";
    case "broadcast_pause_invalid_state":
      return "Поставить на паузу можно только запланированную или уже запущенную рассылку.";
    case "broadcast_resume_invalid_state":
      return "Возобновить можно только рассылку на паузе.";
    case "broadcast_resume_missing_run":
      return "Не удалось возобновить рассылку: активный запуск не найден.";
    case "broadcast_cancel_invalid_state":
      return "Отменить можно только запланированную, запущенную или поставленную на паузу рассылку.";
    case "broadcast_test_send_idempotency_invalid":
      return "Не удалось повторно использовать test send из-за поврежденного состояния запроса.";
    case "unknown_plan":
      return "Тариф не найден.";
    case "config_unavailable":
      return "Каталог тарифов временно недоступен.";
    case "remnawave_not_configured":
    case "remnawave_unavailable":
    case "remnawave_subscription_url_missing":
    case "manual_grant_inconsistent_state":
      return "Сервис подписки временно недоступен. Попробуйте позже.";
    case "idempotency_required":
      return "Укажите ключ запроса и попробуйте снова.";
    case "idempotency_account_conflict":
      return "Этот ключ уже используется для другого аккаунта.";
    case "idempotency_plan_conflict":
      return "Этот ключ уже используется для другого тарифа.";
    case "idempotency_amount_conflict":
      return "Этот ключ уже используется для другой суммы покупки.";
    case "idempotency_duration_conflict":
      return "Этот ключ уже используется для другого срока подписки.";
    case "idempotency_admin_conflict":
      return "Этот ключ уже используется другим администратором.";
    case "idempotency_comment_conflict":
      return "Этот ключ уже используется с другим комментарием.";
    default:
      return fallback;
  }
}

export function parseAdminApiErrorPayload(
  payload: unknown,
  fallback: string,
): { detail: string; errorCode: string | null } {
  if (!payload || typeof payload !== "object") {
    return {
      detail: fallback,
      errorCode: null,
    };
  }

  const { detail, error_code: errorCode } = payload as AdminApiErrorPayload;
  const normalizedErrorCode = typeof errorCode === "string" ? errorCode : null;
  const normalizedDetail = typeof detail === "string" && detail.trim() ? detail : fallback;

  return {
    detail: mapAdminErrorCodeToMessage(normalizedErrorCode, normalizedDetail),
    errorCode: normalizedErrorCode,
  };
}
