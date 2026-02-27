from fastapi import APIRouter

router = APIRouter()


@router.get("/config")
async def webapp_config() -> dict:
    return {"todo": "webapp config"}


@router.post("/order")
async def create_order() -> dict:
    return {"todo": "create order"}
