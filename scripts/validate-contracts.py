#!/usr/bin/env python3
"""Fail CI on malformed or provider-divergent contracts."""

import json
import os
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        assert key not in result, f"duplicate YAML key: {key}"
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping
)


def validate_openapi(path: Path) -> set[tuple[str, str]]:
    document = yaml.load(path.read_text(), Loader=UniqueKeyLoader)
    assert document.get("openapi", "").startswith("3.1"), (
        f"{path}: OpenAPI 3.1 required"
    )
    status = document.get("x-implementation-status")
    assert status, f"{path}: x-implementation-status is required"
    operations: set[tuple[str, str]] = set()
    operation_ids: set[str] = set()
    for route, item in document.get("paths", {}).items():
        for method, operation in item.items():
            if method not in HTTP_METHODS:
                continue
            operation_id = operation.get("operationId")
            assert operation_id and operation_id not in operation_ids, (
                f"{path}: duplicate/missing operationId"
            )
            operation_ids.add(operation_id)
            operations.add((route, method))
            responses = operation.get("responses", {})
            assert any(str(code).startswith("2") for code in responses), (
                f"{path}: {operation_id} needs a success response"
            )
            if status.startswith("implemented"):
                success = next(
                    value
                    for code, value in responses.items()
                    if str(code).startswith("2")
                )
                assert "content" in success, (
                    f"{path}: {operation_id} success response needs a schema"
                )
                if method in {"post", "put", "patch"}:
                    assert operation.get("requestBody"), (
                        f"{path}: {operation_id} needs a request body"
                    )
            if status.startswith("implemented"):
                for name in _path_parameters(route):
                    parameters = operation.get("parameters", []) + item.get(
                        "parameters", []
                    )
                    assert any(
                        _parameter_name(value) == name for value in parameters
                    ), f"{path}: {operation_id} is missing path parameter {name}"
    return operations


def _path_parameters(route: str) -> set[str]:
    return {
        part[1:-1]
        for part in route.split("/")
        if part.startswith("{") and part.endswith("}")
    }


def _parameter_name(parameter: dict) -> str | None:
    if "$ref" in parameter:
        return (
            parameter["$ref"]
            .rsplit("/", 1)[-1]
            .replace("EncounterId", "encounter_id")
            .replace("SnapshotId", "snapshot_id")
            .replace("VerificationId", "verification_id")
        )
    return parameter.get("name")


def validate_provider(service: str, static_operations: set[tuple[str, str]]) -> None:
    os.environ.setdefault("PARTICIPANT_LOOKUP_HMAC_KEY", "11" * 32)
    os.environ.setdefault("FIELD_ENCRYPTION_MASTER_KEY", "22" * 32)
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]
    sys.path[0:0] = [
        str(ROOT / f"services/{service}"),
        str(ROOT / "libs/python-auth"),
        str(ROOT / "libs/canonical-data"),
    ]
    from app.main import app

    generated = app.openapi()
    provider = {
        (route, method)
        for route, item in generated["paths"].items()
        if route.startswith(("/api/v1", "/internal/v1"))
        for method in item
        if method in HTTP_METHODS
    }
    assert provider == static_operations, (
        f"{service} contract/provider mismatch: static-only={static_operations - provider}, provider-only={provider - static_operations}"
    )
    del sys.path[:3]


def main() -> None:
    provider_contracts: dict[str, set[tuple[str, str]]] = {}
    for path in sorted((ROOT / "contracts/openapi").glob("*.yaml")):
        operations = validate_openapi(path)
        if path.name == "encounter-v1.yaml":
            provider_contracts["encounter-service"] = operations
        elif path.name == "evidence-v1.yaml":
            provider_contracts["evidence-service"] = operations
        elif path.name == "verification-v1.yaml":
            provider_contracts["verification-service"] = operations
        elif path.name == "review-v1.yaml":
            provider_contracts["review-service"] = operations
    for path in sorted((ROOT / "contracts/events/v1").glob("*.json")):
        Draft202012Validator.check_schema(json.loads(path.read_text()))
    for service, operations in provider_contracts.items():
        validate_provider(service, operations)
    print(
        "[contract] OpenAPI files, event schemas, and implemented provider routes are valid"
    )


if __name__ == "__main__":
    main()
