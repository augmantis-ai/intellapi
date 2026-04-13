"""Sample FastAPI application for testing."""

from fastapi import FastAPI, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional

app = FastAPI(title="Sample API", version="1.0.0")


# ─── Models ─────────────────────────────────────────────────────────────────


class UserCreate(BaseModel):
    """Schema for creating a new user."""

    name: str = Field(..., min_length=1, max_length=100, description="User's full name")
    email: str = Field(..., description="User's email address")
    age: Optional[int] = Field(None, ge=0, le=150, description="User's age")


class UserResponse(BaseModel):
    """Schema for user response."""

    id: int
    name: str
    email: str
    age: Optional[int] = None


class ItemCreate(BaseModel):
    """Schema for creating a new item."""

    title: str = Field(..., description="Item title")
    description: Optional[str] = Field(None, description="Item description")
    price: float = Field(..., gt=0, description="Item price in USD")
    owner_id: int = Field(..., description="ID of the item owner")


class ItemResponse(BaseModel):
    """Schema for item response."""

    id: int
    title: str
    description: Optional[str] = None
    price: float
    owner_id: int


# ─── Auth dependency (simulated) ────────────────────────────────────────────


def get_current_user():
    """Dependency to get the current authenticated user."""
    return {"id": 1, "name": "Test User"}


# ─── Endpoints ──────────────────────────────────────────────────────────────


@app.get("/api/users", response_model=list[UserResponse], tags=["users"])
def list_users(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(10, ge=1, le=100, description="Max records to return"),
):
    """List all users with pagination."""
    return []


@app.get("/api/users/{user_id}", response_model=UserResponse, tags=["users"])
def get_user(user_id: int):
    """Get a specific user by ID."""
    return {"id": user_id, "name": "John", "email": "john@example.com"}


@app.post("/api/users", response_model=UserResponse, status_code=201, tags=["users"])
def create_user(user: UserCreate):
    """Create a new user."""
    return {"id": 1, **user.model_dump()}


@app.put("/api/users/{user_id}", response_model=UserResponse, tags=["users"])
def update_user(user_id: int, user: UserCreate):
    """Update an existing user."""
    return {"id": user_id, **user.model_dump()}


@app.delete("/api/users/{user_id}", status_code=204, tags=["users"])
def delete_user(user_id: int, current_user=Depends(get_current_user)):
    """Delete a user. Requires authentication."""
    pass


@app.get("/api/items", response_model=list[ItemResponse], tags=["items"])
def list_items(
    owner_id: Optional[int] = Query(None, description="Filter by owner ID"),
):
    """List all items, optionally filtered by owner."""
    return []


@app.post("/api/items", response_model=ItemResponse, status_code=201, tags=["items"])
def create_item(item: ItemCreate, current_user=Depends(get_current_user)):
    """Create a new item. Requires authentication."""
    return {"id": 1, **item.model_dump()}


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
