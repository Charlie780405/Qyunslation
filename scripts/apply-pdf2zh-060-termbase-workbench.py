#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Inject PLAN-060's server-side term-review hooks into pdf2zh-next GUI.

The upstream GUI is installed outside this repository.  This idempotent patch
adds only Python/Gradio callbacks: it never places an internal URL, HMAC
header, or secret in ``head=``/browser JavaScript.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)

PY_MARKER = "# _qy_060_term_bridge_runtime"
OFFICE_MARKER = "# _qy_060_term_bridge_office"
COMPLETE_MARKER = "# _qy_060_term_bridge_complete"
EARLY_COMPLETE_MARKER = "# _qy_060_term_bridge_early_complete"
UI_MARKER = "# _qy_060_term_review_ui"
EVENT_MARKER = "# _qy_060_term_review_events"
TIMER_MARKER = "# _qy_060_term_review_timer"
CSS_MARKER = "/* _qy_060_term_review_css */"

CSS_BLOCK = r'''
    /* _qy_060_term_review_css */
    .qy-060-term-badge {
      width: auto !important;
      min-height: 36px !important;
      margin: 8px 16px !important;
      border-radius: 8px !important;
      font-weight: 600 !important;
    }
    /* PLAN-015 锁一屏；检查器/术语表高于视口时必须自滚，否则「保存」被裁切。 */
    .qy-050-inspector, .qy-050-help {
      position: fixed !important;
      top: calc(var(--qy-appbar-h, 48px) + 8px) !important;
      left: 16px !important;
      right: 16px !important;
      z-index: 90 !important;
      max-height: calc(100vh - var(--qy-appbar-h, 48px) - 24px) !important;
      overflow-x: hidden !important;
      overflow-y: auto !important;
      overscroll-behavior: contain !important;
      box-shadow: 0 12px 40px rgba(15, 23, 42, 0.18) !important;
    }
    .qy-050-inspector .wrap,
    .qy-050-inspector .contain,
    .qy-050-inspector .form,
    .qy-050-help .wrap,
    .qy-050-help .contain,
    .qy-050-help .form {
      height: auto !important;
      max-height: none !important;
      overflow: visible !important;
    }
    .qy-050-inspector .table-wrap,
    .qy-050-inspector .dataframe-wrap {
      max-width: 100% !important;
      overflow-x: auto !important;
    }
    @media (max-width: 767px) {
      .qy-060-term-badge { width: calc(100% - 32px) !important; }
      .qy-050-inspector, .qy-050-help {
        left: 8px !important;
        right: 8px !important;
      }
    }
'''

_TRANSLATE_SIGNATURE = '''async def translate_files(
    file_type,
    file_input,
    link_input,
    *ui_args,
    progress=None,
):'''
_TRANSLATE_SIGNATURE_LEGACY = '''async def translate_files(
    file_type,
    file_input,
    link_input,
    *ui_args,
    request: gr.Request | None = None,
    progress=None,
):'''
_TRANSLATE_SIGNATURE_PATCHED = '''async def translate_files(
    file_type,
    file_input,
    link_input,
    request: gr.Request | None = None,
    *ui_args,
    progress=None,
):'''

PY_BLOCK = f'''    {PY_MARKER}
    _qy060_actor_sub = str(getattr(request, "username", "") or "").strip()
    state.setdefault("_qy060_runs", {{}})
    state.setdefault("_qy060_term_summaries", {{}})
    state.setdefault("_qy060_term_note", "")
    state["_qy060_term_done"] = False
'''

START_BLOCK = '''            _qy060_current = None
            try:
                if _qy060_actor_sub:
                    from qyunslation.workbench.gui_client import prepare_workbench_translation
                    _qy060_current = await asyncio.to_thread(
                        prepare_workbench_translation,
                        file_path,
                        actor_sub=_qy060_actor_sub,
                        src_lang=ui_inputs.get("lang_from"),
                        tgt_lang=ui_inputs.get("lang_to"),
                        external_task_id=session_id,
                    )
                    state["_qy060_runs"][filename] = _qy060_current
                else:
                    state["_qy060_term_note"] = "请登录后使用专业词库。"
            except Exception:
                # Term review must not turn a successful translation into a
                # failed job; the panel will expose its degraded state.
                state["_qy060_term_note"] = "专业词库暂不可用；本次未写入共享词库。"

'''

