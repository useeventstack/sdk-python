"""Tests for strict project isolation in the Python SDK."""

from __future__ import annotations

import pytest
import respx
import httpx

from useeventstack import UseEventStackClient


class TestProjectIdRequired:
    """Client constructor must reject missing project_id."""

    def test_raises_if_project_id_not_provided(self):
        with pytest.raises((ValueError, TypeError)):
            UseEventStackClient(api_key="useeventstack_test_key")

    def test_raises_if_project_id_is_empty_string(self):
        with pytest.raises(ValueError):
            UseEventStackClient(api_key="useeventstack_test_key", project_id="")

    def test_raises_if_project_id_is_whitespace(self):
        with pytest.raises(ValueError):
            UseEventStackClient(api_key="useeventstack_test_key", project_id="   ")

    def test_accepts_valid_project_id(self):
        client = UseEventStackClient(
            api_key="useeventstack_test_key",
            project_id="proj_abc123",
        )
        assert client._project_id == "proj_abc123"


class TestProjectHeaderInRequests:
    """All requests must include x-useeventstack-project header."""

    def test_headers_include_project_id(self):
        client = UseEventStackClient(
            api_key="useeventstack_test_key",
            project_id="proj_xyz",
        )
        headers = client._headers()
        assert headers["x-useeventstack-project"] == "proj_xyz"

    @respx.mock
    def test_emit_request_contains_project_header(self):
        client = UseEventStackClient(
            api_key="useeventstack_test_key",
            project_id="proj_header_test",
            base_url="http://mock-api",
        )
        route = respx.post("http://mock-api/events").mock(
            return_value=httpx.Response(200, json={"id": "evt_1"})
        )
        client.events.emit("test.event", payload={"foo": "bar"})

        assert route.called
        request = route.calls[0].request
        assert request.headers["x-useeventstack-project"] == "proj_header_test"

    @respx.mock
    def test_query_request_contains_project_header(self):
        client = UseEventStackClient(
            api_key="useeventstack_test_key",
            project_id="proj_query_test",
            base_url="http://mock-api",
        )
        route = respx.get("http://mock-api/events").mock(
            return_value=httpx.Response(200, json=[])
        )
        client.events.query()

        assert route.called
        request = route.calls[0].request
        assert request.headers["x-useeventstack-project"] == "proj_query_test"


class TestEmitBodyIncludesProjectId:
    """emit() must include project_id in the request body."""

    @respx.mock
    def test_emit_body_contains_project_id(self):
        client = UseEventStackClient(
            api_key="useeventstack_test_key",
            project_id="proj_body_test",
            base_url="http://mock-api",
        )
        route = respx.post("http://mock-api/events").mock(
            return_value=httpx.Response(200, json={"id": "evt_2"})
        )
        client.events.emit("deploy.completed", payload={"service": "api"})

        assert route.called
        import json
        body = json.loads(route.calls[0].request.content)
        assert body["project_id"] == "proj_body_test"
