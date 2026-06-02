"""Verify SecurityHeadersMiddleware adds OWASP-basic headers to all responses."""
import pytest
from httpx import ASGITransport, AsyncClient

from joggy.main import app


_EXPECTED_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


@pytest.mark.asyncio
async def test_security_headers_present_on_health():
    """All 5 OWASP headers present on /health."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    for name, expected_value in _EXPECTED_HEADERS.items():
        assert name in response.headers, f"Missing header: {name}"
        assert response.headers[name] == expected_value, (
            f"Header {name}: expected {expected_value!r}, got {response.headers[name]!r}"
        )
