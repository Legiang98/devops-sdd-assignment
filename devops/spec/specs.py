#!/usr/bin/env python
"""Spec loading helpers for baseline + feature-delta workflows."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = deepcopy(base)
        for key, value in override.items():
            if key in merged:
                merged[key] = _deep_merge(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged

    if isinstance(override, list):
        return deepcopy(override)

    return deepcopy(override)


def _default_workspace(spec_path: Path) -> dict[str, str]:
    app_root = spec_path.resolve().parents[1]
    return {
        "path": str(app_root),
        "src_path": "src",
        "tests_path": "tests",
        "dockerfile_path": "Dockerfile",
        "manifest_path": f"devops/k8s/{app_root.name}",
    }


def _merge_api_endpoints(
    base_spec: dict[str, Any],
    feature_spec: dict[str, Any],
    merged_spec: dict[str, Any],
) -> dict[str, Any]:
    base_endpoints = (
        ((base_spec.get("api_contract") or {}).get("endpoints") or [])
        if isinstance(base_spec, dict)
        else []
    )
    feature_endpoints = (
        ((feature_spec.get("api_contract") or {}).get("endpoints") or [])
        if isinstance(feature_spec, dict)
        else []
    )

    if not feature_endpoints:
        return merged_spec

    endpoint_map: dict[tuple[str, str], dict[str, Any]] = {}
    for endpoint in base_endpoints:
        if not isinstance(endpoint, dict):
            continue
        key = (str(endpoint.get("method", "")).upper(), str(endpoint.get("path", "")))
        endpoint_map[key] = deepcopy(endpoint)
    for endpoint in feature_endpoints:
        if not isinstance(endpoint, dict):
            continue
        key = (str(endpoint.get("method", "")).upper(), str(endpoint.get("path", "")))
        endpoint_map[key] = deepcopy(endpoint)

    api_contract = deepcopy(merged_spec.get("api_contract") or {})
    api_contract["endpoints"] = list(endpoint_map.values())
    merged_spec["api_contract"] = api_contract
    return merged_spec


def _normalize_resolved_spec(spec: dict[str, Any], spec_path: Path) -> dict[str, Any]:
    resolved = deepcopy(spec)

    workspace = resolved.get("workspace")
    if not isinstance(workspace, dict):
        workspace = {}
    resolved["workspace"] = _deep_merge(_default_workspace(spec_path), workspace)

    docs = resolved.get("docs")
    if not isinstance(docs, dict):
        resolved["docs"] = {}

    quality = resolved.get("quality")
    if not isinstance(quality, dict):
        resolved["quality"] = {}

    return resolved


def load_resolved_spec(spec_path: Path) -> dict[str, Any]:
    raw_spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw_spec, dict):
        raise SystemExit(f"Expected mapping YAML in spec: {spec_path}")

    baseline_candidate = spec_path.with_name("BASELINE.yaml")
    merged_spec = raw_spec
    if baseline_candidate.exists() and baseline_candidate.resolve() != spec_path.resolve():
        baseline_spec = yaml.safe_load(baseline_candidate.read_text(encoding="utf-8")) or {}
        if not isinstance(baseline_spec, dict):
            raise SystemExit(f"Expected mapping YAML in baseline spec: {baseline_candidate}")
        merged_spec = _deep_merge(baseline_spec, raw_spec)
        merged_spec = _merge_api_endpoints(baseline_spec, raw_spec, merged_spec)

    return _normalize_resolved_spec(merged_spec, spec_path)