_OFFICE_SIGNATURE = '''async def _qy_run_office_sidecar_task(
    file_path: Path,
    output_dir: Path,
    progress,
    task_prefix: str = "",
    to_lang: str = "简体中文",
):'''
_OFFICE_SIGNATURE_PATCHED = '''async def _qy_run_office_sidecar_task(
    file_path: Path,
    output_dir: Path,
    progress,
    task_prefix: str = "",
    to_lang: str = "简体中文",
    termbase_policy: dict | None = None,
    termbase_version: str | None = None,
):'''
_OFFICE_PAYLOAD = '    payload = {"workflow_type": workflow_type, "to_lang": mapped}\n'
_OFFICE_PAYLOAD_PATCHED = '''    payload = {"workflow_type": workflow_type, "to_lang": mapped}
    # _qy_060_term_bridge_office
    if termbase_policy:
        from qyunslation.workbench.gui_client import office_term_payload
        payload.update(office_term_payload(termbase_policy))
        payload["termbase_version"] = termbase_version or payload.get("termbase_version")
'''

UI_BLOCK = f'''        {UI_MARKER}
        qy060_term_badge = gr.Button(
            "专业词汇：翻译后生成",
            visible=False,
            size="sm",
            elem_classes=["qy-060-term-badge"],
        )
        with qy_inspector:
            gr.Markdown("### 专业词汇")
            qy060_term_filter = gr.Dropdown(
                choices=["待确认", "待管理员", "已应用", "术语未遵循", "已处理"],
                value="待确认",
                label="筛选",
            )
            qy060_term_table = gr.Dataframe(
                headers=["源词", "实际译法", "推荐译法", "确认译法", "风险", "类型", "次数", "状态"],
                datatype=["str", "str", "str", "str", "str", "str", "number", "str"],
                value=[],
                type="array",
                interactive=True,
                static_columns=[0, 1, 2, 4, 5, 6, 7],
                col_count=(8, "fixed"),
                label="术语候选",
            )
            qy060_candidate_id = gr.Dropdown(choices=[], label="待审术语")
            qy060_context = gr.Markdown("翻译完成后可查看页码、表格或 OCR 定位。")
            gr.Markdown("选择候选后可编辑“确认译法”列或下方确认译法；实际译法和推荐译法为本次证据与 AI 建议。保存后确认译法将进入词库。")
            qy060_actual = gr.Textbox(label="实际译法（原文证据）", interactive=False)
            qy060_recommended = gr.Textbox(label="推荐译法（AI 建议）", interactive=False)
            qy060_target = gr.Textbox(label="确认译法（保存采用）", placeholder="请输入最终确认译法")
            qy060_action = gr.Dropdown(
                choices=["批准", "编辑后批准", "关联已有词条", "不译", "拒绝", "提交管理员复核"],
                value="批准",
                label="操作",
            )
            qy060_concept = gr.Dropdown(choices=[], allow_custom_value=True, label="关联已有词条（点选或粘贴 Concept ID）")
            qy060_note = gr.Textbox(label="审校备注")
            qy060_decide = gr.Button("保存术语决定", variant="primary")
            qy060_batch_exact = gr.Button("批量确认精确项", size="sm")
            qy060_decision_status = gr.Markdown("")
'''

