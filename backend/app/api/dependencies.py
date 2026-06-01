from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.security import decode_access_token
from app.models.user import User

from app.core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=settings.AUTH_URL)

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    user_id = decode_access_token(token)
    if user_id is None:
        raise credentials_exception
        
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    # Auto-create the local user stub if the microservice token provides an ID 
    # but the user doesn't exist in the local Postgres DB yet.
    if user is None:
        try:
            # Create a placeholder user to satisfy foreign key constraints
            # We don't have their email from just the UUID token, but we satisfy the relation
            user = User(id=user_id, email=f"{user_id}@external.auth", hashed_password="external")
            db.add(user)
            await db.commit()
            await db.refresh(user)
        except Exception:
            raise credentials_exception
        
    return user
