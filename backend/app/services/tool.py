"""检修工具业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.store import store

MODULE = "tool"
TOOL_ID_FIELD = "工具编号"
REQUIRED_FIELDS = ["工具编号", "工具名称", "规格型号"]
TOOL_FIELDS = ["工具编号", "工具名称", "规格型号", "检定日期", "下次检定日", "存放位置", "领用人", "工具状态"]
STATUS_ORDER = ["合格可用", "待检定", "已过期", "已报废"]
AVAILABLE_STATUS = "合格可用"
PENDING_INSPECTION_STATUS = "待检定"
EXPIRED_STATUS = "已过期"
SCRAPPED_STATUS = "已报废"
ACTION_RULES = {"办理领用": AVAILABLE_STATUS, "送检测试": PENDING_INSPECTION_STATUS, "申请报废": SCRAPPED_STATUS}

CHECKOUT_ACTION = "办理领用"
INSPECTION_ACTION = "送检测试"
SCRAP_ACTION = "申请报废"

CALIBRATION_DATE_FIELD = "检定日期"
NEXT_CALIBRATION_DATE_FIELD = "下次检定日"
SCRAP_DATE_FIELD = "报废日期"
LOCATION_FIELD = "存放位置"
HOLDER_FIELD = "领用人"
LEGACY_HOLDER_FIELD = "领用记录"
TOOL_STATUS_FIELD = "工具状态"

DATE_FIELDS = (CALIBRATION_DATE_FIELD, NEXT_CALIBRATION_DATE_FIELD, SCRAP_DATE_FIELD)
WRITABLE_FIELDS = (
    TOOL_ID_FIELD,
    "工具名称",
    "规格型号",
    CALIBRATION_DATE_FIELD,
    NEXT_CALIBRATION_DATE_FIELD,
    SCRAP_DATE_FIELD,
    LOCATION_FIELD,
    HOLDER_FIELD,
)


def _clean_text(value: Any) -> str:
    """统一清理文本字段，历史记录中的空值也按同一口径展示。"""
    if value is None:
        return ""
    return str(value).strip()


def parse_tool_date(value: Any) -> date | None:
    """解析检修工具相关日期；只接受 ISO 日期，非法日期不参与状态判断。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _clean_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def display_tool_date(value: Any) -> str | None:
    """接口日期统一输出 YYYY-MM-DD；无法解析的历史值原样保留。"""
    parsed = parse_tool_date(value)
    if parsed is not None:
        return parsed.isoformat()
    return _clean_text(value) or None


def display_tool_text(value: Any) -> str | None:
    return _clean_text(value) or None


def _stored_status(row: dict[str, Any]) -> str:
    status = _clean_text(row.get("status"))
    return status if status in STATUS_ORDER else ""


def build_tool_status(row: dict[str, Any], *, today: date | None = None) -> str:
    """根据报废信息、检定周期和流转状态拼装唯一的工具状态。"""
    today = today or date.today()
    stored_status = _stored_status(row)
    scrap_date = parse_tool_date(row.get(SCRAP_DATE_FIELD))

    if stored_status == SCRAPPED_STATUS or (scrap_date is not None and scrap_date <= today):
        return SCRAPPED_STATUS
    if stored_status == PENDING_INSPECTION_STATUS:
        return PENDING_INSPECTION_STATUS

    next_calibration_date = parse_tool_date(row.get(NEXT_CALIBRATION_DATE_FIELD))
    if next_calibration_date is not None:
        if next_calibration_date < today:
            return EXPIRED_STATUS
        if next_calibration_date == today:
            return PENDING_INSPECTION_STATUS
        return AVAILABLE_STATUS

    return stored_status or AVAILABLE_STATUS


