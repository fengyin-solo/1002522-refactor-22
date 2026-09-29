"""检修工具业务规则：统一调用工具状态与接口字段的拼装实现。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.services.tool_state import (
    ACTION_STATUS,
    TOOL_STATUS_ORDER,
    apply_tool_action,
    build_tool_view,
    raw_tool_code,
    tool_code_counts,
)
from app.store import store

MODULE = "tool"
REQUIRED_FIELDS = ["工具编号", "工具名称", "规格型号"]
STATUS_ORDER = TOOL_STATUS_ORDER
ACTION_RULES = ACTION_STATUS
NEGATIVE_ACTIONS = []

# 登记时允许一并保存的业务字段；接口展示统一由 build_tool_view 处理。
OPTIONAL_FIELDS = ["检定日期", "下次检定日", "存放位置", "领用人", "报废日期"]


class ToolService:
    @staticmethod
    def _today() -> date:
        return date.today()

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        today = self._today()
        counts = tool_code_counts(rows)
        items = [
            build_tool_view(row, code_counts=counts, today=today)
            for row in rows
        ]

        keyword_text = (keyword or "").strip()
        if keyword_text:
            items = [
                item
                for item in items
                if keyword_text in str(item.get("工具编号", ""))
            ]
        if status:
            items = [item for item in items if item.get("工具状态") == status]

        total = len(items)
        start = max(page - 1, 0) * size
        return items[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None
        counts = tool_code_counts(store.rows(MODULE))
        return build_tool_view(row, code_counts=counts, today=self._today())

    def create_entry(
        self,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, list[str]]:
        absent_fields = [
            field
            for field in REQUIRED_FIELDS
            if not str(values.get(field) or "").strip()
        ]
        if absent_fields:
            return None, [f"缺少必填字段：{'、'.join(absent_fields)}"]

        rows = store.rows(MODULE)
        tool_code = str(values.get("工具编号") or "").strip()
        duplicate_ids = [
            row.get("id") for row in rows if raw_tool_code(row) == tool_code
        ]
        if duplicate_ids:
            return None, [f"工具编号「{tool_code}」重复，已被记录 {duplicate_ids[0]} 使用"]

        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: str(values.get(field) or "").strip() for field in REQUIRED_FIELDS})
        for field in OPTIONAL_FIELDS:
            if values.get(field) is not None and str(values.get(field)).strip():
                entry[field] = str(values.get(field)).strip()

        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        view = build_tool_view(
            entry,
            code_counts=tool_code_counts(rows),
            today=self._today(),
        )
        return view, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检修工具 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于检修工具可执行范围"

        counts = tool_code_counts(store.rows(MODULE))
        today = self._today()
        apply_tool_action(entry, action, values, today=today)
        return build_tool_view(entry, code_counts=counts, today=today), f"检修工具已{action}"
