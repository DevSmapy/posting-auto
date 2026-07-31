"""Template Studio — clone editorial themes, edit placeholders, preview.

Run:
  uv run streamlit run apps/template_studio/app.py

Separated from Ops Console. Pipeline morning-run wiring is follow-up.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(SCRIPTS))

from cards.bundles import list_bundles  # noqa: E402
from cards.editorial import (  # noqa: E402
    SLIDE_FILES,
    EditorialCarouselTemplate,
    placeholder_content,
)
from themes import clone_theme, list_editorial_themes, theme_dir  # noqa: E402


def _load_placeholders(theme: str) -> dict[str, dict[str, str]]:
    path = theme_dir(theme) / "placeholders.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}
    return placeholder_content()


def _save_placeholders(theme: str, content: dict[str, dict[str, str]]) -> None:
    path = theme_dir(theme) / "placeholders.json"
    path.write_text(
        json.dumps(content, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _init_state() -> None:
    if "studio_theme" not in st.session_state:
        themes = list_editorial_themes()
        st.session_state.studio_theme = themes[0] if themes else "editorial"
    if "studio_content" not in st.session_state:
        st.session_state.studio_content = _load_placeholders(st.session_state.studio_theme)
    if "studio_brand" not in st.session_state:
        st.session_state.studio_brand = "BRAND"


def main() -> None:
    st.set_page_config(page_title="Template Studio", layout="wide")
    st.title("Template Studio")
    st.caption(
        "Editorial 테마 복제 · 플레이스홀더 편집 · 미리보기. "
        "아침 파이프라인 연결은 후속입니다."
    )
    _init_state()

    tab_themes, tab_edit, tab_preview, tab_bundles = st.tabs(
        ["Themes", "Placeholders", "Preview", "Bundles"]
    )
    with tab_themes:
        _themes_tab()
    with tab_edit:
        _placeholders_tab()
    with tab_preview:
        _preview_tab()
    with tab_bundles:
        _bundles_tab()


def _themes_tab() -> None:
    themes = list_editorial_themes()
    st.subheader("Editorial themes")
    st.write(", ".join(themes) if themes else "(none)")

    selected = st.selectbox(
        "Active theme",
        options=themes or ["editorial"],
        index=(
            themes.index(st.session_state.studio_theme)
            if st.session_state.studio_theme in themes
            else 0
        ),
    )
    if selected != st.session_state.studio_theme:
        st.session_state.studio_theme = selected
        st.session_state.studio_content = _load_placeholders(selected)
        st.rerun()

    st.divider()
    st.subheader("Clone theme")
    with st.form("clone_theme"):
        source = st.selectbox("Source", options=themes or ["editorial"])
        new_name = st.text_input("New name", placeholder="morning_blue → editorial_morning_blue")
        submitted = st.form_submit_button("Clone")
        if submitted:
            try:
                dest = clone_theme(source, new_name)
                st.success(f"Cloned → `{dest.relative_to(ROOT)}`")
                st.session_state.studio_theme = dest.name
                st.session_state.studio_content = _load_placeholders(dest.name)
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

    css_path = theme_dir(st.session_state.studio_theme) / "design-system.css"
    if css_path.is_file():
        st.subheader("design-system.css")
        edited = st.text_area(
            "CSS variables / rules",
            value=css_path.read_text(encoding="utf-8"),
            height=280,
        )
        if st.button("Save CSS"):
            css_path.write_text(edited, encoding="utf-8")
            st.success("CSS saved")


def _placeholders_tab() -> None:
    content: dict[str, dict[str, str]] = dict(st.session_state.studio_content)
    brand = st.text_input("Brand", value=st.session_state.studio_brand)
    st.session_state.studio_brand = brand

    slide = st.selectbox("Slide", options=list(SLIDE_FILES))
    fields = dict(content.get(slide) or {})
    updated: dict[str, str] = {}
    with st.form(f"fields_{slide}"):
        new_field = st.text_input("New field name", value="")
        keys = sorted(fields.keys()) or ["headline"]
        nk = (new_field or "").strip()
        if nk and nk not in keys:
            keys = sorted([*keys, nk])
        for key in keys:
            updated[key] = st.text_area(key, value=str(fields.get(key, "")), height=80)
        if st.form_submit_button("Apply slide fields"):
            content[slide] = updated
            st.session_state.studio_content = content
            st.success(f"Updated {slide}")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Reload from theme disk"):
            st.session_state.studio_content = _load_placeholders(st.session_state.studio_theme)
            st.rerun()
    with col_b:
        if st.button("Save placeholders.json to theme"):
            _save_placeholders(st.session_state.studio_theme, st.session_state.studio_content)
            st.success("Saved placeholders.json")


def _preview_tab() -> None:
    theme = st.session_state.studio_theme
    brand = st.session_state.studio_brand
    content = st.session_state.studio_content
    render_png = st.checkbox("Also render PNG (needs Browserless/Chrome)", value=False)

    if st.button("Generate preview", type="primary"):
        try:
            tpl = EditorialCarouselTemplate(
                brand=brand,
                content=content,
                templates_dir=theme_dir(theme),
            )
            old_preview = st.session_state.get("studio_preview_dir")
            if old_preview:
                shutil.rmtree(old_preview, ignore_errors=True)
            out = Path(tempfile.mkdtemp(prefix="template_studio_"))
            result = tpl.export(out, render_png=render_png)
            st.session_state.studio_preview_dir = str(out)
            st.success(f"Preview written to `{out}`")
            html_paths = result.get("html") or []
            if html_paths:
                first = Path(html_paths[0])
                st.components.v1.html(
                    first.read_text(encoding="utf-8"),
                    height=700,
                    scrolling=True,
                )
            png_paths = result.get("png") or []
            if png_paths:
                st.image([str(p) for p in png_paths], width=240)
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))

    prev = st.session_state.get("studio_preview_dir")
    if prev and Path(prev).is_dir():
        st.caption(f"Last preview: `{prev}`")
        slides = sorted(Path(prev).glob("slide-*.html"))
        pick = st.selectbox(
            "Open slide HTML",
            options=[p.name for p in slides],
            key="studio_slide_pick",
        )
        if pick:
            html_doc = (Path(prev) / pick).read_text(encoding="utf-8")
            st.components.v1.html(html_doc, height=700, scrolling=True)


def _bundles_tab() -> None:
    st.subheader("Pipeline card bundles")
    st.caption("`scripts/cards/bundles/*.json` — morning run selection stays in Ops Console.")
    for bundle in list_bundles():
        badge = f" · {bundle.badge}" if bundle.badge else ""
        st.markdown(
            f"**{bundle.id}** — {bundle.name_ko}{badge}  \n"
            f"{bundle.purpose} · cards={bundle.card_count}"
        )


if __name__ == "__main__":
    main()
