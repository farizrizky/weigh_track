import base64
import io
import zipfile
from datetime import date, datetime
from xml.etree import ElementTree as ET

from odoo.tests import tagged

from .test_daily_stock_report import DailyStockReportCase


@tagged("post_install", "-at_install")
class TestStockShrinkageReports(DailyStockReportCase):
    def _wizards(self, start=date(2020, 2, 1), end=date(2020, 2, 4), include_shipping=False, **filters):
        models = ("wt.storage.shrinkage.report.wizard", "wt.stock.out.report.wizard")
        if include_shipping:
            models += ("wt.shipping.report.wizard",)
        return [self.env[model].new({
            "company_id": self.company.id, "start_date": start, "end_date": end, **filters,
        }) for model in models]

    def _loss_total(self, wizard):
        data = wizard._prepare_report_data()
        key = "total_shrinkage_qty" if wizard._name.startswith("wt.storage") else "total_storage_shrinkage_qty"
        return data[key], data

    def _assert_loss(self, amount, **filters):
        for wizard in self._wizards(**filters):
            with self.subTest(report=wizard._name, filters=filters):
                total, data = self._loss_total(wizard)
                self.assertAlmostEqual(total, amount)
                self.assertAlmostEqual(sum(row["quantity"] for row in data["detail_vals"]), data.get("total_quantity", total))

    def _assert_daily_closing(self, day, start=date(2020, 2, 1)):
        expected = self._report(day)["analysis_values"]["closing_stock"]
        for wizard in self._wizards(start=start, end=date(2020, 2, day), include_shipping=True):
            data = wizard._prepare_report_data()
            self.assertAlmostEqual(data["total_balance_qty"], expected.get("total", 0))
            for division in self.divisions:
                balance = sum(row["balance_qty"] for row in data["summary_vals"]
                              if row["division_id"] == division.id)
                self.assertAlmostEqual(balance, expected.get("division:%s" % division.id, 0))

    def test_pending_transit_is_included_in_closing_stock(self):
        self._transit()
        self._assert_daily_closing(1)
        for wizard in self._wizards(end=date(2020, 2, 1), include_shipping=True):
            data = wizard._prepare_report_data()
            self.assertEqual(data["total_opening_qty"], 1000)
            self.assertEqual(data["total_balance_qty"], 1000)
            self.assertEqual(data.get("total_shipping_qty", 0), 0)

    def test_next_month_opening_retains_transit_stock(self):
        self._transit()
        for wizard in self._wizards(start=date(2020, 3, 1), end=date(2020, 3, 1), include_shipping=True):
            data = wizard._prepare_report_data()
            self.assertEqual(data["total_opening_qty"], 1000)
            self.assertEqual(data["total_balance_qty"], 1000)
            self.assertEqual(data["total_stock_in_qty"], 0)

    def test_closing_uses_manual_loss_and_partial_shipping_shares(self):
        lot = self._transit()
        self._manual_loss(lot, (95, 5))
        self._assert_daily_closing(2)
        self._move(450, lot, self.transit_location, self.customer, 3)
        self._assert_daily_closing(3)

    def test_closing_restores_partial_transit_loss_reversal(self):
        lot = self._transit()
        delivery, original = self._manual_loss(lot, (95, 5))
        reverse = self._move(40, lot, self.loss, self.transit_location, 3)
        reverse.write({"wt_delivery_id": delivery.id, "origin_returned_move_id": original.id})
        self._assert_daily_closing(3)

    def test_warehouse_closing_follows_physical_transit_location(self):
        lot = self._transit()
        other = self.env["stock.warehouse"].create({
            "name": "Transit Balance QA", "code": "DSTB", "company_id": self.company.id,
        })
        other_transit = self.env["stock.location"].create({
            "name": "Other Transit QA", "usage": "transit", "company_id": self.company.id,
            "location_id": other.view_location_id.id,
        })
        self._move(300, lot, self.transit_location, other_transit, 2)
        self._assert_daily_closing(2)
        for warehouse, expected in ((self.warehouse, 700), (other, 300)):
            for wizard in self._wizards(end=date(2020, 2, 2), warehouse_id=warehouse.id, include_shipping=True):
                data = wizard._prepare_report_data()
                self.assertEqual(data["total_balance_qty"], expected)

    def test_unassigned_loss_does_not_remove_transit_closing(self):
        lot = self._transit()
        self._manual_loss(lot, (95, 5), saved=False)
        self._assert_daily_closing(2)
        for wizard in self._wizards(end=date(2020, 2, 2), include_shipping=True):
            self.assertEqual(wizard._prepare_report_data()["total_balance_qty"], 900)

    def test_shipping_partial_transit_uses_actual_quantity_and_manual_shares(self):
        lot = self._transit()
        delivery, _move = self._manual_loss(lot, (95, 5))
        delivery.state = "done"
        picking = self.env["stock.picking"].create({
            "company_id": self.company.id, "picking_type_id": self.warehouse.out_type_id.id,
            "location_id": self.transit_location.id, "location_dest_id": self.customer.id,
            "wt_delivery_id": delivery.id,
        })
        self._move(450, lot, self.transit_location, self.customer, 3, picking)
        wizard = self._wizards(end=date(2020, 2, 3), include_shipping=True)[-1]
        partial = wizard._prepare_report_data()
        self.assertEqual(partial["total_quantity"], 450)
        self.assertEqual(partial["total_balance_qty"], 450)
        by_division = {row["division_id"]: row for row in partial["summary_vals"]}
        self.assertEqual(by_division[self.divisions[0].id]["quantity"], 252.5)
        self.assertEqual(by_division[self.divisions[1].id]["quantity"], 197.5)
        self._move(450, lot, self.transit_location, self.customer, 4, picking)
        final = self._wizards(include_shipping=True)[-1]._prepare_report_data()
        self.assertEqual(final["total_quantity"], 900)
        self.assertEqual(final["total_balance_qty"], 0)

    def test_shipping_pdf_data_and_excel_include_transit_balance(self):
        self._transit()
        report = self.env["wt.shipping.report"].create({})
        wizard = self.env["wt.shipping.report.wizard"].create({
            "report_id": report.id, "company_id": self.company.id,
            "start_date": date(2020, 2, 1), "end_date": date(2020, 2, 1),
        })
        wizard.action_apply_filter()
        self.assertEqual(report.total_balance_qty, 1000)
        self.assertEqual(sum(report.detail_line_ids.mapped("balance_qty")), 1000)
        docs = self.env["report.weightrack.report_shipping_document"]._get_report_values(report.ids)["docs"]
        self.assertEqual(docs.total_balance_qty, 1000)
        html, _type = self.env["ir.actions.report"]._render_qweb_html("weightrack.report_shipping_document", report.ids)
        self.assertIn(b"1000.00", html)
        action = report.action_export_excel()
        attachment = self.env["ir.attachment"].browse(int(action["url"].split("/web/content/")[1].split("?")[0]))
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(attachment.datas))) as workbook:
            sheet = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        cell = sheet.find(".//s:c[@r='H%s']/s:v" % (11 + len(report.summary_line_ids)), ns)
        self.assertEqual(float(cell.text), 1000)

    def test_production_loss_and_partial_reversal_are_net(self):
        lot = self.lots[0]
        self._move(1000, lot, self.supply, self.warehouse.lot_stock_id, 0)
        self._move(100, lot, self.warehouse.lot_stock_id, self.loss, 2)
        self._move(40, lot, self.loss, self.warehouse.lot_stock_id, 3)
        self._assert_loss(60)
        for wizard in self._wizards():
            total, data = self._loss_total(wizard)
            self.assertEqual(data["total_opening_qty"], 1000)
            self.assertEqual(data["total_balance_qty"], 940)
            self.assertEqual(data["total_stock_qty"] - total, data["total_balance_qty"])

    def test_reversal_in_next_month_is_negative_in_that_month(self):
        lot = self.lots[0]
        self._move(1000, lot, self.supply, self.warehouse.lot_stock_id, 0)
        self._move(100, lot, self.warehouse.lot_stock_id, self.loss, 2)
        reverse = self._move(40, lot, self.loss, self.warehouse.lot_stock_id, 3)
        reverse.date = datetime(2020, 3, 1, 12)
        self._assert_loss(100)
        self._assert_loss(-40, start=date(2020, 3, 1), end=date(2020, 3, 1))

    def test_transit_loss_uses_move_date_instead_of_do_date(self):
        lot = self._transit()
        delivery, _move = self._manual_loss(lot, (95, 5))
        self.assertNotEqual(delivery.date, date(2020, 2, 2))
        self._assert_loss(100, start=date(2020, 2, 2), end=date(2020, 2, 2))
        self._assert_loss(0, start=delivery.date, end=delivery.date)
        self._assert_loss(95, division_id=self.divisions[0].id)
        self._assert_loss(5, division_id=self.divisions[1].id)

    def test_unsaved_and_edited_proportions_keep_actual_total(self):
        lot = self._transit()
        delivery, _move = self._manual_loss(lot, (95, 5), saved=False)
        self._assert_loss(100)
        self._assert_loss(0, division_id=self.divisions[0].id)
        for wizard in self._wizards():
            _total, data = self._loss_total(wizard)
            pending = [row for row in data["summary_vals"] if not row["division_id"]]
            self.assertEqual(pending[0]["division_name"], "Transit belum diproporsikan")
        delivery.action_save_transit_proportion()
        self._assert_loss(95, division_id=self.divisions[0].id)
        prop = delivery.transit_shrinkage_proportion_ids.filtered(lambda p: p.lot_id == self.lots[0])
        prop.proportion_qty = 90
        self.assertFalse(delivery.transit_shrinkage_proportion_saved)
        self._assert_loss(100)
        self._assert_loss(0, division_id=self.divisions[0].id)

    def test_invalid_saved_proportion_is_not_normalized(self):
        lot = self._transit()
        delivery, _move = self._manual_loss(lot, (95, 5))
        delivery.transit_shrinkage_proportion_ids[0].proportion_qty = 1
        delivery.transit_shrinkage_proportion_saved = True
        self._assert_loss(100)
        self._assert_loss(0, division_id=self.divisions[0].id)

    def test_transit_return_restores_original_manual_shares_without_do_link(self):
        lot = self._transit()
        _delivery, original = self._manual_loss(lot, (95, 5))
        reverse = self._move(40, lot, self.loss, self.transit_location, 3)
        reverse.origin_returned_move_id = original
        self._assert_loss(60)
        self._assert_loss(57, division_id=self.divisions[0].id)
        self._assert_loss(3, division_id=self.divisions[1].id)
        self._assert_loss(-40, start=date(2020, 2, 3), end=date(2020, 2, 3))

    def test_split_transit_shipping_does_not_add_loss_twice(self):
        lot = self._transit()
        delivery, _move = self._manual_loss(lot, (95, 5))
        delivery.state = "done"
        picking = self.env["stock.picking"].create({
            "company_id": self.company.id, "picking_type_id": self.warehouse.out_type_id.id,
            "location_id": self.transit_location.id, "location_dest_id": self.customer.id,
            "wt_delivery_id": delivery.id,
        })
        self._move(450, lot, self.transit_location, self.customer, 3, picking)
        self._move(450, lot, self.transit_location, self.customer, 4, picking)
        wizard = self._wizards()[1]
        data = wizard._prepare_report_data()
        self.assertEqual(data["total_shipping_qty"], 900)
        self.assertEqual(data["total_storage_shrinkage_qty"], 100)
        self.assertEqual(data["total_quantity"], 1000)
        by_division = {row["division_id"]: row for row in data["summary_vals"]}
        self.assertEqual(by_division[self.divisions[0].id]["shipping_qty"], 505)
        self.assertEqual(by_division[self.divisions[1].id]["shipping_qty"], 395)

    def test_transit_merge_is_not_loss(self):
        self._transit()
        self._assert_loss(0)

    def test_excluded_rollback_pair_remains_excluded(self):
        lot = self._transit()
        _delivery, loss = self._manual_loss(lot, (95, 5))
        reverse = self._move(100, lot, self.loss, self.transit_location, 3)
        (loss | reverse).write({"wt_exclude_from_weightrack_reports": True})
        self._assert_loss(0)

    def test_warehouse_filter_retains_actual_transit_loss(self):
        lot = self._transit()
        self._manual_loss(lot, (95, 5))
        self._assert_loss(100, warehouse_id=self.warehouse.id)
        other = self.env["stock.warehouse"].create({"name": "Other QA", "code": "DSOQ", "company_id": self.company.id})
        self._assert_loss(0, warehouse_id=other.id)

    def test_report_pdf_data_and_excel_keep_pending_loss(self):
        lot = self._transit()
        self._manual_loss(lot, (95, 5), saved=False)
        for model, template, total_field in (
            ("wt.storage.shrinkage.report", "storage_shrinkage", "total_shrinkage_qty"),
            ("wt.stock.out.report", "stock_out", "total_storage_shrinkage_qty"),
        ):
            report = self.env[model].create({})
            wizard = self.env[model + ".wizard"].create({
                "report_id": report.id, "company_id": self.company.id,
                "start_date": date(2020, 2, 1), "end_date": date(2020, 2, 4),
            })
            wizard.action_apply_filter()
            self.assertEqual(report[total_field], 100)
            docs = self.env["report.weightrack.report_%s_document" % template]._get_report_values(report.ids)["docs"]
            self.assertEqual(docs[total_field], 100)
            html, _type = self.env["ir.actions.report"]._render_qweb_html("weightrack.report_%s_document" % template, report.ids)
            self.assertIn(b"Transit belum diproporsikan", html)
            action = report.action_export_excel()
            attachment = self.env["ir.attachment"].browse(int(action["url"].split("/web/content/")[1].split("?")[0]))
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(attachment.datas))) as workbook:
                strings = workbook.read("xl/sharedStrings.xml")
                sheet = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
            self.assertIn(b"Transit belum diproporsikan", strings)
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            numbers = [float(c.find("s:v", ns).text) for c in sheet.findall(".//s:c", ns)
                       if c.get("t") not in ("s", "inlineStr") and c.find("s:v", ns) is not None]
            self.assertIn(100, numbers)
