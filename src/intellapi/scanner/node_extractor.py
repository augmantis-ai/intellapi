"""Node/TypeScript extractor for Express, Next.js, and SvelteKit."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from intellapi.scanner.base_extractor import BaseExtractor
from intellapi.scanner.ir import EndpointInfo, FieldInfo, IntermediateRepresentation, ModelInfo, ParamInfo


HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
HTTP_METHODS_LOWER = tuple(method.lower() for method in HTTP_METHODS)
AUTH_HINTS = (
    "auth",
    "token",
    "session",
    "oauth",
    "jwt",
    "bearer",
    "currentuser",
    "getserversession",
    "clerk",
    "supabase",
    "protected",
)
JSON_CALL_PATTERNS = (
    re.compile(r"(?:NextResponse|Response)\.json\("),
    re.compile(r"res(?:\s*\.\s*status\([^)]*\))?\s*\.json\("),
    re.compile(r"(?<![.\w])json\("),
)


class NodeExtractor(BaseExtractor):
    """Extract API details from JS/TS frameworks using static heuristics."""

    def __init__(self, framework: str = "express"):
        self._framework = framework
        self._last_language = "javascript"
        self._reset_state()

    @property
    def framework_name(self) -> str:
        names = {"express": "Express", "nextjs": "Next.js", "sveltekit": "SvelteKit"}
        return names.get(self._framework, self._framework)

    @property
    def language(self) -> str:
        return self._last_language

    def extract(self, files: list[Path]) -> IntermediateRepresentation:
        self._reset_state()
        if not files:
            return IntermediateRepresentation(framework=self._framework, language="unknown")

        source_files = sorted(path.resolve() for path in files if path.suffix.lower() in {".js", ".jsx", ".ts", ".tsx"})
        if not source_files:
            return IntermediateRepresentation(framework=self._framework, language="unknown")

        project_root = self._project_root(source_files)
        self._load_package_metadata(project_root)

        documents: list[tuple[Path, str]] = []
        for path in source_files:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                self._warnings.append(f"Skipped unreadable file {path}: {exc}")
                continue
            documents.append((path, text))

        for path, text in documents:
            self._collect_models(path, text)

        if self._framework == "express":
            self._prepare_express_prefixes(documents)

        endpoints: list[EndpointInfo] = []
        for path, text in documents:
            if self._framework == "express":
                endpoints.extend(self._extract_express_routes(path, text))
            elif self._framework == "nextjs":
                endpoints.extend(self._extract_nextjs_routes(path, text, project_root))
            elif self._framework == "sveltekit":
                endpoints.extend(self._extract_sveltekit_routes(path, text, project_root))

        self._last_language = (
            "typescript" if any(path.suffix.lower() in {".ts", ".tsx"} for path, _ in documents) else "javascript"
        )

        return IntermediateRepresentation(
            service_name=self._service_name or f"{self.framework_name} Service",
            framework=self._framework,
            language=self._last_language,
            endpoints=self._dedupe_endpoints(endpoints),
            models=sorted(self._model_registry.values(), key=lambda model: model.name),
            dependencies=sorted(self._dependencies),
            auth_patterns=sorted(self._auth_patterns),
            source_evidence={key: sorted(value) for key, value in self._source_evidence.items() if value},
            extraction_warnings=self._warnings,
        )

    def _reset_state(self) -> None:
        self._service_name: str | None = None
        self._dependencies: set[str] = set()
        self._warnings: list[str] = []
        self._auth_patterns: set[str] = set()
        self._source_evidence: dict[str, set[str]] = {"endpoints": set(), "models": set()}
        self._model_registry: dict[str, ModelInfo] = {}
        self._express_prefixes: dict[str, set[str]] = {"app": {""}}
        self._express_router_names: set[str] = {"app"}

    def _project_root(self, files: list[Path]) -> Path:
        package_roots: list[Path] = []
        for path in files:
            for parent in [path.parent, *path.parents]:
                if (parent / "package.json").exists():
                    package_roots.append(parent)
                    break

        if package_roots:
            common = Path(os.path.commonpath([str(root) for root in package_roots]))
            if (common / "package.json").exists():
                return common
            return min(package_roots, key=lambda root: len(root.parts))

        return Path(os.path.commonpath([str(path.parent) for path in files]))

    def _load_package_metadata(self, project_root: Path) -> None:
        package_json = project_root / "package.json"
        if not package_json.exists():
            return

        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self._warnings.append(f"Could not parse package.json at {package_json}: {exc}")
            return

        name = data.get("name")
        if isinstance(name, str) and name.strip():
            self._service_name = name.strip()

        for group in ("dependencies", "devDependencies", "peerDependencies"):
            deps = data.get(group)
            if isinstance(deps, dict):
                self._dependencies.update(str(key) for key in deps.keys())

    def _collect_models(self, path: Path, text: str) -> None:
        interface_pattern = re.compile(
            r"(?:export\s+)?interface\s+([A-Z][A-Za-z0-9_]*)\s*\{(?P<body>.*?)\}",
            re.DOTALL,
        )
        type_pattern = re.compile(
            r"(?:export\s+)?type\s+([A-Z][A-Za-z0-9_]*)\s*=\s*\{(?P<body>.*?)\};",
            re.DOTALL,
        )

        for pattern in (interface_pattern, type_pattern):
            for match in pattern.finditer(text):
                fields = self._parse_ts_object_fields(match.group("body"))
                model = ModelInfo(
                    name=match.group(1),
                    fields=fields,
                    source_file=str(path),
                    line_number=text[: match.start()].count("\n") + 1,
                )
                self._model_registry[model.name] = model
                self._source_evidence["models"].add(str(path))

    def _prepare_express_prefixes(self, documents: list[tuple[Path, str]]) -> None:
        self._express_router_names = {"app"}
        mounts: list[tuple[str, str, str]] = []

        for _, text in documents:
            for match in re.finditer(
                r"\b(?:const|let|var)\s+(\w+)\s*=\s*(?:express\.)?Router\(\s*\)",
                text,
            ):
                self._express_router_names.add(match.group(1))
            for match in re.finditer(
                r"\b(?:const|let|var)\s+(\w+)\s*=\s*Router\(\s*\)",
                text,
            ):
                self._express_router_names.add(match.group(1))

        for name in self._express_router_names:
            self._express_prefixes.setdefault(name, {""} if name == "app" else set())

        use_pattern = re.compile(r"(?P<owner>\w+)\.use\(")
        for _, text in documents:
            for match in use_pattern.finditer(text):
                call_end = self._balanced_segment_end(text, match.end() - 1)
                if call_end is None:
                    self._warnings.append(f"Skipped malformed Express mount near index {match.start()}.")
                    continue

                args = self._split_top_level_args(text[match.end() : call_end])
                if not args:
                    continue

                child = args[-1].strip()
                owner = match.group("owner")
                if owner not in self._express_router_names or child not in self._express_router_names:
                    continue

                prefix = ""
                if len(args) >= 2:
                    maybe_prefix = self._string_literal(args[0])
                    if maybe_prefix is not None:
                        prefix = self._normalize_prefix(maybe_prefix)
                mounts.append((owner, child, prefix))

        changed = True
        while changed:
            changed = False
            for owner, child, prefix in mounts:
                owner_prefixes = self._express_prefixes.get(owner, {""})
                child_prefixes = self._express_prefixes.setdefault(child, set())
                for base_prefix in owner_prefixes:
                    full_prefix = self._join_paths(base_prefix, prefix or "/")
                    normalized = "" if full_prefix == "/" else full_prefix
                    if normalized not in child_prefixes:
                        child_prefixes.add(normalized)
                        changed = True

        for name in self._express_router_names:
            if name != "app" and not self._express_prefixes.get(name):
                self._express_prefixes[name] = {""}

    def _extract_express_routes(self, path: Path, text: str) -> list[EndpointInfo]:
        endpoints: list[EndpointInfo] = []
        for route in self._iter_express_routes(text):
            parameters = self._express_parameters(str(route["path"]), str(route["doc"]), str(route["handler"]))
            auth_required = self._express_middlewares_imply_auth(list(route["middlewares"])) or self._text_implies_auth(
                str(route["handler"]) + "\n" + str(route["doc"])
            )
            request_body = self._request_body_model(
                path=path,
                route_path=str(route["path"]),
                method=str(route["method"]),
                body_text=str(route["handler"]),
                doc=str(route["doc"]),
                body_patterns=("req.body", "body"),
            )
            response_model = self._response_model_from_text(
                path,
                str(route["path"]),
                str(route["method"]),
                str(route["handler"]),
            )
            for prefix in self._express_prefixes.get(str(route["target"]), {""}):
                full_path = self._join_paths(prefix, self._normalize_express_path(str(route["path"])))
                endpoints.append(
                    EndpointInfo(
                        method=str(route["method"]),
                        path=full_path,
                        handler_name=self._route_handler_name(str(route["method"]), full_path, str(route["handler"])),
                        docstring=self._jsdoc_summary(str(route["doc"])),
                        parameters=parameters,
                        request_body=request_body,
                        response_model=response_model,
                        auth_required=auth_required,
                        decorators=[f"{route['target']}.{str(route['method']).lower()}"],
                        source_file=str(path),
                        line_number=int(route["line_number"]),
                        confidence=0.85,
                    )
                )
                self._source_evidence["endpoints"].add(str(path))
        return endpoints

    def _extract_nextjs_routes(self, path: Path, text: str, project_root: Path) -> list[EndpointInfo]:
        route_path = self._nextjs_route_path(path, project_root)
        if route_path is None:
            return []

        if self._is_nextjs_pages_route(path, project_root):
            return self._extract_nextjs_pages_routes(path, text, route_path)

        endpoints: list[EndpointInfo] = []
        for handler in self._iter_exported_handlers(text):
            parameters = self._merge_route_params(
                route_path,
                self._query_params_from_text(str(handler["body"]), "searchParams"),
            )
            request_body = self._request_body_model(
                path=path,
                route_path=route_path,
                method=str(handler["name"]),
                body_text=str(handler["body"]),
                doc=str(handler["doc"]),
                body_patterns=("body", "request_body"),
            )
            response_model = self._response_model_from_text(path, route_path, str(handler["name"]), str(handler["body"]))
            endpoints.append(
                EndpointInfo(
                    method=str(handler["name"]),
                    path=route_path,
                    handler_name=str(handler["name"]),
                    docstring=self._jsdoc_summary(str(handler["doc"])),
                    parameters=self._dedupe_params(parameters),
                    request_body=request_body,
                    response_model=response_model,
                    auth_required=self._text_implies_auth(str(handler["body"]) + "\n" + str(handler["doc"])),
                    decorators=["exported route handler"],
                    source_file=str(path),
                    line_number=int(handler["line_number"]),
                    confidence=0.87,
                )
            )
            self._source_evidence["endpoints"].add(str(path))
        return endpoints

    def _extract_nextjs_pages_routes(self, path: Path, text: str, route_path: str) -> list[EndpointInfo]:
        handler = self._extract_default_export_handler(text)
        if handler is None:
            self._warnings.append(
                f"Could not identify a default-export API handler in {path}. "
                "Only explicit pages/api handlers are supported."
            )
            return []

        branches = self._pages_method_branches(str(handler["body"]))
        if not branches:
            self._warnings.append(
                f"Could not infer HTTP method branches in {path}. "
                "Use req.method checks or switch(req.method) for reliable extraction."
            )
            return []

        endpoints: list[EndpointInfo] = []
        for method, branch_body in branches:
            parameters = self._merge_route_params(route_path, self._query_params_from_text(branch_body, "req.query"))
            request_body = self._request_body_model(
                path=path,
                route_path=route_path,
                method=method,
                body_text=branch_body,
                doc=str(handler["doc"]),
                body_patterns=("req.body", "body"),
            )
            response_model = self._response_model_from_text(path, route_path, method, branch_body)
            endpoints.append(
                EndpointInfo(
                    method=method,
                    path=route_path,
                    handler_name=f"{handler['name']}_{method.lower()}",
                    docstring=self._jsdoc_summary(str(handler["doc"])),
                    parameters=self._dedupe_params(parameters),
                    request_body=request_body,
                    response_model=response_model,
                    auth_required=self._text_implies_auth(branch_body + "\n" + str(handler["doc"])),
                    decorators=["default-export API handler"],
                    source_file=str(path),
                    line_number=int(handler["line_number"]),
                    confidence=0.83,
                )
            )
            self._source_evidence["endpoints"].add(str(path))
        return endpoints

    def _extract_sveltekit_routes(self, path: Path, text: str, project_root: Path) -> list[EndpointInfo]:
        route_path = self._sveltekit_route_path(path, project_root)
        if route_path is None:
            return []

        endpoints: list[EndpointInfo] = []
        for handler in self._iter_exported_handlers(text):
            parameters = self._merge_route_params(
                route_path,
                self._query_params_from_text(str(handler["body"]), "url.searchParams"),
            )
            request_body = self._request_body_model(
                path=path,
                route_path=route_path,
                method=str(handler["name"]),
                body_text=str(handler["body"]),
                doc=str(handler["doc"]),
                body_patterns=("request", "body"),
            )
            response_model = self._response_model_from_text(path, route_path, str(handler["name"]), str(handler["body"]))
            endpoints.append(
                EndpointInfo(
                    method=str(handler["name"]),
                    path=route_path,
                    handler_name=str(handler["name"]),
                    docstring=self._jsdoc_summary(str(handler["doc"])),
                    parameters=self._dedupe_params(parameters),
                    request_body=request_body,
                    response_model=response_model,
                    auth_required=self._text_implies_auth(str(handler["body"]) + "\n" + str(handler["doc"])),
                    decorators=["SvelteKit route handler"],
                    source_file=str(path),
                    line_number=int(handler["line_number"]),
                    confidence=0.86,
                )
            )
            self._source_evidence["endpoints"].add(str(path))
        return endpoints

    def _iter_express_routes(self, text: str) -> list[dict[str, object]]:
        routes: list[dict[str, object]] = []
        method_pattern = "|".join(HTTP_METHODS_LOWER)

        direct_pattern = re.compile(rf"(?P<target>\w+)\.(?P<method>{method_pattern})\(")
        for match in direct_pattern.finditer(text):
            call_end = self._balanced_segment_end(text, match.end() - 1)
            if call_end is None:
                self._warnings.append(f"Skipped malformed Express route call near index {match.start()}.")
                continue
            args = self._split_top_level_args(text[match.end() : call_end])
            if not args:
                continue
            route_path = self._string_literal(args[0])
            if route_path is None:
                continue
            routes.append(
                {
                    "target": match.group("target"),
                    "method": match.group("method").upper(),
                    "path": route_path,
                    "middlewares": args[1:-1] if len(args) > 1 else [],
                    "handler": args[-1] if len(args) > 1 else "",
                    "doc": self._preceding_jsdoc(text, match.start()),
                    "line_number": text[: match.start()].count("\n") + 1,
                }
            )

        chain_pattern = re.compile(r"(?P<target>\w+)\.route\(")
        for match in chain_pattern.finditer(text):
            route_end = self._balanced_segment_end(text, match.end() - 1)
            if route_end is None:
                continue
            route_args = self._split_top_level_args(text[match.end() : route_end])
            if not route_args:
                continue
            route_path = self._string_literal(route_args[0])
            if route_path is None:
                continue

            cursor = route_end + 1
            while cursor < len(text):
                chained = re.match(rf"\s*\.\s*(?P<method>{method_pattern})\(", text[cursor:])
                if chained is None:
                    break
                open_paren = cursor + chained.end() - 1
                call_end = self._balanced_segment_end(text, open_paren)
                if call_end is None:
                    self._warnings.append(f"Skipped malformed chained Express route near index {cursor}.")
                    break
                args = self._split_top_level_args(text[open_paren + 1 : call_end])
                routes.append(
                    {
                        "target": match.group("target"),
                        "method": chained.group("method").upper(),
                        "path": route_path,
                        "middlewares": args[:-1] if args else [],
                        "handler": args[-1] if args else "",
                        "doc": self._preceding_jsdoc(text, match.start()),
                        "line_number": text[: match.start()].count("\n") + 1,
                    }
                )
                cursor = call_end + 1

        return routes

    def _iter_exported_handlers(self, text: str) -> list[dict[str, object]]:
        handlers: list[dict[str, object]] = []
        seen: set[tuple[str, int]] = set()
        method_pattern = "|".join(HTTP_METHODS)

        function_pattern = re.compile(rf"export\s+(?:async\s+)?function\s+(?P<name>{method_pattern})\s*\(")
        for match in function_pattern.finditer(text):
            params_end = self._balanced_segment_end(text, match.end() - 1)
            if params_end is None:
                self._warnings.append(f"Skipped malformed exported handler {match.group('name')}.")
                continue
            body_start = text.find("{", params_end)
            if body_start == -1:
                continue
            body_end = self._balanced_brace_end(text, body_start)
            if body_end is None:
                self._warnings.append(f"Skipped malformed exported handler {match.group('name')}.")
                continue
            key = (match.group("name"), match.start())
            if key in seen:
                continue
            seen.add(key)
            handlers.append(
                {
                    "name": match.group("name"),
                    "body": text[body_start + 1 : body_end],
                    "doc": self._preceding_jsdoc(text, match.start()),
                    "line_number": text[: match.start()].count("\n") + 1,
                }
            )

        const_pattern = re.compile(rf"export\s+const\s+(?P<name>{method_pattern})\b")
        for match in const_pattern.finditer(text):
            search_window = text[match.end() : match.end() + 300]
            if "=" not in search_window:
                continue
            equals_index = text.find("=", match.end(), match.end() + 300)
            arrow_index = text.find("=>", equals_index, equals_index + 300) if equals_index != -1 else -1
            function_index = text.find("function", equals_index, equals_index + 300) if equals_index != -1 else -1
            if equals_index == -1 or (arrow_index == -1 and function_index == -1):
                continue
            if arrow_index != -1:
                body_start = text.find("{", arrow_index)
            else:
                open_paren = text.find("(", function_index, function_index + 300)
                if open_paren == -1:
                    continue
                params_end = self._balanced_segment_end(text, open_paren)
                if params_end is None:
                    self._warnings.append(f"Skipped malformed exported handler {match.group('name')}.")
                    continue
                body_start = text.find("{", params_end)
            if body_start == -1:
                continue
            body_end = self._balanced_brace_end(text, body_start)
            if body_end is None:
                self._warnings.append(f"Skipped malformed exported handler {match.group('name')}.")
                continue
            key = (match.group("name"), match.start())
            if key in seen:
                continue
            seen.add(key)
            handlers.append(
                {
                    "name": match.group("name"),
                    "body": text[body_start + 1 : body_end],
                    "doc": self._preceding_jsdoc(text, match.start()),
                    "line_number": text[: match.start()].count("\n") + 1,
                }
            )

        handlers.sort(key=lambda handler: int(handler["line_number"]))
        return handlers

    def _extract_default_export_handler(self, text: str) -> dict[str, object] | None:
        direct_pattern = re.compile(r"export\s+default\s+(?:async\s+)?function(?:\s+(?P<name>\w+))?\s*\(")
        direct_match = direct_pattern.search(text)
        if direct_match is not None:
            params_end = self._balanced_segment_end(text, direct_match.end() - 1)
            if params_end is None:
                return None
            body_start = text.find("{", params_end)
            if body_start == -1:
                return None
            body_end = self._balanced_brace_end(text, body_start)
            if body_end is None:
                return None
            return {
                "name": direct_match.group("name") or "handler",
                "body": text[body_start + 1 : body_end],
                "doc": self._preceding_jsdoc(text, direct_match.start()),
                "line_number": text[: direct_match.start()].count("\n") + 1,
            }

        export_reference = re.search(r"export\s+default\s+(?P<name>\w+)\s*;?", text)
        if export_reference is None:
            return None

        name = export_reference.group("name")
        variable_pattern = re.compile(rf"(?:const|let|var)\s+{name}\b")
        variable_match = variable_pattern.search(text)
        if variable_match is None:
            return None

        assignment_window = text[variable_match.end() : variable_match.end() + 300]
        equals_index = text.find("=", variable_match.end(), variable_match.end() + 300)
        arrow_index = text.find("=>", equals_index, equals_index + 300) if equals_index != -1 else -1
        function_index = text.find("function", equals_index, equals_index + 300) if equals_index != -1 else -1
        if "=" not in assignment_window or (arrow_index == -1 and function_index == -1):
            return None
        if arrow_index != -1:
            body_start = text.find("{", arrow_index)
        else:
            open_paren = text.find("(", function_index, function_index + 300)
            if open_paren == -1:
                return None
            params_end = self._balanced_segment_end(text, open_paren)
            if params_end is None:
                return None
            body_start = text.find("{", params_end)
        if body_start == -1:
            return None
        body_end = self._balanced_brace_end(text, body_start)
        if body_end is None:
            return None
        return {
            "name": name,
            "body": text[body_start + 1 : body_end],
            "doc": self._preceding_jsdoc(text, variable_match.start()),
            "line_number": text[: variable_match.start()].count("\n") + 1,
        }

    def _pages_method_branches(self, body: str) -> list[tuple[str, str]]:
        branches: list[tuple[str, str]] = []
        seen_methods: set[str] = set()

        switch_match = re.search(r"switch\s*\(\s*req\.method\s*\)\s*\{", body)
        if switch_match is not None:
            switch_end = self._balanced_brace_end(body, switch_match.end() - 1)
            if switch_end is not None:
                switch_body = body[switch_match.end() : switch_end]
                case_pattern = re.compile(r"case\s+['\"](?P<method>[A-Z]+)['\"]\s*:")
                case_matches = list(case_pattern.finditer(switch_body))
                for index, case_match in enumerate(case_matches):
                    method = case_match.group("method")
                    if method not in HTTP_METHODS or method in seen_methods:
                        continue
                    branch_start = case_match.end()
                    branch_end = case_matches[index + 1].start() if index + 1 < len(case_matches) else len(switch_body)
                    branches.append((method, switch_body[branch_start:branch_end]))
                    seen_methods.add(method)

        if branches:
            return branches

        condition_pattern = re.compile(r"req\.method\s*(?:===|==)\s*['\"](?P<method>[A-Z]+)['\"]")
        for condition in condition_pattern.finditer(body):
            method = condition.group("method")
            if method not in HTTP_METHODS or method in seen_methods:
                continue
            body_start = body.find("{", condition.end())
            if body_start == -1:
                continue
            body_end = self._balanced_brace_end(body, body_start)
            if body_end is None:
                continue
            branches.append((method, body[body_start + 1 : body_end]))
            seen_methods.add(method)
        return branches

    def _express_parameters(self, route_path: str, doc: str, handler: str) -> list[ParamInfo]:
        params = self._merge_route_params(
            self._normalize_express_path(route_path),
            self._query_params_from_text(handler, "req.query"),
        )
        for kind, param_type, name, optional, description in self._jsdoc_tags(doc):
            if kind == "query":
                params.append(
                    ParamInfo(
                        name=name,
                        type=param_type,
                        required=not optional,
                        location="query",
                        description=description,
                    )
                )
            elif kind == "param":
                params.append(
                    ParamInfo(
                        name=name,
                        type=param_type,
                        required=True,
                        location="path",
                        description=description,
                    )
                )
        return self._dedupe_params(params)

    def _request_body_model(
        self,
        path: Path,
        route_path: str,
        method: str,
        body_text: str,
        doc: str,
        body_patterns: tuple[str, ...],
    ) -> ModelInfo | None:
        if method not in {"POST", "PUT", "PATCH"}:
            return None

        fields = [
            FieldInfo(name=name, type=field_type, required=not optional, description=description)
            for kind, field_type, name, optional, description in self._jsdoc_tags(doc)
            if kind == "body"
        ]
        if fields:
            return self._register_inline_model(path, route_path, method, "Request", fields)

        typed_match = re.search(
            r"(?:const|let|var)\s+\w+\s*:\s*([A-Z][A-Za-z0-9_]*)(?:\[\])?\s*=\s*(?:await\s+\w+\.json\(\)|req\.body)",
            body_text,
        )
        if typed_match and typed_match.group(1) in self._model_registry:
            return self._model_registry[typed_match.group(1)]

        discovered_fields = self._body_fields_from_text(body_text, body_patterns)
        if discovered_fields:
            fields = [FieldInfo(name=name, type="any", required=True) for name in sorted(discovered_fields)]
            return self._register_inline_model(path, route_path, method, "Request", fields)

        if "request.json()" in body_text or "req.body" in body_text:
            return self._register_inline_model(path, route_path, method, "Request", [])
        return None

    def _response_model_from_text(self, path: Path, route_path: str, method: str, body_text: str) -> ModelInfo | None:
        typed_variables = self._collect_typed_variables(body_text)
        for argument in self._json_call_arguments(body_text):
            variable = argument.strip()
            if variable in typed_variables and typed_variables[variable] in self._model_registry:
                return self._model_registry[typed_variables[variable]]
            if variable in self._model_registry:
                return self._model_registry[variable]
            if variable.startswith("{") and variable.endswith("}"):
                fields = [FieldInfo(name=name, type="any", required=True) for name in self._object_literal_keys(variable)]
                if fields:
                    return self._register_inline_model(path, route_path, method, "Response", fields)
        return None

    def _collect_typed_variables(self, text: str) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for match in re.finditer(
            r"(?:const|let|var)\s+(\w+)\s*:\s*([A-Z][A-Za-z0-9_]*)(?:\[\])?\s*=",
            text,
        ):
            mapping[match.group(1)] = match.group(2)
        return mapping

    def _json_call_arguments(self, text: str) -> list[str]:
        arguments: list[str] = []
        seen_spans: set[int] = set()
        for pattern in JSON_CALL_PATTERNS:
            for match in pattern.finditer(text):
                if match.start() in seen_spans:
                    continue
                seen_spans.add(match.start())
                call_end = self._balanced_segment_end(text, match.end() - 1)
                if call_end is None:
                    continue
                args = self._split_top_level_args(text[match.end() : call_end])
                if args:
                    arguments.append(args[0].strip())
        return arguments

    def _body_fields_from_text(self, text: str, body_patterns: tuple[str, ...]) -> set[str]:
        fields: set[str] = set()
        for body_pattern in body_patterns:
            access_pattern = re.compile(
                rf"{re.escape(body_pattern)}\.([A-Za-z_][A-Za-z0-9_]*)\b(?!\s*\()"
            )
            fields.update(match.group(1) for match in access_pattern.finditer(text))

            destructure_pattern = re.compile(
                rf"(?:const|let|var)\s*\{{(?P<body>[^}}]+)\}}\s*=\s*{re.escape(body_pattern)}"
            )
            for match in destructure_pattern.finditer(text):
                for raw_name in match.group("body").split(","):
                    name = raw_name.split(":", 1)[0].split("=", 1)[0].strip()
                    if name:
                        fields.add(name)
        return fields

    def _query_params_from_text(self, text: str, prefix: str) -> list[ParamInfo]:
        params: list[ParamInfo] = []
        access_pattern = re.compile(rf"{re.escape(prefix)}\.get\(\s*['\"]([^'\"]+)['\"]\s*\)")
        destructure_pattern = re.compile(
            rf"(?:const|let|var)\s*\{{(?P<body>[^}}]+)\}}\s*=\s*{re.escape(prefix)}"
        )

        for match in access_pattern.finditer(text):
            params.append(ParamInfo(name=match.group(1), type="string", required=False, location="query"))
        if not prefix.endswith("searchParams"):
            dotted_pattern = re.compile(rf"{re.escape(prefix)}\.([A-Za-z_][A-Za-z0-9_]*)")
            for match in dotted_pattern.finditer(text):
                params.append(ParamInfo(name=match.group(1), type="string", required=False, location="query"))
        for match in destructure_pattern.finditer(text):
            for raw_name in match.group("body").split(","):
                name = raw_name.split(":", 1)[0].split("=", 1)[0].strip()
                if name:
                    params.append(ParamInfo(name=name, type="string", required=False, location="query"))
        return self._dedupe_params(params)

    def _nextjs_route_path(self, path: Path, project_root: Path) -> str | None:
        relative = path.resolve().relative_to(project_root.resolve())
        parts = list(relative.parts)

        if "app" in parts and parts[-1].startswith("route."):
            app_index = parts.index("app")
            route_parts = parts[app_index + 1 : -1]
            return self._join_route_parts(self._normalize_route_segment(part) for part in route_parts)

        if self._is_nextjs_pages_route(path, project_root):
            pages_index = parts.index("pages")
            route_parts = parts[pages_index + 1 : -1]
            stem = path.stem
            if stem != "index":
                route_parts.append(stem)
            return self._join_route_parts(self._normalize_route_segment(part) for part in route_parts)

        return None

    def _is_nextjs_pages_route(self, path: Path, project_root: Path) -> bool:
        relative = path.resolve().relative_to(project_root.resolve())
        parts = list(relative.parts)
        if "pages" not in parts:
            return False
        pages_index = parts.index("pages")
        return len(parts) > pages_index + 1 and parts[pages_index + 1] == "api"

    def _sveltekit_route_path(self, path: Path, project_root: Path) -> str | None:
        relative = path.resolve().relative_to(project_root.resolve())
        parts = list(relative.parts)
        if len(parts) >= 3 and parts[0] == "src" and parts[1] == "routes" and parts[-1].startswith("+server."):
            return self._join_route_parts(self._normalize_route_segment(part) for part in parts[2:-1])
        return None

    def _normalize_route_segment(self, segment: str) -> str:
        if not segment or segment == "index":
            return ""
        if segment.startswith("(") and segment.endswith(")"):
            return ""
        if segment.startswith("@"):
            return ""
        if segment.startswith("[[...") and segment.endswith("]]"):
            return "{" + segment[5:-2] + "}"
        if segment.startswith("[...") and segment.endswith("]"):
            return "{" + segment[4:-1] + "}"
        if segment.startswith("[") and segment.endswith("]"):
            return "{" + segment[1:-1] + "}"
        return segment

    def _normalize_express_path(self, route_path: str) -> str:
        return re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", r"{\1}", route_path)

    def _normalize_prefix(self, prefix: str | None) -> str:
        if not prefix:
            return ""
        if prefix == "/":
            return "/"
        return "/" + prefix.strip("/")

    def _join_route_parts(self, parts) -> str:
        normalized = [part for part in parts if isinstance(part, str) and part]
        return "/" + "/".join(normalized) if normalized else "/"

    def _join_paths(self, base: str, route: str) -> str:
        base_clean = base.strip("/")
        route_clean = route.strip("/")
        if not base_clean and not route_clean:
            return "/"
        if not base_clean:
            return "/" + route_clean
        if not route_clean:
            return "/" + base_clean
        return "/" + "/".join([base_clean, route_clean])

    def _file_route_parameters(self, route_path: str) -> list[ParamInfo]:
        return [
            ParamInfo(name=name, type="string", required=True, location="path")
            for name in re.findall(r"{([^}]+)}", route_path)
        ]

    def _merge_route_params(self, route_path: str, extra_params: list[ParamInfo]) -> list[ParamInfo]:
        path_params = self._file_route_parameters(route_path)
        path_names = {param.name for param in path_params}
        params = list(path_params)
        for param in extra_params:
            if param.location == "query" and param.name in path_names:
                continue
            params.append(param)
        return self._dedupe_params(params)

    def _parse_ts_object_fields(self, body: str) -> list[FieldInfo]:
        fields: list[FieldInfo] = []
        for raw_line in body.splitlines():
            line = raw_line.strip().rstrip(";").rstrip(",")
            if not line or ":" not in line:
                continue
            match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)(\?)?\s*:\s*([^/]+?)(?:\s*//\s*(.*))?$", line)
            if match is None:
                continue
            fields.append(
                FieldInfo(
                    name=match.group(1),
                    type=match.group(3).strip(),
                    required=match.group(2) != "?",
                    description=match.group(4).strip() if match.group(4) else None,
                )
            )
        return fields

    def _register_inline_model(
        self,
        path: Path,
        route_path: str,
        method: str,
        suffix: str,
        fields: list[FieldInfo],
    ) -> ModelInfo:
        model_name = self._inline_model_name(route_path, method, suffix)
        model = self._model_registry.get(model_name)
        if model is None or (not model.fields and fields):
            model = ModelInfo(
                name=model_name,
                fields=fields,
                source_file=str(path),
                line_number=1,
            )
            self._model_registry[model_name] = model
            self._source_evidence["models"].add(str(path))
        return model

    def _inline_model_name(self, route_path: str, method: str, suffix: str) -> str:
        base = re.sub(r"[^A-Za-z0-9]+", " ", route_path).title().replace(" ", "")
        return f"{method.title()}{base or 'Root'}{suffix}"

    def _route_handler_name(self, method: str, route_path: str, handler: str) -> str:
        stripped = handler.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", stripped):
            return stripped
        named = re.search(r"(?:function\s+([A-Za-z_][A-Za-z0-9_]*)|([A-Za-z_][A-Za-z0-9_]*)\s*=>)", stripped)
        if named:
            return named.group(1) or named.group(2)
        normalized = re.sub(r"[^A-Za-z0-9]+", "_", route_path).strip("_")
        return f"{method.lower()}_{normalized or 'root'}"

    def _text_implies_auth(self, text: str) -> bool:
        lowered = text.lower()
        for hint in AUTH_HINTS:
            if hint in lowered:
                self._auth_patterns.add(hint)
                return True
        return False

    def _express_middlewares_imply_auth(self, middlewares: list[object]) -> bool:
        return any(self._text_implies_auth(str(middleware)) for middleware in middlewares)

    def _preceding_jsdoc(self, text: str, start: int) -> str:
        prefix = text[:start]
        last_match = None
        for match in re.finditer(r"/\*\*(?P<body>.*?)\*/", prefix, re.DOTALL):
            last_match = match
        if last_match is None:
            return ""
        return last_match.group("body") if prefix[last_match.end() :].strip() == "" else ""

    def _jsdoc_summary(self, doc: str) -> str | None:
        if not doc:
            return None
        lines: list[str] = []
        for raw_line in doc.splitlines():
            line = raw_line.strip().lstrip("*").strip()
            if not line or line.startswith("@"):
                continue
            lines.append(line)
        return " ".join(lines) if lines else None

    def _jsdoc_tags(self, doc: str) -> list[tuple[str, str, str, bool, str | None]]:
        tags: list[tuple[str, str, str, bool, str | None]] = []
        if not doc:
            return tags
        pattern = re.compile(r"@(query|param|body)\s+\{([^}]+)\}\s+(\[?[\w.]+\]?)\s*-\s*(.+)")
        for raw_line in doc.splitlines():
            line = raw_line.strip().lstrip("*").strip()
            match = pattern.match(line)
            if match is None:
                continue
            raw_name = match.group(3)
            optional = raw_name.startswith("[") and raw_name.endswith("]")
            tags.append(
                (
                    match.group(1),
                    match.group(2),
                    raw_name.strip("[]"),
                    optional,
                    match.group(4).strip(),
                )
            )
        return tags

    def _balanced_segment_end(self, text: str, open_paren_index: int) -> int | None:
        depth = 0
        quote: str | None = None
        escape = False
        for index in range(open_paren_index, len(text)):
            char = text[index]
            if quote:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == quote:
                    quote = None
                continue
            if char in {"'", '"', "`"}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
        return None

    def _balanced_brace_end(self, text: str, open_brace_index: int) -> int | None:
        depth = 0
        quote: str | None = None
        escape = False
        for index in range(open_brace_index, len(text)):
            char = text[index]
            if quote:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == quote:
                    quote = None
                continue
            if char in {"'", '"', "`"}:
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index
        return None

    def _split_top_level_args(self, text: str) -> list[str]:
        args: list[str] = []
        depth_paren = depth_brace = depth_bracket = 0
        quote: str | None = None
        escape = False
        current: list[str] = []

        for char in text:
            if quote:
                current.append(char)
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == quote:
                    quote = None
                continue
            if char in {"'", '"', "`"}:
                quote = char
                current.append(char)
                continue
            if char == "(":
                depth_paren += 1
            elif char == ")":
                depth_paren -= 1
            elif char == "{":
                depth_brace += 1
            elif char == "}":
                depth_brace -= 1
            elif char == "[":
                depth_bracket += 1
            elif char == "]":
                depth_bracket -= 1
            elif char == "," and depth_paren == depth_brace == depth_bracket == 0:
                value = "".join(current).strip()
                if value:
                    args.append(value)
                current = []
                continue
            current.append(char)

        tail = "".join(current).strip()
        if tail:
            args.append(tail)
        return args

    def _string_literal(self, text: str) -> str | None:
        match = re.match(r"^[\"'`](.*)[\"'`]$", text.strip(), re.DOTALL)
        return match.group(1) if match else None

    def _object_literal_keys(self, text: str) -> list[str]:
        body = text.strip()
        if body.startswith("{") and body.endswith("}"):
            body = body[1:-1]
        keys: list[str] = []
        for raw_part in self._split_top_level_args(body):
            part = raw_part.strip()
            if not part:
                continue
            key = part.split(":", 1)[0].strip().strip("'\"`")
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
                keys.append(key)
        return keys

    def _dedupe_params(self, params: list[ParamInfo]) -> list[ParamInfo]:
        seen: set[tuple[str, str]] = set()
        result: list[ParamInfo] = []
        for param in params:
            key = (param.name, param.location)
            if key in seen:
                continue
            seen.add(key)
            result.append(param)
        return result

    def _dedupe_endpoints(self, endpoints: list[EndpointInfo]) -> list[EndpointInfo]:
        seen: set[tuple[str, str, str, int]] = set()
        result: list[EndpointInfo] = []
        for endpoint in sorted(endpoints, key=lambda item: (item.path, item.method, item.line_number)):
            key = (endpoint.method, endpoint.path, endpoint.handler_name, endpoint.line_number)
            if key in seen:
                continue
            seen.add(key)
            result.append(endpoint)
        return result
