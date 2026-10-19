import base64
import io
import zipfile
from datetime import date
from xml.etree import ElementTree as ET

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRejectSlabGrouping(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].set_param("ir_attachment.location", "db")
        cls.company = cls.env["res.company"].create({"name": "Reject Slab Identity QA"})
        cls.env = cls.env(context={**cls.env.context, "allowed_company_ids": [cls.company.id], "lang": "en_US"})
        cls.estate = cls.env["wt.estate"].create({"name": "Reject QA", "code": "RSL", "company_id": cls.company.id})
        cls.division = cls.env["wt.division"].create({"name": "Reject QA", "code": "RSL", "estate_id": cls.estate.id})
        job = cls.env["hr.job"].create({"name": "Reject QA", "company_id": cls.company.id})
        cls.env["wt.employee.role"].create([
            {"company_id": cls.company.id, "role": role, "job_id": job.id}
            for role in ("tapper", "foreman")
        ])
        employees = cls.env["hr.employee"].create([
            {"name": name, "company_id": cls.company.id, "job_id": job.id}
            for name in ("Same Tapper", "Same Tapper", "Same Foreman", "Same Foreman")
        ])
        cls.tapper_employees = employees[:2]
        cls.foremen = cls.env["wt.foreman"].create([
            {"employee_id": employee.id, "division_id": cls.division.id}
            for employee in employees[2:]
        ])
        cls.tappers = cls.env["wt.tapper"].create([
            {"employee_id": employee.id, "division_id": cls.division.id, "foreman_id": cls.foremen[0].id}
            for employee in cls.tapper_employees
        ])

    def _weighing(self, employee, reject=3, slab=5, foreman=None, production_date=date(2020, 2, 15), received=True):
        foreman = foreman or self.foremen[0]
        record = self.env["wt.weighing"].create({
            "company_id": self.company.id, "estate_id": self.estate.id, "division_id": self.division.id,
            "production_date": production_date, "weighing_date": "%s 08:00:00" % production_date,
            "tapper_employee_id": employee.id, "foreman_employee_id": foreman.employee_id.id,
            "production_weight": 100 + reject + slab, "reject_weight": reject, "slab_weight": slab,
            "net_weight": 100,
        })
        if received:
            record.with_context(allow_production_receipt_update=True).write({"state": "receipt_validated"})
        return record

    def _wizard(self, **extra):
        return self.env["wt.weighing.reject.slab.report.wizard"].new({
            "company_id": self.company.id, "estate_id": self.estate.id,
            "start_date": date(2020, 2, 15), "end_date": date(2020, 2, 15), **extra,
        })

    def _same_name_weighings(self):
        self._weighing(self.tapper_employees[0], 3, 5)
        self._weighing(self.tapper_employees[1], 7, 11)

    def test_same_name_different_tapper_ids_remain_separate(self):
        self._same_name_weighings()
        data = self._wizard()._prepare_report_data()
        self.assertEqual(len(data["rows"]), 2)
        self.assertEqual([(r["total_reject"], r["total_slab"]) for r in data["rows"]], [(3, 5), (7, 11)])
        self.assertEqual(data["total_reject_weight"], 10)
        self.assertEqual(data["total_slab_weight"], 16)

    def test_repeated_weighings_of_same_tapper_are_combined(self):
        self._weighing(self.tapper_employees[0], 3, 5)
        self._weighing(self.tapper_employees[0], 7, 11)
        data = self._wizard()._prepare_report_data()
        self.assertEqual(len(data["rows"]), 1)
        self.assertEqual(data["rows"][0]["total_reject"], 10)
        self.assertEqual(data["rows"][0]["total_slab"], 16)

    def test_same_tapper_preserves_historical_foreman_ids(self):
        self._weighing(self.tapper_employees[0], 3, 5)
        self.tappers[0].foreman_id = self.foremen[1]
        self._weighing(self.tapper_employees[0], 7, 11, foreman=self.foremen[1])
        data = self._wizard()._prepare_report_data()
        self.assertEqual(len(data["rows"]), 2)
        self.assertEqual(sorted(r["total_reject"] for r in data["rows"]), [3, 7])

    def test_missing_tapper_assignment_falls_back_to_employee_id(self):
        employees = self.env["hr.employee"].create([
            {"name": "Legacy Tapper", "company_id": self.company.id} for _index in range(2)
        ])
        first = self._weighing(employees[0], 3, 5)
        self._weighing(employees[0], 2, 4)
        second = self._weighing(employees[1], 7, 11)
        self.assertFalse(first.tapper_id or second.tapper_id)
        data = self._wizard()._prepare_report_data()
        self.assertEqual(len(data["rows"]), 2)
        self.assertEqual(sorted((r["total_reject"], r["total_slab"]) for r in data["rows"]), [(5, 9), (7, 11)])

    def test_archived_tapper_still_uses_recorded_id(self):
        self._same_name_weighings()
        self.tappers[0].active = False
        self.assertEqual(len(self._wizard()._prepare_report_data()["rows"]), 2)

    def test_tapper_filter_selects_id_despite_same_name(self):
        self._same_name_weighings()
        data = self._wizard(tapper_id=self.tappers[1].id)._prepare_report_data()
        self.assertEqual(len(data["rows"]), 1)
        self.assertEqual(data["total_reject_weight"], 7)
        self.assertEqual(data["total_slab_weight"], 11)

    def test_date_and_receipt_status_filters_are_preserved(self):
        self._weighing(self.tapper_employees[0], 3, 5)
        self._weighing(self.tapper_employees[0], 999, 999, received=False)
        self._weighing(self.tapper_employees[0], 888, 888, production_date=date(2020, 2, 16))
        data = self._wizard()._prepare_report_data()
        self.assertEqual(data["total_reject_weight"], 3)
        self.assertEqual(data["total_slab_weight"], 5)

    def test_report_pdf_and_excel_preserve_separate_rows(self):
        self._same_name_weighings()
        report = self.env["wt.weighing.reject.slab.report"].create({})
        wizard = self.env["wt.weighing.reject.slab.report.wizard"].create({
            "report_id": report.id, "company_id": self.company.id, "estate_id": self.estate.id,
            "start_date": date(2020, 2, 15), "end_date": date(2020, 2, 15),
        })
        wizard.action_apply_filter()
        self.assertEqual(len(report.line_ids), 2)
        docs = self.env["report.weightrack.report_weighing_reject_slab_doc"]._get_report_values(report.ids)["docs"]
        self.assertEqual(len(docs.line_ids), 2)
        html, _type = self.env["ir.actions.report"]._render_qweb_html("weightrack.report_weighing_reject_slab_doc", report.ids)
        self.assertEqual(html.count(b"Same Tapper"), 2)
        action = report.action_export_excel()
        attachment = self.env["ir.attachment"].browse(int(action["url"].split("/web/content/")[1].split("?")[0]))
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(attachment.datas))) as workbook:
            sheet = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        for address, value in (("F12", 3), ("G12", 5), ("F13", 7), ("G13", 11), ("F14", 10), ("G14", 16)):
            self.assertEqual(float(sheet.find(".//s:c[@r='%s']/s:v" % address, ns).text), value)
