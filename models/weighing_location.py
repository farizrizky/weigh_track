from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..constants.roles import Role


class WeighingLocation(models.Model):
    _name = "wt.weighing.location"
    _description = "Weighing Location"
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
    operator_id = fields.Many2one(
        "hr.employee",
        string="Operator",
        ondelete="restrict",
        domain="[('id', 'in', allowed_operator_employee_ids)]",
        tracking=True,
    )
    allowed_operator_employee_ids = fields.Many2many(
        "hr.employee",
        compute="_compute_allowed_operator_employee_ids",
        string="Allowed Operator Employees",
    )
    allowed_division_ids = fields.Many2many(
        "wt.division",
        "wt_weighing_location_division_rel",
        "weighing_location_id",
        "division_id",
        string="Allowed Divisions",
        domain="[('estate_id', '=', estate_id)]",
        tracking=True,
    )
    def init(self):
        self.env.cr.execute(
            """
            ALTER TABLE wt_weighing_location
            DROP CONSTRAINT IF EXISTS wt_weighing_location_code_estate_uniq
            """
        )
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS wt_weighing_location_code_estate_active_uniq
            ON wt_weighing_location (code, estate_id)
            WHERE active
            """
        )

    @api.constrains("code", "estate_id")
    def _check_unique_code_estate(self):
        for location in self:
            duplicate = self.search_count(
                [
                    ("id", "!=", location.id),
                    ("code", "=", location.code),
                    ("estate_id", "=", location.estate_id.id),
                    ("active", "=", True),
                ]
            )
            if location.active and duplicate:
                raise ValidationError(
                    _("Weighing location code must be unique per estate.")
                )

    @api.constrains("estate_id", "allowed_division_ids")
    def _check_allowed_division_estate(self):
        for location in self:
            invalid_divisions = location.allowed_division_ids.filtered(
                lambda division: division.estate_id != location.estate_id
            )
            if invalid_divisions:
                raise ValidationError(
                    _("Allowed divisions must belong to the same estate as the weighing location.")
                )

    @api.constrains("operator_id", "estate_id")
    def _check_operator_company(self):
        for location in self:
            self.env["wt.employee.role"].check_employee_allowed(
                location.operator_id,
                location.company_id,
                Role.OPERATOR,
                _("Operator"),
            )

    @api.onchange("estate_id")
    def _onchange_estate_id(self):
        return {
            "domain": {
                "operator_id": self.env[
                    "wt.employee.role"
                ].get_employee_domain(self.company_id, Role.OPERATOR)
            }
        }

    @api.depends("company_id")
    def _compute_allowed_operator_employee_ids(self):
        mapping_model = self.env["wt.employee.role"]
        for location in self:
            location.allowed_operator_employee_ids = mapping_model.get_allowed_employees(
                location.company_id,
                Role.OPERATOR,
            )