EVENT_BLOCK = f'''        {EVENT_MARKER}
        def _qy060_current_run(state):
            runs = (state or {{}}).get("_qy060_runs") or {{}}
            return list(runs.values())[-1] if runs else None

        _QY060_PLACEHOLDERS = frozenset({{"未可靠对齐", "需人工填写", "暂无 AI 推荐"}})

        def _qy060_filter_status(label):
            return {{"待确认": "pending", "待管理员": "pending_admin", "已应用": "applied", "术语未遵循": "violation", "已处理": None}}.get(label)

        def _qy060_rows_for_filter(rows, selected_filter):
            status = _qy060_filter_status(selected_filter)
            if selected_filter == "已处理":
                return [row for row in rows if row.get("status") in {{"approved", "rejected"}}]
            if status:
                return [row for row in rows if row.get("status") == status]
            return list(rows)

        def _qy060_confirm_default(row):
            match = (row or {{}}).get("match_type")
            if match not in {{"termbase", "verbatim", "exact", "alias", "llm"}}:
                return ""
            return (row.get("suggested_target") or row.get("observed_target") or "")

        def _qy060_row_context(row):
            if not row:
                return "当前筛选下没有待确认术语。"
            locations = [
                f"第{{item.get('page_no') or '-'}}页 / {{item.get('block_id') or item.get('object_id') or '正文'}}"
                for item in row.get("occurrences") or []
            ]
            return "\\n\\n".join([
                f"**源词：** {{row.get('source_term', '')}}",
                f"**原文上下文：** {{row.get('source_context') or '-'}}",
                f"**译文上下文：** {{row.get('target_context') or '-'}}",
                f"**定位：** {{'；'.join(locations) or '-'}}",
            ])

        def _qy060_table_confirmation(review, candidate_id, table_data, selected_filter):
            """读取唯一可编辑列；证据列永远不作为人工决定写入。"""
            if not isinstance(table_data, list):
                return None
            rows = _qy060_rows_for_filter(review.get("candidates", []), selected_filter)
            index = next((index for index, row in enumerate(rows) if row.get("id") == candidate_id), None)
            if index is None or index >= len(table_data) or not isinstance(table_data[index], (list, tuple)):
                return None
            values = table_data[index]
            if len(values) <= 3:
                return None
            value = str(values[3] or "").strip()
            return None if not value or value in _QY060_PLACEHOLDERS else value

        def _qy060_render_terms(state, selected_filter, keep_selection=None):
            from qyunslation.workbench.gui_client import get_workbench_term_review
            run = _qy060_current_run(state)
            note = (state or {{}}).get("_qy060_term_note", "")
            if not run:
                return (
                    gr.update(value=note or "专业词汇：本次不可用", visible=bool(note)),
                    gr.update(value=[]),
                    gr.update(choices=[], value=None),
                    gr.update(value=note or "尚无可审校术语。"),
                    gr.update(value=""),
                    gr.update(value=""),
                    gr.update(value=""),
                )
            try:
                review = get_workbench_term_review(run)
            except Exception:
                return (
                    gr.update(value="专业词汇：提取降级", visible=True),
                    gr.update(value=[]),
                    gr.update(choices=[], value=None),
                    gr.update(value="专业词库暂不可用；译文未受影响，未写入共享词库。"),
                    gr.update(value=""),
                    gr.update(value=""),
                    gr.update(value=""),
                )
            summary = review["summary"]
            rows = _qy060_rows_for_filter(review["candidates"], selected_filter)
            table = [[
                row.get("source_term", ""), row.get("observed_target") or "需人工填写",
                row.get("suggested_target") or "暂无 AI 推荐", _qy060_confirm_default(row),
                row.get("risk", ""), row.get("term_type", ""), len(row.get("occurrences") or []), row.get("status", ""),
            ] for row in rows]
            choices = [(f"{{row.get('source_term', '')}} · {{row.get('status', '')}}", row["id"]) for row in rows]
            badge = f"专业词汇：待确认 {{summary.get('pending', 0)}}"
            if summary.get("pending_admin"):
                badge += f" · 待复核 {{summary['pending_admin']}}"
            if summary.get("status") == "extraction_degraded":
                badge += " · 提取降级"
            if summary.get("violation"):
                badge += f" · 未遵循 {{summary['violation']}}"
            selected = next((row for row in rows if row.get("id") == keep_selection), None) or (rows[0] if rows else None)
            actual = (selected or {{}}).get("observed_target") or ""
            recommended = (selected or {{}}).get("suggested_target") or ""
            return (
                gr.update(value=badge, visible=True),
                gr.update(value=table),
                gr.update(choices=choices, value=selected["id"] if selected else None),
                gr.update(value=_qy060_row_context(selected)),
                gr.update(value=actual or "需人工填写"),
                gr.update(value=recommended or "暂无 AI 推荐"),
                gr.update(value=_qy060_confirm_default(selected or {{}})),
            )

        def _qy060_concept_update(state, source_term):
            from qyunslation.workbench.gui_client import search_workbench_concepts
            run = _qy060_current_run(state)
            if not run or not source_term:
                return gr.update(choices=[], value=None)
            try:
                matches = search_workbench_concepts(run, source_term)
            except Exception:
                return gr.update()
            choices = [
                (f"{{item.get('source_term')}} → {{item.get('preferred_target')}}（{{item.get('layer')}}）", item.get("concept_id"))
                for item in matches
                if item.get("concept_id")
            ]
            return gr.update(choices=choices, value=choices[0][1] if choices else None)

        def _qy060_select_term(state, candidate_id):
            from qyunslation.workbench.gui_client import get_workbench_term_review
            run = _qy060_current_run(state)
            if not run or not candidate_id:
                return gr.update(value=""), gr.update(value=""), gr.update(value=""), gr.update(value=""), gr.update(choices=[], value=None)
            try:
                candidates = get_workbench_term_review(run).get("candidates", [])
            except Exception:
                return gr.update(value="专业词库暂不可用。"), gr.update(value=""), gr.update(value=""), gr.update(value=""), gr.update()
            row = next((item for item in candidates if item.get("id") == candidate_id), None)
            if not row:
                return gr.update(value="术语已更新，请刷新列表。"), gr.update(value=""), gr.update(value=""), gr.update(value=""), gr.update()
            actual = row.get("observed_target") or ""
            recommended = row.get("suggested_target") or ""
            return (
                gr.update(value=_qy060_row_context(row)),
                gr.update(value=actual or "需人工填写"),
                gr.update(value=recommended or "暂无 AI 推荐"),
                gr.update(value=_qy060_confirm_default(row)),
                _qy060_concept_update(state, row.get("source_term")),
            )

        def _qy060_select_table_row(state, selected_filter, event: gr.SelectData):
            from qyunslation.workbench.gui_client import get_workbench_term_review
            run = _qy060_current_run(state)
            if not run:
                return gr.update(value=None), gr.update(value=""), gr.update(value=""), gr.update(value=""), gr.update(value=""), gr.update()
            try:
                review = get_workbench_term_review(run)
                rows = _qy060_rows_for_filter(review.get("candidates", []), selected_filter)
                raw_index = event.index[0] if isinstance(event.index, (list, tuple)) else event.index
                try:
                    index = int(raw_index)
                except (TypeError, ValueError):
                    index = -1
                row = rows[index] if 0 <= index < len(rows) else None
            except Exception:
                row = None
            if not row:
                return gr.update(value=None), gr.update(value=""), gr.update(value=""), gr.update(value=""), gr.update(value=""), gr.update()
            actual = row.get("observed_target") or ""
            recommended = row.get("suggested_target") or ""
            return (
                gr.update(value=row.get("id")),
                gr.update(value=_qy060_row_context(row)),
                gr.update(value=actual or "需人工填写"),
                gr.update(value=recommended or "暂无 AI 推荐"),
                gr.update(value=_qy060_confirm_default(row)),
                _qy060_concept_update(state, row.get("source_term")),
            )

        def _qy060_table_input(table_data, state, candidate_id, selected_filter):
            from qyunslation.workbench.gui_client import get_workbench_term_review
            run = _qy060_current_run(state)
            if not run or not candidate_id:
                return gr.update()
            try:
                review = get_workbench_term_review(run)
                value = _qy060_table_confirmation(review, candidate_id, table_data, selected_filter)
            except Exception:
                return gr.update()
            return gr.update() if value is None else gr.update(value=value)

        def _qy060_decide_term(state, candidate_id, label, target, concept_id, note, selected_filter, table_data):
            from qyunslation.workbench.gui_client import decide_workbench_term, get_workbench_term_review
            run = _qy060_current_run(state)
            if not run or not candidate_id:
                return gr.update(value="请先选择术语。"), *_qy060_render_terms(state, selected_filter)
            actions = {{"批准": "approve", "编辑后批准": "approve", "关联已有词条": "merge", "不译": "do_not_translate", "拒绝": "reject", "提交管理员复核": "submit_for_admin"}}
            try:
                review = get_workbench_term_review(run)
                row = next(item for item in review["candidates"] if item.get("id") == candidate_id)
                pending_rows = _qy060_rows_for_filter(review["candidates"], selected_filter)
                current_index = next((index for index, item in enumerate(pending_rows) if item.get("id") == candidate_id), 0)
                table_target = _qy060_table_confirmation(review, candidate_id, table_data, selected_filter)
                chosen_target = (table_target or "").strip() or (target or "").strip()
                if chosen_target in _QY060_PLACEHOLDERS:
                    chosen_target = ""
                if actions[label] in {{"approve", "merge"}} and not chosen_target:
                    return gr.update(value="请先填写确认译法，再保存术语决定。"), *_qy060_render_terms(state, selected_filter)
                decide_workbench_term(run, candidate_id, {{"action": actions[label], "expected_version": row["version"], "target_term": chosen_target or None, "concept_id": concept_id or None, "note": note or None}})
            except Exception as exc:
                code = getattr(exc, "status_code", None)
                detail = {{
                    403: "该术语属高风险类别，需管理员复核后才能入库。",
                    409: "术语已被其他审校者更新，请刷新后重试。",
                    404: "术语候选已不存在，请刷新列表。",
                    400: f"保存被拒绝：{{getattr(exc, 'detail', None) or '请检查确认译法或 Concept ID'}}。",
                    503: "专业词库服务不可用；译文未受影响。",
                }}.get(code, f"保存失败（{{code or type(exc).__name__}}）。")
                return gr.update(value=detail), *_qy060_render_terms(state, selected_filter)
            next_id = None
            try:
                leftover = _qy060_rows_for_filter(get_workbench_term_review(run)["candidates"], selected_filter)
                if leftover:
                    next_id = leftover[min(current_index, len(leftover) - 1)]["id"]
            except Exception:
                next_id = None
            badge, table, choices, context, actual, recommended, next_target = _qy060_render_terms(state, selected_filter, keep_selection=next_id)
            saved = "术语决定已保存，已返回候选列表并定位下一条。"
            if not next_id and selected_filter == "待确认":
                saved = "术语决定已保存。本次待确认术语已全部处理。"
            elif actions[label] in {{"approve", "merge", "do_not_translate"}} and selected_filter == "待确认":
                saved = "术语决定已保存，已返回候选列表并定位下一条。该词已移出待确认列表（切「已处理」可查看）。"
            return gr.update(value=saved), badge, table, choices, context, actual, recommended, next_target

        def _qy060_batch_confirm_exact(state, selected_filter):
            from qyunslation.workbench.gui_client import batch_decide_workbench_terms, get_workbench_term_review
            run = _qy060_current_run(state)
            if not run:
                return gr.update(value="本次没有可确认的专业词汇。"), *_qy060_render_terms(state, selected_filter)
            try:
                review = get_workbench_term_review(run)
                decisions = [
                    {{
                        "candidate_id": row["id"],
                        "action": "approve",
                        "expected_version": row["version"],
                        "target_term": row.get("suggested_target") or row.get("observed_target"),
                    }}
                    for row in review.get("candidates", [])
                    if row.get("status") == "pending"
                    and row.get("risk") not in {{"high", "critical"}}
                    and row.get("match_type") in {{"exact", "alias"}}
                    and (row.get("suggested_target") or row.get("observed_target"))
                ]
                if not decisions:
                    return gr.update(value="没有可批量确认的低风险精确术语。"), *_qy060_render_terms(state, selected_filter)
                result = batch_decide_workbench_terms(run, decisions)
            except Exception:
                return gr.update(value="批量确认失败：请刷新后重试。"), *_qy060_render_terms(state, selected_filter)
            return gr.update(value=f"已确认 {{result.get('count', 0)}} 个精确术语。"), *_qy060_render_terms(state, selected_filter)

        qy060_term_badge.click(_qy050_flip_insp, [qy_insp_on], [qy_insp_on, qy_inspector])
        qy060_term_filter.change(_qy060_render_terms, [state, qy060_term_filter], [qy060_term_badge, qy060_term_table, qy060_candidate_id, qy060_context, qy060_actual, qy060_recommended, qy060_target])
        qy060_candidate_id.change(_qy060_select_term, [state, qy060_candidate_id], [qy060_context, qy060_actual, qy060_recommended, qy060_target, qy060_concept])
        qy060_term_table.select(_qy060_select_table_row, [state, qy060_term_filter], [qy060_candidate_id, qy060_context, qy060_actual, qy060_recommended, qy060_target, qy060_concept])
        qy060_term_table.input(_qy060_table_input, [qy060_term_table, state, qy060_candidate_id, qy060_term_filter], [qy060_target])
        qy060_decide.click(_qy060_decide_term, [state, qy060_candidate_id, qy060_action, qy060_target, qy060_concept, qy060_note, qy060_term_filter, qy060_term_table], [qy060_decision_status, qy060_term_badge, qy060_term_table, qy060_candidate_id, qy060_context, qy060_actual, qy060_recommended, qy060_target])
        qy060_batch_exact.click(_qy060_batch_confirm_exact, [state, qy060_term_filter], [qy060_decision_status, qy060_term_badge, qy060_term_table, qy060_candidate_id, qy060_context, qy060_actual, qy060_recommended, qy060_target])
        {TIMER_MARKER}
        def _qy060_poll_terms(state, selected_filter, candidate_id):
            rendered = _qy060_render_terms(state, selected_filter, keep_selection=candidate_id)
            active = not bool((state or {{}}).get("_qy060_term_done"))
            return (*rendered[:6], gr.update(active=active))

        qy060_term_timer = gr.Timer(value=1.0, active=True)
        qy060_term_timer.tick(
            _qy060_poll_terms,
            [state, qy060_term_filter, qy060_candidate_id],
            [qy060_term_badge, qy060_term_table, qy060_candidate_id, qy060_context, qy060_actual, qy060_recommended, qy060_term_timer],
            show_progress="hidden",
        )
        _qy_translate_evt.then(_qy060_render_terms, [state, qy060_term_filter], [qy060_term_badge, qy060_term_table, qy060_candidate_id, qy060_context, qy060_actual, qy060_recommended, qy060_target])
'''

