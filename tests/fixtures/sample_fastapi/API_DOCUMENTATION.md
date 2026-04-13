# Sample API is a FastAPI-based REST service providing user and item management capabilities

## Overview

Sample API is a FastAPI-based REST service providing user and item management capabilities. It offers endpoints for creating, retrieving, updating, and deleting users, as well as managing items associated with users. The API supports optional pagination on list endpoints and includes a health check endpoint for monitoring service availability.

## Authentication

Authentication is required for sensitive operations: creating items (POST /api/items) and deleting users (DELETE /api/users/{user_id}). The API uses a get_current_user dependency for authentication. Read operations and user creation do not require authentication.

## Endpoints

### `GET` /api/users

List all users with pagination

Retrieve a paginated list of all users in the system. Supports optional skip and limit parameters for pagination control.


**Parameters:**

| Name | Location | Type | Required | Description |
|------|----------|------|----------|-------------|
| `skip` | query | `integer` | No | Number of users to skip (default: 0) |
| `limit` | query | `integer` | No | Maximum number of users to return (default: 10) |


**Response** (`200` — `application/json`):

| Field | Type | Description |
|-------|------|-------------|
| `id` | `integer` | Unique identifier for the user |
| `name` | `string` | User's full name |
| `email` | `string` | User's email address |
| `age` | `integer` | User's age (optional) |

```json
[{"id": 1, "name": "John Doe", "email": "john@example.com", "age": 30}, {"id": 2, "name": "Jane Smith", "email": "jane@example.com", "age": null}]
```



---

### `POST` /api/users

Create a new user

Create a new user in the system. Requires a name and email address; age is optional.


**Request Body** (`application/json`):

Schema: `UserCreate`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | Yes | User's full name |
| `email` | `string` | Yes | User's email address |
| `age` | `integer` | No | User's age (optional) |

```json
{"name": "Alice Johnson", "email": "alice@example.com", "age": 28}
```

**Response** (`201` — `application/json`):

| Field | Type | Description |
|-------|------|-------------|
| `id` | `integer` | Unique identifier for the user |
| `name` | `string` | User's full name |
| `email` | `string` | User's email address |
| `age` | `integer` | User's age (optional) |

```json
{"id": 3, "name": "Alice Johnson", "email": "alice@example.com", "age": 28}
```



---

### `GET` /api/users/{user_id}

Get a specific user by ID

Retrieve detailed information about a specific user by their unique identifier.


**Parameters:**

| Name | Location | Type | Required | Description |
|------|----------|------|----------|-------------|
| `user_id` | path | `integer` | Yes | The unique identifier of the user |


**Response** (`200` — `application/json`):

| Field | Type | Description |
|-------|------|-------------|
| `id` | `integer` | Unique identifier for the user |
| `name` | `string` | User's full name |
| `email` | `string` | User's email address |
| `age` | `integer` | User's age (optional) |

```json
{"id": 1, "name": "John Doe", "email": "john@example.com", "age": 30}
```



---

### `PUT` /api/users/{user_id}

Update an existing user

Update the information of an existing user. Provide the fields you wish to update in the request body.


**Parameters:**

| Name | Location | Type | Required | Description |
|------|----------|------|----------|-------------|
| `user_id` | path | `integer` | Yes | The unique identifier of the user to update |

**Request Body** (`application/json`):

Schema: `UserCreate`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | Yes | User's full name |
| `email` | `string` | Yes | User's email address |
| `age` | `integer` | No | User's age (optional) |

```json
{"name": "John Smith", "email": "john.smith@example.com", "age": 31}
```

**Response** (`200` — `application/json`):

| Field | Type | Description |
|-------|------|-------------|
| `id` | `integer` | Unique identifier for the user |
| `name` | `string` | User's full name |
| `email` | `string` | User's email address |
| `age` | `integer` | User's age (optional) |

```json
{"id": 1, "name": "John Smith", "email": "john.smith@example.com", "age": 31}
```



---

### `DELETE` /api/users/{user_id}

Delete a user

Delete a user from the system. This operation requires authentication. Returns 204 No Content on successful deletion.

> **Authentication required**

**Parameters:**

| Name | Location | Type | Required | Description |
|------|----------|------|----------|-------------|
| `user_id` | path | `integer` | Yes | The unique identifier of the user to delete |


**Response** (`204` — `application/json`):




---

### `GET` /api/items

List all items, optionally filtered by owner

Retrieve a list of all items in the system. Optionally filter results by owner_id to retrieve items belonging to a specific user.


**Parameters:**

| Name | Location | Type | Required | Description |
|------|----------|------|----------|-------------|
| `owner_id` | query | `integer` | No | Filter items by owner user ID (optional) |


**Response** (`200` — `application/json`):

| Field | Type | Description |
|-------|------|-------------|
| `id` | `integer` | Unique identifier for the item |
| `title` | `string` | Item title |
| `description` | `string` | Item description (optional) |
| `price` | `number` | Item price |
| `owner_id` | `integer` | ID of the user who owns this item |

```json
[{"id": 1, "title": "Laptop", "description": "High-performance laptop", "price": 1299.99, "owner_id": 1}, {"id": 2, "title": "Mouse", "description": null, "price": 29.99, "owner_id": 2}]
```



