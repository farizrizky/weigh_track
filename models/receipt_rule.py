# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ReceiptRule(models.Model):
    _name = "wt.receipt.rule"
    _description = "Receipt Rule"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "weighing_location_id, division_id"

    active = fields.Boolean(default=True, tracking=True)
    name = fields.Char(
        compute="_compute_name",
        store=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="weighing_location_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    estate_id = fields.Many2one(
        "wt.estate",
        string="Estate",
        related="weighing_location_id.estate_id",
        store=True,
        readonly=True,
        index=True,
    )
    weighing_location_id = fields.Many2one(
        "wt.weighing.location",
        string="Weighing Location",
        required=True,
        ondelete="restrict",
        domain="[('location_type', '=', 'warehouse')]",
        index=True,
        tracking=True,
    )
    allowed_division_ids = fields.Many2many(
        "wt.division",
        compute="_compute_allowed_division_ids",
        string="Allowed Divisions",
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Division",
        required=True,
        ondelete="restrict",
        domain="[('id', 'in', allowed_division_ids)]",
        index=True,
        tracking=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Warehouse",
        required=True,
        ondelete="restrict",
        domain="[('company_id', '=', company_id), ('estate_id', '=', estate_id)]",
        tracking=True,
    )
    allowed_location_ids = fields.Many2many(
        "stock.location",
        compute="_compute_allowed_location_ids",
        string="Allowed Locations",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Location",
        required=True,
        ondelete="restrict",
        domain="[('id', 'in', allowed_location_ids)]",
        tracking=True,
    )
    operation_type_id = fields.Many2one(
        "stock.picking.type",
        string="Operation Type",
        required=True,
        ondelete="restrict",
        domain="[('warehouse_id', '=', warehouse_id)]",
        tracking=True,
    )

    def init(self):
        self.env.cr.execute(
            """
            ALTER TABLE wt_receipt_rule
            DROP CONSTRAINT IF EXISTS wt_receipt_rule_receipt_rule_uniq
            """
        )
        self.env.cr.execute(
            """
            DROP INDEX IF EXISTS wt_receipt_rule_scope_active_uniq
            """
        )
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS wt_receipt_rule_scope_active_uniq
            ON wt_receipt_rule (weighing_location_id, division_id)
            WHERE active
            """
        )

    @api.depends("weighing_location_id", "division_id")
    def _compute_name(self):
        for mapping in self:
            mapping.name = "%s - %s" % (
                mapping.weighing_location_id.name or "",
                mapping.division_id.name or "",
            )

    @api.depends("weighing_location_id")
    def _compute_allowed_division_ids(self):
        for mapping in self:
            mapping.allowed_division_ids = mapping.weighing_location_id.allowed_division_ids

    @api.depends("warehouse_id", "company_id")
    def _compute_allowed_location_ids(self):
        location_model = self.env["stock.location"]
        for mapping in self:
            if not mapping.warehouse_id or not mapping.warehouse_id.view_location_id:
                mapping.allowed_location_ids = location_model.browse()
                continue

            domain = [
                ("id", "child_of", mapping.warehouse_id.view_location_id.id),
                ("usage", "=", "internal"),
            ]
            if mapping.company_id:
                domain.append(("company_id", "in", [False, mapping.company_id.id]))

            mapping.allowed_location_ids = location_model.search(domain)

    @api.onchange("weighing_location_id")
    def _onchange_weighing_location_id(self):
        for mapping in self:
            mapping.division_id = False
            if mapping.weighing_location_id:
                mapping.warehouse_id = False
                mapping.location_id = False
                mapping.operation_type_id = False

    @api.onchange("warehouse_id")
    def _onchange_warehouse_id(self):
        for mapping in self:
            mapping.operation_type_id = False
            mapping.location_id = False

    @api.constrains(
        "company_id",
        "estate_id",
        "weighing_location_id",
        "division_id",
        "active",
    )
    def _check_unique_company_location_division(self):
        for mapping in self:
            if not (
                mapping.active
                and mapping.company_id
                and mapping.weighing_location_id
                and mapping.division_id
            ):
                continue

            duplicate = self.search(
                [
                    ("id", "!=", mapping.id),
                    ("company_id", "=", mapping.company_id.id),
                    ("weighing_location_id", "=", mapping.weighing_location_id.id),
                    ("division_id", "=", mapping.division_id.id),
                    ("active", "=", True),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _(
                        "Receipt Rule already exists for company '%(company)s', "
                        "weighing location '%(location)s', and division '%(division)s'. "
                        "Please use the existing rule or change one of those values."
                    )
                    % {
                        "company": mapping.company_id.display_name,
                        "location": mapping.weighing_location_id.display_name,
                        "division": mapping.division_id.display_name,
                    }
                )

    @api.constrains(
        "company_id",
        "estate_id",
        "weighing_location_id",
        "division_id",
        "warehouse_id",
        "location_id",
        "operation_type_id",
    )
    def _check_mapping_consistency(self):
        for mapping in self:
            if (
                mapping.weighing_location_id
                and mapping.weighing_location_id.company_id != mapping.company_id
            ):
                raise ValidationError(
                    _("Weighing location must belong to the same company.")
                )

            if (
                mapping.weighing_location_id
                and mapping.weighing_location_id.location_type != "warehouse"
            ):
                raise ValidationError(
                    _("Receipt Rule can only use Warehouse weighing locations.")
                )

            if mapping.division_id and mapping.division_id.company_id != mapping.company_id:
                raise ValidationError(_("Division must belong to the same company."))

            if (
                mapping.weighing_location_id
                and mapping.division_id
                and mapping.division_id not in mapping.weighing_location_id.allowed_division_ids
            ):
                raise ValidationError(
                    _("Division must be allowed in the selected weighing location.")
                )

            if (
                mapping.warehouse_id
                and mapping.warehouse_id.company_id != mapping.company_id
            ):
                raise ValidationError(_("Warehouse must belong to the same company."))

            if (
                mapping.warehouse_id
                and mapping.warehouse_id.estate_id != mapping.estate_id
            ):
                raise ValidationError(_("Warehouse must belong to the same estate."))

            location_company = mapping.location_id.company_id
            if location_company and location_company != mapping.company_id:
                raise ValidationError(
                    _("Location must belong to the same company or be a shared location.")
                )

            if mapping.location_id and mapping.location_id.usage != "internal":
                raise ValidationError(_("Location must be an internal stock location."))

            if (
                mapping.location_id
                and mapping.warehouse_id
                and not mapping._is_location_under_selected_warehouse()
            ):
                raise ValidationError(
                    _("Location must be under the selected warehouse.")
                )

            operation_company = mapping.operation_type_id.company_id
            if operation_company and operation_company != mapping.company_id:
                raise ValidationError(
                    _("Operation type must belong to the same company.")
                )

            if (
                mapping.operation_type_id.warehouse_id
                and mapping.operation_type_id.warehouse_id != mapping.warehouse_id
            ):
                raise ValidationError(
                    _("Operation type must belong to the selected warehouse.")
                )

    def _is_location_under_selected_warehouse(self):
        self.ensure_one()
        warehouse_root = self.warehouse_id.view_location_id
        if not self.location_id or not warehouse_root:
            return True

        if self.location_id == warehouse_root:
            return True

        if self.location_id.parent_path and warehouse_root.parent_path:
            return self.location_id.parent_path.startswith(warehouse_root.parent_path)

        parent = self.location_id.parent_id
        while parent:
            if parent == warehouse_root:
                return True
            parent = parent.parent_id
        return False
