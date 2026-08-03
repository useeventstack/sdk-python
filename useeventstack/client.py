"""Sync and async HTTP clients for the useEventStack API.

Usage (sync):
    from useeventstack import UseEventStackClient

    client = UseEventStackClient(api_key="useeventstack_your_key", project_id="proj_xxx")
    event = client.events.emit("deployment.completed", payload={...})

Usage (async):
    from useeventstack import AsyncUseEventStackClient

    client = AsyncUseEventStackClient(api_key="useeventstack_your_key", project_id="proj_xxx")
    event = await client.events.emit("deployment.completed", payload={...})
"""

from __future__ import annotations

import json as _json
from typing import Any, Literal

import httpx

from useeventstack.errors import UseEventStackApiError

Environment = Literal["production", "sandbox"]


class _EventsNamespace:
    """Event ingestion and querying operations."""

    def __init__(self, client: "_BaseClient"):
        self._c = client

    def emit(
        self,
        event_type: str,
        *,
        payload: dict[str, Any],
        environment: Environment | None = None,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> dict[str, Any]:
        headers = {}
        if idempotency_key:
            headers["x-useeventstack-idempotency-key"] = idempotency_key
        return self._c._request("POST", "/events", json={
            "type": event_type,
            # Required by the API's CreateEventRequest schema. For API-key auth the
            # server overrides this with the key's own organization, but the field
            # must still be present for the request body to deserialize.
            "organization_id": self._c._org_id,
            "project_id": self._c._project_id,
            "metadata": {
                "schema_version": 1,
                "source": "sdk.python",
                "trace_depth": 0,
                # Only sent when the caller explicitly asserts an environment. An
                # API key already carries its own, and sending an unrequested one
                # made every sandbox key fail.
                **({"environment": environment or self._c._environment}
                   if (environment or self._c._environment) else {}),
            },
            "payload": payload,
            "correlation_id": correlation_id,
            "causation_id": causation_id,
        }, extra_headers=headers)

    def query(
        self,
        *,
        event_type: str | None = None,
        environment: Environment | None = None,
        correlation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if event_type:
            params["event_type"] = event_type
        if environment:
            params["environment"] = environment
        if correlation_id:
            params["correlation_id"] = correlation_id
        return self._c._request("GET", "/events", params=params)

    def get(self, event_id: str, *, environment: Environment | None = None) -> dict[str, Any]:
        return self._c._request("GET", f"/events/{event_id}", env_override=environment)

    def trace(self, event_id: str, *, environment: Environment | None = None) -> dict[str, Any]:
        """The causation chain around an event, and the workflow steps that ran on it.

        Returns ``{"events": [...], "reactions": [...]}``. Before 0.3.0 this returned
        the chain alone, so a caller could see that an event had derived children but
        not whether any workflow had actually run — the question a trace is usually
        opened to answer.
        """
        return self._c._request("GET", f"/events/{event_id}/trace", env_override=environment)


class _WorkflowsNamespace:
    """Workflow management operations."""

    def __init__(self, client: "_BaseClient"):
        self._c = client

    def query(self, *, event_type: str | None = None, environment: Environment | None = None) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if event_type:
            params["event_type"] = event_type
        if environment:
            params["environment"] = environment
        return self._c._request("GET", "/workflows/query", params=params)

    def list(self) -> list[dict[str, Any]]:
        result = self._c._request("GET", f"/organizations/{self._c._org_id}/workflows")
        if isinstance(result, dict):
            return result.get("workflows", [])
        return result if isinstance(result, list) else []

    def get(self, workflow_id: str) -> dict[str, Any]:
        return self._c._request("GET", f"/organizations/{self._c._org_id}/workflows/{workflow_id}")

    def create(self, workflow: dict[str, Any]) -> dict[str, Any]:
        return self._c._request("POST", f"/organizations/{self._c._org_id}/workflows", json=workflow)

    def update(self, workflow_id: str, workflow: dict[str, Any]) -> dict[str, Any]:
        return self._c._request("PUT", f"/organizations/{self._c._org_id}/workflows/{workflow_id}", json=workflow)

    def delete(self, workflow_id: str) -> None:
        self._c._request("DELETE", f"/organizations/{self._c._org_id}/workflows/{workflow_id}")

    def enable(self, workflow_id: str) -> dict[str, Any]:
        return self._c._request("POST", f"/organizations/{self._c._org_id}/workflows/{workflow_id}/enable")

    def disable(self, workflow_id: str) -> dict[str, Any]:
        return self._c._request("POST", f"/organizations/{self._c._org_id}/workflows/{workflow_id}/disable")


class _CustomActionsNamespace:
    """Custom WASM action management."""

    def __init__(self, client: "_BaseClient"):
        self._c = client

    def list(self) -> list[dict[str, Any]]:
        return self._c._request("GET", f"/organizations/{self._c._org_id}/custom-actions")

    def get(self, action_id: str) -> dict[str, Any]:
        return self._c._request("GET", f"/organizations/{self._c._org_id}/custom-actions/{action_id}")

    def delete(self, action_id: str) -> None:
        self._c._request("DELETE", f"/organizations/{self._c._org_id}/custom-actions/{action_id}")

    def upload(
        self,
        name: str,
        wasm: bytes,
        *,
        description: str | None = None,
        permissions: list[str] | None = None,
        file_name: str | None = None,
    ) -> dict[str, Any]:
        """Upload a compiled WASM module for review.

        ``permissions`` declares the secrets the module may read, as
        ``read_secret:<KEY>``. A secret it does not declare is never injected, so
        this list is what an approver consents to.
        """
        data: dict[str, Any] = {"name": name}
        if description is not None:
            data["description"] = description
        if permissions:
            data["permissions"] = _json.dumps(permissions)
        return self._c._request(
            "POST",
            f"/organizations/{self._c._org_id}/custom-actions",
            data=data,
            files={"file": (file_name or f"{name}.wasm", wasm, "application/wasm")},
        )

    def review(self, action_id: str, status: str) -> dict[str, Any]:
        """Approve or reject an upload. ``status`` is ``approved`` or ``rejected``."""
        return self._c._request(
            "POST",
            f"/organizations/{self._c._org_id}/custom-actions/{action_id}/review",
            json={"status": status},
        )

    def simulate(
        self,
        action_id: str,
        payload: dict[str, Any] | None = None,
        *,
        secrets: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Dry-run an action.

        Secrets are supplied by the caller: stored values are never read for a
        simulation, because a module that echoes one would turn a dry run into an
        exfiltration path for a reviewer who has not yet decided to trust it.
        """
        return self._c._request(
            "POST",
            f"/organizations/{self._c._org_id}/custom-actions/{action_id}/simulate",
            json={"payload": payload, "secrets": secrets},
        )

    def list_secrets(self, action_id: str) -> list[dict[str, Any]]:
        """Secret names and write timestamps. A value is never returned."""
        return self._c._request("GET", f"/organizations/{self._c._org_id}/custom-actions/{action_id}/secrets")

    def set_secret(self, action_id: str, key: str, value: str) -> dict[str, Any]:
        return self._c._request(
            "POST",
            f"/organizations/{self._c._org_id}/custom-actions/{action_id}/secrets",
            json={"key": key, "value": value},
        )

    def delete_secret(self, action_id: str, key: str) -> None:
        self._c._request("DELETE", f"/organizations/{self._c._org_id}/custom-actions/{action_id}/secrets/{key}")


class _ContractsNamespace:
    """Event-contract reads and deletion for the active project."""

    def __init__(self, client: "_BaseClient"):
        self._c = client

    def list(self) -> list[dict[str, Any]]:
        result = self._c._request("GET", f"/organizations/{self._c._org_id}/event-contracts")
        if isinstance(result, dict):
            return result.get("contracts", result.get("event_contracts", []))
        return result if isinstance(result, list) else []

    def delete(self, contract_id: str) -> None:
        self._c._request(
            "DELETE", f"/organizations/{self._c._org_id}/event-contracts/{contract_id}"
        )


class _ProjectsNamespace:
    """Project lifecycle operations for the client's organization."""

    def __init__(self, client: "_BaseClient"):
        self._c = client

    def list(self) -> list[dict[str, Any]]:
        result = self._c._request("GET", f"/organizations/{self._c._org_id}/projects")
        return result if isinstance(result, list) else result.get("projects", []) if isinstance(result, dict) else []

    def get(self, project_id: str) -> dict[str, Any]:
        return self._c._request("GET", f"/organizations/{self._c._org_id}/projects/{project_id}")

    def delete(self, project_id: str) -> None:
        self._c._request("DELETE", f"/organizations/{self._c._org_id}/projects/{project_id}")

    def purge(self, project_id: str, confirmation: str) -> dict[str, Any]:
        """Remove mutable project resources; confirmation must match its current name."""
        return self._c._request(
            "POST",
            f"/organizations/{self._c._org_id}/projects/{project_id}/purge",
            json={"confirmation": confirmation},
        )


class _ReplayNamespace:
    """Event replay operations."""

    def __init__(self, client: "_BaseClient"):
        self._c = client

    def single(self, event_id: str, *, skip_side_effects: bool = True) -> dict[str, Any]:
        return self._c._request("POST", "/replay", json={
            "event_id": event_id,
            "skip_external_side_effects": skip_side_effects,
        })

    def bulk(
        self,
        *,
        event_ids: list[str] | None = None,
        event_type: str | None = None,
        since: str | None = None,
        until: str | None = None,
        skip_side_effects: bool = True,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._c._request("POST", "/replay/bulk", json={
            "event_ids": event_ids,
            "event_type": event_type,
            "since": since,
            "until": until,
            "skip_external_side_effects": skip_side_effects,
            "limit": limit,
        })


class _DlqNamespace:
    """Dead letter queue operations."""

    def __init__(self, client: "_BaseClient"):
        self._c = client

    def list(self) -> list[dict[str, Any]]:
        return self._c._request("GET", "/dead-letter-events")

    def reprocess(self, event_id: str, skip_external_side_effects: bool = True) -> dict[str, Any]:
        """Re-queue one dead-lettered event through the replay path.

        Deliberately the replay route, not the platform clear route: this used to
        take no arguments and clear the whole dead-letter queue, which is the
        opposite of reprocessing.
        """
        return self._c._request("POST", "/replay", json={
            "event_id": event_id,
            "skip_external_side_effects": skip_external_side_effects,
        })

    def clear(self) -> dict[str, Any]:
        """Discard every dead-lettered event in the organization. Not reversible."""
        return self._c._request("POST", "/platform/dead-letter-events/clear")


class _ApiKeysNamespace:
    """API key management."""

    def __init__(self, client: "_BaseClient"):
        self._c = client

    def list(self) -> list[dict[str, Any]]:
        return self._c._request("GET", f"/organizations/{self._c._org_id}/api-keys")

    def create(self, name: str, scopes: list[str] | None = None) -> dict[str, Any]:
        return self._c._request("POST", f"/organizations/{self._c._org_id}/api-keys", json={
            "name": name,
            "scopes": scopes or ["*"],
        })

    def delete(self, key_id: str) -> None:
        self._c._request("DELETE", f"/organizations/{self._c._org_id}/api-keys/{key_id}")


class _ProjectionsNamespace:
    """Projection querying."""

    def __init__(self, client: "_BaseClient"):
        self._c = client

    def query(self, *, projection: str | None = None, environment: Environment | None = None) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if projection:
            params["projection"] = projection
        if environment:
            params["environment"] = environment
        return self._c._request("GET", "/projections", params=params)

    def service_status(self, *, environment: Environment | None = None) -> list[dict[str, Any]]:
        return self.query(environment=environment)


class _BaseClient:
    """Shared request logic for sync and async clients."""

    def __init__(
        self,
        *,
        api_key: str,
        project_id: str,
        base_url: str = "https://api.useeventstack.com",
        organization_id: str | None = None,
        environment: Environment | None = None,
    ):
        """Create a client.

        ``environment`` asserts which environment this client talks to. An API key
        is issued for exactly one environment and the server always uses the key's
        own, so this does not choose where events are written — a mismatch is
        reported as an ``environment_mismatch`` error rather than silently
        coerced. Leave it unset to let the key decide.
        """
        if not api_key or not api_key.strip():
            raise ValueError("api_key is required")
        if not project_id or not project_id.strip():
            raise ValueError("project_id is required")
        self._api_key = api_key
        self._project_id = project_id
        self._base_url = base_url.rstrip("/")
        self._org_id = organization_id or "00000000-0000-0000-0000-000000000000"
        self._environment = environment

    def _headers(
        self,
        extra: dict[str, str] | None = None,
        env_override: Environment | None = None,
        *,
        json_body: bool = True,
    ) -> dict[str, str]:
        h = {
            "authorization": f"Bearer {self._api_key}",
            "x-useeventstack-organization": self._org_id,
            "x-useeventstack-project": self._project_id,
        }
        # A multipart body carries its own content type, including the boundary
        # httpx generates. Setting it here would produce a request the server
        # cannot parse.
        if json_body:
            h["content-type"] = "application/json"
        environment = env_override or self._environment
        if environment:
            h["x-useeventstack-environment"] = environment
        if extra:
            h.update(extra)
        return h

    def _handle_response(self, response: httpx.Response) -> Any:
        if response.status_code == 204:
            return None
        try:
            body = response.json() if response.content else {}
        except ValueError:
            # Some framework-level rejections (e.g. malformed request bodies) are
            # returned as text/plain rather than the API's JSON error envelope.
            body = {}
            if not response.is_success:
                raise UseEventStackApiError(
                    status=response.status_code,
                    code="invalid_response_body",
                    message=(response.text or response.reason_phrase or "Unknown error").strip(),
                    details=None,
                ) from None
        if not response.is_success:
            error = body.get("error", {}) if isinstance(body, dict) else {}
            raise UseEventStackApiError(
                status=response.status_code,
                code=error.get("code", "request_failed"),
                message=error.get("message", response.reason_phrase or "Unknown error"),
                details=error.get("details"),
            )
        return body


class UseEventStackClient(_BaseClient):
    """Synchronous useEventStack API client.

    Example:
        client = UseEventStackClient(api_key="useeventstack_your_key", project_id="proj_xxx")
        client.events.emit("deployment.completed", payload={"service": "api", ...})
    """

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._http = httpx.Client(timeout=30.0)
        self.events = _EventsNamespace(self)
        self.workflows = _WorkflowsNamespace(self)
        self.custom_actions = _CustomActionsNamespace(self)
        self.contracts = _ContractsNamespace(self)
        self.projects = _ProjectsNamespace(self)
        self.replay = _ReplayNamespace(self)
        self.dlq = _DlqNamespace(self)
        self.api_keys = _ApiKeysNamespace(self)
        self.projections = _ProjectionsNamespace(self)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
        env_override: Environment | None = None,
    ) -> Any:
        response = self._http.request(
            method,
            f"{self._base_url}{path}",
            headers=self._headers(extra_headers, env_override, json_body=files is None),
            json=json,
            data=data,
            files=files,
            params=params,
        )
        return self._handle_response(response)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "UseEventStackClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


class AsyncUseEventStackClient(_BaseClient):
    """Asynchronous useEventStack API client (for asyncio/FastAPI).

    Example:
        async with AsyncUseEventStackClient(api_key="useeventstack_your_key", project_id="proj_xxx") as client:
            await client.events.emit("deployment.completed", payload={...})
    """

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._http = httpx.AsyncClient(timeout=30.0)
        self.events = _AsyncEventsNamespace(self)
        self.workflows = _AsyncWorkflowsNamespace(self)
        self.custom_actions = _AsyncCustomActionsNamespace(self)
        self.contracts = _AsyncContractsNamespace(self)
        self.projects = _AsyncProjectsNamespace(self)
        self.replay = _AsyncReplayNamespace(self)
        self.dlq = _AsyncDlqNamespace(self)
        self.api_keys = _AsyncApiKeysNamespace(self)
        self.projections = _AsyncProjectionsNamespace(self)

    async def _request(  # type: ignore[override]
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
        env_override: Environment | None = None,
    ) -> Any:
        response = await self._http.request(
            method,
            f"{self._base_url}{path}",
            headers=self._headers(extra_headers, env_override, json_body=files is None),
            json=json,
            data=data,
            files=files,
            params=params,
        )
        return self._handle_response(response)

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncUseEventStackClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()


# ─── Async namespace wrappers ────────────────────────────────────────────────
# These mirror the sync namespaces but make methods async.

class _AsyncEventsNamespace(_EventsNamespace):
    async def emit(self, *args: Any, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        environment = kwargs.get("environment") or self._c._environment
        return await self._c._request("POST", "/events", json={
            "type": args[0] if args else kwargs.get("event_type", ""),
            "organization_id": self._c._org_id,
            "project_id": self._c._project_id,
            "metadata": {"schema_version": 1, "source": "sdk.python", "trace_depth": 0,
                         **({"environment": environment} if environment else {})},
            "payload": kwargs.get("payload", {}),
            "correlation_id": kwargs.get("correlation_id"),
            "causation_id": kwargs.get("causation_id"),
        }, extra_headers={"x-useeventstack-idempotency-key": kwargs["idempotency_key"]} if kwargs.get("idempotency_key") else None)

    async def query(self, **kwargs: Any) -> list[dict[str, Any]]:  # type: ignore[override]
        params: dict[str, str] = {}
        if kwargs.get("event_type"): params["event_type"] = kwargs["event_type"]
        if kwargs.get("environment"): params["environment"] = kwargs["environment"]
        if kwargs.get("correlation_id"): params["correlation_id"] = kwargs["correlation_id"]
        return await self._c._request("GET", "/events", params=params)

    async def get(self, event_id: str, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        return await self._c._request("GET", f"/events/{event_id}", env_override=kwargs.get("environment"))

    async def trace(self, event_id: str, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        """See :meth:`_EventsNamespace.trace`."""
        return await self._c._request("GET", f"/events/{event_id}/trace", env_override=kwargs.get("environment"))


class _AsyncWorkflowsNamespace(_WorkflowsNamespace):
    async def list(self) -> list[dict[str, Any]]:  # type: ignore[override]
        result = await self._c._request("GET", f"/organizations/{self._c._org_id}/workflows")
        if isinstance(result, dict):
            return result.get("workflows", [])
        return result if isinstance(result, list) else []
    async def get(self, workflow_id: str) -> dict[str, Any]:  # type: ignore[override]
        return await self._c._request("GET", f"/organizations/{self._c._org_id}/workflows/{workflow_id}")
    async def create(self, workflow: dict[str, Any]) -> dict[str, Any]:  # type: ignore[override]
        return await self._c._request("POST", f"/organizations/{self._c._org_id}/workflows", json=workflow)
    async def update(self, workflow_id: str, workflow: dict[str, Any]) -> dict[str, Any]:  # type: ignore[override]
        return await self._c._request("PUT", f"/organizations/{self._c._org_id}/workflows/{workflow_id}", json=workflow)
    async def delete(self, workflow_id: str) -> None:  # type: ignore[override]
        await self._c._request("DELETE", f"/organizations/{self._c._org_id}/workflows/{workflow_id}")
    async def enable(self, workflow_id: str) -> dict[str, Any]:  # type: ignore[override]
        return await self._c._request("POST", f"/organizations/{self._c._org_id}/workflows/{workflow_id}/enable")
    async def disable(self, workflow_id: str) -> dict[str, Any]:  # type: ignore[override]
        return await self._c._request("POST", f"/organizations/{self._c._org_id}/workflows/{workflow_id}/disable")


class _AsyncCustomActionsNamespace(_CustomActionsNamespace):
    async def list(self) -> list[dict[str, Any]]:  # type: ignore[override]
        return await self._c._request("GET", f"/organizations/{self._c._org_id}/custom-actions")
    async def get(self, action_id: str) -> dict[str, Any]:  # type: ignore[override]
        return await self._c._request("GET", f"/organizations/{self._c._org_id}/custom-actions/{action_id}")
    async def delete(self, action_id: str) -> None:  # type: ignore[override]
        await self._c._request("DELETE", f"/organizations/{self._c._org_id}/custom-actions/{action_id}")
    async def simulate(self, action_id: str, payload: dict[str, Any] | None = None, *, secrets: dict[str, str] | None = None) -> dict[str, Any]:  # type: ignore[override]
        return await self._c._request("POST", f"/organizations/{self._c._org_id}/custom-actions/{action_id}/simulate", json={"payload": payload, "secrets": secrets})
    async def upload(  # type: ignore[override]
        self,
        name: str,
        wasm: bytes,
        *,
        description: str | None = None,
        permissions: list[str] | None = None,
        file_name: str | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"name": name}
        if description is not None:
            data["description"] = description
        if permissions:
            data["permissions"] = _json.dumps(permissions)
        return await self._c._request(
            "POST",
            f"/organizations/{self._c._org_id}/custom-actions",
            data=data,
            files={"file": (file_name or f"{name}.wasm", wasm, "application/wasm")},
        )
    async def review(self, action_id: str, status: str) -> dict[str, Any]:  # type: ignore[override]
        return await self._c._request("POST", f"/organizations/{self._c._org_id}/custom-actions/{action_id}/review", json={"status": status})
    async def list_secrets(self, action_id: str) -> list[dict[str, Any]]:  # type: ignore[override]
        return await self._c._request("GET", f"/organizations/{self._c._org_id}/custom-actions/{action_id}/secrets")
    async def set_secret(self, action_id: str, key: str, value: str) -> dict[str, Any]:  # type: ignore[override]
        return await self._c._request("POST", f"/organizations/{self._c._org_id}/custom-actions/{action_id}/secrets", json={"key": key, "value": value})
    async def delete_secret(self, action_id: str, key: str) -> None:  # type: ignore[override]
        await self._c._request("DELETE", f"/organizations/{self._c._org_id}/custom-actions/{action_id}/secrets/{key}")


class _AsyncContractsNamespace(_ContractsNamespace):
    async def list(self) -> list[dict[str, Any]]:  # type: ignore[override]
        result = await self._c._request("GET", f"/organizations/{self._c._org_id}/event-contracts")
        if isinstance(result, dict):
            return result.get("contracts", result.get("event_contracts", []))
        return result if isinstance(result, list) else []

    async def delete(self, contract_id: str) -> None:  # type: ignore[override]
        await self._c._request(
            "DELETE", f"/organizations/{self._c._org_id}/event-contracts/{contract_id}"
        )


class _AsyncProjectsNamespace(_ProjectsNamespace):
    async def list(self) -> list[dict[str, Any]]:  # type: ignore[override]
        result = await self._c._request("GET", f"/organizations/{self._c._org_id}/projects")
        return result if isinstance(result, list) else result.get("projects", []) if isinstance(result, dict) else []

    async def get(self, project_id: str) -> dict[str, Any]:  # type: ignore[override]
        return await self._c._request("GET", f"/organizations/{self._c._org_id}/projects/{project_id}")

    async def delete(self, project_id: str) -> None:  # type: ignore[override]
        await self._c._request("DELETE", f"/organizations/{self._c._org_id}/projects/{project_id}")

    async def purge(self, project_id: str, confirmation: str) -> dict[str, Any]:  # type: ignore[override]
        return await self._c._request(
            "POST",
            f"/organizations/{self._c._org_id}/projects/{project_id}/purge",
            json={"confirmation": confirmation},
        )


class _AsyncReplayNamespace(_ReplayNamespace):
    async def single(self, event_id: str, *, skip_side_effects: bool = True) -> dict[str, Any]:  # type: ignore[override]
        return await self._c._request("POST", "/replay", json={"event_id": event_id, "skip_external_side_effects": skip_side_effects})
    async def bulk(self, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        return await self._c._request("POST", "/replay/bulk", json={
            "event_ids": kwargs.get("event_ids"), "event_type": kwargs.get("event_type"),
            "since": kwargs.get("since"), "until": kwargs.get("until"),
            "skip_external_side_effects": kwargs.get("skip_side_effects", True), "limit": kwargs.get("limit", 100),
        })


class _AsyncDlqNamespace(_DlqNamespace):
    async def list(self) -> list[dict[str, Any]]:  # type: ignore[override]
        return await self._c._request("GET", "/dead-letter-events")
    async def reprocess(self, event_id: str, skip_external_side_effects: bool = True) -> dict[str, Any]:  # type: ignore[override]
        return await self._c._request("POST", "/replay", json={
            "event_id": event_id,
            "skip_external_side_effects": skip_external_side_effects,
        })
    async def clear(self) -> dict[str, Any]:  # type: ignore[override]
        return await self._c._request("POST", "/platform/dead-letter-events/clear")


class _AsyncApiKeysNamespace(_ApiKeysNamespace):
    async def list(self) -> list[dict[str, Any]]:  # type: ignore[override]
        return await self._c._request("GET", f"/organizations/{self._c._org_id}/api-keys")
    async def create(self, name: str, scopes: list[str] | None = None) -> dict[str, Any]:  # type: ignore[override]
        return await self._c._request("POST", f"/organizations/{self._c._org_id}/api-keys", json={"name": name, "scopes": scopes or ["*"]})
    async def delete(self, key_id: str) -> None:  # type: ignore[override]
        await self._c._request("DELETE", f"/organizations/{self._c._org_id}/api-keys/{key_id}")


class _AsyncProjectionsNamespace(_ProjectionsNamespace):
    async def query(self, **kwargs: Any) -> list[dict[str, Any]]:  # type: ignore[override]
        params: dict[str, str] = {}
        if kwargs.get("projection"): params["projection"] = kwargs["projection"]
        if kwargs.get("environment"): params["environment"] = kwargs["environment"]
        return await self._c._request("GET", "/projections", params=params)
    async def service_status(self, **kwargs: Any) -> list[dict[str, Any]]:  # type: ignore[override]
        return await self.query(**kwargs)
