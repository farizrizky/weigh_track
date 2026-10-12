import base64
import io
import zipfile
import xml.etree.ElementTree as ET

from lxml import html

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
        current_line = foreman_budget.foreman_line_ids.filtered(
            lambda line: line.employee_id == self.employee_1
            and line.division_id == new_division
        )
        self.assertEqual(len(current_line), 1)
        self.assertNotEqual(current_line, historical_line)

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

    def _create_replacement_foreman(self, division=None):
        employee = self.env["hr.employee"].create({
            "name": "KPI Replacement Foreman", "company_id": self.company.id,
            "job_id": self.foreman_job.id,
        })
        return self.env["wt.foreman"].create({
            "employee_id": employee.id, "division_id": (division or self.division).id,
        })

    def _replacement_wizard(self, line, replacement, month="07", old_action="zero"):
        return self.env["wt.kpi.foreman.budget.replacement.wizard"].create({
            "line_id": line.id, "new_foreman_id": replacement.id,
            "start_month": month, "old_line_action": old_action,
        })

    def test_same_employee_has_independent_division_targets_and_sync(self):
        second_division = self.env["wt.division"].create({
            "name": "KPI Second Assignment", "code": "KPI-SECOND-ASSIGN",
            "estate_id": self.estate.id,
        })
        self._create_valid_main_budget()
        budget = self._create_foreman_budget()
        second_assignment = self.env["wt.foreman"].create({
            "employee_id": self.employee_1.id, "division_id": second_division.id,
        })
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            budget.action_validate()
        budget.action_sync_foremen()
        old_line = budget.foreman_line_ids.filtered(
            lambda line: line.employee_id == self.employee_1 and line.division_id == self.division
        )
        second_line = budget.foreman_line_ids.filtered(
            lambda line: line.employee_id == self.employee_1 and line.division_id == second_division
        )
        self.assertEqual(second_line.foreman_id, second_assignment)
        old_line.january = 25
        second_line.january = 30
        january = {row["division_id"]: row for row in budget._comparison_rows() if row["month"] == "01"}
        self.assertEqual(january[self.division.id]["total_foreman"], 25)
        self.assertEqual(january[second_division.id]["total_foreman"], 30)
        self.env["wt.weighing"].create([
            {
                "company_id": self.company.id, "estate_id": self.estate.id,
                "division_id": division.id, "foreman_employee_id": self.employee_1.id,
                "production_date": "%s-01-15" % self.TEST_YEAR,
                "weighing_date": "%s-01-15 08:00:00" % self.TEST_YEAR,
                "production_weight": net_weight + 5, "reject_weight": 5,
                "net_weight": net_weight,
            }
            for division, net_weight in ((self.division, 10), (second_division, 20))
        ])
        report = self.env["wt.kpi.foreman.budget.target.report"].new({
            "company_id": self.company.id, "year": self.TEST_YEAR,
            "budget_mandor_id": budget.id,
        })
        actuals = {
            row["division"]: row["actual_values"][0]
            for row in report._get_report_rows()
            if row["kind"] == "foreman" and row["foreman"] == self.employee_1.name
        }
        self.assertEqual(actuals, {self.division.code: 10, second_division.code: 20})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            second_line.january = 101
        self.assertEqual(old_line.january, 25)
        self.assertEqual(second_line.january, 30)
        budget.action_sync_foremen()
        self.assertEqual(len(budget.foreman_line_ids), 3)

    def test_replacement_preserves_previous_months_and_division_allocation(self):
        self._create_valid_main_budget()
        budget = self._create_foreman_budget()
        old_line = budget.foreman_line_ids.filtered(lambda line: line.employee_id == self.employee_1)
        other_line = budget.foreman_line_ids - old_line
        old_line.write({field: 60 for field in MONTH_FIELDS})
        other_line.write({field: 40 for field in MONTH_FIELDS})
        self.foreman_1.active = False
        replacement = self._create_replacement_foreman()
        wizard = self._replacement_wizard(old_line, replacement)
        self.assertEqual(wizard.transfer_total, 360)
        wizard.action_apply()
        new_line = budget.foreman_line_ids.filtered(lambda line: line.employee_id == replacement.employee_id)
        self.assertEqual(old_line.june, 60)
        self.assertEqual(old_line.july, 0)
        self.assertEqual(old_line.december, 0)
        self.assertEqual(new_line.june, 0)
        self.assertEqual(new_line.july, 60)
        self.assertEqual(new_line.december, 60)
        self.assertTrue(all(row["total_foreman"] == 100 for row in budget._comparison_rows()))
        budget.action_validate()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            old_line.action_zero_targets()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            old_line.action_open_replacement()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            old_line.unlink()

    def test_replacement_adds_to_existing_target_without_changing_other_division(self):
        second_division = self.env["wt.division"].create({
            "name": "KPI Replacement Other Division", "code": "KPI-REPLACE-OTHER",
            "estate_id": self.estate.id,
        })
        replacement = self._create_replacement_foreman()
        self.env["wt.foreman"].create({
            "employee_id": replacement.employee_id.id, "division_id": second_division.id,
        })
        self._create_valid_main_budget()
        budget = self._create_foreman_budget()
        old_line = budget.foreman_line_ids.filtered(lambda line: line.employee_id == self.employee_1)
        new_line = budget.foreman_line_ids.filtered(
            lambda line: line.employee_id == replacement.employee_id and line.division_id == self.division
        )
        other_division_line = budget.foreman_line_ids.filtered(
            lambda line: line.employee_id == replacement.employee_id and line.division_id == second_division
        )
        old_line.write({field: 60 for field in MONTH_FIELDS})
        new_line.write({field: 10 for field in MONTH_FIELDS})
        other_division_line.write({field: 75 for field in MONTH_FIELDS})
        self.foreman_1.active = False
        self._replacement_wizard(old_line, replacement).action_apply()
        self.assertEqual(new_line.june, 10)
        self.assertEqual(new_line.july, 70)
        self.assertEqual(other_division_line.july, 75)
        self.assertEqual(len(budget.foreman_line_ids), 4)

    def test_deleted_master_can_transfer_target_and_remove_old_budget_line(self):
        self._create_valid_main_budget()
        budget = self._create_foreman_budget()
        old_line = budget.foreman_line_ids.filtered(lambda line: line.employee_id == self.employee_1)
        old_line.write({field: 60 for field in MONTH_FIELDS[6:]})
        self.foreman_1.unlink()
        replacement = self._create_replacement_foreman()
        wizard = self._replacement_wizard(old_line, replacement, old_action="delete")
        wizard.action_apply()
        self.assertFalse(old_line.exists())
        new_line = budget.foreman_line_ids.filtered(lambda line: line.employee_id == replacement.employee_id)
        self.assertEqual(new_line.june, 0)
        self.assertEqual(new_line.july, 60)
        budget.action_sync_foremen()
        self.assertEqual(len(budget.foreman_line_ids), 2)

    def test_replacement_rejects_deleting_previous_months_and_invalid_assignment(self):
        second_division = self.env["wt.division"].create({
            "name": "KPI Invalid Replacement Division", "code": "KPI-INVALID-REPLACE",
            "estate_id": self.estate.id,
        })
        self._create_valid_main_budget()
        budget = self._create_foreman_budget()
        old_line = budget.foreman_line_ids.filtered(lambda line: line.employee_id == self.employee_1)
        old_line.write({field: 60 for field in MONTH_FIELDS})
        self.foreman_1.active = False
        wrong_division_foreman = self._create_replacement_foreman(second_division)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._replacement_wizard(old_line, wrong_division_foreman).action_apply()
        replacement = self._create_replacement_foreman()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._replacement_wizard(old_line, replacement, old_action="delete").action_apply()
        self.assertEqual(old_line.january, 60)
        self.assertEqual(old_line.july, 60)
        self.assertEqual(len(budget.foreman_line_ids), 2)

    def test_discontinued_line_can_be_zeroed_and_deleted_in_draft(self):
        self._create_valid_main_budget()
        budget = self._create_foreman_budget()
        old_line = budget.foreman_line_ids.filtered(lambda line: line.employee_id == self.employee_1)
        old_line.january = 60
        self.foreman_1.active = False
        old_line.action_zero_targets()
        self.assertTrue(all(old_line[field] == 0 for field in MONTH_FIELDS))
        self.assertTrue(all(row["total_foreman"] == 0 for row in budget._comparison_rows()))
        old_line.unlink()
        budget.action_sync_foremen()
        self.assertEqual(len(budget.foreman_line_ids), 1)

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
                    "production_weight": 50.0,
                    "reject_weight": 10.0,
                    "net_weight": 40.0,
                },
                {
                    "company_id": self.company.id,
                    "production_date": "%s-01-16" % self.TEST_YEAR,
                    "weighing_date": "%s-01-16 08:00:00" % self.TEST_YEAR,
                    "estate_id": self.estate.id,
                    "division_id": self.division.id,
                    "foreman_employee_id": self.employee_2.id,
                    "production_weight": 15.0,
                    "reject_weight": 5.0,
                    "net_weight": 10.0,
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
        self.assertIn("Ketercapaian (%)", str(report.preview_html))
        preview = html.fromstring(str(report.preview_html))
        self.assertEqual(
            len(preview.xpath("//thead/tr[2]/th[text()='Ketercapaian (%)']")), 13
        )
        for row in preview.xpath("//tbody/tr"):
            self.assertEqual(sum(int(cell.get("colspan", 1)) for cell in row), 56)
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
        self.assertEqual(division_total["achievement_values"][0], 50.0)
        self.assertAlmostEqual(division_total["achievement_total"], 50 / 1200 * 100)
        self.assertEqual(report._ratio_values([50, 150, 10], [100, 100, 0]), [50, 150, 0])
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
            self.assertIn(b"KETERCAPAIAN (%)", shared_strings)
            self.assertIn(b"conditionalFormatting", sheet_xml)
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            sheet = ET.fromstring(sheet_xml)
            total_row_number = rows.index(division_total) + 7
            monthly_cell = sheet.find(f".//s:c[@r='H{total_row_number}']", ns)
            annual_cell = sheet.find(f".//s:c[@r='BD{total_row_number}']", ns)
            self.assertAlmostEqual(float(monthly_cell.find("s:v", ns).text), 0.5)
            self.assertAlmostEqual(float(annual_cell.find("s:v", ns).text), 50 / 1200)
            styles = ET.fromstring(workbook_archive.read("xl/styles.xml"))
            cell_style = list(styles.find("s:cellXfs", ns))[int(monthly_cell.get("s"))]
            number_format = styles.find(
                "s:numFmts/s:numFmt[@numFmtId='%s']" % cell_style.get("numFmtId"), ns
            )
            self.assertEqual(number_format.get("formatCode"), "0.00%")
            variance_ranges = [cell.get("sqref") for cell in sheet.findall("s:conditionalFormatting", ns)]
            self.assertTrue(any(value.startswith("BC") for value in variance_ranges))
            self.assertFalse(any(value.startswith("BD") for value in variance_ranges))

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
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            self.env["wt.kpi.foreman.budget.replacement.wizard"].with_user(report_user).create({
                "line_id": foreman_budget.foreman_line_ids[0].id,
                "new_foreman_id": self.foreman_2.id,
                "start_month": "07",
            })