TIMER_BLOCK = f'''        {TIMER_MARKER}
        def _qy060_poll_terms(state, selected_filter, candidate_id):
            rendered = _qy060_render_terms(state, selected_filter, keep_selection=candidate_id)
            active = not bool((state or {{}}).get("_qy060_term_done"))
            return (*rendered[:6], gr.update(active=active))

        qy060_term_timer = gr.Timer(value=1.0, active=True)
        qy060_term_timer.tick(
            _qy060_poll_terms,
            [state, qy060_term_filter, qy060_candidate_id],
            [qy060_term_badge, qy060_term_table, qy060_candidate_id, qy060_context, qy060_actual, qy060_recommended, qy060_term_timer],
            show_progress="hidden",
        )
'''


def _replace_once(text: str, old: str, new: str, *, marker: str) -> tuple[str, bool]:
    if marker in text:
        return text, False
    if old not in text:
        return text, False
    return text.replace(old, new, 1), True


def apply_css(text: str) -> tuple[str, bool]:
    block = CSS_BLOCK.strip("\n") + "\n"
    css_re = re.compile(
        r"(?:(?<=\n)|^)    /\* _qy_060_term_review_css \*/\n.*?(?=\n    /\* _qy_050_workbench_css \*/)",
        re.S,
    )
    match = css_re.search(text)
    if match:
        updated = text[: match.start()] + block + text[match.end() :]
        return updated, updated != text
    anchor = "    /* _qy_050_workbench_css */\n"
    if anchor not in text:
        return text, False
    return text.replace(anchor, block + anchor, 1), True


