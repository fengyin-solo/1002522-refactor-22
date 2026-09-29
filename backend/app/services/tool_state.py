"""检修工具状态与接口字段的共用拼装规则。

领用、送检、报废以及列表/明细读取都走这里，避免同一把工具在不同入口
被拼出不同的状态、日期或字段。
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any, Mapping

STATUS_AVAILABLE = "合格可用"
STATUS_PENDING = "待检定"
STATUS_EXPIRED = "已过期"
STATUS_SCRAPPED = "已报废"

TOOL_STATUS_ORDER = [
    STATUS_AVAILABLE,
    STATUS_PENDING,
    STATUS_EXPIRED,
    STATUS_SCRAPPED,
]

DEFAULT_VALID_DAYS = 365

VIEW_FIELDS = [
    "id",
    "工具编号",
    "工具名称",
    "规格型号",
    "检定日期",
    "下次检定日",
    "存放位置",
    "领用人",
    "领用记录",
    "报废日期",
    "工具状态",
    "status",
    "pending",
    "abnormal",
]

FIELD_ALIASES = {
    "工具编号": ("工具编号", "编号"),
    "工具名称": ("工具名称", "名称"),
    "规格型号": ("规格型号", "型号"),
    "检定日期": ("检定日期", "校验日期", "校准日期", "检定时间"),
    "下次检定日": ("下次检定日", "下次校验日", "下次校准日", "有效期至", "有效截止日期"),
    "存放位置": ("存放位置", "存放地点", "位置"),
    "领用人": ("领用人", "领用人员", "借用人", "使用人"),
    "报废日期": ("报废日期", "报废时间"),
}

ACTION_STATUS = {
    "办理领用": STATUS_AVAILABLE,
    "送检测试": STATUS_PENDING,
    "申请报废": STATUS_SCRAPPED,
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_date(value: Any) -> date | None:
    """把接口中常见的日期写法解析成 date；无法识别时不猜测。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _clean(value)
    if not text:
        return None

    for parser in (
        lambda: date.fromisoformat(text),
        lambda: datetime.strptime(text, "%Y/%m/%d").date(),
        lambda: datetime.strptime(text, "%Y.%m.%d").date(),
        lambda: datetime.strptime(text, "%Y%m%d").date(),
    ):
        try:
            return parser()
        except ValueError:
            continue
    return None


def format_date(value: Any) -> str:
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else _clean(value)


def add_days(day: date, days: int = DEFAULT_VALID_DAYS) -> date:
    return day + timedelta(days=days)


def first_present(row: Mapping[str, Any], field: str, default: Any = "") -> Any:
    for key in FIELD_ALIASES.get(field, (field,)):
        value = row.get(key)
        if _clean(value):
            return value
    return default


def raw_tool_code(row: Mapping[str, Any]) -> str:
    return _clean(first_present(row, "工具编号", ""))


