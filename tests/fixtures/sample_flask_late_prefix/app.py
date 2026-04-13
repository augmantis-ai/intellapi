"""Flask fixture covering register_blueprint url prefixes."""

from flask import Blueprint, Flask


app = Flask(__name__)
users = Blueprint("users", __name__)


@users.get("/me")
def get_me():
    """Get current user."""
    return {"id": 1}


app.register_blueprint(users, url_prefix="/api/v2/users")
