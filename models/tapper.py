from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..constants.roles import Role


class Tapper(models.Model):
    _name = "wt.tapper"
    _description = "Tapper"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "division_id, foreman_id, employee_id"

    active = fields.Boolean(default=True, tracking=True)
    name = fields.Char(
        string="Name",
        related="employee_id.name",
        store=True,
        readonly=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Tapper",
        required=True,
        ondelete="restrict",
        index=True,
        domain="[('id', 'in', allowed_tapper_employee_ids)]",
        tracking=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Division",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    foreman_id = fields.Many2one(
        "wt.foreman",
        string="Foreman",
        ondelete="restrict",
        index=True,
        domain="[('division_id', '=', division_id)]",
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="division_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    allowed_tapper_employee_ids = fields.Many2many(
        "hr.employee",
        compute="_compute_allowed_tapper_employee_ids",
        string="Allowed Tapper Employees",
    )

    def init(self):
        self.env.cr.execute(
            """
            ALTER TABLE wt_tapper
            DROP CONSTRAINT IF EXISTS wt_tapper_employee_uniq
            """
        )
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS wt_tapper_employee_active_uniq
            ON wt_tapper (employee_id)
            WHERE active
            """
        )

    @api.constrains("employee_id", "active")
    def _check_unique_employee(self):
        for tapper in self:
            if not (tapper.active and tapper.employee_id):
                continue
            duplicate = self.search_count(
                [
                    ("id", "!=", tapper.id),
                    ("employee_id", "=", tapper.employee_id.id),
                    ("active", "=", True),
                ]
            )
            if duplicate:
                raise ValidationError(_("Tapper employee must be unique."))

    @api.constrains("employee_id", "division_id")
    def _check_employee_company(self):
        for tapper in self:
            self.env["wt.employee.role"].check_employee_allowed(
                tapper.employee_id,
                tapper.company_id,
                Role.TAPPER,
                _("Tapper"),
            )

    @api.constrains("division_id", "foreman_id")
    def _check_foreman_division(self):
        for tapper in self:
            if (
                tapper.foreman_id
                and tapper.division_id
                and tapper.foreman_id.division_id != tapper.division_id
            ):
                raise ValidationError(_("Tapper and foreman must belong to the same division."))

    @api.onchange("division_id")
    def _onchange_division_id(self):
        if self.foreman_id and self.foreman_id.division_id != self.division_id:
            self.foreman_id = False

        foreman_domain = [("division_id", "=", self.division_id.id)]
        if not self.division_id:
            foreman_domain = [("id", "=", False)]

        return {
            "domain": {
                "employee_id": self.env[
                    "wt.employee.role"
                ].get_employee_domain(self.company_id, Role.TAPPER),
                "foreman_id": foreman_domain,
            }
        }

    @api.depends("company_id")
    def _compute_allowed_tapper_employee_ids(self):
        mapping_model = self.env["wt.employee.role"]
        for tapper in self:
            tapper.allowed_tapper_employee_ids = mapping_model.get_allowed_employees(
                tapper.company_id,
                Role.TAPPER,
            )
