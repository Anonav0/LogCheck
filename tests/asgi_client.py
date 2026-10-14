"""Zero-dependency ASGI Test Client for offline testing."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import urlparse


class ASGIResponse:
    """Synchronous representation of an ASGI HTTP response."""

    def __init__(
        self, status_code: int, headers: list[tuple[bytes, bytes]], body: bytes
    ) -> None:
        self.status_code = status_code
        self.content = body
        self._headers: dict[str, str] = {}
        for k, v in headers:
            self._headers[k.decode("latin-1").lower()] = v.decode("latin-1")

    @property
    def headers(self) -> dict[str, str]:
        return self._headers

    @property
    def text(self) -> str:
        return self.content.decode("utf-8")

    def json(self) -> Any:
        return json.loads(self.text)


class ASGIClient:
    """Synchronous test client executing requests against an ASGI application."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_data: Any = None,
        data: bytes | str | None = None,
    ) -> ASGIResponse:
        return asyncio.run(
            self._async_request(
                method=method,
                url=url,
                headers=headers,
                json_data=json_data,
                data=data,
            )
        )

    async def _async_request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_data: Any = None,
        data: bytes | str | None = None,
    ) -> ASGIResponse:
        parsed_url = urlparse(url)
        path = parsed_url.path or "/"
        query_string = (parsed_url.query or "").encode("latin-1")

        req_headers = dict(headers or {})
        # Normalize header keys to lowercase
        norm_headers: dict[str, str] = {
            k.lower(): str(v) for k, v in req_headers.items()
        }
        norm_headers.setdefault("host", "testserver")

        body_bytes = b""
        if json_data is not None:
            body_bytes = json.dumps(json_data).encode("utf-8")
            norm_headers.setdefault("content-type", "application/json")
        elif data is not None:
            if isinstance(data, str):
                body_bytes = data.encode("utf-8")
            else:
                body_bytes = data

        if body_bytes and "content-length" not in norm_headers:
            norm_headers["content-length"] = str(len(body_bytes))

        raw_headers = [
            (k.encode("latin-1"), v.encode("latin-1")) for k, v in norm_headers.items()
        ]

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method.upper(),
            "headers": raw_headers,
            "path": path,
            "raw_path": path.encode("latin-1"),
            "query_string": query_string,
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "root_path": "",
            "app": self.app,
        }

        request_sent = False

        async def receive() -> dict[str, Any]:
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {
                    "type": "http.request",
                    "body": body_bytes,
                    "more_body": False,
                }
            return {
                "type": "http.request",
                "body": b"",
                "more_body": False,
            }

        response_status = 200
        response_headers: list[tuple[bytes, bytes]] = []
        response_body = bytearray()

        async def send(message: dict[str, Any]) -> None:
            nonlocal response_status, response_headers, response_body
            msg_type = message.get("type")
            if msg_type == "http.response.start":
                response_status = message["status"]
                response_headers = list(message.get("headers", []))
            elif msg_type == "http.response.body":
                response_body.extend(message.get("body", b""))

        await self.app(scope, receive, send)

        return ASGIResponse(response_status, response_headers, bytes(response_body))

    def get(self, url: str, *, headers: dict[str, str] | None = None) -> ASGIResponse:
        return self.request("GET", url, headers=headers)

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any = None,
        data: bytes | str | None = None,
    ) -> ASGIResponse:
        return self.request("POST", url, headers=headers, json_data=json, data=data)
