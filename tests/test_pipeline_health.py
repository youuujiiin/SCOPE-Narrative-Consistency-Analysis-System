"""분석 파이프라인 연결 사전 점검 (GET /pipeline/health + RemotePipeline.health)."""
from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient

from app.pipeline.remote import RemotePipeline

URL = "/pipeline/health"


# ── API ─────────────────────────────────────────────────────
async def test_health_fake_ok(client: AsyncClient, auth_headers: dict) -> None:
    r = await client.get(URL, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["mode"] == "fake"


async def test_health_requires_auth(client: AsyncClient) -> None:
    r = await client.get(URL)
    assert r.status_code == 401


async def test_health_reports_down_pipeline_as_200(
    client: AsyncClient, auth_headers: dict, monkeypatch
) -> None:
    """AI 서버가 꺼져 있어도 500 이 아니라 ok=false + 원인으로 내려온다."""

    class _Down:
        async def health(self):
            return RemotePipeline._down("AI 서버에 연결할 수 없습니다.")

    monkeypatch.setattr("app.service.pipeline_service.get_pipeline", lambda: _Down())
    r = await client.get(URL, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["mode"] == "remote"
    assert "연결할 수 없습니다" in body["message"]


# ── RemotePipeline.health 의 실패 분류 ─────────────────────────
def _patch_transport(monkeypatch, handler) -> None:
    """RemotePipeline 이 만드는 AsyncClient 에 가짜 전송 계층을 끼운다."""
    real = httpx.AsyncClient
    monkeypatch.setattr(
        "app.pipeline.remote.httpx.AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )


async def test_remote_health_ok(monkeypatch) -> None:
    _patch_transport(
        monkeypatch,
        lambda req: httpx.Response(200, json={"ok": True, "extract_mode": "echo", "review_mode": "echo"}),
    )
    h = await RemotePipeline("http://ai").health()
    assert h.ok is True
    assert h.message == "AI 서버 연결됨"
    assert h.info["extract_mode"] == "echo"


async def test_remote_health_warns_when_embedder_loading(monkeypatch) -> None:
    _patch_transport(
        monkeypatch,
        lambda req: httpx.Response(
            200, json={"ok": True, "review_mode": "llm", "scope": {"embedder_loaded": False}}
        ),
    )
    h = await RemotePipeline("http://ai").health()
    assert h.ok is True
    assert "임베딩 모델 준비 중" in h.message


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (httpx.ConnectError("refused"), "연결할 수 없습니다"),
        (httpx.ReadTimeout("slow"), "응답하지 않습니다"),
        (httpx.RemoteProtocolError("broken"), "RemoteProtocolError"),
    ],
)
async def test_remote_health_transport_errors(monkeypatch, error, expected) -> None:
    def handler(req):
        raise error

    _patch_transport(monkeypatch, handler)
    h = await RemotePipeline("http://ai").health()
    assert h.ok is False
    assert expected in h.message


async def test_remote_health_bad_status(monkeypatch) -> None:
    _patch_transport(monkeypatch, lambda req: httpx.Response(503, text="down"))
    h = await RemotePipeline("http://ai").health()
    assert h.ok is False
    assert "HTTP 503" in h.message


async def test_remote_health_not_json(monkeypatch) -> None:
    _patch_transport(monkeypatch, lambda req: httpx.Response(200, text="<html>"))
    h = await RemotePipeline("http://ai").health()
    assert h.ok is False
    assert "JSON" in h.message


async def test_remote_health_real_refused_port() -> None:
    """실제 소켓: 아무도 안 듣는 포트면 ConnectError 경로로 떨어진다."""
    h = await RemotePipeline("http://127.0.0.1:9").health()
    assert h.ok is False
    assert "연결할 수 없습니다" in h.message
