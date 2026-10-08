import base64
import io
import zipfile
from datetime import date
from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestKpiBudgetTarget(TransactionCase):
    TEST_YEAR = 2098

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.estate = cls.env["wt.estate"].create(
            {
                "name": "KPI Test Estate",
                "code": "KPI-TEST-ESTATE",
                "company_id": cls.company.id,
            }
        )
        cls.division = cls.env["wt.division"].create(
            {
                "name": "KPI Test Production",
                "code": "KPI-TEST-PROD",
                "estate_id": cls.estate.id,
            }
        )

    def _create_budget(self, year=None):
        year = year or self.TEST_YEAR
        return self.env["wt.kpi.budget.target"].create(
            {
                "name": "MANUAL-NUMBER-MUST-BE-IGNORED",
                "year": year,
                "company_id": self.company.id,
            }
        )

    def test_create_generates_sequence_divisions_and_months(self):
        budget = self._create_budget()
        active_divisions = self.env["wt.division"].search_count(
            [("active", "=", True), ("company_id", "=", self.company.id)]
        )

        self.assertRegex(budget.name, rf"^BT/{self.TEST_YEAR}/\d{{5}}$")
        self.assertEqual(budget.state, "draft")
        self.assertEqual(len(budget.production_target_line_ids), active_divisions)
        self.assertEqual(len(budget.sales_target_line_ids), active_divisions)
        self.assertEqual(
            set(budget.production_target_line_ids.mapped("line_type")),
            {"production_target"},
        )
        self.assertEqual(
            set(budget.sales_target_line_ids.mapped("line_type")),
            {"sales_target"},
        )
        self.assertEqual(len(budget.factory_received_line_ids), 12)
        self.assertEqual(len(budget.dry_production_line_ids), 12)
        self.assertEqual(
            budget.factory_received_line_ids.sorted("sequence").mapped("month"),
            [f"{month:02d}" for month in range(1, 13)],
        )
        self.assertEqual(
            set(budget.factory_received_line_ids.mapped("uom_name")),
            {"Kg Basah"},
        )
        self.assertEqual(
            set(budget.dry_production_line_ids.mapped("uom_name")),
            {"Kg Basah"},
        )
        with self.assertRaises(ValidationError):
            budget.write({"name": "MANUAL"})
        with self.assertRaises(ValidationError):
            budget.write({"year": self.TEST_YEAR + 1})

    def test_duplicate_year_per_company_is_rejected(self):
        self._create_budget()

        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._create_budget()

    def test_invalid_year_and_negative_values_are_rejected(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._create_budget(year=26)

        budget = self._create_budget()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            budget.production_target_line_ids[0].write({"january": -1})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            budget.factory_received_line_ids[0].write({"value": -1})

    def test_duplicate_division_and_month_are_rejected(self):
        budget = self._create_budget()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.env["wt.kpi.budget.target.division.line"].create(
                {
                    "budget_target_id": budget.id,
                    "line_type": "production_target",
                    "division_id": self.division.id,
                }
            )
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.env["wt.kpi.budget.target.monthly.line"].create(
                {
                    "budget_target_id": budget.id,
                    "line_type": "factory_received",
                    "month": "01",
                    "sequence": 1,
                }
            )

    def test_sync_divisions_only_adds_missing_lines(self):
        budget = self._create_budget()
        production_line = budget.production_target_line_ids.filtered(
            lambda line: line.division_id == self.division
        )
        production_line.january = 1250.5
        new_division = self.env["wt.division"].create(
            {
                "name": "KPI Test Warehouse",
                "code": "KPI-TEST-WH",
                "estate_id": self.estate.id,
            }
        )

        result = budget.action_sync_divisions()

        self.assertEqual(result["params"]["message"], "Divisi berhasil disinkronkan.")
        self.assertEqual(production_line.january, 1250.5)
        self.assertEqual(
            len(
                budget.production_target_line_ids.filtered(
                    lambda line: line.division_id == new_division
                )
            ),
            1,
        )
        self.assertEqual(
            len(
                budget.sales_target_line_ids.filtered(
                    lambda line: line.division_id == new_division
                )
            ),
            1,
        )
        self.assertEqual(
            budget.action_sync_divisions()["params"]["message"],
            "Semua divisi sudah tersinkronisasi.",
        )

    def test_valid_status_locks_values_and_can_return_to_draft(self):
        budget = self._create_budget()
        line = budget.production_target_line_ids[0]
        self._fill_all_values(budget)

        budget.action_validate()

        self.assertEqual(budget.state, "valid")
        with self.assertRaises(ValidationError):
            line.write({"january": 100})
        with self.assertRaises(ValidationError):
            budget.action_sync_divisions()

        duplicate = budget.copy({"year": self.TEST_YEAR + 1})
        self.assertEqual(duplicate.state, "draft")

        budget.action_set_draft()
        line.write({"january": 100})
        self.assertEqual(budget.state, "draft")
        self.assertEqual(line.january, 100)

    def test_copy_keeps_values_without_duplicate_generated_lines(self):
        source = self._create_budget()
        source.production_target_line_ids[0].january = 321.5

        duplicate = source.copy({"year": self.TEST_YEAR + 1})

        self.assertNotEqual(duplicate.name, source.name)
        self.assertRegex(
            duplicate.name,
            rf"^BT/{self.TEST_YEAR + 1}/\d{{5}}$",
        )
        self.assertEqual(
            len(duplicate.production_target_line_ids),
            len(source.production_target_line_ids),
        )
        self.assertEqual(
            len(duplicate.sales_target_line_ids),
            len(source.sales_target_line_ids),
        )
        self.assertEqual(len(duplicate.factory_received_line_ids), 12)
        self.assertEqual(len(duplicate.dry_production_line_ids), 12)
        self.assertIn(321.5, duplicate.production_target_line_ids.mapped("january"))

    def test_validation_requires_every_value(self):
        budget = self._create_budget()

        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            budget.action_validate()

        self._fill_all_values(budget)
        budget.action_validate()

        self.assertEqual(budget.state, "valid")

    def test_reporting_domains_and_cascade_delete(self):
        budget = self._create_budget()
        division_line_ids = (
            budget.production_target_line_ids | budget.sales_target_line_ids
        ).ids
        monthly_line_ids = (
            budget.factory_received_line_ids | budget.dry_production_line_ids
        ).ids

        production_lines = self.env["wt.kpi.budget.target.division.line"].search(
            [
                ("budget_target_id", "=", budget.id),
                ("line_type", "=", "production_target"),
            ]
        )
        sales_lines = self.env["wt.kpi.budget.target.division.line"].search(
            [
                ("budget_target_id", "=", budget.id),
                ("line_type", "=", "sales_target"),
            ]
        )
        self.assertEqual(production_lines, budget.production_target_line_ids)
        self.assertEqual(sales_lines, budget.sales_target_line_ids)

        budget.unlink()
        self.assertFalse(
            self.env["wt.kpi.budget.target.division.line"]
            .browse(division_line_ids)
            .exists()
        )
        self.assertFalse(
            self.env["wt.kpi.budget.target.monthly.line"]
            .browse(monthly_line_ids)
            .exists()
        )

    def test_security_admin_can_manage_and_report_viewer_is_read_only(self):
        admin_user = new_test_user(
            self.env,
            login="kpi_admin_test",
            groups="weightrack.group_admin",
        )
        report_user = new_test_user(
            self.env,
            login="kpi_report_test",
            groups="weightrack.group_report_viewer",
        )
        budget = self.env["wt.kpi.budget.target"].with_user(admin_user).create(
            {"year": self.TEST_YEAR, "company_id": self.company.id}
        )

        report_values = budget.with_user(report_user).read(["name"])[0]
        self.assertEqual(report_values["name"], budget.name)
        with self.assertRaises(AccessError):
            budget.production_target_line_ids[0].with_user(report_user).write(
                {"january": 1}
            )
        with self.assertRaises(AccessError):
            budget.with_user(report_user).unlink()

        report = self.env["wt.kpi.budget.target.report"].with_user(
            report_user
        ).create({})
        wizard = self.env["wt.kpi.budget.target.report.wizard"].with_user(
            report_user
        ).create(
            {
                "report_id": report.id,
                "company_id": self.company.id,
                "year": str(self.TEST_YEAR),
            }
        )
        self.assertTrue(report.exists())
        self.assertTrue(wizard.exists())

    def test_factory_dry_weight_follows_received_weight_flow(self):
        delivery_model = self.env["wt.delivery"]
        with patch.object(
            type(delivery_model),
            "_get_business_today",
            return_value=date(self.TEST_YEAR, 12, 31),
        ):
            delivery = delivery_model.create(
                {
                    "company_id": self.company.id,
                    "date": "%s-01-10" % self.TEST_YEAR,
                    "state": "delivered",
                    "received_qty": 100.0,
                }
            )

        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            delivery.action_mark_done()

        delivery.factory_dry_qty = 70.0
        delivery.action_mark_done()
        self.assertEqual(delivery.state, "done")
        self.assertEqual(
            delivery.action_open_received_qty_correction()["res_model"],
            "wt.delivery.received.qty.correction.wizard",
        )

        correction = self.env[
            "wt.delivery.received.qty.correction.wizard"
        ].with_context(default_delivery_id=delivery.id).create(
            {"reason": "Koreksi hasil timbang pabrik"}
        )
        self.assertEqual(correction.new_received_qty, 100.0)
        self.assertEqual(correction.new_factory_dry_qty, 70.0)

        correction.write(
            {
                "new_received_qty": 95.0,
                "new_factory_dry_qty": 65.0,
            }
        )
        correction.action_apply()

        self.assertEqual(delivery.received_qty, 95.0)
        self.assertEqual(delivery.factory_dry_qty, 65.0)

    def test_budget_target_report_calculation_and_excel_export(self):
        budget = self._create_budget()
        month_values = {
            field_name: 100.0
            for field_name in (
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
        }
        budget.production_target_line_ids.write(month_values)
        budget.sales_target_line_ids.write(
            {field_name: 80.0 for field_name in month_values}
        )
        budget.factory_received_line_ids.write({"value": 70.0})
        budget.dry_production_line_ids.write({"value": 49.0})
        budget.action_validate()
        self.env["wt.weighing"].create(
            {
                "company_id": self.company.id,
                "production_date": "%s-01-15" % self.TEST_YEAR,
                "weighing_date": "%s-01-15 08:00:00" % self.TEST_YEAR,
                "estate_id": self.estate.id,
                "division_id": self.division.id,
                "production_weight": 35.0,
            }
        )
        delivery_model = self.env["wt.delivery"]
        with patch.object(
            type(delivery_model),
            "_get_business_today",
            return_value=date(self.TEST_YEAR, 12, 31),
        ):
            delivery_model.create(
                {
                    "company_id": self.company.id,
                    "date": "%s-01-20" % self.TEST_YEAR,
                    "state": "done",
                    "received_qty": 60.0,
                    "factory_dry_qty": 42.0,
                }
            )

        report = self.env["wt.kpi.budget.target.report"].create({})
        wizard = self.env["wt.kpi.budget.target.report.wizard"].create(
            {
                "report_id": report.id,
                "company_id": self.company.id,
                "year": str(self.TEST_YEAR),
            }
        )
        action = wizard.action_apply_filter()
        self.assertEqual(action["res_id"], report.id)
        self.assertEqual(report.budget_target_id, budget)
        self.assertEqual(report.year_display, str(self.TEST_YEAR))
        self.assertTrue(report.preview_html)
        self.assertIn("Realisasi", str(report.preview_html))
        self.assertIn("Selisih", str(report.preview_html))
        self.assertIn("color:#15803d", str(report.preview_html))
        self.assertIn("color:#dc2626", str(report.preview_html))

        rows = report._get_report_rows()
        grand_totals = [row for row in rows if row["kind"] == "grand_total"]
        division_count = len(budget.production_target_line_ids)
        self.assertEqual(grand_totals[0]["values"][0], division_count * 100.0)
        self.assertEqual(grand_totals[1]["values"][0], division_count * 80.0)
        self.assertEqual(grand_totals[0]["actual_values"][0], 35.0)
        self.assertEqual(
            grand_totals[0]["variance_values"][0],
            35.0 - (division_count * 100.0),
        )
        self.assertEqual(grand_totals[1]["actual_values"][0], 0.0)
        metrics = {row["no"]: row for row in rows if row["kind"] == "metric"}
        self.assertAlmostEqual(metrics["3"]["total"], 20.0)
        self.assertAlmostEqual(metrics["3"]["actual_total"], 100.0)
        self.assertAlmostEqual(metrics["5"]["actual_values"][0], 60.0)
        self.assertAlmostEqual(metrics["6"]["total"], 70.0)
        self.assertAlmostEqual(metrics["6"]["actual_total"], 70.0)
        self.assertEqual(metrics["7"]["actual_values"][0], 42.0)
        self.assertEqual(metrics["7"]["actual_values"][1:], [0.0] * 11)
        self.assertEqual(metrics["7"]["actual_total"], 42.0)

        export_action = report.action_export_excel()
        attachment_id = int(
            export_action["url"].split("/web/content/", 1)[1].split("?", 1)[0]
        )
        attachment = self.env["ir.attachment"].browse(attachment_id)
        self.assertEqual(attachment.name, "Laporan Budget Target - 2098.xlsx")
        with zipfile.ZipFile(
            io.BytesIO(base64.b64decode(attachment.datas)), "r"
        ) as workbook_archive:
            self.assertIn("xl/worksheets/sheet1.xml", workbook_archive.namelist())
            shared_strings = workbook_archive.read("xl/sharedStrings.xml")
            sheet_xml = workbook_archive.read("xl/worksheets/sheet1.xml")
            self.assertIn(b"REALISASI", shared_strings)
            self.assertIn(b"SELISIH", shared_strings)
            self.assertIn(b"conditionalFormatting", sheet_xml)

    def test_budget_target_report_orders_sebayur_before_gembung(self):
        estates = self.env["wt.estate"].create(
            [
                {
                    "name": "Gembung Report Test",
                    "code": "REPORT-GEMBUNG",
                    "company_id": self.company.id,
                },
                {
                    "name": "Other Report Test",
                    "code": "REPORT-OTHER",
                    "company_id": self.company.id,
                },
                {
                    "name": "Sebayur Report Test",
                    "code": "REPORT-SEBAYUR",
                    "company_id": self.company.id,
                },
            ]
        )
        report = self.env["wt.kpi.budget.target.report"].create({})

        ordered_estates = estates.sorted(key=report._estate_sort_key)

        self.assertEqual(
            ordered_estates.mapped("name"),
            [
                "Sebayur Report Test",
                "Gembung Report Test",
                "Other Report Test",
            ],
        )

    def _fill_all_values(self, budget):
        month_values = {
            field_name: 1
            for field_name in (
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
        }
        (
            budget.production_target_line_ids | budget.sales_target_line_ids
        ).write(month_values)
        (
            budget.factory_received_line_ids | budget.dry_production_line_ids
        ).write({"value": 1})
