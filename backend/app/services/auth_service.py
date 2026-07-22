from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.repositories.user_repository import UserRepository
from sqlalchemy.exc import IntegrityError


class AuthService:
    def __init__(self, users: UserRepository):
        self.users = users

    async def register(self, *, email: str, username: str, password: str) -> User:
        if await self.users.get_by_email(email):
            raise ValueError("邮箱已注册")
        if await self.users.get_by_username(username):
            raise ValueError("用户名已使用")
        try:
            return await self.users.create(
                email=email,
                username=username,
                password_hash=hash_password(password),
            )
        except IntegrityError as exc:
            await self.users.session.rollback()
            raise ValueError("邮箱或用户名已使用") from exc

    async def login(self, *, email: str, password: str) -> tuple[str, User]:
        user = await self.users.get_by_email(email)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise ValueError("邮箱或密码错误")
        return create_access_token(user.id), user