def serialize_tool_entry(row: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    """拼装接口返回字段，同时兼容历史“领用记录”写法。"""
    holder = row.get(HOLDER_FIELD)
    if not _clean_text(holder):
        holder = row.get(LEGACY_HOLDER_FIELD)

    return {
        "id": row.get("id"),
        TOOL_ID_FIELD: display_tool_text(row.get(TOOL_ID_FIELD)),
        "工具名称": display_tool_text(row.get("工具名称")),
        "规格型号": display_tool_text(row.get("规格型号")),
        CALIBRATION_DATE_FIELD: display_tool_date(row.get(CALIBRATION_DATE_FIELD)),
        NEXT_CALIBRATION_DATE_FIELD: display_tool_date(row.get(NEXT_CALIBRATION_DATE_FIELD)),
        LOCATION_FIELD: display_tool_text(
            row.get(LOCATION_FIELD) or row.get("存放地点")
        ),
        HOLDER_FIELD: display_tool_text(holder),
        TOOL_STATUS_FIELD: build_tool_status(row, today=today),
    }


class ToolService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        keyword = _clean_text(keyword)
        status = _clean_text(status)
        items = [self.serialize_entry(row) for row in rows]
        if keyword:
            items = [item for item in items if keyword in str(item.get(TOOL_ID_FIELD) or "")]
        if status:
            items = [item for item in items if item.get(TOOL_STATUS_FIELD) == status]
        total = len(items)
        start = max(page - 1, 0) * size
        return items[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return self.serialize_entry(row) if row is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not _clean_text(values.get(field))]
        if missing:
            return None, missing

        rows = store.rows(MODULE)
        tool_code = _clean_text(values.get(TOOL_ID_FIELD))
        duplicate_error = self._duplicate_code_error(tool_code, rows, exclude_id=None)
        if duplicate_error:
            return None, [duplicate_error]

        updates, error = self._normalize_values(values)
        if error:
            return None, [error]

        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        rows.append(entry)
        entry.update({field: updates.get(field, "") for field in WRITABLE_FIELDS})
        self._refresh_status(entry)
        return self.serialize_entry(entry), []

    def checkout(self, entry_id: int, values: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
        return self.run_action(entry_id, CHECKOUT_ACTION, values or {})

    def send_for_inspection(
        self,
        entry_id: int,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        return self.run_action(entry_id, INSPECTION_ACTION, values or {})

    def scrap(self, entry_id: int, values: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
        return self.run_action(entry_id, SCRAP_ACTION, values or {})

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None, f"检修工具 {entry_id} 不存在或已归档"
        action = _clean_text(action)
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于检修工具可执行范围"

        updates, error = self._normalize_values(values or {}, action=action)
        if error:
            return None, error

        current_code = _clean_text(row.get(TOOL_ID_FIELD))
        candidate_code = updates.get(TOOL_ID_FIELD, current_code)
        if not candidate_code:
            return None, "工具编号缺失，不能执行检修工具动作"
        duplicate_error = self._duplicate_code_error(candidate_code, store.rows(MODULE), exclude_id=entry_id)
        if duplicate_error:
            return None, duplicate_error

        row.update(updates)
        row["status"] = ACTION_RULES[action]
        self._refresh_status(row)
        return self.serialize_entry(row), f"检修工具已{action}"

    def serialize_entry(self, row: dict[str, Any]) -> dict[str, Any]:
        return serialize_tool_entry(row)

    def _normalize_values(
        self,
        values: dict[str, Any],
        *,
        action: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        updates: dict[str, Any] = {}

        for field in WRITABLE_FIELDS:
            if field in values:
                if field in DATE_FIELDS:
                    raw_date = values[field]
                    if _clean_text(raw_date):
                        parsed_date = parse_tool_date(raw_date)
                        if parsed_date is None:
                            return {}, f"{field}格式不正确，应使用 YYYY-MM-DD"
                        updates[field] = parsed_date.isoformat()
                    else:
                        updates[field] = ""
                else:
                    updates[field] = _clean_text(values[field])

        today = date.today().isoformat()
        if action == INSPECTION_ACTION and CALIBRATION_DATE_FIELD not in updates:
            updates[CALIBRATION_DATE_FIELD] = today
        if action == SCRAP_ACTION and SCRAP_DATE_FIELD not in updates:
            updates[SCRAP_DATE_FIELD] = today

        return updates, ""

    def _duplicate_code_error(
        self,
        tool_code: str,
        rows: list[dict[str, Any]],
        *,
        exclude_id: int | None,
    ) -> str:
        if not tool_code:
            return "工具编号缺失"
        for row in rows:
            if exclude_id is not None and int(row.get("id", 0)) == exclude_id:
                continue
            if _clean_text(row.get(TOOL_ID_FIELD)) == tool_code:
                return f"工具编号「{tool_code}」重复"
        return ""

    def _refresh_status(self, row: dict[str, Any]) -> None:
        status = build_tool_status(row)
        row["status"] = status
        row[TOOL_STATUS_FIELD] = status
        row["pending"] = status in (AVAILABLE_STATUS, PENDING_INSPECTION_STATUS)
        row["abnormal"] = status == EXPIRED_STATUS
