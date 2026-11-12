from odoo.exceptions import ValidationError
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTapper(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Tapper Master Test"})
        cls.env = cls.env(
            context={
                **cls.env.context,
                "allowed_company_ids": [cls.company.id],
                "lang": "en_US",
            }
        )
        estate = cls.env["wt.estate"].create(
            {"name": "Tapper Test", "code": "TAP", "company_id": cls.company.id}
        )
        cls.divisions = cls.env["wt.division"].create(
            [
                {"name": name, "code": name, "estate_id": estate.id}
                for name in ("TAP-1", "TAP-2")
            ]
        )
        job = cls.env["hr.job"].create(
            {"name": "Tapper Test Job", "company_id": cls.company.id}
        )
        cls.env["wt.employee.role"].create(
            [
                {"company_id": cls.company.id, "role": role, "job_id": job.id}
                for role in ("tapper", "foreman")
            ]
        )
        employees = cls.env["hr.employee"].create(
            [
                {"name": name, "company_id": cls.company.id, "job_id": job.id}
                for name in ("Tapper One", "Tapper Two", "Replacement", "Foreman")
            ]
        )
        cls.tapper_employees = employees[:3]
        cls.foremen = cls.env["wt.foreman"].create(
            [
                {"employee_id": employees[3].id, "division_id": division.id}
                for division in cls.divisions
            ]
        )
        cls.tappers = cls.env["wt.tapper"].create(
            [
                {
                    "employee_id": employee.id,
                    "division_id": cls.divisions[0].id,
                    "foreman_id": cls.foremen[0].id,
                }
                for employee in cls.tapper_employees[:2]
            ]
        )

    def test_employee_cannot_be_changed(self):
        with self.assertRaisesRegex(ValidationError, "cannot be changed after creation"):
            self.tappers[0].write({"employee_id": self.tapper_employees[2].id})
        self.assertEqual(self.tappers[0].employee_id, self.tapper_employees[0])

    def test_employee_cannot_be_cleared(self):
        with self.assertRaisesRegex(ValidationError, "cannot be changed after creation"):
            self.tappers[0].write({"employee_id": False})
        self.assertEqual(self.tappers[0].employee_id, self.tapper_employees[0])

    def test_same_employee_and_foreman_update_allowed(self):
        self.tappers[0].write(
            {
                "employee_id": self.tapper_employees[0].id,
                "foreman_id": self.foremen[1].id,
            }
        )
        self.assertEqual(self.tappers[0].employee_id, self.tapper_employees[0])
        self.assertEqual(self.tappers[0].foreman_id, self.foremen[1])
        self.assertEqual(self.tappers[0].division_id, self.divisions[1])

    def test_division_update_allowed(self):
        self.tappers[0].write(
            {"foreman_id": False, "division_id": self.divisions[1].id}
        )
        self.assertEqual(self.tappers[0].division_id, self.divisions[1])
        self.assertEqual(self.tappers[0].employee_id, self.tapper_employees[0])

    def test_batch_employee_change_rejected_before_other_updates(self):
        with self.assertRaisesRegex(ValidationError, "cannot be changed after creation"):
            self.tappers.write(
                {"employee_id": self.tapper_employees[0].id, "active": False}
            )
        self.assertEqual(self.tappers.mapped("employee_id"), self.tapper_employees[:2])
        self.assertTrue(all(self.tappers.mapped("active")))

    def test_archive_and_restore(self):
        tapper = self.tappers[0]
        domain = [("id", "=", tapper.id)]
        tapper.action_archive()
        self.assertFalse(tapper.active)
        self.assertFalse(self.env["wt.tapper"].search(domain))
        self.assertEqual(
            self.env["wt.tapper"].search(domain + [("active", "=", False)]),
            tapper,
        )
        tapper.action_unarchive()
        self.assertTrue(tapper.active)
        self.assertEqual(self.env["wt.tapper"].search(domain), tapper)

    def test_archived_employee_cannot_be_changed(self):
        self.tappers[0].action_archive()
        with self.assertRaisesRegex(ValidationError, "cannot be changed after creation"):
            self.tappers[0].write({"employee_id": self.tapper_employees[2].id})

    def test_archive_allows_new_assignment_for_same_employee(self):
        tapper = self.tappers[0]
        tapper.action_archive()
        replacement = self.env["wt.tapper"].create(
            {
                "employee_id": tapper.employee_id.id,
                "foreman_id": self.foremen[1].id,
            }
        )
        self.assertNotEqual(replacement, tapper)
        self.assertTrue(replacement.active)
        self.assertFalse(tapper.active)
        self.assertEqual(tapper.employee_id, replacement.employee_id)
        self.assertEqual(tapper.division_id, self.divisions[0])
        self.assertEqual(replacement.division_id, self.divisions[1])

    def test_form_employee_editable_only_on_creation(self):
        with Form(self.env["wt.tapper"], view="weightrack.view_wt_tapper_form") as form:
            form.division_id = self.divisions[0]
            form.employee_id = self.tapper_employees[2]
        tapper = form.record
        self.assertEqual(tapper.employee_id, self.tapper_employees[2])
        with Form(tapper, view="weightrack.view_wt_tapper_form") as form:
            with self.assertRaises(AssertionError):
                form.employee_id = self.tapper_employees[0]

