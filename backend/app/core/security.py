from datetime import datetime, timedelta, timezone
from typing import Any, Union
import uuid
from jose import jwt
from passlib.context import CryptContext
import bcrypt

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# def get_password_hash(password: str) -> str:
#     return pwd_context.hash(password)

# def verify_password(plain_password: str, hashed_password: str) -> bool:
#     return pwd_context.verify(plain_password, hashed_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def create_access_token(subject: Union[str, Any], expires_delta: timedelta = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
    return encoded_jwt

def decode_access_token(token: str) -> Union[str, None]:
    try:
        # Decode the token without verifying the signature because it is 
        # signed by the external microservice, not our local secret.
        decoded_token = jwt.decode(token, "", options={"verify_signature": False})
        
        # Extract user identifier from the external token
        # The Wissen microservice stores its ID as a plain integer (e.g. "73")
        external_id = decoded_token.get("sub") or decoded_token.get("id") or decoded_token.get("user_id")
        if not external_id:
            return None
        
        # Convert the external numeric ID into a stable, deterministic UUID.
        # uuid.uuid5 is deterministic: same input always → same UUID output.
        # This means user "73" always maps to the same UUID in Postgres.
        deterministic_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"wissen:{external_id}")
        return str(deterministic_uuid)
    except Exception as e:
        print(f"Token decode error: {e}")
        return None
