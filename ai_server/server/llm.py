"""Claude 호출 통로. EXTRACT_MODE=llm / REVIEW_MODE=llm 일 때만 import 된다.

분석·검수 로직은 scope_ai 패키지가 갖고 있고, 이 파일은 "어느 모델을 어떤
설정으로 부르나"만 정한다. scope_ai 는 동기 코드라 server/scope_bridge.py 가
워커 스레드에서 돌리므로, 거기 넘기는 call_sync 도 동기 클라이언트를 쓴다.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from fastapi import HTTPException

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

logger = logging.getLogger("glitch-ai.llm")

MODEL_NAME = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
MAX_TOKENS = int(os.getenv("ANTHROPIC_MAX_TOKENS", "8192"))


def _api_key() -> str:
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip().strip('"').strip("'")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY 가 설정되어 있지 않습니다.")
    return api_key


@lru_cache
def _client():
    api_key = _api_key()
    from anthropic import AsyncAnthropic
    return AsyncAnthropic(api_key=api_key)


@lru_cache
def _sync_client():
    api_key = _api_key()
    from anthropic import Anthropic
    return Anthropic(api_key=api_key)


def call_sync(user_text: str, system_prompt: str) -> str:
    """scope_ai 의 llm_callable 규격 (user, system) -> text.

    Claude 응답을 스트리밍으로 수신한 후 완성된 텍스트를 반환한다.
    """
    try:
        with _sync_client().messages.stream(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_text}],
        ) as stream:
            resp = stream.get_final_message()

    except Exception as exc:
        if getattr(exc, "status_code", None) == 401:
            raise HTTPException(
                401,
                "Claude API 인증 실패(401). ai_server/.env의 "
                "ANTHROPIC_API_KEY를 확인하세요."
            ) from exc
        raise

    logger.info(
        "Claude 응답 완료: model=%s input_tokens=%s "
        "output_tokens=%s stop_reason=%s",
        resp.model,
        resp.usage.input_tokens,
        resp.usage.output_tokens,
        resp.stop_reason,
    )

    if resp.stop_reason == "max_tokens":
        logger.warning(
            "응답이 max_tokens(%d)에서 잘림",
            MAX_TOKENS,
        )

    return "\n".join(
        block.text
        for block in resp.content
        if block.type == "text"
    )


async def ping() -> dict:
    """통로 확인 전용. max_tokens=1 로 왕복만 본다 — 비용은 사실상 0.

    키가 유효한지, 네트워크가 열려 있는지, 모델명이 맞는지만 확인한다.
    분석 품질은 보지 않는다(그건 check_review.py 가 할 일이고, 그건 진짜
    호출이므로 필요할 때만 돌린다).
    """
    try:
        resp = await _client().messages.create(
        model=MODEL_NAME,
        max_tokens=1,
        messages=[{"role": "user", "content": "."}],
        )
    except Exception as exc:
        if getattr(exc, "status_code", None) == 401:
            raise HTTPException(401, "Claude API 인증 실패(401). ai_server/.env의 ANTHROPIC_API_KEY를 확인하세요.") from exc
        raise
    return {
        "ok": True,
        "model": resp.model,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }
