"""Sample Flask application for extractor tests."""

from flask import Blueprint, Flask
from pydantic import BaseModel, Field


app = Flask(__name__)
users = Blueprint("users", __name__, url_prefix="/api/users")


class UserPayload(BaseModel):
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")


class UserResponse(BaseModel):
    id: int
    name: str
    email: str


def login_required(func):
    return func


@users.get("/")
def list_users(limit: int = 20):
    """List users."""
    return []


@users.get("/<int:user_id>")
def get_user(user_id: int) -> UserResponse:
    """Get a user by ID."""
    return UserResponse(id=user_id, name="Alice", email="alice@example.com")


@users.post("/")
@login_required
def create_user(payload: UserPayload) -> UserResponse:
    """Create a user."""
    return UserResponse(id=1, **payload.model_dump())


app.register_blueprint(users)
