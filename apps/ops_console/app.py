"""Ops console — schedule, RSS feeds, card bundle (Streamlit).

Run:
  uv run streamlit run apps/ops_console/app.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cards.bundles import list_bundles  # noqa: E402
from ops_config import (  # noqa: E402
    ensure_ops_config,
    load_ops_config,
    ops_path,
    save_ops_config,
)

WEEKDAY_LABELS = {
    1: "월",
    2: "화",
    3: "수",
    4: "목",
    5: "금",
    6: "토",
    7: "일",
}


def _init_state() -> None:
    if "ops" not in st.session_state:
        st.session_state.ops = ensure_ops_config()


def _reload_ops() -> None:
    st.session_state.ops = load_ops_config()


def main() -> None:
    st.set_page_config(page_title="Ops Console", layout="wide")
    st.title("Ops Console")
    st.caption(
        f"설정 파일: `{ops_path()}` · Discord Approve 흐름은 그대로 둡니다."
    )
    _init_state()

    tab_schedule, tab_feeds, tab_cards = st.tabs(["Schedule", "Feeds", "Cards"])

    with tab_schedule:
        _schedule_tab()
    with tab_feeds:
        _feeds_tab()
    with tab_cards:
        _cards_tab()


def _schedule_tab() -> None:
    ops = st.session_state.ops
    schedule = dict(ops.get("schedule") or {})
    current_days = [int(d) for d in (schedule.get("weekdays") or [1, 2, 3, 4, 5])]

    with st.form("schedule_form"):
        st.subheader("실행 · 알림 시각")
        tz = st.text_input("Timezone", value=str(ops.get("timezone") or "Asia/Seoul"))
        selected = st.multiselect(
            "Weekdays (ISO 1=월 … 7=일)",
            options=list(WEEKDAY_LABELS.keys()),
            default=current_days,
            format_func=lambda d: f"{d} ({WEEKDAY_LABELS[d]})",
        )
        run_at = st.text_input("run_at (HH:MM)", value=str(schedule.get("run_at") or "06:00"))
        notify_at = st.text_input(
            "notify_at (HH:MM)",
            value=str(schedule.get("notify_at") or "07:00"),
            help="Discord 등 Approve 초안 발송 시각. NOTIFY_SEND_AT env가 있으면 env가 우선합니다.",
        )
        submitted = st.form_submit_button("Save schedule")
        if submitted:
            if not selected:
                st.error("요일을 하나 이상 선택하세요.")
            else:
                try:
                    updated = {
                        **ops,
                        "timezone": tz.strip() or "Asia/Seoul",
                        "schedule": {
                            "weekdays": sorted(int(d) for d in selected),
                            "run_at": run_at.strip(),
                            "notify_at": notify_at.strip(),
                        },
                    }
                    save_ops_config(updated)
                    _reload_ops()
                    st.success("Schedule saved.")
                except ValueError as exc:
                    st.error(str(exc))

    st.info(
        "crontab은 UI에서 바꾸지 않습니다. 예:\n"
        '`0 6 * * 1-5 "/ABS/scripts/cron_run_draft.sh" >>"/ABS/output/cron.log" 2>&1`'
    )


def _feeds_tab() -> None:
    ops = st.session_state.ops
    feeds = list(ops.get("feeds") or [])
    # Keep an editable buffer in session for add/remove outside the save form.
    if "feeds_draft" not in st.session_state:
        st.session_state.feeds_draft = [
            {
                "_id": uuid4().hex,
                "label": str(f.get("label") or ""),
                "url": str(f.get("url") or ""),
            }
            for f in feeds
        ]

    st.subheader("RSS feeds")
    draft = st.session_state.feeds_draft

    remove_idx: int | None = None
    for i, row in enumerate(draft):
        row_id = str(row.setdefault("_id", uuid4().hex))
        c1, c2, c3 = st.columns([2, 6, 1])
        with c1:
            row["label"] = st.text_input(
                f"label_{i}",
                value=row.get("label") or "",
                label_visibility="collapsed",
                placeholder="Label",
                key=f"feed_label_{row_id}",
            )
        with c2:
            row["url"] = st.text_input(
                f"url_{i}",
                value=row.get("url") or "",
                label_visibility="collapsed",
                placeholder="https://…/rss",
                key=f"feed_url_{row_id}",
            )
        with c3:
            if st.button("Del", key=f"feed_del_{row_id}"):
                remove_idx = i

    if remove_idx is not None:
        draft.pop(remove_idx)
        st.session_state.feeds_draft = draft
        st.rerun()

    if st.button("Add feed"):
        draft.append({"_id": uuid4().hex, "label": "FEED", "url": ""})
        st.session_state.feeds_draft = draft
        st.rerun()

    with st.form("feeds_save_form"):
        st.caption("위 목록을 확인한 뒤 Save feeds를 누르세요.")
        if st.form_submit_button("Save feeds"):
            cleaned = []
            cleaned_draft = []
            for row in st.session_state.feeds_draft:
                url = str(row.get("url") or "").strip()
                if not url:
                    continue
                label = str(row.get("label") or "FEED").strip() or "FEED"
                cleaned.append({"label": label, "url": url})
                cleaned_draft.append(
                    {
                        "_id": str(row.get("_id") or uuid4().hex),
                        "label": label,
                        "url": url,
                    }
                )
            if not cleaned:
                st.error("URL이 있는 피드를 하나 이상 남겨 주세요.")
            else:
                updated = {**ops, "feeds": cleaned}
                save_ops_config(updated)
                _reload_ops()
                st.session_state.feeds_draft = cleaned_draft
                st.success(f"Saved {len(cleaned)} feed(s).")


def _cards_tab() -> None:
    ops = st.session_state.ops
    cards = dict(ops.get("cards") or {})
    bundles = list(list_bundles())
    ids = [b.id for b in bundles]
    if not ids:
        st.subheader("Instagram card bundle")
        st.info("사용 가능한 카드 번들이 없습니다.")
        return
    current = str(cards.get("bundle_id") or "daily_briefing")
    if current not in ids and ids:
        current = ids[0]
    labels = {
        b.id: f"{b.id} — {b.name_ko} ({b.card_count}장)"
        for b in bundles
    }

    with st.form("cards_form"):
        st.subheader("Instagram card bundle")
        choice = st.selectbox(
            "bundle_id",
            options=ids,
            index=ids.index(current) if current in ids else 0,
            format_func=lambda i: labels.get(i, i),
        )
        if st.form_submit_button("Save bundle"):
            updated = {**ops, "cards": {"bundle_id": choice}}
            save_ops_config(updated)
            _reload_ops()
            st.success(f"bundle_id={choice} saved.")

    st.divider()
    st.subheader("Preview")
    st.caption("저장된 bundle_id로 preview_cardnews를 실행합니다 (샘플 데이터).")
    if st.button("Run preview"):
        bundle_id = str(
            (st.session_state.ops.get("cards") or {}).get("bundle_id")
            or "daily_briefing"
        )
        out_dir = ROOT / "output" / "cardnews-preview-ops"
        cmd = [
            sys.executable,
            str(SCRIPTS / "preview_cardnews.py"),
            "--bundle",
            bundle_id,
            "--out",
            str(out_dir),
            "--no-png",
        ]
        # Prefer uv when available for deps.
        try:
            proc = subprocess.run(
                ["uv", "run", "python", *cmd[1:]],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            proc = subprocess.run(
                cmd,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
        if proc.returncode != 0:
            st.error("Preview failed")
            st.code((proc.stderr or proc.stdout or "")[-4000:])
        else:
            st.success(f"Preview OK → {out_dir}")
            st.code((proc.stdout or "")[-4000:])
            meta = out_dir / "meta.json"
            if meta.is_file():
                st.json(json.loads(meta.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