def apply_python_hook(text: str) -> tuple[str, bool]:
    if PY_MARKER in text:
        # Gradio only injects special parameters while scanning positional
        # parameters.  An earlier PLAN-060 patch put Request after *ui_args,
        # making the callback silently receive request=None in queue mode.
        if _TRANSLATE_SIGNATURE_LEGACY in text:
            return text.replace(_TRANSLATE_SIGNATURE_LEGACY, _TRANSLATE_SIGNATURE_PATCHED, 1), True
        return text, False
    if _TRANSLATE_SIGNATURE in text:
        text = text.replace(_TRANSLATE_SIGNATURE, _TRANSLATE_SIGNATURE_PATCHED, 1)
    elif _TRANSLATE_SIGNATURE_PATCHED not in text:
        return text, False
    anchor = '    state = ui_inputs["state"]\n'
    if anchor not in text:
        return text, False
    text = text.replace(anchor, anchor + PY_BLOCK, 1)
    task_anchor = "            if _qy_is_office_sidecar_file(file_path):\n"
    if task_anchor not in text:
        return text, False
    text = text.replace(task_anchor, START_BLOCK + task_anchor, 1)
    return text, True


def apply_office_hook(text: str) -> tuple[str, bool]:
    if OFFICE_MARKER in text:
        return text, False
    if _OFFICE_SIGNATURE not in text or _OFFICE_PAYLOAD not in text:
        return text, False
    text = text.replace(_OFFICE_SIGNATURE, _OFFICE_SIGNATURE_PATCHED, 1)
    text = text.replace(_OFFICE_PAYLOAD, _OFFICE_PAYLOAD_PATCHED, 1)
    office_call = '''                        to_lang=ui_inputs.get("lang_to"),
                    )'''
    office_call_new = '''                        to_lang=ui_inputs.get("lang_to"),
                        termbase_policy=(_qy060_current or {}).get("policy"),
                        termbase_version=((_qy060_current or {}).get("policy") or {}).get("termbase_version"),
                    )'''
    if office_call not in text:
        return text, False
    text = text.replace(office_call, office_call_new, 1)
    pdf_anchor = '''                # Create task
                task = asyncio.create_task('''
    pdf_new = '''                if _qy060_current:
                    from qyunslation.workbench.gui_client import apply_pdf_term_policy
                    apply_pdf_term_policy(translate_settings, _qy060_current.get("policy"), output_dir)

                # Create task
                task = asyncio.create_task('''
    if pdf_anchor not in text:
        return text, False
    return text.replace(pdf_anchor, pdf_new, 1), True


