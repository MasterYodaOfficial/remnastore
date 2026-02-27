class UserService:
    async def get_me(self) -> dict:
        return {"todo": "get current user"}
