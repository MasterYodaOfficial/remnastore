from pydantic import BaseModel


class RemnawaveNode(BaseModel):
    id: str
    name: str
    status: str | None = None
