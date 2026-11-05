from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from server import scope_bridge
from server.schemas import CanonSnapshot, ExtractRequest, ReviewRequest
from tests.test_scope_bridge import CH1, CH2, FakeLLM
import server.llm


class IntegratedFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = (scope_bridge.DATA_ROOT, scope_bridge.EMBEDDING_MODE, scope_bridge._embedder, server.llm.call_sync)
        scope_bridge.DATA_ROOT = Path(self.tmp.name)
        scope_bridge.EMBEDDING_MODE = "hash"
        scope_bridge._embedder = None
        self.fake = FakeLLM()
        server.llm.call_sync = self.fake
        self.canon = CanonSnapshot(project_id="integrated")

    def tearDown(self):
        scope_bridge.DATA_ROOT, scope_bridge.EMBEDDING_MODE, scope_bridge._embedder, server.llm.call_sync = self.original
        self.tmp.cleanup()

    def run_async(self, coro):
        return asyncio.run(coro)

    def extract(self, n, text):
        return self.run_async(scope_bridge.extract(ExtractRequest(canon=self.canon, chapter_text=text, chapter_no=n)))

    def review(self, n, text, delta):
        return self.run_async(scope_bridge.review(ReviewRequest(canon=self.canon, chapter_text=text, chapter_no=n, delta=delta)))

    def test_review_syncs_user_delta_and_produces_sources(self):
        first = self.extract(1, CH1)
        self.assertEqual(first["events"][0]["event_id"], "EVENT_001")
        root = Path(self.tmp.name) / "integrated"
        self.assertFalse((root / "embeddings" / "event_embeddings.json").exists())
        manifest = json.loads((root / "split" / "ep1" / "event_sources" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["events"]["EVENT_001"]["source_status"], "verified")
        item = {"entity_key": "EVENT_001", "label": "사용자 수정된 사건 제목", "order_index": 1, "note": "중요한 검수 메모"}
        self.review(1, CH1, {"events": [item]})
        ep = json.loads((root / "ep_global.json").read_text(encoding="utf-8"))
        event = ep["events"][0]
        self.assertEqual(event["event_id"], "EVENT_001")
        self.assertEqual(event["title"], item["label"])
        self.assertEqual(event["user_note"], item["note"])
        self.assertTrue((root / "embeddings" / "event_embeddings.json").exists())
        state = json.loads((root / "episodes" / "ep1_workflow.json").read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "reviewed")

    def test_reviewed_edit_locked(self):
        self.extract(1, CH1)
        self.review(1, CH1, {})
        root = Path(self.tmp.name) / "integrated"
        from scope_ai.workflow import edit_submission
        from scope_ai.common import load_json, StoryPaths
        ep = load_json(StoryPaths("integrated", Path(self.tmp.name)).ep(1))
        with self.assertRaises(ValueError):
            edit_submission("integrated", 1, ep, data_root=Path(self.tmp.name))

    def test_failed_review_restores_editable_state(self):
        self.extract(1, CH1)
        self.extract(2, CH2)
        server.llm.call_sync = lambda text, prompt: self.fake(text, prompt) if prompt.startswith("chap") else "not json"
        with self.assertRaises(Exception):
            self.review(2, CH2, {})
        root = Path(self.tmp.name) / "integrated"
        state = json.loads((root / "episodes" / "ep2_workflow.json").read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "confirmed")

    def test_confirmed_revision_reembeds_changed_field_only(self):
        self.extract(1, CH1)
        from scope_ai.workflow import confirm_submission, edit_submission
        from scope_ai.common import load_json, StoryPaths
        root = Path(self.tmp.name)
        paths = StoryPaths("integrated", root)
        scope_bridge._apply_confirmed_delta(paths, 1, {})
        confirm_submission("integrated", 1, data_root=root, embedder=scope_bridge.get_embedder())
        before = load_json(paths.ep_global)["events"][0]
        ep = load_json(paths.ep(1))
        ep["events"][0]["summary"] = "수정된 사건 설명"
        edit_submission("integrated", 1, ep, data_root=root)
        outcome = confirm_submission("integrated", 1, data_root=root, embedder=scope_bridge.get_embedder())
        event_id = before["event_id"]
        self.assertEqual(load_json(paths.ep_global)["events"][0]["event_id"], event_id)
        self.assertEqual(outcome["embedding"]["updated_fields"][event_id], ["summary"])

    def test_api_transient_error_retried_once(self):
        self.extract(1, CH1)
        self.extract(2, CH2)
        calls = []
        fake = self.fake
        class TransientError(Exception):
            status_code = 429
        def request(text, prompt):
            if prompt.startswith("chap"):
                return fake(text, prompt)
            calls.append(text)
            if len(calls) == 1:
                raise TransientError("temporarily unavailable")
            return fake(text, prompt)
        server.llm.call_sync = request
        response = self.review(2, CH2, {})
        self.assertTrue(response.contradictions)
        self.assertEqual(len(calls), 2)

    def test_revision_keeps_unverified_candidates(self):
        first = self.extract(1, CH1)
        root = Path(self.tmp.name) / "integrated"
        item = {"entity_key": "EVENT_001", "label": "수정된 사건", "order_index": 1, "quote": "원문과 불일치하는 참고 문장"}
        self.review(1, CH1, {"events": [item]})
        self.extract(2, CH2)
        response = self.review(2, CH2, {})
        self.assertEqual(len(response.contradictions), 1)
        self.assertTrue((root / "split" / "ep2" / "event_sources" / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
