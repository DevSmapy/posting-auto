"""Tests for final publish guard."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from publish.guard import assert_publish_ready  # noqa: E402


def _briefing() -> dict:
    return {
        "title": "t",
        "instagram_post": "한국어 브리핑 캡션입니다.",
        "stories": [
            {
                "headline": "원·달러 환율 하락",
                "what_happened": "서울 외환시장에서 환율이 떨어졌습니다.",
                "why_important": "수입 물가에 영향을 줄 수 있습니다.",
                "watch_next": "고용지표를 확인하세요.",
                "one_liner": "환율 하락이 이어지고 있습니다.",
            }
            for _ in range(3)
        ],
    }


class PublishGuardTest(unittest.TestCase):
    def test_live_requires_llm_reviewer(self) -> None:
        with patch.dict(os.environ, {"EDITORIAL_LLM_REVIEWER": "0"}, clear=False):
            result = assert_publish_ready(
                _briefing(),
                png_paths=[],
                live=True,
                editorial_decision={"decision": "publish"},
                preflight={"ok": True},
            )
        self.assertFalse(result["ok"])
        self.assertTrue(any("EDITORIAL_LLM_REVIEWER" in b for b in result["blockers"]))

    def test_chinese_caption_blocks_live(self) -> None:
        briefing = _briefing()
        briefing["instagram_post"] = "中国市场今天上涨。"
        with patch.dict(os.environ, {"EDITORIAL_LLM_REVIEWER": "1"}, clear=False):
            with tempfile.TemporaryDirectory() as tmp:
                png1 = Path(tmp) / "1.png"
                png2 = Path(tmp) / "2.png"
                png1.write_bytes(b"x")
                png2.write_bytes(b"y")
                result = assert_publish_ready(
                    briefing,
                    png_paths=[png1, png2],
                    live=True,
                    editorial_decision={"decision": "publish"},
                    preflight={"ok": True},
                )
        self.assertFalse(result["ok"])
        self.assertTrue(any("caption:language:hard_fail" in b for b in result["blockers"]))

    def test_missing_env_blockers_when_live(self) -> None:
        with patch.dict(
            os.environ,
            {
                "EDITORIAL_LLM_REVIEWER": "1",
                "PUBLISH_CARDS": "1",
                "R2_ENDPOINT": "",
                "IG_USER_ID": "",
                "META_ACCESS_TOKEN": "",
            },
            clear=False,
        ):
            with tempfile.TemporaryDirectory() as tmp:
                png1 = Path(tmp) / "1.png"
                png2 = Path(tmp) / "2.png"
                png1.write_bytes(b"x")
                png2.write_bytes(b"y")
                result = assert_publish_ready(
                    _briefing(),
                    png_paths=[png1, png2],
                    live=True,
                    editorial_decision={"decision": "publish"},
                    preflight={"ok": True},
                )
        self.assertFalse(result["ok"])
        blockers = result["blockers"]
        self.assertTrue(any("r2_not_configured" in b for b in blockers))
        self.assertTrue(any("instagram_not_configured" in b for b in blockers))


if __name__ == "__main__":
    unittest.main()
