from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_account, get_current_admin
from app.api.v1.endpoints.admin_accounts import router as admin_accounts_router
from app.api.v1.endpoints.admin_auth import router as admin_auth_router
from app.api.v1.endpoints.admin_broadcasts import router as admin_broadcasts_router
from app.api.v1.endpoints.admin_dashboard import router as admin_dashboard_router
from app.api.v1.endpoints.admin_withdrawals import router as admin_withdrawals_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.internal import router as internal_router
from app.api.v1.endpoints.accounts import router as accounts_router
from app.api.v1.endpoints.bootstrap import router as bootstrap_router
from app.api.v1.endpoints.ledger import router as ledger_router
from app.api.v1.endpoints.notifications import router as notifications_router
from app.api.v1.endpoints.payments import router as payments_router
from app.api.v1.endpoints.referrals import router as referrals_router
from app.api.v1.endpoints.subscriptions import router as subscriptions_router
from app.api.v1.endpoints.users import router as users_router
from app.api.v1.endpoints.withdrawals import router as withdrawals_router
from app.api.v1.endpoints.webapp import router as webapp_router
from app.api.v1.endpoints.webhooks import router as webhooks_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.linking import router as linking_router

api_router = APIRouter()

api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(admin_auth_router, prefix="/admin/auth", tags=["admin-auth"])
api_router.include_router(internal_router, prefix="/internal", tags=["internal"])
api_router.include_router(linking_router, prefix="/accounts", tags=["linking"])

protected_router = APIRouter(dependencies=[Depends(get_current_account)])
protected_router.include_router(bootstrap_router, tags=["bootstrap"])
protected_router.include_router(ledger_router, prefix="/ledger", tags=["ledger"])
protected_router.include_router(notifications_router, prefix="/notifications", tags=["notifications"])
protected_router.include_router(payments_router, prefix="/payments", tags=["payments"])
protected_router.include_router(referrals_router, prefix="/referrals", tags=["referrals"])
protected_router.include_router(users_router, prefix="/users", tags=["users"])
protected_router.include_router(subscriptions_router, prefix="/subscriptions", tags=["subscriptions"])
protected_router.include_router(withdrawals_router, prefix="/withdrawals", tags=["withdrawals"])
protected_router.include_router(webapp_router, prefix="/webapp", tags=["webapp"])
protected_router.include_router(accounts_router, tags=["accounts"])

api_router.include_router(protected_router)
api_router.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])

admin_router = APIRouter(prefix="/admin", dependencies=[Depends(get_current_admin)])
admin_router.include_router(admin_accounts_router, prefix="/accounts", tags=["admin-accounts"])
admin_router.include_router(admin_broadcasts_router, prefix="/broadcasts", tags=["admin-broadcasts"])
admin_router.include_router(admin_dashboard_router, prefix="/dashboard", tags=["admin-dashboard"])
admin_router.include_router(admin_withdrawals_router, prefix="/withdrawals", tags=["admin-withdrawals"])
api_router.include_router(admin_router)
