from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_subscriptions() -> dict:
    return {"todo": "list subscriptions"}


@router.post("/")
async def create_subscription() -> dict:
    return {"todo": "create subscription"}