def apply_complete_hook(text: str) -> tuple[str, bool]:
    early_anchor = "            # _qy_imgtr_post\n"
    result_anchor = "            result_entry = {\n"
    if early_anchor not in text or result_anchor not in text:
        return text, False

    early_block = f'''            {EARLY_COMPLETE_MARKER}
            try:
                if _qy060_current:
                    from qyunslation.workbench.gui_client import complete_workbench_translation
                    _qy060_term_result = await asyncio.to_thread(
                        complete_workbench_translation,
                        _qy060_current,
                        file_path,
                        _mono or _dual,
                    )
                    state["_qy060_term_summaries"][filename] = _qy060_term_result.get("summary", {{}})
            except Exception:
                state["_qy060_term_note"] = "术语候选提取降级；译文已生成，未自动写入共享词库。"

'''
    final_block = f'''            {COMPLETE_MARKER}
            try:
                if _qy060_current:
                    from qyunslation.workbench.gui_client import complete_workbench_translation
                    _qy060_term_result = await asyncio.to_thread(
                        complete_workbench_translation,
                        _qy060_current,
                        file_path,
                        _mono or _dual,
                    )
                    state["_qy060_term_summaries"][filename] = _qy060_term_result.get("summary", {{}})
            except Exception:
                state["_qy060_term_note"] = "术语候选提取降级；译文已生成，未自动写入共享词库。"
            finally:
                state["_qy060_term_done"] = True

'''

    changed = False
    if EARLY_COMPLETE_MARKER not in text:
        text = text.replace(early_anchor, early_block + early_anchor, 1)
        changed = True

    if COMPLETE_MARKER not in text:
        text = text.replace(result_anchor, final_block + result_anchor, 1)
        changed = True
    else:
        old_except = '''            except Exception:
                state["_qy060_term_note"] = "术语候选提取降级；译文已生成，未自动写入共享词库。"

'''
        new_except = '''            except Exception:
                state["_qy060_term_note"] = "术语候选提取降级；译文已生成，未自动写入共享词库。"
            finally:
                state["_qy060_term_done"] = True

'''
        final_start = text.index(COMPLETE_MARKER)
        before_final = text[:final_start]
        final_part = text[final_start:]
        updated_final = final_part
        if 'state["_qy060_term_done"] = True' not in final_part:
            updated_final = final_part.replace(old_except, new_except, 1)
        if updated_final != final_part:
            text = before_final + updated_final
            changed = True

        early_start = text.index(EARLY_COMPLETE_MARKER)
        early_end = text.index(early_anchor, early_start)
        early_part = text[early_start:early_end]
        early_without_done = early_part.replace(
            '''            finally:
                state["_qy060_term_done"] = True

''',
            "",
            1,
        )
        if early_without_done != early_part:
            text = text[:early_start] + early_without_done + text[early_end:]
            changed = True

    return text, changed


