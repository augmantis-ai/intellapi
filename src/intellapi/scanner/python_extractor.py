"""Python extractor for FastAPI, Flask, and Django REST."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from intellapi.scanner.base_extractor import BaseExtractor
from intellapi.scanner.ir import EndpointInfo, FieldInfo, IntermediateRepresentation, ModelInfo, ParamInfo


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
DJANGO_ACTION_METHODS = {
    "list": ("GET", False),
    "retrieve": ("GET", True),
    "create": ("POST", False),
    "update": ("PUT", True),
    "partial_update": ("PATCH", True),
    "destroy": ("DELETE", True),
}
AUTH_DECORATOR_HINTS = {"login_required", "jwt_required", "permission_classes", "authentication_classes"}
AUTH_DEPENDENCY_HINTS = {
    "auth",
    "oauth",
    "token",
    "current_user",
    "current_account",
    "current_identity",
    "jwt",
    "bearer",
    "permission",
    "login",
    "session_user",
    "require_user",
}


class PythonExtractor(BaseExtractor):
    """Extract API information from Python backend frameworks using ``ast``."""

    def __init__(self, framework: str = "fastapi"):
        self._framework = framework
        self._reset_state()

    @property
    def framework_name(self) -> str:
        names = {"fastapi": "FastAPI", "flask": "Flask", "django_rest": "Django REST Framework"}
        return names.get(self._framework, self._framework)

    @property
    def language(self) -> str:
        return "python"

    def extract(self, files: list[Path]) -> IntermediateRepresentation:
        self._reset_state()
        module_asts: list[tuple[Path, ast.Module]] = []

        for path in sorted(files):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except OSError as exc:
                self._warnings.append(f"Skipped unreadable file {path}: {exc}")
                continue
            except SyntaxError as exc:
                self._warnings.append(f"Skipped file with syntax error {path}: {exc.msg} (line {exc.lineno})")
                continue
            module_asts.append((path, tree))
            self._collect_module_metadata(path, tree)

        endpoints: list[EndpointInfo] = []
        for path, tree in module_asts:
            if self._framework == "fastapi":
                endpoints.extend(self._extract_fastapi_routes(path, tree))
            elif self._framework == "flask":
                endpoints.extend(self._extract_flask_routes(path, tree))
            elif self._framework == "django_rest":
                endpoints.extend(self._extract_django_routes(path, tree))

        return IntermediateRepresentation(
            service_name=self._service_name or f"{self.framework_name} Service",
            framework=self._framework,
            language="python",
            endpoints=sorted(endpoints, key=lambda ep: (ep.path, ep.method, ep.line_number)),
            models=sorted(self._model_registry.values(), key=lambda model: model.name),
            dependencies=sorted(self._dependencies),
            auth_patterns=sorted(self._auth_patterns),
            source_evidence={key: sorted(value) for key, value in self._source_evidence.items() if value},
            extraction_warnings=self._warnings,
        )

    def _reset_state(self) -> None:
        self._model_registry: dict[str, ModelInfo] = {}
        self._dependencies: set[str] = set()
        self._router_prefixes: dict[str, str] = {"app": ""}
        self._fastapi_scope_auth: dict[str, bool] = {"app": False}
        self._fastapi_router_mounts: dict[str, list[tuple[str, bool]]] = {}
        self._flask_prefixes: dict[str, str] = {"app": ""}
        self._flask_mount_prefixes: dict[str, list[str]] = {}
        self._django_urlpatterns: dict[str, list[str]] = {}
        self._django_api_classes: dict[str, ast.ClassDef] = {}
        self._django_router_names: set[str] = set()
        self._source_evidence: dict[str, set[str]] = {"endpoints": set(), "models": set()}
        self._service_name: str | None = None
        self._auth_patterns: set[str] = set()
        self._warnings: list[str] = []

    def _collect_module_metadata(self, path: Path, tree: ast.Module) -> None:
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._dependencies.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                self._dependencies.add(node.module.split(".")[0])

            if isinstance(node, ast.ClassDef):
                self._maybe_register_model(path, node)
                if self._framework == "django_rest" and self._is_django_view_class(node):
                    self._django_api_classes[node.name] = node

            if isinstance(node, ast.Assign):
                self._collect_assignment_metadata(node)
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                self._collect_expression_metadata(node.value)

        if self._framework == "django_rest":
            self._collect_django_urlpatterns(tree)

    def _collect_assignment_metadata(self, node: ast.Assign) -> None:
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            return
        target_name = node.targets[0].id
        value = node.value
        if not isinstance(value, ast.Call):
            return

        callee = self._call_name(value.func)
        if self._framework == "fastapi" and callee == "FastAPI":
            title = self._keyword_constant(value, "title")
            if isinstance(title, str):
                self._service_name = title
            self._router_prefixes[target_name] = ""
            self._fastapi_scope_auth[target_name] = self._dependencies_list_implies_auth(
                self._keyword_expr(value, "dependencies")
            )
        elif self._framework == "fastapi" and callee == "APIRouter":
            self._router_prefixes[target_name] = self._normalize_prefix(self._keyword_constant(value, "prefix"))
            self._fastapi_scope_auth[target_name] = self._dependencies_list_implies_auth(
                self._keyword_expr(value, "dependencies")
            )
        elif self._framework == "flask" and callee == "Flask":
            self._service_name = self._service_name or f"{target_name.title()} API"
            self._flask_prefixes[target_name] = ""
        elif self._framework == "flask" and callee == "Blueprint":
            self._flask_prefixes[target_name] = self._normalize_prefix(self._keyword_constant(value, "url_prefix"))
        elif self._framework == "django_rest" and callee in {"DefaultRouter", "SimpleRouter"}:
            self._django_router_names.add(target_name)

    def _collect_expression_metadata(self, call: ast.Call) -> None:
        if isinstance(call.func, ast.Attribute):
            owner_name = self._name_from_expr(call.func.value)
            method_name = call.func.attr
        else:
            owner_name = None
            method_name = self._call_name(call.func)

        if self._framework == "fastapi" and method_name == "include_router" and owner_name:
            router_name = self._name_from_expr(call.args[0]) if call.args else None
            if router_name:
                include_prefix = self._normalize_prefix(self._keyword_constant(call, "prefix"))
                include_auth = self._dependencies_list_implies_auth(self._keyword_expr(call, "dependencies"))
                self._fastapi_router_mounts.setdefault(router_name, []).append((include_prefix, include_auth))
        elif self._framework == "flask" and method_name == "register_blueprint" and owner_name:
            blueprint_name = self._name_from_expr(call.args[0]) if call.args else None
            if blueprint_name:
                url_prefix = self._normalize_prefix(self._keyword_constant(call, "url_prefix"))
                self._flask_mount_prefixes.setdefault(blueprint_name, []).append(url_prefix)
        elif self._framework == "django_rest" and method_name == "register" and owner_name in self._django_router_names:
            route_prefix = self._constant_str(call.args[0]) if call.args else None
            view_name = self._name_from_expr(call.args[1]) if len(call.args) > 1 else None
            if route_prefix and view_name:
                self._django_urlpatterns.setdefault(view_name, []).append(self._normalize_django_path(route_prefix))

    def _extract_fastapi_routes(self, path: Path, tree: ast.Module) -> list[EndpointInfo]:
        endpoints: list[EndpointInfo] = []
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                route = self._parse_fastapi_decorator(decorator)
                if route is None:
                    continue
                owner_name, method, route_path, response_model, decorators, decorator_auth = route
                base_path = self._join_paths(self._router_prefixes.get(owner_name, ""), route_path)
                mount_contexts = self._fastapi_mount_contexts(owner_name)
                for mount_prefix, mount_auth in mount_contexts:
                    endpoint_path = self._join_paths(mount_prefix, base_path)
                    request_body, parameters, auth_required = self._extract_function_signature(node, endpoint_path, method)
                    final_auth = auth_required or decorator_auth or mount_auth or self._fastapi_scope_auth.get(owner_name, False)
                    endpoints.append(
                        EndpointInfo(
                            method=method,
                            path=endpoint_path,
                            handler_name=node.name,
                            docstring=ast.get_docstring(node),
                            parameters=parameters,
                            request_body=request_body,
                            response_model=response_model,
                            auth_required=final_auth,
                            decorators=decorators,
                            source_file=str(path),
                            line_number=node.lineno,
                            confidence=0.92,
                        )
                    )
                    self._source_evidence["endpoints"].add(str(path))
        return endpoints

    def _extract_flask_routes(self, path: Path, tree: ast.Module) -> list[EndpointInfo]:
        endpoints: list[EndpointInfo] = []
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            route_specs = self._parse_flask_decorators(node.decorator_list)
            for owner_name, method, route_path, decorators, auth_required in route_specs:
                base_path = self._join_paths(self._flask_prefixes.get(owner_name, ""), route_path)
                mount_prefixes = self._flask_mount_prefixes.get(owner_name, [""])
                for mount_prefix in mount_prefixes:
                    endpoint_path = self._join_paths(mount_prefix, base_path)
                    request_body, parameters, signature_auth = self._extract_function_signature(node, endpoint_path, method)
                    response_model = self._resolve_model_from_expr(node.returns) if node.returns is not None else None
                    endpoints.append(
                        EndpointInfo(
                            method=method,
                            path=endpoint_path,
                            handler_name=node.name,
                            docstring=ast.get_docstring(node),
                            parameters=parameters,
                            request_body=request_body,
                            response_model=response_model,
                            auth_required=auth_required or signature_auth,
                            decorators=decorators,
                            source_file=str(path),
                            line_number=node.lineno,
                            confidence=0.88,
                        )
                    )
                    self._source_evidence["endpoints"].add(str(path))
        return endpoints

    def _extract_django_routes(self, path: Path, tree: ast.Module) -> list[EndpointInfo]:
        endpoints: list[EndpointInfo] = []
        function_lookup = {
            node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        class_lookup = {
            node.name: node for node in tree.body if isinstance(node, ast.ClassDef) and self._is_django_view_class(node)
        }
        for view_name, route_paths in self._django_urlpatterns.items():
            if view_name in function_lookup:
                endpoints.extend(self._extract_django_function_view(path, function_lookup[view_name], route_paths))
            elif view_name in class_lookup:
                endpoints.extend(self._extract_django_class_view(path, class_lookup[view_name], route_paths))
        return endpoints

    def _extract_django_function_view(
        self,
        path: Path,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        route_paths: list[str],
    ) -> list[EndpointInfo]:
        methods = self._django_api_view_methods(node) or ["GET"]
        endpoints: list[EndpointInfo] = []
        for route_path in route_paths:
            for method in methods:
                request_body, parameters, auth_required = self._extract_function_signature(
                    node,
                    route_path,
                    method,
                    skip_names={"request"},
                )
                endpoints.append(
                    EndpointInfo(
                        method=method,
                        path=route_path,
                        handler_name=node.name,
                        docstring=ast.get_docstring(node),
                        parameters=parameters,
                        request_body=request_body,
                        response_model=None,
                        auth_required=auth_required or self._has_auth_decorator(node.decorator_list),
                        decorators=[self._expr_to_str(dec) for dec in node.decorator_list],
                        source_file=str(path),
                        line_number=node.lineno,
                        confidence=0.85,
                    )
                )
                self._source_evidence["endpoints"].add(str(path))
        return endpoints

    def _extract_django_class_view(self, path: Path, node: ast.ClassDef, route_paths: list[str]) -> list[EndpointInfo]:
        serializer_model = self._serializer_from_class(node)
        class_auth = self._class_requires_auth(node)
        endpoints: list[EndpointInfo] = []
        for child in node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            method_name = child.name.lower()
            if method_name in HTTP_METHODS:
                methods_and_paths = [(method_name.upper(), route) for route in route_paths]
            elif method_name in DJANGO_ACTION_METHODS:
                method, detail = DJANGO_ACTION_METHODS[method_name]
                methods_and_paths = [(method, self._route_with_detail(route, detail)) for route in route_paths]
            else:
                action_spec = self._parse_django_action(child)
                if action_spec is None:
                    continue
                action_methods, detail, action_path = action_spec
                methods_and_paths = []
                for route in route_paths:
                    base_path = self._route_with_detail(route, detail)
                    full_path = self._join_paths(base_path, action_path)
                    methods_and_paths.extend((method, full_path) for method in action_methods)

            for http_method, route_path in methods_and_paths:
                request_body, parameters, signature_auth = self._extract_function_signature(
                    child,
                    route_path,
                    http_method,
                    skip_names={"self", "request", "pk"},
                )
                if request_body is None and http_method in {"POST", "PUT", "PATCH"}:
                    request_body = serializer_model
                endpoints.append(
                    EndpointInfo(
                        method=http_method,
                        path=route_path,
                        handler_name=f"{node.name}.{child.name}",
                        docstring=ast.get_docstring(child) or ast.get_docstring(node),
                        parameters=parameters,
                        request_body=request_body,
                        response_model=serializer_model,
                        auth_required=class_auth or signature_auth,
                        decorators=[self._expr_to_str(dec) for dec in child.decorator_list],
                        source_file=str(path),
                        line_number=child.lineno,
                        confidence=0.83,
                    )
                )
                self._source_evidence["endpoints"].add(str(path))
        return endpoints

    def _parse_fastapi_decorator(
        self,
        decorator: ast.expr,
    ) -> tuple[str, str, str, ModelInfo | None, list[str], bool] | None:
        if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
            return None
        method_name = decorator.func.attr.lower()
        if method_name not in HTTP_METHODS:
            return None
        owner_name = self._name_from_expr(decorator.func.value)
        route_path = self._constant_str(decorator.args[0]) if decorator.args else None
        if owner_name is None or route_path is None:
            return None
        response_model = self._resolve_model_from_expr(self._keyword_expr(decorator, "response_model"))
        decorator_auth = self._dependencies_list_implies_auth(self._keyword_expr(decorator, "dependencies"))
        return owner_name, method_name.upper(), route_path, response_model, [self._expr_to_str(decorator)], decorator_auth

    def _parse_flask_decorators(self, decorators: list[ast.expr]) -> list[tuple[str, str, str, list[str], bool]]:
        results: list[tuple[str, str, str, list[str], bool]] = []
        auth_required = self._has_auth_decorator(decorators)
        for decorator in decorators:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            owner_name = self._name_from_expr(decorator.func.value)
            if owner_name is None:
                continue
            method_name = decorator.func.attr.lower()
            route_path = self._constant_str(decorator.args[0]) if decorator.args else None
            if route_path is None:
                continue
            if method_name in HTTP_METHODS:
                results.append(
                    (
                        owner_name,
                        method_name.upper(),
                        self._normalize_flask_path(route_path),
                        [self._expr_to_str(decorator)],
                        auth_required,
                    )
                )
            elif method_name == "route":
                methods = self._keyword_list_of_strings(decorator, "methods") or ["GET"]
                for method in methods:
                    results.append(
                        (
                            owner_name,
                            method.upper(),
                            self._normalize_flask_path(route_path),
                            [self._expr_to_str(decorator)],
                            auth_required,
                        )
                    )
        return results

    def _extract_function_signature(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        route_path: str,
        method: str,
        skip_names: set[str] | None = None,
    ) -> tuple[ModelInfo | None, list[ParamInfo], bool]:
        path_params = self._path_param_names(route_path)
        request_body: ModelInfo | None = None
        parameters: list[ParamInfo] = []
        auth_required = False
        skip_names = skip_names or set()

        positional = list(node.args.posonlyargs) + list(node.args.args)
        pos_defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
        kw_defaults = list(node.args.kw_defaults)

        for arg, default in list(zip(positional, pos_defaults)) + list(zip(node.args.kwonlyargs, kw_defaults)):
            if arg.arg in skip_names or arg.arg == "self":
                continue
            base_annotation = self._annotation_base_expr(arg.annotation)
            annotation_text = self._annotation_to_str(base_annotation)
            metadata_calls = self._annotation_metadata_calls(arg.annotation)
            dependency_call = self._dependency_call(default, metadata_calls)
            param_config_call = self._parameter_config_call(default, metadata_calls)
            call_name = self._call_name(param_config_call.func) if isinstance(param_config_call, ast.Call) else None

            if dependency_call is not None:
                auth_required = auth_required or self._dependency_call_implies_auth(dependency_call)
                continue

            if request_body is None:
                model_candidate = self._resolve_model_from_expr(base_annotation)
                if (
                    model_candidate is not None
                    and arg.arg not in path_params
                    and call_name not in {"Query", "Path", "Header", "Cookie"}
                    and method in {"POST", "PUT", "PATCH"}
                ):
                    request_body = model_candidate
                    continue

            location = "query"
            if arg.arg in path_params or call_name == "Path":
                location = "path"
            elif call_name == "Header":
                location = "header"
            elif call_name == "Body":
                location = "body"

            parameters.append(
                ParamInfo(
                    name=arg.arg,
                    type=annotation_text,
                    required=self._parameter_required(base_annotation, param_config_call or default, location),
                    default=self._expr_to_str(param_config_call or default) if (param_config_call or default) is not None else None,
                    location=location,
                    description=self._field_call_description(param_config_call or default),
                )
            )

        return request_body, parameters, auth_required or self._has_auth_decorator(node.decorator_list)

    def _maybe_register_model(self, path: Path, node: ast.ClassDef) -> None:
        if self._is_pydantic_model(node):
            model = self._extract_pydantic_model(path, node)
        elif self._is_serializer_model(node):
            model = self._extract_serializer_model(path, node)
        else:
            return
        self._model_registry[node.name] = model
        self._source_evidence["models"].add(str(path))

    def _extract_pydantic_model(self, path: Path, node: ast.ClassDef) -> ModelInfo:
        fields: list[FieldInfo] = []
        for child in node.body:
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                fields.append(
                    FieldInfo(
                        name=child.target.id,
                        type=self._annotation_to_str(child.annotation),
                        required=self._annassign_required(child),
                        default=self._expr_to_str(child.value) if child.value is not None else None,
                        description=self._field_call_description(child.value),
                    )
                )
        return ModelInfo(
            name=node.name,
            docstring=ast.get_docstring(node),
            fields=fields,
            source_file=str(path),
            line_number=node.lineno,
        )

    def _extract_serializer_model(self, path: Path, node: ast.ClassDef) -> ModelInfo:
        fields: list[FieldInfo] = []
        for child in node.body:
            if not isinstance(child, ast.Assign) or len(child.targets) != 1 or not isinstance(child.targets[0], ast.Name):
                continue
            if not isinstance(child.value, ast.Call):
                continue
            fields.append(
                FieldInfo(
                    name=child.targets[0].id,
                    type=self._serializer_field_type(child.value),
                    required=self._serializer_field_required(child.value),
                    description=self._serializer_field_description(child.value),
                )
            )
        return ModelInfo(
            name=node.name,
            docstring=ast.get_docstring(node),
            fields=fields,
            source_file=str(path),
            line_number=node.lineno,
        )

    def _collect_django_urlpatterns(self, tree: ast.Module) -> None:
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == "urlpatterns" for target in node.targets):
                continue
            if not isinstance(node.value, (ast.List, ast.Tuple)):
                continue
            for element in node.value.elts:
                if not isinstance(element, ast.Call):
                    continue
                if self._call_name(element.func) not in {"path", "re_path"}:
                    continue
                route = self._constant_str(element.args[0]) if element.args else None
                target_name = self._django_view_name(element.args[1] if len(element.args) > 1 else None)
                if route and target_name:
                    self._django_urlpatterns.setdefault(target_name, []).append(self._normalize_django_path(route))

    def _django_view_name(self, expr: ast.expr | None) -> str | None:
        if isinstance(expr, ast.Name):
            return expr.id
        if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and expr.func.attr == "as_view":
            return self._name_from_expr(expr.func.value)
        return None

    def _django_api_view_methods(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and self._call_name(decorator.func) == "api_view":
                for arg in decorator.args:
                    if isinstance(arg, (ast.List, ast.Tuple)):
                        return [value.upper() for value in (self._constant_str(item) for item in arg.elts) if value]
        return []

    def _is_django_view_class(self, node: ast.ClassDef) -> bool:
        view_bases = {"APIView", "GenericAPIView", "ViewSet", "ModelViewSet", "ReadOnlyModelViewSet"}
        return any(self._base_name(base) in view_bases for base in node.bases)

    def _serializer_from_class(self, node: ast.ClassDef) -> ModelInfo | None:
        for child in node.body:
            if isinstance(child, ast.Assign) and len(child.targets) == 1 and isinstance(child.targets[0], ast.Name):
                if child.targets[0].id == "serializer_class":
                    return self._resolve_model_from_expr(child.value)
        return None

    def _class_requires_auth(self, node: ast.ClassDef) -> bool:
        for child in node.body:
            if not isinstance(child, ast.Assign):
                continue
            for target in child.targets:
                if isinstance(target, ast.Name) and target.id in {"permission_classes", "authentication_classes"}:
                    self._auth_patterns.add(target.id)
                    return True
        return False

    def _route_with_detail(self, route_path: str, detail: bool) -> str:
        route_path = route_path.rstrip("/")
        if detail and "{pk}" not in route_path and "{id}" not in route_path:
            return f"{route_path}/{{pk}}"
        return route_path or "/"

    def _parse_django_action(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[list[str], bool, str] | None:
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or self._call_name(decorator.func) != "action":
                continue
            methods = [method.upper() for method in self._keyword_list_of_strings(decorator, "methods")] or ["GET"]
            detail = bool(self._keyword_constant(decorator, "detail"))
            url_path = self._keyword_constant(decorator, "url_path")
            if not isinstance(url_path, str):
                url_path = node.name.replace("_", "-")
            return methods, detail, url_path
        return None

    def _resolve_model_from_expr(self, expr: ast.expr | None) -> ModelInfo | None:
        name = self._model_name_from_expr(expr) if expr is not None else None
        return self._model_registry.get(name) if name else None

    def _model_name_from_expr(self, expr: ast.expr) -> str | None:
        if isinstance(expr, ast.Name):
            return expr.id
        if isinstance(expr, ast.Attribute):
            return expr.attr
        if isinstance(expr, ast.Subscript):
            if self._name_from_expr(expr.value) == "Annotated":
                return self._model_name_from_expr(self._annotation_base_expr(expr) or expr.slice)
            if isinstance(expr.slice, ast.Tuple):
                names = [self._model_name_from_expr(item) for item in expr.slice.elts]
                return next((name for name in reversed(names) if name), None)
            return self._model_name_from_expr(expr.slice)
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr):
            return self._model_name_from_expr(expr.right) or self._model_name_from_expr(expr.left)
        if isinstance(expr, ast.Call):
            return self._model_name_from_expr(expr.func)
        return None

    def _is_pydantic_model(self, node: ast.ClassDef) -> bool:
        return any(self._base_name(base) == "BaseModel" for base in node.bases)

    def _is_serializer_model(self, node: ast.ClassDef) -> bool:
        return any(self._base_name(base) in {"Serializer", "ModelSerializer"} for base in node.bases)

    def _base_name(self, expr: ast.expr) -> str | None:
        if isinstance(expr, ast.Name):
            return expr.id
        if isinstance(expr, ast.Attribute):
            return expr.attr
        return None

    def _annotation_base_expr(self, annotation: ast.expr | None) -> ast.expr | None:
        if (
            isinstance(annotation, ast.Subscript)
            and self._name_from_expr(annotation.value) == "Annotated"
            and isinstance(annotation.slice, ast.Tuple)
            and annotation.slice.elts
        ):
            return annotation.slice.elts[0]
        return annotation

    def _annotation_metadata_calls(self, annotation: ast.expr | None) -> list[ast.Call]:
        if (
            isinstance(annotation, ast.Subscript)
            and self._name_from_expr(annotation.value) == "Annotated"
            and isinstance(annotation.slice, ast.Tuple)
        ):
            return [expr for expr in annotation.slice.elts[1:] if isinstance(expr, ast.Call)]
        return []

    def _dependency_call(self, default: ast.expr | None, metadata_calls: list[ast.Call]) -> ast.Call | None:
        for expr in [default, *metadata_calls]:
            if isinstance(expr, ast.Call) and self._call_name(expr.func) in {"Depends", "Security"}:
                return expr
        return None

    def _parameter_config_call(self, default: ast.expr | None, metadata_calls: list[ast.Call]) -> ast.Call | None:
        for expr in [default, *metadata_calls]:
            if isinstance(expr, ast.Call) and self._call_name(expr.func) in {"Query", "Path", "Header", "Body", "Cookie"}:
                return expr
        return None

    def _dependency_call_implies_auth(self, call: ast.Call) -> bool:
        call_name = self._call_name(call.func)
        dependency_name = self._name_from_expr(call.args[0]) if call.args else None
        if call_name == "Security":
            if dependency_name:
                self._auth_patterns.add(dependency_name)
            return True
        if dependency_name and any(hint in dependency_name.lower() for hint in AUTH_DEPENDENCY_HINTS):
            self._auth_patterns.add(dependency_name)
            return True
        return False

    def _dependencies_list_implies_auth(self, expr: ast.expr | None) -> bool:
        if not isinstance(expr, (ast.List, ast.Tuple)):
            return False
        return any(self._dependency_call_implies_auth(item) for item in expr.elts if isinstance(item, ast.Call))

    def _fastapi_mount_contexts(self, owner_name: str) -> list[tuple[str, bool]]:
        if owner_name == "app":
            return [("", self._fastapi_scope_auth.get(owner_name, False))]
        contexts = self._fastapi_router_mounts.get(owner_name)
        if contexts:
            return contexts
        return [("", self._fastapi_scope_auth.get(owner_name, False))]

    def _annassign_required(self, node: ast.AnnAssign) -> bool:
        if node.value is None:
            return not self._annotation_is_optional(node.annotation)
        if isinstance(node.value, ast.Constant) and node.value.value is None:
            return False
        if isinstance(node.value, ast.Call) and self._call_name(node.value.func) == "Field":
            if node.value.args:
                first = node.value.args[0]
                if isinstance(first, ast.Constant) and first.value is Ellipsis:
                    return True
                if isinstance(first, ast.Constant) and first.value is None:
                    return False
        return not self._annotation_is_optional(node.annotation)

    def _serializer_field_type(self, call: ast.Call) -> str:
        name = self._call_name(call.func) or "Field"
        return name[:-5].lower() if name.endswith("Field") else name.lower()

    def _serializer_field_required(self, call: ast.Call) -> bool:
        for keyword in call.keywords:
            if keyword.arg == "read_only" and bool(self._literal_value(keyword.value)):
                return False
            if keyword.arg == "required":
                return bool(self._literal_value(keyword.value))
        return True

    def _serializer_field_description(self, call: ast.Call) -> str | None:
        for keyword in call.keywords:
            if keyword.arg in {"help_text", "label"}:
                value = self._literal_value(keyword.value)
                if isinstance(value, str):
                    return value
        return None

    def _normalize_prefix(self, value: Any) -> str:
        if not isinstance(value, str) or not value:
            return ""
        return "/" + value.strip("/")

    def _join_paths(self, prefix: str, route: str) -> str:
        if not prefix:
            return route
        return "/" + "/".join(part for part in [prefix.strip("/"), route.strip("/")] if part)

    def _normalize_django_path(self, route: str) -> str:
        route = re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", route.strip())
        route = "/" + route.lstrip("/")
        return route.rstrip("/") or "/"

    def _normalize_flask_path(self, route: str) -> str:
        return re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", route)

    def _path_param_names(self, route_path: str) -> set[str]:
        return set(re.findall(r"{([^}]+)}", route_path))

    def _parameter_required(self, annotation: ast.expr | None, default: ast.expr | None, location: str) -> bool:
        if location == "path":
            return True
        if default is None:
            return not self._annotation_is_optional(annotation)
        if isinstance(default, ast.Constant) and default.value is None:
            return False
        if isinstance(default, ast.Call) and self._call_name(default.func) in {"Query", "Path", "Header", "Body"}:
            if default.args:
                first = default.args[0]
                if isinstance(first, ast.Constant) and first.value is Ellipsis:
                    return True
                if isinstance(first, ast.Constant) and first.value is None:
                    return False
        return False

    def _annotation_is_optional(self, annotation: ast.expr | None) -> bool:
        text = self._annotation_to_str(annotation) or ""
        return "Optional[" in text or "| None" in text or "None |" in text

    def _field_call_description(self, expr: ast.expr | None) -> str | None:
        if not isinstance(expr, ast.Call):
            return None
        for keyword in expr.keywords:
            if keyword.arg in {"description", "help_text"}:
                value = self._literal_value(keyword.value)
                if isinstance(value, str):
                    return value
        return None

    def _keyword_constant(self, call: ast.Call, name: str) -> Any:
        return self._literal_value(self._keyword_expr(call, name))

    def _keyword_expr(self, call: ast.Call, name: str) -> ast.expr | None:
        for keyword in call.keywords:
            if keyword.arg == name:
                return keyword.value
        return None

    def _keyword_list_of_strings(self, call: ast.Call, name: str) -> list[str]:
        expr = self._keyword_expr(call, name)
        if isinstance(expr, (ast.List, ast.Tuple)):
            return [value for value in (self._constant_str(item) for item in expr.elts) if value]
        return []

    def _literal_value(self, expr: ast.expr | None) -> Any:
        return expr.value if isinstance(expr, ast.Constant) else None

    def _call_name(self, expr: ast.expr | None) -> str | None:
        if isinstance(expr, ast.Name):
            return expr.id
        if isinstance(expr, ast.Attribute):
            return expr.attr
        return None

    def _name_from_expr(self, expr: ast.expr | None) -> str | None:
        if isinstance(expr, ast.Name):
            return expr.id
        if isinstance(expr, ast.Attribute):
            return expr.attr
        return None

    def _annotation_to_str(self, expr: ast.expr | None) -> str | None:
        if expr is None:
            return None
        try:
            return ast.unparse(expr)
        except Exception:
            return None

    def _constant_str(self, expr: ast.expr | None) -> str | None:
        value = self._literal_value(expr)
        return value if isinstance(value, str) else None

    def _expr_to_str(self, expr: ast.expr | None) -> str:
        if expr is None:
            return ""
        try:
            return ast.unparse(expr)
        except Exception:
            return repr(expr)

    def _has_auth_decorator(self, decorators: list[ast.expr]) -> bool:
        for decorator in decorators:
            name = self._call_name(decorator.func) if isinstance(decorator, ast.Call) else self._call_name(decorator)
            if name in AUTH_DECORATOR_HINTS or (name and name.endswith("_required")):
                if name:
                    self._auth_patterns.add(name)
                return True
        return False
