"""프로젝트 수정 + 썸네일 업로드 테스트."""
from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.core.db import SessionLocal
from app.repository.project_repo import ProjectRepository


async def test_patch_project(client: AsyncClient, auth_headers: dict, project_id: str):
    r = await client.patch(
        f"/projects/{project_id}",
        json={"author": "Cho", "description": "정직한 나무꾼"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["author"] == "Cho" and body["description"] == "정직한 나무꾼"


async def test_patch_ownership(client: AsyncClient, auth_headers: dict, project_id: str):
    r2 = await client.post(
        "/auth/register",
        json={"email": f"o_{uuid.uuid4().hex[:8]}@x.com", "password": "secret123"},
    )
    h2 = {"Authorization": f"Bearer {r2.json()['access_token']}"}
    r = await client.patch(f"/projects/{project_id}", json={"author": "x"}, headers=h2)
    assert r.status_code == 403


async def test_thumbnail_upload(client: AsyncClient, auth_headers: dict, project_id: str):
    # 이미지 content-type 이면 통과(바이트 내용은 검사 안 함)
    r = await client.post(
        f"/projects/{project_id}/thumbnail",
        files={"file": ("t.png", b"\x89PNG fake-bytes", "image/png")},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["thumbnail_url"].startswith("/uploads/thumbnails/")

    async with SessionLocal() as s:
        project = await ProjectRepository(s).get_by_id(uuid.UUID(project_id))
        assert project.thumbnail_url


async def test_thumbnail_rejects_non_image(client: AsyncClient, auth_headers: dict, project_id: str):
    r = await client.post(
        f"/projects/{project_id}/thumbnail",
        files={"file": ("t.txt", b"not an image", "text/plain")},
        headers=auth_headers,
    )
    assert r.status_code == 400
