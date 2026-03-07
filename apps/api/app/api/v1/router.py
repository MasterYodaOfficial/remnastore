from fastapi import APIRouter, Depends

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.accounts import router as accounts_router
from app.api.v1.endpoints.subscriptions import router as subscriptions_router
from app.api.v1.endpoints.users import router as users_router
from app.api.v1.endpoints.webapp import router as webapp_router
from app.api.v1.endpoints.webhooks import router as webhooks_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.dependencies import get_current_account

api_router = APIRouter()

api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])

protected_router = APIRouter(dependencies=[Depends(get_current_account)])
protected_router.include_router(users_router, prefix="/users", tags=["users"])
protected_router.include_router(subscriptions_router, prefix="/subscriptions", tags=["subscriptions"])
protected_router.include_router(webapp_router, prefix="/webapp", tags=["webapp"])
protected_router.include_router(accounts_router, tags=["accounts"])

api_router.include_router(protected_router)
api_router.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])