def tool_code_counts(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    """统计非空工具编号，缺失编号不参与重复判断。"""
    return Counter(raw_tool_code(row) for row in rows if raw_tool_code(row))


def resolve_tool_code(
    row: Mapping[str, Any],
    counts: Mapping[str, int] | None = None,
) -> str:
    """编号缺失或重复时，三个入口使用同一套兜底展示口径。"""
    entry_id = row.get("id", "")
    code = raw_tool_code(row)
    if not code:
        return f"未编号-{entry_id}"
    if counts and counts.get(code, 0) > 1:
        return f"{code}（重复编号：{entry_id}）"
    return code


def _read_due_date(row: Mapping[str, Any]) -> date | None:
    due = parse_date(first_present(row, "下次检定日", ""))
    if due:
        return due
    checked = parse_date(first_present(row, "检定日期", ""))
    if checked:
        return add_days(checked)
    return None


def build_tool_status(row: Mapping[str, Any], today: date | None = None) -> str:
    """计算工具状态。历史行中显式记录的状态优先，保证旧数据逐条兼容。"""
    today = today or date.today()
    # status 是内部状态流转字段；旧的“工具状态”只作为接口展示位，不能参与判定。
    explicit = _clean(row.get("status"))
    if explicit in TOOL_STATUS_ORDER:
        return explicit

    scrapped_on = parse_date(first_present(row, "报废日期", ""))
    if scrapped_on:
        return STATUS_SCRAPPED

    due_on = _read_due_date(row)
    if due_on is None:
        return STATUS_PENDING
    if due_on < today:
        return STATUS_EXPIRED
    return STATUS_AVAILABLE


def _normalize_record(value: Any) -> dict[str, str] | None:
    if isinstance(value, Mapping):
        person = _clean(value.get("领用人") or value.get("使用人")) or "未登记"
        checked_on = format_date(value.get("领用日期") or value.get("领用时间"))
        record = {"领用人": person}
        if checked_on:
            record["领用日期"] = checked_on
        return record

    text = _clean(value)
    if not text:
        return None
    return {"领用人": text}


def usage_records(row: Mapping[str, Any]) -> list[dict[str, str]]:
    """新写法为领用记录列表；旧的领用人字符串保留在原字段中，只在读出时适配。"""
    raw_records = row.get("领用记录", row.get("借用记录", []))
    if isinstance(raw_records, Mapping):
        raw_records = [raw_records]
    elif not isinstance(raw_records, list):
        raw_records = [raw_records] if _clean(raw_records) else []

    records = [
        record
        for item in raw_records
        if (record := _normalize_record(item)) is not None
    ]

    if not records:
        legacy_person = first_present(row, "领用人", "")
        legacy_record = _normalize_record(
            {
                "领用人": legacy_person,
                "领用日期": row.get("领用日期") or row.get("领用时间", ""),
            }
        )
        if legacy_record and legacy_record["领用人"] != "未登记":
            records.append(legacy_record)
    return records


def build_tool_view(
    row: Mapping[str, Any],
    *,
    code_counts: Mapping[str, int] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """拼装所有接口共用的一份工具明细。"""
    today = today or date.today()
    status = build_tool_status(row, today)
    records = usage_records(row)
    current_holder = records[-1]["领用人"] if records else _clean(first_present(row, "领用人", ""))

    view = {field: row.get(field) for field in VIEW_FIELDS}
    view.update(
        {
            "id": row.get("id"),
            "工具编号": resolve_tool_code(row, code_counts),
            "工具名称": _clean(first_present(row, "工具名称", "")),
            "规格型号": _clean(first_present(row, "规格型号", "")),
            "检定日期": format_date(first_present(row, "检定日期", "")),
            "下次检定日": format_date(first_present(row, "下次检定日", "")),
            "存放位置": _clean(first_present(row, "存放位置", "")),
            "领用人": current_holder,
            "领用记录": records,
            "报废日期": format_date(first_present(row, "报废日期", "")),
            "工具状态": status,
            "status": status,
            "pending": bool(row.get("pending", status != STATUS_SCRAPPED)),
            "abnormal": bool(row.get("abnormal", False)),
        }
    )
    return view


def _date_from_values(
    values: Mapping[str, Any],
    field: str,
    *,
    default: date,
) -> date:
    raw = values.get(field)
    return parse_date(raw) or default


def apply_tool_action(
    row: dict[str, Any],
    action: str,
    values: Mapping[str, Any] | None = None,
    *,
    today: date | None = None,
) -> None:
    """按统一口径执行领用、送检、报废，并只在这里维护日期与状态字段。"""
    today = today or date.today()
    values = values or {}
    target = ACTION_STATUS[action]

    if values.get("存放位置") is not None and _clean(values.get("存放位置")):
        row["存放位置"] = _clean(values.get("存放位置"))

    if action == "办理领用":
        person = _clean(
            values.get("领用人")
            or values.get("使用人")
            or first_present(row, "领用人", "")
        ) or "未登记"
        row["领用人"] = person
        records = usage_records(row)
        records.append({"领用人": person, "领用日期": today.isoformat()})
        row["领用记录"] = records

    elif action == "送检测试":
        checked_on = _date_from_values(values, "检定日期", default=today)
        try:
            valid_days = int(values.get("检定周期天") or DEFAULT_VALID_DAYS)
        except (TypeError, ValueError):
            valid_days = DEFAULT_VALID_DAYS
        due_on = parse_date(values.get("下次检定日")) or add_days(checked_on, valid_days)
        row["检定日期"] = checked_on.isoformat()
        row["下次检定日"] = due_on.isoformat()

    elif action == "申请报废":
        scrapped_on = _date_from_values(values, "报废日期", default=today)
        row["报废日期"] = scrapped_on.isoformat()

    row["status"] = target
    row["pending"] = target != STATUS_SCRAPPED
    row["abnormal"] = False
