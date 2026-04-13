"""Tests for the Node/TypeScript extractor."""

from pathlib import Path

from intellapi.scanner.file_discovery import discover_files
from intellapi.scanner.node_extractor import NodeExtractor


FIXTURES = Path(__file__).parent / "fixtures"


class TestNodeExtractor:
    def test_extract_express_app(self):
        files = discover_files(FIXTURES / "sample_express")
        ir = NodeExtractor(framework="express").extract(files)

        assert ir.service_name == "sample-express-app"
        assert ir.language == "javascript"
        assert len(ir.endpoints) == 8
        paths = {(endpoint.method, endpoint.path) for endpoint in ir.endpoints}
        assert ("GET", "/api/users") in paths
        assert ("POST", "/api/users") in paths
        assert ("POST", "/api/items") in paths

        list_users = next(endpoint for endpoint in ir.endpoints if endpoint.method == "GET" and endpoint.path == "/api/users")
        create_item = next(endpoint for endpoint in ir.endpoints if endpoint.method == "POST" and endpoint.path == "/api/items")
        delete_user = next(endpoint for endpoint in ir.endpoints if endpoint.method == "DELETE" and endpoint.path == "/api/users/{id}")

        assert {param.name for param in list_users.parameters} == {"skip", "limit"}
        assert create_item.auth_required is True
        assert delete_user.auth_required is True

    def test_extract_nextjs_app_router(self):
        files = discover_files(FIXTURES / "sample_nextjs")
        ir = NodeExtractor(framework="nextjs").extract(files)

        assert ir.service_name == "sample-nextjs-app"
        assert ir.language == "typescript"
        assert {(endpoint.method, endpoint.path) for endpoint in ir.endpoints} == {
            ("GET", "/api/users"),
            ("POST", "/api/users"),
        }

        get_users = next(endpoint for endpoint in ir.endpoints if endpoint.method == "GET")
        post_users = next(endpoint for endpoint in ir.endpoints if endpoint.method == "POST")

        assert {param.name for param in get_users.parameters} == {"limit", "skip"}
        assert post_users.request_body is not None
        assert post_users.request_body.name == "PostApiUsersRequest"
        assert post_users.response_model is not None
        assert post_users.response_model.name == "User"

    def test_extract_nextjs_pages_router(self):
        files = discover_files(FIXTURES / "sample_nextjs_pages")
        ir = NodeExtractor(framework="nextjs").extract(files)

        assert ir.service_name == "sample-nextjs-pages-app"
        assert {(endpoint.method, endpoint.path) for endpoint in ir.endpoints} == {
            ("GET", "/api/orders/{orderId}"),
            ("PATCH", "/api/orders/{orderId}"),
        }

        get_order = next(endpoint for endpoint in ir.endpoints if endpoint.method == "GET")
        patch_order = next(endpoint for endpoint in ir.endpoints if endpoint.method == "PATCH")

        assert {f"{param.location}:{param.name}" for param in get_order.parameters} == {
            "path:orderId",
            "query:includeHistory",
        }
        assert get_order.response_model is not None
        assert get_order.response_model.name == "Order"
        assert patch_order.request_body is not None
        assert patch_order.request_body.name == "OrderPayload"

    def test_extract_sveltekit_routes(self):
        files = discover_files(FIXTURES / "sample_sveltekit")
        ir = NodeExtractor(framework="sveltekit").extract(files)

        assert ir.service_name == "sample-sveltekit-app"
        assert {(endpoint.method, endpoint.path) for endpoint in ir.endpoints} == {
            ("GET", "/api/posts/{slug}"),
            ("PATCH", "/api/posts/{slug}"),
        }

        get_post = next(endpoint for endpoint in ir.endpoints if endpoint.method == "GET")
        patch_post = next(endpoint for endpoint in ir.endpoints if endpoint.method == "PATCH")

        assert {f"{param.location}:{param.name}" for param in get_post.parameters} == {
            "path:slug",
            "query:expand",
        }
        assert get_post.response_model is not None
        assert get_post.response_model.name == "Post"
        assert patch_post.request_body is not None
        assert {field.name for field in patch_post.request_body.fields} == {"body", "title"}