def apply_ui(text: str) -> tuple[str, bool]:
    if UI_MARKER in text:
        pattern = re.compile(
            rf"(?m)^        {re.escape(UI_MARKER)}\n.*?(?=^        qy_help_on = gr\.State\(False\)\n)",
            re.S,
        )
        match = pattern.search(text)
        if not match:
            return text, False
        replacement = UI_BLOCK.rstrip("\n") + "\n"
        updated = text[: match.start()] + replacement + text[match.end() :]
        return updated, updated != text
    anchor = "        qy_help_on = gr.State(False)\n"
    if anchor not in text:
        return text, False
    return text.replace(anchor, UI_BLOCK.rstrip("\n") + "\n" + anchor, 1), True


def apply_events(text: str) -> tuple[str, bool]:
    if EVENT_MARKER in text:
        pattern = re.compile(
            rf"(?m)^        {re.escape(EVENT_MARKER)}\n.*?(?=^        # _qy_office_preview_then\n)",
            re.S,
        )
        match = pattern.search(text)
        if not match:
            return text, False
        replacement = EVENT_BLOCK.rstrip("\n") + "\n"
        updated = text[: match.start()] + replacement + text[match.end() :]
        return updated, updated != text
    anchor = "        # _qy_office_preview_then\n"
    if anchor not in text:
        return text, False
    return text.replace(anchor, EVENT_BLOCK.rstrip("\n") + "\n" + anchor, 1), True


