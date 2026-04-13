"""FastAPI fixture covering router mounting and dependency heuristics."""

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel


app = FastAPI()
users_router = APIRouter()


class UserResponse(BaseModel):
    id: int
    email: str


def get_db():
    return object()


def get_current_user():
    return {"id": 1}


@users_router.get("/")
def list_users(db=Depends(get_db)):
    """List users with a non-auth dependency."""
    return []


@users_router.get("/me", response_model=UserResponse)
def get_me(current_user: Annotated[dict, Depends(get_current_user)]):
    """Get the authenticated user."""
    return {"id": 1, "email": "me@example.com"}


app.include_router(users_router, prefix="/api/v1/users")
