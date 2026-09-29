import unittest
from copy import deepcopy
from datetime import date

from app.seed import SEED_ROWS
from app.services import tool as tool_service_module
from app.services.tool import ToolService
from app.services.tool_state import (
    STATUS_AVAILABLE,
    STATUS_EXPIRED,
    STATUS_PENDING,
    STATUS_SCRAPPED,
    build_tool_status,
    build_tool_view,
)
from app.store import Store


class ToolServiceTest(unittest.TestCase):
    def setUp(self):
        tool_service_module.store = Store()
        self.service = ToolService()
        self.service._today = staticmethod(lambda: date(2026, 9, 29))

    def test_seed_status_matches_before_and_after_refactor(self):
        items, total = self.service.list_entries()
        self.assertEqual(total, 3)
        self.assertEqual(
            [(item["id"], item["工具状态"]) for item in items],
            [(1, STATUS_AVAILABLE), (2, STATUS_PENDING), (3, STATUS_EXPIRED)],
        )
        pending_items, pending_total = self.service.list_entries(status=STATUS_PENDING)
        self.assertEqual(pending_total, 1)
        self.assertEqual(pending_items[0]["id"], 2)

        expected_fields = [
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
        self.assertEqual(list(pending_items[0].keys()), expected_fields)

    def test_statuses_are_built_from_one_date_rule(self):
        available = build_tool_status(
            {"检定日期": "2026-08-01", "下次检定日": "2027-08-01"},
            today=date(2026, 9, 29),
        )
        expired = build_tool_status(
            {"检定日期": "2025-08-01", "下次检定日": "2026-08-01"},
            today=date(2026, 9, 29),
        )
        self.assertEqual(available, STATUS_AVAILABLE)
        self.assertEqual(expired, STATUS_EXPIRED)

    def test_three_actions_return_same_view_as_list_and_detail(self):
        actions_and_status = [
            ("办理领用", STATUS_AVAILABLE),
            ("送检测试", STATUS_PENDING),
            ("申请报废", STATUS_SCRAPPED),
        ]
        for entry_id, (action, status) in enumerate(actions_and_status, start=1):
            action_entry, _ = self.service.run_action(entry_id, action)
            detail = self.service.get_entry(entry_id)
            list_items, _ = self.service.list_entries(size=100)
            list_entry = next(item for item in list_items if item["id"] == entry_id)

            self.assertEqual(action_entry["工具状态"], status)
            self.assertEqual(action_entry, detail)
            self.assertEqual(detail, list_entry)

    def test_action_dates_can_be_supplied_and_remain_consistent_in_views(self):
        action_entry, _ = self.service.run_action(
            3,
            "送检测试",
            {"检定日期": "2026-08-01", "下次检定日": "2027-08-01"},
        )
        self.assertEqual(action_entry["检定日期"], "2026-08-01")
        self.assertEqual(action_entry["下次检定日"], "2027-08-01")

        action_entry, _ = self.service.run_action(
            3,
            "申请报废",
            {"报废日期": "2026-09-20"},
        )
        self.assertEqual(action_entry["报废日期"], "2026-09-20")
        self.assertEqual(self.service.get_entry(3)["报废日期"], "2026-09-20")

    def test_send_inspection_and_scrap_use_one_date_rule(self):
        action_entry, _ = self.service.run_action(2, "送检测试")
        self.assertEqual(action_entry["检定日期"], "2026-09-29")
        self.assertEqual(action_entry["下次检定日"], "2027-09-29")

        action_entry, _ = self.service.run_action(2, "申请报废")
        self.assertEqual(action_entry["报废日期"], "2026-09-29")
        self.assertEqual(action_entry["工具状态"], STATUS_SCRAPPED)

    def test_missing_and_duplicate_codes_use_same_view_rule(self):
        rows = tool_service_module.store.rows("tool")
        duplicate = deepcopy(SEED_ROWS["tool"][0])
        duplicate["id"] = 4
        rows.append(duplicate)
        rows.append({"id": 5, "status": STATUS_AVAILABLE, "工具名称": "缺失编号", "规格型号": "T"})

        items, total = self.service.list_entries(size=100)
        self.assertEqual(total, 5)
        self.assertEqual(items[0]["工具编号"], "TOOL-0001（重复编号：1）")
        self.assertEqual(items[3]["工具编号"], "TOOL-0001（重复编号：4）")
        self.assertEqual(items[4]["工具编号"], "未编号-5")
        self.assertEqual(self.service.get_entry(4)["工具编号"], items[3]["工具编号"])
        self.assertEqual(self.service.get_entry(5)["工具编号"], items[4]["工具编号"])

        duplicate_entry, _ = self.service.run_action(4, "办理领用")
        missing_entry, _ = self.service.run_action(5, "办理领用")
        self.assertEqual(duplicate_entry["工具编号"], "TOOL-0001（重复编号：4）")
        self.assertEqual(missing_entry["工具编号"], "未编号-5")

    def test_duplicate_code_is_rejected_when_creating(self):
        entry, errors = self.service.create_entry(
            {"工具编号": "TOOL-0001", "工具名称": "新工具", "规格型号": "T"}
        )
        self.assertIsNone(entry)
        self.assertEqual(errors, ["工具编号「TOOL-0001」重复，已被记录 1 使用"])

    def test_missing_required_fields_are_reported_together(self):
        entry, errors = self.service.create_entry({"工具名称": "新工具"})
        self.assertIsNone(entry)
        self.assertEqual(errors, ["缺少必填字段：工具编号、规格型号"])

    def test_legacy_holder_is_read_as_usage_record_without_mutating_seed(self):
        before = deepcopy(tool_service_module.store.rows("tool")[1])
        view = build_tool_view(tool_service_module.store.rows("tool")[1])
        self.assertEqual(view["领用人"], "检修工具样例2")
        self.assertEqual(view["领用记录"], [{"领用人": "检修工具样例2"}])
        self.assertEqual(tool_service_module.store.rows("tool")[1], before)

        action_entry, _ = self.service.run_action(2, "办理领用", {"领用人": "张工"})
        self.assertEqual(action_entry["领用人"], "张工")
        self.assertIn({"领用人": "张工", "领用日期": "2026-09-29"}, action_entry["领用记录"])


if __name__ == "__main__":
    unittest.main()
