"""Tests for the Python extractor."""

from pathlib import Path

from intellapi.scanner.file_discovery import discover_files
from intellapi.scanner.python_extractor import PythonExtractor


FIXTURES = Path(__file__).parent / "fixtures"


class TestPythonExtractor:
    def test_extract_fastapi_app(self):
        files = discover_files(FIXTURES / "sample_fastapi")
        ir = PythonExtractor(framework="fastapi").extract(files)

        assert ir.service_name == "Sample API"
        assert len(ir.endpoints) == 8
        assert any(endpoint.path == "/api/users" and endpoint.method == "POST" for endpoint in ir.endpoints)
        create_user = next(endpoint for endpoint in ir.endpoints if endpoint.handler_name == "create_user")
        assert create_user.request_body is not None
        assert create_user.request_body.name == "UserCreate"
        assert create_user.response_model is not None
        assert create_user.response_model.name == "UserResponse"
        delete_user = next(endpoint for endpoint in ir.endpoints if endpoint.handler_name == "delete_user")
        assert delete_user.auth_required is True
        assert any(parameter.name == "user_id" and parameter.location == "path" for parameter in delete_user.parameters)
        assert "UserCreate" in {model.name for model in ir.models}

    def test_extract_flask_app(self):
        files = discover_files(FIXTURES / "sample_flask")
        ir = PythonExtractor(framework="flask").extract(files)

        assert len(ir.endpoints) == 3
        paths = {(endpoint.method, endpoint.path) for endpoint in ir.endpoints}
        assert ("GET", "/api/users") in paths
        assert ("GET", "/api/users/{user_id}") in paths
        assert ("POST", "/api/users") in paths
        create_user = next(endpoint for endpoint in ir.endpoints if endpoint.handler_name == "create_user")
        assert create_user.request_body is not None
        assert create_user.request_body.name == "UserPayload"
        assert create_user.auth_required is True
        get_user = next(endpoint for endpoint in ir.endpoints if endpoint.handler_name == "get_user")
        assert any(parameter.name == "user_id" and parameter.location == "path" for parameter in get_user.parameters)
        assert "UserResponse" in {model.name for model in ir.models}

    def test_extract_django_rest_app(self):
        files = discover_files(FIXTURES / "sample_django_rest")
        ir = PythonExtractor(framework="django_rest").extract(files)

        assert len(ir.endpoints) == 3
        paths = {(endpoint.method, endpoint.path) for endpoint in ir.endpoints}
        assert ("GET", "/health") in paths
        assert ("GET", "/users") in paths
        assert ("POST", "/users") in paths
        post_endpoint = next(endpoint for endpoint in ir.endpoints if endpoint.method == "POST")
        assert post_endpoint.request_body is not None
        assert post_endpoint.request_body.name == "UserSerializer"
        assert post_endpoint.response_model is not None
        assert post_endpoint.response_model.name == "UserSerializer"
        assert post_endpoint.auth_required is True
        assert "permission_classes" in ir.auth_patterns

    def test_fastapi_router_mount_and_dependency_heuristics(self):
        files = discover_files(FIXTURES / "sample_fastapi_advanced")
        ir = PythonExtractor(framework="fastapi").extract(files)

        paths = {(endpoint.method, endpoint.path) for endpoint in ir.endpoints}
        assert ("GET", "/api/v1/users") in paths
        assert ("GET", "/api/v1/users/me") in paths

        list_users = next(endpoint for endpoint in ir.endpoints if endpoint.handler_name == "list_users")
        get_me = next(endpoint for endpoint in ir.endpoints if endpoint.handler_name == "get_me")
        assert list_users.auth_required is False
        assert get_me.auth_required is True

    def test_flask_register_blueprint_prefix(self):
        files = discover_files(FIXTURES / "sample_flask_late_prefix")
        ir = PythonExtractor(framework="flask").extract(files)

        assert len(ir.endpoints) == 1
        assert ir.endpoints[0].path == "/api/v2/users/me"

    def test_django_rest_router_and_action_support(self):
        files = discover_files(FIXTURES / "sample_django_rest_router")
        ir = PythonExtractor(framework="django_rest").extract(files)

        paths = {(endpoint.method, endpoint.path) for endpoint in ir.endpoints}
        assert ("GET", "/users") in paths
        assert ("GET", "/users/{pk}") in paths
        assert ("POST", "/users/{pk}/reset-password") in paths

        reset_password = next(
            endpoint for endpoint in ir.endpoints if endpoint.handler_name == "UserViewSet.reset_password"
        )
        assert reset_password.auth_required is True
        assert reset_password.request_body is not None
        id_field = next(field for field in reset_password.request_body.fields if field.name == "id")
        assert id_field.required is False

    def test_extractor_surfaces_skipped_file_warnings(self, tmp_path):
        valid_file = tmp_path / "main.py"
        valid_file.write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
        broken_file = tmp_path / "broken.py"
        broken_file.write_text("def broken(:\n", encoding="utf-8")

        ir = PythonExtractor(framework="fastapi").extract([valid_file, broken_file])
        assert ir.extraction_warnings
        assert "broken.py" in ir.extraction_warnings[0]
