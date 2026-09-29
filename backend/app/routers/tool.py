"""检修工具接口：维护检修工具，覆盖办理领用、送检测试、申请报废等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.tool import (
    CHECKOUT_ACTION,
    INSPECTION_ACTION,
    REQUIRED_FIELDS,
    SCRAP_ACTION,
    STATUS_ORDER,
    TOOL_FIELDS,
    ToolService,
)

router = APIRouter(prefix="/api/tool", tags=["检修工具"])

service = ToolService()

LIST_FIELDS = TOOL_FIELDS
STATUSES = STATUS_ORDER


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按工具编号检索"),
    status: str | None = Query(default=None, description="合格可用、待检定、已过期、已报废"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按工具编号与状态过滤检修工具列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出检修工具清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "tool", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条检修工具明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"检修工具 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条检修工具，缺字段或编号重复时说明原因而不是静默丢弃。"""
    entry, errors = service.create_entry(payload.values)
    if errors:
        message = "；".join(errors)
        if errors[0] in REQUIRED_FIELDS:
            message = f"缺少必填字段：{message}"
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="检修工具已登记", entry=entry)


@router.post("/{entry_id}/checkout", response_model=ActionResult)
def checkout_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """办理领用：状态、日期与返回字段走检修工具共用拼装。"""
    entry, message = service.checkout(entry_id, payload.values)
    return _action_result(entry, message, CHECKOUT_ACTION)


@router.post("/{entry_id}/inspection", response_model=ActionResult)
def inspect_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """送检测试：状态、日期与返回字段走检修工具共用拼装。"""
    entry, message = service.send_for_inspection(entry_id, payload.values)
    return _action_result(entry, message, INSPECTION_ACTION)


@router.post("/{entry_id}/scrap", response_model=ActionResult)
def scrap_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """申请报废：状态、日期与返回字段走检修工具共用拼装。"""
    entry, message = service.scrap(entry_id, payload.values)
    return _action_result(entry, message, SCRAP_ACTION)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """兼容原统一动作入口，实际仍调用同一份检修工具状态实现。"""
    action = str(payload.values.get("action") or "").strip()
    values = {key: value for key, value in payload.values.items() if key != "action"}
    entry, message = service.run_action(entry_id, action, values)
    return _action_result(entry, message, action)


def _action_result(entry: dict[str, Any] | None, message: str, action: str) -> ActionResult:
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=f"检修工具已{action}" if action else message, entry=entry)