def apply_timer(text: str) -> tuple[str, bool]:
    if TIMER_MARKER in text:
        return text, False
    anchor = "        _qy_translate_evt.then(_qy060_render_terms, [state, qy060_term_filter], [qy060_term_badge, qy060_term_table, qy060_candidate_id, qy060_context])\n"
    if anchor not in text:
        return text, False
    return text.replace(anchor, TIMER_BLOCK + anchor, 1), True


def apply(text: str) -> tuple[str, bool]:
    changed = False
    for fn in (apply_css, apply_python_hook, apply_office_hook, apply_complete_hook, apply_ui, apply_events, apply_timer):
        text, current = fn(text)
        changed = changed or current
    return text, changed


def verify(text: str) -> int:
    required = (
        CSS_MARKER,
        PY_MARKER,
        OFFICE_MARKER,
        COMPLETE_MARKER,
        EARLY_COMPLETE_MARKER,
        UI_MARKER,
        EVENT_MARKER,
        TIMER_MARKER,
        "gr.Request",
    )
    missing = [item for item in required if item not in text]
    if missing:
        print(f"ERROR: PLAN-060 patch missing {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0


def _fixture_gui_source() -> str:
    """Small supported upstream-shape fixture for idempotence regression tests."""
    return '''async def _qy_run_office_sidecar_task(
    file_path: Path,
    output_dir: Path,
    progress,
    task_prefix: str = "",
    to_lang: str = "简体中文",
):
    payload = {"workflow_type": workflow_type, "to_lang": mapped}

async def translate_files(
    file_type,
    file_input,
    link_input,
    *ui_args,
    progress=None,
):
    state = ui_inputs["state"]
            if _qy_is_office_sidecar_file(file_path):
                    _qy_run_office_sidecar_task(
                        file_path,
                        output_dir,
                        progress,
                        task_prefix=task_prefix,
                        to_lang=ui_inputs.get("lang_to"),
                    )
                # Create task
                task = asyncio.create_task(
            result_entry = {
        with qy_inspector:
            pass
        qy_help_on = gr.State(False)
        _qy_translate_evt = translate_btn.click(
            translate_files,
        )
        # _qy_office_preview_then
'''


def main() -> int:
    if not GUI.is_file():
        print(f"ERROR: GUI not found: {GUI}", file=sys.stderr)
        return 1
    original = GUI.read_text(encoding="utf-8")
    updated, changed = apply(original)
    if changed:
        GUI.write_text(updated, encoding="utf-8")
    return verify(updated)


if __name__ == "__main__":
    raise SystemExit(main())
