import asyncio
import sys

from sqlalchemy import select

from app.core.database import async_session_maker, engine
from app.core.security import hash_password
from app.models.user import User

MIN_PASSWORD_LENGTH = 8


async def _reset_user_password(email: str, new_password: str) -> int:
    normalized_email = email.strip().lower()
    if len(new_password) < MIN_PASSWORD_LENGTH:
        print("Error: password must be at least 8 characters long.")
        return 1

    try:
        async with async_session_maker() as session:
            user = await session.scalar(
                select(User).where(User.email == normalized_email)
            )
            if user is None:
                print(f"Error: user '{normalized_email}' not found.")
                return 1

            user.password_hash = hash_password(new_password)
            await session.commit()
    finally:
        await engine.dispose()

    print(f"Password updated for '{normalized_email}'.")
    return 0


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python -m scripts.reset_password <email> <new_password>")
        return 1
    return asyncio.run(_reset_user_password(sys.argv[1], sys.argv[2]))


if __name__ == "__main__":
    raise SystemExit(main())
