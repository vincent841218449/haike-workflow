"""Connection failures stay actionable without bypassing TLS or exposing secrets."""
import ssl
from urllib.error import URLError

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot.studio import Studio, atomic_private, gateway_connection_message
from backlot.studio_api import router


def test_expired_certificate_is_reported_without_raw_gateway_details(tmp_path, monkeypatch):
    studio = Studio(tmp_path / "projects")
    atomic_private(studio.config_path, {"api_key":"private-fixture-key"})
    expired = ssl.SSLCertVerificationError("raw-private-server-detail")
    expired.verify_code = 10
    class Client:
        def request(self, *args): raise URLError(expired)
    monkeypatch.setattr(studio, "client", lambda: Client())
    app = FastAPI(); app.state.studio = studio; app.include_router(router)
    client = TestClient(app)
    for path in ["/api/studio/account", "/api/studio/voices"]:
        response = client.get(path)
        assert response.status_code in {422, 503}
        assert "证书已过期" in response.json()["detail"]
        assert "private" not in response.text
    assert gateway_connection_message(ValueError("private"), "连接失败") == "连接失败"
