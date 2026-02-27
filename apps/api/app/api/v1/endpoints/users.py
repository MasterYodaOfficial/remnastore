from fastapi import APIRouter

router = APIRouter()


@router.get("/me")
async def me() -> dict:
    return {"todo": "user profile"}
