import base64
import io
import zipfile
import xml.etree.ElementTree as ET
from datetime import date

from odoo.tests import TransactionCase, tagged

from .production_receipt_helpers import configure_report_receipts, make_report_receipt


@tagged("post_install", "-at_install")
class TestProductionTotalReceipt(TransactionCase):
    production_date = date(2020, 2, 15)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].set_param("ir_attachment.location", "db")
        cls.company = cls.env["res.company"].create({"name": "Production Receipt Report QA"})
        cls.env = cls.env(context={**cls.env.context, "allowed_company_ids": [cls.company.id], "lang": "en_US"})
        cls.estate = cls.env["wt.estate"].create({"name": "Receipt QA", "code": "RPTQ", "company_id": cls.company.id})
        cls.division = cls.env["wt.division"].create({"name": "Receipt QA", "code": "RPTQ", "estate_id": cls.estate.id})
        cls.setup = configure_report_receipts(cls.env, cls.company, cls.estate, cls.division)
        cls.foreman, cls.tapper = cls.env["hr.employee"].create([
            {"name": name, "company_id": cls.company.id} for name in ("Receipt Foreman", "Receipt Tapper")
        ])

    def _weighing(self, net=85, **extra):
        state = extra.pop("state", None)
        weighing = self.env["wt.weighing"].create({
            "company_id": self.company.id, "estate_id": self.estate.id, "division_id": self.division.id,
            "production_date": self.production_date, "weighing_date": "2020-02-15 08:00:00",
            "foreman_employee_id": self.foreman.id, "tapper_employee_id": self.tapper.id,
            "production_weight": net + 15, "reject_weight": 15, "net_weight": net, **extra,
        })
        if state:
            weighing.with_context(allow_production_receipt_update=True).write({"state": state})
        return weighing

    def _wizards(self):
        values = {"company_id": self.company.id, "division_id": self.division.id,
                  "date_start": self.production_date, "date_end": self.production_date}
        return [self.env["wt.tapper.production.total.report.wizard"].new(values), *[
            self.env["wt.production.summary.report.wizard"].new({**values, "report_level": level})
            for level in ("division", "foreman")
        ]]

    def _assert_total(self, expected):
        for wizard in self._wizards():
            with self.subTest(model=wizard._name, level=getattr(wizard, "report_level", "tapper")):
                data = wizard._prepare_report_data()
                self.assertEqual(data["total_production"], expected)
                self.assertEqual(data["date_totals"][self.production_date.isoformat()], expected)

    def test_only_validated_receipts_with_done_inventory_are_counted(self):
        make_report_receipt(self.env, self._weighing(), self.setup)
        self._weighing(999)
        for state in ("draft", "processed", "cancelled"):
            make_report_receipt(self.env, self._weighing(100), self.setup, state=state)
        make_report_receipt(self.env, self._weighing(200), self.setup, done=False)
        self._weighing(300, state="receipt_validated")
        self._assert_total(85)

    def test_pending_inventory_enters_report_when_done(self):
        _receipt, picking = make_report_receipt(self.env, self._weighing(), self.setup, done=False)
        self._assert_total(0)
        picking.move_ids._action_done()
        self._assert_total(85)

    def test_cancelled_receipt_is_removed_and_new_receipt_is_counted_once(self):
        weighing = self._weighing()
        receipt, _picking = make_report_receipt(self.env, weighing, self.setup)
        self._assert_total(85)
        receipt.action_confirm_cancel("Receipt report regression")
        self.assertEqual(weighing.state, "receipt_cancelled")
        self._assert_total(0)
        make_report_receipt(self.env, weighing, self.setup)
        self.assertEqual(self.env["wt.production.receipt.line"].search_count([("weighing_id", "=", weighing.id)]), 2)
        self._assert_total(85)

    def test_each_weighing_uses_its_own_picking_in_multi_picking_receipt(self):
        receipt, _done = make_report_receipt(self.env, self._weighing(85), self.setup)
        _receipt, pending = make_report_receipt(self.env, self._weighing(15), self.setup, receipt=receipt, done=False)
        self._assert_total(85)
        pending.move_ids._action_done()
        self._assert_total(100)

    def test_production_date_filter_is_preserved(self):
        receipt, _picking = make_report_receipt(self.env, self._weighing(), self.setup)
        receipt.with_context(allow_production_receipt_update=True).write({"received_date": date(2020, 2, 16)})
        self._assert_total(85)
        for wizard in self._wizards():
            wizard.date_start = wizard.date_end = date(2020, 2, 16)
            self.assertEqual(wizard._prepare_report_data()["total_production"], 0)

    def test_preview_pdf_document_and_excel_share_filtered_totals(self):
        make_report_receipt(self.env, self._weighing(), self.setup)
        self._weighing(999)
        for wizard in self._wizards():
            is_tapper = wizard._name == "wt.tapper.production.total.report.wizard"
            report_model = "wt.tapper.production.total.report" if is_tapper else "wt.production.summary.report"
            values = {} if is_tapper else {"report_level": wizard.report_level}
            report = self.env[report_model].create(values)
            wizard.report_id = report
            wizard.action_apply_filter()
            self.assertEqual(report.total_production, 85)
            self.assertEqual(sum(report.line_ids.mapped("total_production")), 85)
            self.assertIn("85.00", str(report.preview_html))
            pdf_model = "report.weightrack.report_tapper_production_total_document" if is_tapper else "report.weightrack.report_production_summary_document"
            self.assertEqual(self.env[pdf_model]._get_report_values(report.ids)["docs"].total_production, 85)
            action = report.action_export_excel()
            attachment_id = int(action["url"].split("/web/content/")[1].split("?")[0])
            raw = base64.b64decode(self.env["ir.attachment"].browse(attachment_id).datas)
            with zipfile.ZipFile(io.BytesIO(raw)) as workbook:
                sheet = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            numeric_values = [
                float(cell.find("s:v", ns).text) for cell in sheet.findall(".//s:c", ns)
                if cell.get("t") not in ("s", "inlineStr") and cell.find("s:v", ns) is not None
            ]
            self.assertIn(85, numeric_values)
            self.assertNotIn(999, numeric_values)
