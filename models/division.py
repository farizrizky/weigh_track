from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..constants.roles import Role


class Division(models.Model):
    _name = "wt.division"
    _description = "Division"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "estate_id, code, name"

    active = fields.Boolean(default=True, tracking=True)
    code = fields.Char(string="Code", required=True, index=True, tracking=True)
    name = fields.Char(string="Name", required=True, tracking=True)
    estate_id = fields.Many2one(
        "wt.estate",
        string="Estate",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="estate_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    clerk_id = fields.Many2one(
        "hr.employee",
        string="Clerk",
        ondelete="restrict",
        domain="[('id', 'in', allowed_clerk_employee_ids)]",
        tracking=True,
    )
    allowed_clerk_employee_ids = fields.Many2many(
        "hr.employee",
        compute="_compute_allowed_clerk_employee_ids",
        string="Allowed Clerk Employees",
    )
    def init(self):
        self.env.cr.execute(
            """
            ALTER TABLE wt_division
            DROP CONSTRAINT IF EXISTS wt_division_code_estate_uniq
            """
        )
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS wt_division_code_estate_active_uniq
            ON wt_division (code, estate_id)
            WHERE active
            """
        )

    @api.constrains("code", "estate_id")
    def _check_unique_code_estate(self):
        for division in self:
            duplicate = self.search_count(
                [
                    ("id", "!=", division.id),
                    ("code", "=", division.code),
                    ("estate_id", "=", division.estate_id.id),
                    ("active", "=", True),
                ]
            )
            if division.active and duplicate:
                raise ValidationError(_("Division code must be unique per estate."))

    @api.constrains("clerk_id", "estate_id")
    def _check_clerk_company(self):
        for division in self:
            self.env["wt.employee.role"].check_employee_allowed(
                division.clerk_id,
                division.company_id,
                Role.CLERK,
                _("Clerk"),
            )

    @api.onchange("estate_id")
    def _onchange_estate_id(self):
        return {
            "domain": {
                "clerk_id": self.env[
                    "wt.employee.role"
                ].get_employee_domain(self.company_id, Role.CLERK)
            }
        }

    @api.depends("company_id")
    def _compute_allowed_clerk_employee_ids(self):
        mapping_model = self.env["wt.employee.role"]
        for division in self:
            division.allowed_clerk_employee_ids = mapping_model.get_allowed_employees(
                division.company_id,
                Role.CLERK,
            )
