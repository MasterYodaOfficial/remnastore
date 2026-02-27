from fastapi import APIRouter

router = APIRouter()


@router.post("/payments")
async def payments_webhook() -> dict:
    return {"todo": "handle payment webhook"}