---

### `POST` /api/items

Create a new item

Create a new item in the system. Requires authentication. The item will be associated with the specified owner.

> **Authentication required**

**Request Body** (`application/json`):

Schema: `ItemCreate`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | `string` | Yes | Item title |
| `description` | `string` | No | Item description (optional) |
| `price` | `number` | Yes | Item price |
| `owner_id` | `integer` | Yes | ID of the user who owns this item |

```json
{"title": "Keyboard", "description": "Mechanical keyboard with RGB lighting", "price": 149.99, "owner_id": 1}
```

**Response** (`201` — `application/json`):

| Field | Type | Description |
|-------|------|-------------|
| `id` | `integer` | Unique identifier for the item |
| `title` | `string` | Item title |
| `description` | `string` | Item description (optional) |
| `price` | `number` | Item price |
| `owner_id` | `integer` | ID of the user who owns this item |

```json
{"id": 3, "title": "Keyboard", "description": "Mechanical keyboard with RGB lighting", "price": 149.99, "owner_id": 1}
```



---

### `GET` /health

Health check endpoint

Check the health and availability of the API service. Returns a simple status response.



**Response** (`200` — `application/json`):

```json
{"status": "healthy"}
```



---


## Data Models

### UserCreate

Schema for creating a new user. Used in POST /api/users and PUT /api/users/{user_id} requests.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | Yes | User's full name |
| `email` | `string` | Yes | User's email address |
| `age` | `integer` | No | User's age (optional) |

### UserResponse

Schema for user response. Returned by all user-related endpoints.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `integer` | Yes | Unique identifier for the user |
| `name` | `string` | Yes | User's full name |
| `email` | `string` | Yes | User's email address |
| `age` | `integer` | No | User's age (optional) |

### ItemCreate

Schema for creating a new item. Used in POST /api/items requests.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | `string` | Yes | Item title |
| `description` | `string` | No | Item description (optional) |
| `price` | `number` | Yes | Item price |
| `owner_id` | `integer` | Yes | ID of the user who owns this item |

### ItemResponse

Schema for item response. Returned by all item-related endpoints.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `integer` | Yes | Unique identifier for the item |
| `title` | `string` | Yes | Item title |
| `description` | `string` | No | Item description (optional) |
| `price` | `number` | Yes | Item price |
| `owner_id` | `integer` | Yes | ID of the user who owns this item |


## Error Handling

The API follows standard HTTP status codes for error responses. Expected error codes include: 400 Bad Request for invalid input, 401 Unauthorized for missing or invalid authentication, 404 Not Found for non-existent resources (e.g., user or item not found), and 500 Internal Server Error for server-side issues. Specific error response formats are not detailed in the source code analysis; refer to FastAPI's default error handling behavior.


## Dependencies

fastapi, pydantic, typing


## Usage Examples

### Create a new user

Example of creating a new user in the system

```bash
curl -X POST http://localhost:8000/api/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Bob Wilson", "email": "bob@example.com", "age": 35}'
```

### List users with pagination

Example of retrieving users with skip and limit parameters

```bash
curl -X GET "http://localhost:8000/api/users?skip=0&limit=5" \
  -H "Content-Type: application/json"
```

### Create a new item (authenticated)

Example of creating a new item with authentication required

```bash
curl -X POST http://localhost:8000/api/items \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"title": "Monitor", "description": "4K Ultra HD Monitor", "price": 399.99, "owner_id": 1}'
```

### Get a specific user

Example of retrieving a user by their ID

```bash
curl -X GET http://localhost:8000/api/users/1 \
  -H "Content-Type: application/json"
```

### Update a user

Example of updating an existing user's information

```bash
curl -X PUT http://localhost:8000/api/users/1 \
  -H "Content-Type: application/json" \
  -d '{"name": "John Updated", "email": "john.updated@example.com", "age": 32}'
```

### Delete a user (authenticated)

Example of deleting a user with authentication required

```bash
curl -X DELETE http://localhost:8000/api/users/1 \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Filter items by owner

Example of retrieving items filtered by a specific owner

```bash
curl -X GET "http://localhost:8000/api/items?owner_id=1" \
  -H "Content-Type: application/json"
```

### Health check

Example of checking the API health status

```bash
curl -X GET http://localhost:8000/health
```


## ⚠️ Uncertain / Needs Verification

- Authentication mechanism details are not specified in the source code analysis. The get_current_user dependency is referenced but its implementation (e.g., token-based, API key, session-based) is not documented. Verify the actual authentication scheme in the implementation.
- Error response schemas and specific error codes are not detailed in the source analysis. Refer to FastAPI's default error handling or the actual API implementation for precise error response formats.
- Default values for pagination parameters (skip and limit) are inferred but not explicitly confirmed in the source code analysis.
- The health check endpoint response format is inferred; verify the actual response structure in the implementation.
- No rate limiting, request validation constraints, or other middleware behaviors are documented in the source analysis.
- The relationship between users and items (e.g., whether owner_id must reference an existing user) is not explicitly validated in the provided documentation.


---

*Generated by [Intellapi](https://github.com/intellapi/intellapi)*
