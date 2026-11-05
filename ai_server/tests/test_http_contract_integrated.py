from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

import httpx
from server import main, scope_bridge
from tests.test_scope_bridge import CH1, CH2, FakeLLM
import server.llm


class HttpContractTest(unittest.TestCase):
    def test_extract_review_health(self):
        with tempfile.TemporaryDirectory() as directory:
            saved = (main.EXTRACT_MODE, main.REVIEW_MODE, scope_bridge.DATA_ROOT, scope_bridge.EMBEDDING_MODE,
                     scope_bridge._embedder, server.llm.call_sync)
            main.EXTRACT_MODE = "llm"
            main.REVIEW_MODE = "llm"
            scope_bridge.DATA_ROOT = Path(directory)
            scope_bridge.EMBEDDING_MODE = "hash"
            scope_bridge._embedder = None
            server.llm.call_sync = FakeLLM()

            async def run():
                transport = httpx.ASGITransport(app=main.app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    health = await client.get("/health")
                    self.assertEqual(health.status_code, 200)
                    self.assertTrue(health.json()["ok"])
                    data = {"canon": {"project_id": "contract"}, "chapter_no": 1, "chapter_text": CH1}
                    response = await client.post("/extract", json=data)
                    self.assertEqual(response.status_code, 200, response.text)
                    event = response.json()["events"][0]
                    self.assertEqual(event["event_id"], "EVENT_001")
                    second = await client.post("/extract", json={**data, "chapter_no": 2, "chapter_text": CH2})
                    self.assertEqual(second.status_code, 200, second.text)
                    review = await client.post("/review", json={**data, "chapter_no": 2, "chapter_text": CH2,
                            "delta": {"events": [{"entity_key": "EVENT_002", "label": "사용자가 바꾼 제목",
                                    "summary": "원문과 대조할 수정 요약", "order_index": 1}]}})
                    self.assertEqual(review.status_code, 200, review.text)
                    self.assertEqual(review.json()["contradictions"][0]["type"], "timeline")

            try:
                asyncio.run(run())
            finally:
                main.EXTRACT_MODE, main.REVIEW_MODE, scope_bridge.DATA_ROOT, scope_bridge.EMBEDDING_MODE, scope_bridge._embedder, server.llm.call_sync = saved
