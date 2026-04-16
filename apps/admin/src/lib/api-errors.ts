import { t } from "./i18n";

type AdminApiErrorPayload = {
  detail?: string;
  error_code?: string;
};

function mapAdminErrorCodeToMessage(errorCode: string | null, fallback: string): string {
  switch (errorCode) {
    case "admin_invalid_credentials":
      return t("admin.apiErrors.adminInvalidCredentials");
    case "admin_missing_credentials":
      return t("admin.apiErrors.adminMissingCredentials");
    case "admin_invalid_token":
    case "admin_invalid_scope":
    case "admin_token_missing_subject":
    case "admin_not_found":
      return t("admin.apiErrors.adminSessionInvalid");
    case "admin_disabled":
      return t("admin.apiErrors.adminDisabled");
    case "admin_request_validation_failed":
      return t("admin.apiErrors.requestValidationFailed");
    case "admin_superuser_required":
      return t("admin.apiErrors.superuserRequired");
    case "admin_account_not_found":
      return t("admin.apiErrors.accountNotFound");
    case "admin_comment_required":
    case "admin_account_status_comment_required":
      return t("admin.apiErrors.adminCommentRequired");
    case "insufficient_funds":
      return t("admin.apiErrors.insufficientFunds");
    case "admin_account_status_conflict":
      return t("admin.apiErrors.accountStatusConflict");
    case "admin_promo_campaign_not_found":
      return t("admin.apiErrors.promoCampaignNotFound");
    case "admin_promo_code_not_found":
      return t("admin.apiErrors.promoCodeNotFound");
    case "admin_promo_validation_failed":
      return t("admin.apiErrors.promoValidationFailed");
    case "admin_promo_code_conflict":
      return t("admin.apiErrors.promoCodeConflict");
    case "admin_promo_batch_conflict":
      return t("admin.apiErrors.promoBatchConflict");
    case "admin_promo_import_conflict":
      return t("admin.apiErrors.promoImportConflict");
    case "admin_promo_invalid_account_id":
      return t("admin.apiErrors.promoInvalidAccountId");
    case "admin_plan_validation_failed":
      return t("admin.apiErrors.planValidationFailed");
    case "admin_plan_conflict":
      return t("admin.apiErrors.planConflict");
    case "admin_plan_not_found":
      return t("admin.apiErrors.planNotFound");
    case "admin_plan_in_use":
      return t("admin.apiErrors.planInUse");
    case "admin_broadcast_not_found":
      return t("admin.apiErrors.broadcastNotFound");
    case "admin_broadcast_run_not_found":
      return t("admin.apiErrors.broadcastRunNotFound");
    case "admin_broadcast_audience_preset_not_found":
      return t("admin.apiErrors.broadcastAudiencePresetNotFound");
    case "admin_broadcast_conflict":
      return t("admin.apiErrors.broadcastConflict");
    case "admin_broadcast_validation_failed":
      return t("admin.apiErrors.broadcastValidationFailed");
    case "broadcast_edit_requires_draft":
      return t("admin.apiErrors.broadcastEditRequiresDraft");
    case "broadcast_delete_requires_draft":
      return t("admin.apiErrors.broadcastDeleteRequiresDraft");
    case "broadcast_launch_requires_draft":
      return t("admin.apiErrors.broadcastLaunchRequiresDraft");
    case "broadcast_schedule_requires_draft":
      return t("admin.apiErrors.broadcastScheduleRequiresDraft");
    case "broadcast_schedule_in_past":
      return t("admin.apiErrors.broadcastScheduleInPast");
    case "broadcast_pause_invalid_state":
      return t("admin.apiErrors.broadcastPauseInvalidState");
    case "broadcast_resume_invalid_state":
      return t("admin.apiErrors.broadcastResumeInvalidState");
    case "broadcast_resume_missing_run":
      return t("admin.apiErrors.broadcastResumeMissingRun");
    case "broadcast_cancel_invalid_state":
      return t("admin.apiErrors.broadcastCancelInvalidState");
    case "broadcast_test_send_idempotency_invalid":
      return t("admin.apiErrors.broadcastTestSendIdempotencyInvalid");
    case "unknown_plan":
      return t("admin.apiErrors.unknownPlan");
    case "config_unavailable":
      return t("admin.apiErrors.configUnavailable");
    case "remnawave_not_configured":
    case "remnawave_unavailable":
    case "remnawave_subscription_url_missing":
    case "manual_grant_inconsistent_state":
      return t("admin.apiErrors.subscriptionServiceUnavailable");
    case "idempotency_required":
      return t("admin.apiErrors.idempotencyRequired");
    case "idempotency_account_conflict":
      return t("admin.apiErrors.idempotencyAccountConflict");
    case "idempotency_plan_conflict":
      return t("admin.apiErrors.idempotencyPlanConflict");
    case "idempotency_amount_conflict":
      return t("admin.apiErrors.idempotencyAmountConflict");
    case "idempotency_duration_conflict":
      return t("admin.apiErrors.idempotencyDurationConflict");
    case "idempotency_admin_conflict":
      return t("admin.apiErrors.idempotencyAdminConflict");
    case "idempotency_comment_conflict":
      return t("admin.apiErrors.idempotencyCommentConflict");
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
