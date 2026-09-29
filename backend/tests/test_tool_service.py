"""检修工具状态与动作入口的回归测试。"""
from __future__ import annotations

import unittest
from datetime import date

from app.seed import SEED_ROWS
from app.services.tool import (
    HOLDER_FIELD,
    LEGACY_HOLDER_FIELD,
    LOCATION_FIELD,
    SCRAP_DATE_FIELD,
    TOOL_ID_FIELD,
    TOOL_STATUS_FIELD,
    ToolService,
    build_tool_status,
    serialize_tool_entry,
)
from app.store import store


class ToolServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.original_rows = [dict(row) for row in store.rows("tool")]
        store.rows("tool")[:] = [dict(row) for row in SEED_ROWS["tool"]]
        self.service = ToolService()

    def tearDown(self) -> None:
        store.rows("tool")[:] = self.original_rows

    def test_seed_statuses_remain_unchanged_after_refactor(self) -> None:
        expected = ["合格可用", "待检定", "已过期"]

        for entry_id, status in enumerate(expected, start=1):
            with self.subTest(entry_id=entry_id):
                self.assertEqual(self.service.get_entry(entry_id)[TOOL_STATUS_FIELD], status)

    def test_list_and_detail_read_status_from_same_serializer(self) -> None:
        entries, _ = self.service.list_entries()
        listed = {entry["id"]: entry for entry in entries}

        self.assertEqual(
            [entry[TOOL_STATUS_FIELD] for entry in listed.values()],
            [self.service.get_entry(entry_id)[TOOL_STATUS_FIELD] for entry_id in listed],
        )

    def test_three_actions_use_same_status_builder(self) -> None:
        available_row = {
            "id": 10,
            "status": "合格可用",
            TOOL_ID_FIELD: "TOOL-CHECK",
            "下次检定日": "2026-12-31",
            LOCATION_FIELD: "一号柜",
        }
        pending_row = dict(available_row)
        pending_row["status"] = "待检定"
        scrapped_row = dict(available_row)
        scrapped_row["status"] = "已报废"

        self.assertEqual(build_tool_status(available_row, today=date(2026, 9, 29)), "合格可用")
        self.assertEqual(build_tool_status(pending_row, today=date(2026, 9, 29)), "待检定")
        self.assertEqual(build_tool_status(scrapped_row, today=date(2026, 9, 29)), "已报废")

    def test_checkout_inspection_and_scrap_return_identical_field_shape(self) -> None:
        expected_fields = [
            "id",
            TOOL_ID_FIELD,
            "工具名称",
            "规格型号",
            "检定日期",
            "下次检定日",
            LOCATION_FIELD,
            HOLDER_FIELD,
            TOOL_STATUS_FIELD,
        ]
        results = [
            self.service.checkout(1)[0],
            self.service.send_for_inspection(1)[0],
            self.service.scrap(1)[0],
        ]

        self.assertTrue(all(entry is not None for entry in results))
        for entry in results:
            self.assertEqual(list(entry.keys()), expected_fields)
        self.assertEqual(results[0][TOOL_STATUS_FIELD], "合格可用")
        self.assertEqual(results[1][TOOL_STATUS_FIELD], "待检定")
        self.assertEqual(results[2][TOOL_STATUS_FIELD], "已报废")
        self.assertEqual(store.find("tool", 1)[SCRAP_DATE_FIELD], date.today().isoformat())

    def test_missing_and_duplicate_tool_id_follow_one_rule(self) -> None:
        entry, missing = self.service.create_entry({"工具名称": "扳手", "规格型号": "10mm"})
        self.assertIsNone(entry)
        self.assertEqual(missing, [TOOL_ID_FIELD])

        entry, errors = self.service.create_entry({
            TOOL_ID_FIELD: "TOOL-0001",
            "工具名称": "扳手",
            "规格型号": "10mm",
        })
        self.assertIsNone(entry)
        self.assertEqual(errors, ["工具编号「TOOL-0001」重复"])

        entry, message = self.service.checkout(1, {TOOL_ID_FIELD: "TOOL-0002"})
        self.assertIsNone(entry)
        self.assertEqual(message, "工具编号「TOOL-0002」重复")

    def test_legacy_holder_field_remains_but_is_read_through_new_field(self) -> None:
        row = {"id": 11, "status": "合格可用", LEGACY_HOLDER_FIELD: "张三"}
        entry = serialize_tool_entry(row)
        self.assertEqual(entry[HOLDER_FIELD], "张三")
        self.assertEqual(row.get(HOLDER_FIELD), None)
        self.assertEqual(row[LEGACY_HOLDER_FIELD], "张三")


if __name__ == "__main__":
    unittest.main()
