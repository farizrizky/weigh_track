import base64
import io
import zipfile

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


MONTH_FIELDS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)


@tagged("post_install", "-at_install")
class TestKpiForemanBudgetTarget(TransactionCase):
    TEST_YEAR = 2096

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create(
            {"name": "KPI Mandor Test Company"}
        )
        cls.model = cls.env["wt.kpi.foreman.budget.target"].with_company(
            cls.company
        )
        cls.estate = cls.env["wt.estate"].create(
            {
                "name": "KPI Mandor Test Estate",
                "code": "KPI-MANDOR-ESTATE",
                "company_id": cls.company.id,
            }
        )
        cls.division = cls.env["wt.division"].create(
            {
                "name": "KPI Mandor Division",
                "code": "KPI-MANDOR-DIV",
                "estate_id": cls.estate.id,
            }
        )
        cls.foreman_job = cls.env["hr.job"].create(
            {"name": "KPI Mandor Test Job", "company_id": cls.company.id}
        )
        cls.env["wt.employee.role"].create(
            {
                "company_id": cls.company.id,
                "role": "foreman",
                "job_id": cls.foreman_job.id,
            }
        )
        cls.employee_1 = cls.env["hr.employee"].create(
            {
                "name": "KPI Mandor One",
                "company_id": cls.company.id,
                "job_id": cls.foreman_job.id,
            }
        )
        cls.employee_2 = cls.env["hr.employee"].create(
            {
                "name": "KPI Mandor Two",
                "company_id": cls.company.id,
                "job_id": cls.foreman_job.id,
            }
        )
        cls.foreman_1 = cls.env["wt.foreman"].create(
            {
                "employee_id": cls.employee_1.id,
                "division_id": cls.division.id,
            }
        )
        cls.foreman_2 = cls.env["wt.foreman"].create(
            {
                "employee_id": cls.employee_2.id,
                "division_id": cls.division.id,
            }
        )

    def _create_valid_main_budget(self, year=None):
        year = year or self.TEST_YEAR
        budget = self.env["wt.kpi.budget.target"].with_company(self.company).create(
            {"year": year, "company_id": self.company.id}
        )
        month_values = {field_name: 100 for field_name in MONTH_FIELDS}
        (
            budget.production_target_line_ids | budget.sales_target_line_ids
        ).write(month_values)
        (
            budget.factory_received_line_ids | budget.dry_production_line_ids
        ).write({"value": 100})
        budget.action_validate()
        return budget

    def _create_foreman_budget(self, year=None):
        return self.model.create(
            {"year": year or self.TEST_YEAR, "company_id": self.company.id}
        )

    def _fill_exact_allocation(self, foreman_budget):
        values = {field_name: 100 for field_name in MONTH_FIELDS}
        foreman_budget.foreman_line_ids.filtered(
            lambda line: line.employee_id == self.employee_1
        ).write(values)

    def test_create_resolves_reference_sequence_lines_and_controls(self):
        main_budget = self._create_valid_main_budget()

        foreman_budget = self._create_foreman_budget()

        self.assertRegex(
            foreman_budget.name,
            rf"^BTM/{self.TEST_YEAR}/\d{{5}}$",
        )
        self.assertEqual(foreman_budget.budget_target_id, main_budget)
        self.assertEqual(foreman_budget.state, "draft")
        self.assertEqual(len(foreman_budget.foreman_line_ids), 2)
        self.assertEqual(len(foreman_budget.control_line_ids), 12)
        self.assertEqual(
            set(foreman_budget.foreman_line_ids.mapped("division_id")),
            {self.division},
        )
        self.assertEqual(
            set(foreman_budget.foreman_line_ids.mapped("uom_name")),
            {"Kg Basah"},
        )
        january = foreman_budget.control_line_ids.filtered(
            lambda line: line.month == "01"
        )
        self.assertEqual(january.target_production, 100)
        self.assertEqual(january.total_foreman, 0)
        self.assertEqual(january.remaining, 100)
        self.assertEqual(january.allocation_status, "less")

    def test_create_without_valid_main_budget_is_rejected(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._create_foreman_budget()

    def test_over_budget_is_rejected_during_draft_write(self):
        self._create_valid_main_budget()
        foreman_budget = self._create_foreman_budget()
        line_1 = foreman_budget.foreman_line_ids.filtered(
            lambda line: line.employee_id == self.employee_1
        )
        line_2 = foreman_budget.foreman_line_ids.filtered(
            lambda line: line.employee_id == self.employee_2
        )
        line_1.january = 60
        line_2.january = 40

        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            line_1.january = 61

        self.assertEqual(line_1.january, 60)
        january = foreman_budget.control_line_ids.filtered(
            lambda line: line.month == "01"
        )
        self.assertEqual(january.total_foreman, 100)
        self.assertEqual(january.allocation_status, "matched")

    def test_shortage_uses_confirmation_wizard(self):
        self._create_valid_main_budget()
        foreman_budget = self._create_foreman_budget()

        action = foreman_budget.action_validate()

        self.assertEqual(
            action["res_model"],
            "wt.kpi.foreman.budget.validation.wizard",
        )
        self.assertEqual(foreman_budget.state, "draft")
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        self.assertIn("Januari", wizard.warning_text)
        wizard.action_confirm_validation()
        self.assertEqual(foreman_budget.state, "valid")

    def test_exact_allocation_validates_directly_and_locks_lines(self):
        self._create_valid_main_budget()
        foreman_budget = self._create_foreman_budget()
        self._fill_exact_allocation(foreman_budget)

        result = foreman_budget.action_validate()

        self.assertTrue(result)
        self.assertEqual(foreman_budget.state, "valid")
        self.assertEqual(
            set(foreman_budget.control_line_ids.mapped("allocation_status")),
            {"matched"},
        )
        with self.assertRaises(ValidationError):
            foreman_budget.foreman_line_ids[0].write({"january": 1})
        foreman_budget.action_set_draft()
        foreman_budget.foreman_line_ids[0].write({"january": 50})

    def test_sync_adds_new_foreman_without_resetting_existing_values(self):
        self._create_valid_main_budget()
        foreman_budget = self._create_foreman_budget()
        existing_line = foreman_budget.foreman_line_ids.filtered(
            lambda line: line.employee_id == self.employee_1
        )
        existing_line.january = 25
        employee_3 = self.env["hr.employee"].create(
            {
                "name": "KPI Mandor Three",
                "company_id": self.company.id,
                "job_id": self.foreman_job.id,
            }
        )
        foreman_3 = self.env["wt.foreman"].create(
            {"employee_id": employee_3.id, "division_id": self.division.id}
        )

        result = foreman_budget.action_sync_foremen()

        self.assertEqual(result["params"]["message"], "Mandor berhasil disinkronkan.")
        self.assertEqual(result["params"]["next"]["tag"], "reload")
        self.assertEqual(existing_line.january, 25)
        self.assertEqual(
            len(
                foreman_budget.foreman_line_ids.filtered(
                    lambda line: line.employee_id == employee_3
                )
            ),
            1,
        )
        no_change_result = foreman_budget.action_sync_foremen()
        self.assertEqual(
            no_change_result["params"]["message"],
            "Semua Mandor sudah tersinkronisasi.",
        )
        self.assertEqual(no_change_result["params"]["next"]["tag"], "reload")

    def test_division_is_a_historical_snapshot(self):
        self._create_valid_main_budget()
        foreman_budget = self._create_foreman_budget()
        historical_line = foreman_budget.foreman_line_ids.filtered(
            lambda line: line.employee_id == self.employee_1
        )
        new_division = self.env["wt.division"].create(
            {
                "name": "KPI Mandor New Division",
                "code": "KPI-MANDOR-NEW-DIV",
                "estate_id": self.estate.id,
            }
        )

        self.foreman_1.division_id = new_division
        foreman_budget.action_sync_foremen()

        self.assertEqual(historical_line.division_id, self.division)

    def test_deleting_master_foreman_keeps_target_and_prevents_resync_duplicate(self):
        self._create_valid_main_budget()
        foreman_budget = self._create_foreman_budget()
        historical_line = foreman_budget.foreman_line_ids.filtered(
            lambda line: line.employee_id == self.employee_1
        )
        historical_line.january = 25

        self.foreman_1.unlink()

        self.assertTrue(historical_line.exists())
        self.assertFalse(historical_line.foreman_id)
        self.assertEqual(historical_line.employee_id, self.employee_1)
        self.assertEqual(historical_line.division_id, self.division)
        self.assertEqual(historical_line.january, 25)

        self.env["wt.foreman"].create(
            {
                "employee_id": self.employee_1.id,
                "division_id": self.division.id,
            }
        )
        result = foreman_budget.action_sync_foremen()

        self.assertEqual(
            result["params"]["message"],
            "Semua Mandor sudah tersinkronisasi.",
        )
        self.assertEqual(
            len(
                foreman_budget.foreman_line_ids.filtered(
                    lambda line: line.employee_id == self.employee_1
                )
            ),
            1,
        )

    def test_duplicate_foreman_is_rejected_and_main_budget_can_reset(self):
        main_budget = self._create_valid_main_budget()
        foreman_budget = self._create_foreman_budget()

        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.env["wt.kpi.foreman.budget.target.line"].create(
                {
                    "budget_mandor_id": foreman_budget.id,
                    "foreman_id": self.foreman_1.id,
                    "division_id": self.division.id,
                }
            )
        main_budget.action_set_draft()

        self.assertEqual(main_budget.state, "draft")
        self.assertTrue(foreman_budget.exists())
        self.assertEqual(foreman_budget.budget_target_id, main_budget)

    def test_copy_uses_a_new_number_and_keeps_snapshot_values(self):
        self._create_valid_main_budget()
        source = self._create_foreman_budget()
        source.foreman_line_ids[0].january = 30

        duplicate = source.copy()

        self.assertNotEqual(duplicate.name, source.name)
        self.assertEqual(duplicate.state, "draft")
        self.assertEqual(duplicate.budget_target_id, source.budget_target_id)
        self.assertEqual(len(duplicate.foreman_line_ids), 2)
        self.assertIn(30, duplicate.foreman_line_ids.mapped("january"))

    def test_report_groups_foremen_and_exports_excel(self):
        self._create_valid_main_budget()
        foreman_budget = self._create_foreman_budget()
        self._fill_exact_allocation(foreman_budget)
        foreman_budget.action_validate()
        self.env["wt.weighing"].with_company(self.company).create(
            [
                {
                    "company_id": self.company.id,
                    "production_date": "%s-01-15" % self.TEST_YEAR,
                    "weighing_date": "%s-01-15 08:00:00" % self.TEST_YEAR,
                    "estate_id": self.estate.id,
                    "division_id": self.division.id,
                    "foreman_employee_id": self.employee_1.id,
                    "production_weight": 40.0,
                },
                {
                    "company_id": self.company.id,
                    "production_date": "%s-01-16" % self.TEST_YEAR,
                    "weighing_date": "%s-01-16 08:00:00" % self.TEST_YEAR,
                    "estate_id": self.estate.id,
                    "division_id": self.division.id,
                    "foreman_employee_id": self.employee_2.id,
                    "production_weight": 10.0,
                },
            ]
        )

        report = self.env["wt.kpi.foreman.budget.target.report"].create({})
        wizard = self.env[
            "wt.kpi.foreman.budget.target.report.wizard"
        ].create(
            {
                "report_id": report.id,
                "company_id": self.company.id,
                "year": str(self.TEST_YEAR),
                "budget_mandor_id": foreman_budget.id,
                "estate_id": self.estate.id,
            }
        )

        action = wizard.action_apply_filter()

        self.assertEqual(action["res_id"], report.id)
        self.assertEqual(report.budget_mandor_id, foreman_budget)
        self.assertEqual(report.estate_id, self.estate)
        self.assertEqual(report.year_display, str(self.TEST_YEAR))
        self.assertTrue(report.preview_html)
        self.assertIn("Realisasi", str(report.preview_html))
        self.assertIn("Selisih", str(report.preview_html))
        self.assertIn("color:#15803d", str(report.preview_html))
        self.assertIn("color:#dc2626", str(report.preview_html))
        rows = report._get_report_rows()
        foreman_rows = [row for row in rows if row["kind"] == "foreman"]
        division_total = next(
            row for row in rows if row["kind"] == "division_total"
        )
        estate_total = next(
            row for row in rows if row["kind"] == "estate_total"
        )
        self.assertEqual(len(foreman_rows), 2)
        actual_by_foreman = {
            row["foreman"]: row["actual_values"][0]
            for row in foreman_rows
        }
        self.assertEqual(actual_by_foreman[self.employee_1.name], 40.0)
        self.assertEqual(actual_by_foreman[self.employee_2.name], 10.0)
        self.assertEqual(division_total["values"][0], 100)
        self.assertEqual(division_total["actual_values"][0], 50.0)
        self.assertEqual(division_total["variance_values"][0], -50.0)
        self.assertEqual(
            division_total["variance_values"][0],
            division_total["actual_values"][0]
            - division_total["values"][0],
        )
        self.assertEqual(
            division_total["variance_total"],
            division_total["actual_total"] - division_total["total"],
        )
        self.assertEqual(estate_total["values"][0], 100)
        self.assertEqual(estate_total["actual_values"][0], 50.0)
        self.assertEqual(
            estate_total["variance_values"][0],
            estate_total["actual_values"][0] - estate_total["values"][0],
        )
        self.assertEqual(
            estate_total["variance_total"],
            estate_total["actual_total"] - estate_total["total"],
        )
        self.assertEqual(estate_total["total"], 1200)
        self.assertEqual(estate_total["actual_total"], 50.0)

        export_action = report.action_export_excel()
        attachment_id = int(
            export_action["url"].split("/web/content/", 1)[1].split("?", 1)[0]
        )
        attachment = self.env["ir.attachment"].browse(attachment_id)
        self.assertEqual(
            attachment.name,
            "Laporan Budget Target Mandor - KPI Mandor Test Estate - 2096.xlsx",
        )
        with zipfile.ZipFile(
            io.BytesIO(base64.b64decode(attachment.datas)), "r"
        ) as workbook_archive:
            self.assertIn("xl/worksheets/sheet1.xml", workbook_archive.namelist())
            shared_strings = workbook_archive.read("xl/sharedStrings.xml")
            sheet_xml = workbook_archive.read("xl/worksheets/sheet1.xml")
            self.assertIn(b"REALISASI", shared_strings)
            self.assertIn(b"SELISIH", shared_strings)
            self.assertIn(b"conditionalFormatting", sheet_xml)

    def test_report_without_estate_shows_every_estate_and_division(self):
        second_estate = self.env["wt.estate"].create(
            {
                "name": "Sebayur Report Test",
                "code": "KPI-MANDOR-SEBAYUR",
                "company_id": self.company.id,
            }
        )
        second_division = self.env["wt.division"].create(
            {
                "name": "KPI Mandor Second Division",
                "code": "KPI-MANDOR-DIV-2",
                "estate_id": second_estate.id,
            }
        )
        employee_3 = self.env["hr.employee"].create(
            {
                "name": "KPI Mandor Three",
                "company_id": self.company.id,
                "job_id": self.foreman_job.id,
            }
        )
        self.env["wt.foreman"].create(
            {
                "employee_id": employee_3.id,
                "division_id": second_division.id,
            }
        )
        self._create_valid_main_budget()
        foreman_budget = self._create_foreman_budget()
        month_values = {field_name: 100 for field_name in MONTH_FIELDS}
        foreman_budget.foreman_line_ids.filtered(
            lambda line: line.employee_id == self.employee_1
        ).write(month_values)
        foreman_budget.foreman_line_ids.filtered(
            lambda line: line.employee_id == employee_3
        ).write(month_values)
        foreman_budget.action_validate()

        report = self.env["wt.kpi.foreman.budget.target.report"].create({})
        wizard = self.env[
            "wt.kpi.foreman.budget.target.report.wizard"
        ].create(
            {
                "report_id": report.id,
                "company_id": self.company.id,
                "year": str(self.TEST_YEAR),
                "budget_mandor_id": foreman_budget.id,
                "estate_id": False,
            }
        )

        wizard.action_apply_filter()

        self.assertFalse(report.estate_id)
        rows = report._get_report_rows()
        estate_headers = [
            row["label"] for row in rows if row["kind"] == "estate_header"
        ]
        division_totals = [
            row for row in rows if row["kind"] == "division_total"
        ]
        estate_totals = [row for row in rows if row["kind"] == "estate_total"]
        self.assertEqual(
            estate_headers,
            ["Sebayur Report Test", "KPI Mandor Test Estate"],
        )
        self.assertEqual(len(division_totals), 2)
        self.assertEqual(len(estate_totals), 2)
        self.assertEqual([row["values"][0] for row in estate_totals], [100, 100])

        export_action = report.action_export_excel()
        attachment_id = int(
            export_action["url"].split("/web/content/", 1)[1].split("?", 1)[0]
        )
        attachment = self.env["ir.attachment"].browse(attachment_id)
        self.assertEqual(
            attachment.name,
            "Laporan Budget Target Mandor - Semua Estate - 2096.xlsx",
        )

    def test_report_viewer_can_use_foreman_budget_report(self):
        self._create_valid_main_budget()
        foreman_budget = self._create_foreman_budget()
        self._fill_exact_allocation(foreman_budget)
        foreman_budget.action_validate()
        report_user = new_test_user(
            self.env,
            login="kpi_mandor_report_viewer_test",
            groups="weightrack.group_report_viewer",
        )
        report_user.write(
            {
                "company_ids": [(4, self.company.id)],
                "company_id": self.company.id,
            }
        )

        report = self.env["wt.kpi.foreman.budget.target.report"].with_user(
            report_user
        ).create({})
        wizard = self.env[
            "wt.kpi.foreman.budget.target.report.wizard"
        ].with_user(report_user).create(
            {
                "report_id": report.id,
                "company_id": self.company.id,
                "year": str(self.TEST_YEAR),
                "budget_mandor_id": foreman_budget.id,
                "estate_id": self.estate.id,
            }
        )

        wizard.action_apply_filter()
        self.assertTrue(report.preview_html)
        foreman_budget.action_set_draft()
        with self.assertRaises(AccessError):
            foreman_budget.with_user(report_user).unlink()
