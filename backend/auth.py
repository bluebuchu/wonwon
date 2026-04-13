import os
from fastapi import Header, HTTPException

API_SECRET = os.getenv("API_SECRET", "")


async def verify_api_key(x_api_key: str | None = Header(default=None)):
    """Verify the API key for write endpoints."""
    if not API_SECRET:
        raise HTTPException(
            status_code=500,
            detail="API_SECRET is not configured on the server.",
        )
    if x_api_key != API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
