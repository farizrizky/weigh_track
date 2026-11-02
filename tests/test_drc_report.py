from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDrcReportLpSource(TransactionCase):
    production_date = date(2020, 2, 15)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "DRC LP Source QA"})
        cls.env = cls.env(
            context={
                **cls.env.context,
                "allowed_company_ids": [cls.company.id],
                "lang": "en_US",
            }
        )
        cls.estate = cls.env["wt.estate"].create(
            {
                "name": "DRC LP Source QA",
                "code": "DRCLP",
                "company_id": cls.company.id,
            }
        )
        cls.division = cls.env["wt.division"].create(
            {
                "name": "DRC LP Source QA",
                "code": "DRCLP",
                "estate_id": cls.estate.id,
            }
        )
        cls.foreman, cls.tapper = cls.env["hr.employee"].create(
            [
                {"name": "DRC Foreman QA", "company_id": cls.company.id},
                {"name": "DRC Tapper QA", "company_id": cls.company.id},
            ]
        )

    def _weighing(self, production_weight, net_weight, state):
        weighing = self.env["wt.weighing"].create(
            {
                "company_id": self.company.id,
                "estate_id": self.estate.id,
                "division_id": self.division.id,
                "production_date": self.production_date,
                "weighing_date": "2020-02-15 08:00:00",
                "foreman_employee_id": self.foreman.id,
                "tapper_employee_id": self.tapper.id,
                "production_weight": production_weight,
                "net_weight": net_weight,
            }
        )
        if state != "not_receipted":
            weighing.with_context(allow_production_receipt_update=True).write(
                {"state": state}
            )
        return weighing

    def test_lp_uses_net_weight_from_validated_receipts(self):
        self._weighing(100.0, 80.0, "receipt_validated")
        self._weighing(30.0, 20.0, "receipt_validated")
        self._weighing(999.0, 900.0, "not_receipted")
        self._weighing(888.0, 800.0, "in_production_receipt")
        self._weighing(777.0, 700.0, "receipt_cancelled")

        wizard = self.env["wt.drc.report.wizard"].new(
            {
                "company_id": self.company.id,
                "date_start": self.production_date,
                "date_end": self.production_date,
            }
        )
        data = wizard._prepare_report_data()
        expected_lp = sum((80.0, 20.0))

        self.assertEqual(data["total_lp"], expected_lp)
        self.assertEqual(data["date_totals"][self.production_date.isoformat()]["lp"], expected_lp)
        self.assertEqual(len(data["rows"]), 1)
        self.assertEqual(data["rows"][0]["total_lp"], expected_lp)
        self.assertEqual(
            data["rows"][0]["daily_data"][self.production_date.isoformat()]["lp"],
            expected_lp,
        )
