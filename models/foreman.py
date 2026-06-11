from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..constants.roles import Role


class Foreman(models.Model):
    _name = "wt.foreman"
    _description = "Foreman"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "division_id, employee_id"

    name = fields.Char(
        string="Name",
        related="employee_id.name",
        store=True,
        readonly=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Foreman",
        required=True,
        ondelete="restrict",
        index=True,
        domain="[('id', 'in', allowed_foreman_employee_ids)]",
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
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="division_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    tapper_ids = fields.One2many(
        "wt.tapper",
        "foreman_id",
        string="Tappers",
    )
    allowed_foreman_employee_ids = fields.Many2many(
        "hr.employee",
        compute="_compute_allowed_foreman_employee_ids",
        string="Allowed Foreman Employees",
    )
    _sql_constraints = [
        (
            "employee_division_uniq",
            "unique(employee_id, division_id)",
            "Foreman employee must be unique per division.",
        ),
    ]

    @api.constrains("employee_id", "division_id")
    def _check_unique_employee_division(self):
        for foreman in self:
            duplicate = self.search_count(
                [
                    ("id", "!=", foreman.id),
                    ("employee_id", "=", foreman.employee_id.id),
                    ("division_id", "=", foreman.division_id.id),
                ]
            )
            if duplicate:
                raise ValidationError(_("Foreman employee must be unique per division."))

    @api.constrains("employee_id", "division_id")
    def _check_employee_company(self):
        for foreman in self:
            self.env["wt.employee.role"].check_employee_allowed(
                foreman.employee_id,
                foreman.company_id,
                Role.FOREMAN,
                _("Foreman"),
            )

    @api.onchange("division_id")
    def _onchange_division_id(self):
        return {
            "domain": {
                "employee_id": self.env[
                    "wt.employee.role"
                ].get_employee_domain(self.company_id, Role.FOREMAN)
            }
        }

    @api.depends("company_id")
    def _compute_allowed_foreman_employee_ids(self):
        mapping_model = self.env["wt.employee.role"]
        for foreman in self:
            foreman.allowed_foreman_employee_ids = mapping_model.get_allowed_employees(
                foreman.company_id,
                Role.FOREMAN,
            )
