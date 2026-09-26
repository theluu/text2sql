import httpx

from app.llm.fake import FakeLLMProvider
from app.main import create_app
from tests.helpers import make_settings


async def test_health_reports_liveness_and_providers_without_secrets() -> None:
    app = create_app(
        make_settings(), providers={"anthropic": FakeLLMProvider("anthropic", "anthropic")}
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
    body = response.json()
    assert response.status_code == 200 and body["status"] == "ok"
    assert body["providers"][0] == {"name": "anthropic", "configured": True, "circuit": "closed"}
    assert {"name": "openai", "configured": False, "circuit": None} in body["providers"]
    assert "key" not in response.text.lower()
