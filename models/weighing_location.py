from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..constants.roles import Role


class WeighingLocation(models.Model):
    _name = "wt.weighing.location"
    _description = "Weighing Location"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "estate_id, code, name"

    LOCATION_TYPE_SELECTION = [
        ("warehouse", "Warehouse"),
        ("field", "Field"),
    ]

    active = fields.Boolean(default=True, tracking=True)
    code = fields.Char(string="Code", required=True, index=True, tracking=True)
    name = fields.Char(string="Name", required=True, tracking=True)
    location_type = fields.Selection(
        LOCATION_TYPE_SELECTION,
        string="Location Type",
        required=True,
        default="warehouse",
        tracking=True,
    )
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
    warehouse_weighing_location_id = fields.Many2one(
        "wt.weighing.location",
        string="Warehouse Weighing Location",
        ondelete="restrict",
        domain="[('location_type', '=', 'warehouse'), ('estate_id', '=', estate_id)]",
        tracking=True,
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
    selectable_division_ids = fields.Many2many(
        "wt.division",
        compute="_compute_selectable_division_ids",
        string="Selectable Divisions",
    )
    allowed_division_ids = fields.Many2many(
        "wt.division",
        "wt_weighing_location_division_rel",
        "weighing_location_id",
        "division_id",
        string="Allowed Divisions",
        domain="[('id', 'in', selectable_division_ids)]",
        tracking=True,
    )

    def init(self):
        self.env.cr.execute(
            """
            UPDATE wt_weighing_location
            SET location_type = 'warehouse'
            WHERE location_type IS NULL
            """
        )
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

    @api.constrains(
        "location_type",
        "estate_id",
        "warehouse_weighing_location_id",
        "allowed_division_ids",
    )
    def _check_location_type_consistency(self):
        for location in self:
            if location.location_type == "warehouse":
                if location.warehouse_weighing_location_id:
                    raise ValidationError(
                        _("Warehouse weighing location must not have a parent warehouse weighing location.")
                    )
                continue

            if location.location_type == "field":
                if not location.warehouse_weighing_location_id:
                    raise ValidationError(
                        _("Field weighing location must select a warehouse weighing location.")
                    )
                if location.warehouse_weighing_location_id == location:
                    raise ValidationError(
                        _("Field weighing location cannot reference itself as warehouse weighing location.")
                    )
                if location.warehouse_weighing_location_id.location_type != "warehouse":
                    raise ValidationError(
                        _("Warehouse weighing location must use Warehouse type.")
                    )
                if location.warehouse_weighing_location_id.estate_id != location.estate_id:
                    raise ValidationError(
                        _("Warehouse weighing location must belong to the same estate.")
                    )
                invalid_divisions = (
                    location.allowed_division_ids
                    - location.warehouse_weighing_location_id.allowed_division_ids
                )
                if invalid_divisions:
                    raise ValidationError(
                        _("Field weighing location divisions must be allowed by the selected warehouse weighing location.")
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
        if (
            self.warehouse_weighing_location_id
            and self.warehouse_weighing_location_id.estate_id != self.estate_id
        ):
            self.warehouse_weighing_location_id = False
        return {
            "domain": {
                "operator_id": self.env[
                    "wt.employee.role"
                ].get_employee_domain(self.company_id, Role.OPERATOR),
                "warehouse_weighing_location_id": [
                    ("location_type", "=", "warehouse"),
                    ("estate_id", "=", self.estate_id.id),
                ] if self.estate_id else [("id", "=", False)],
                "allowed_division_ids": [
                    ("id", "in", self.selectable_division_ids.ids)
                ],
            }
        }

    @api.onchange("location_type", "warehouse_weighing_location_id")
    def _onchange_location_type(self):
        for location in self:
            if location.location_type == "warehouse":
                location.warehouse_weighing_location_id = False
            elif location.warehouse_weighing_location_id:
                location.allowed_division_ids = (
                    location.allowed_division_ids
                    & location.warehouse_weighing_location_id.allowed_division_ids
                )
        return {
            "domain": {
                "allowed_division_ids": [
                    ("id", "in", self.selectable_division_ids.ids)
                ],
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

    @api.depends(
        "estate_id",
        "location_type",
        "warehouse_weighing_location_id",
        "warehouse_weighing_location_id.allowed_division_ids",
    )
    def _compute_selectable_division_ids(self):
        division_model = self.env["wt.division"]
        for location in self:
            if not location.estate_id:
                location.selectable_division_ids = division_model.browse()
            elif location.location_type == "field":
                location.selectable_division_ids = (
                    location.warehouse_weighing_location_id.allowed_division_ids
                )
            else:
                location.selectable_division_ids = division_model.search(
                    [
                        ("estate_id", "=", location.estate_id.id),
                        ("active", "=", True),
                    ]
                )
