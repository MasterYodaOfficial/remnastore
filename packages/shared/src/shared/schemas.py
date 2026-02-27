from pydantic import BaseModel


class UserDTO(BaseModel):
    id: str
    tg_id: int
    username: str | None = None


class SubscriptionDTO(BaseModel):
    id: str
    plan_id: str
    status: str
    expires_at: str | None = None
