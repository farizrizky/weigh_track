# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ReceiptRule(models.Model):
    _name = "wt.receipt.rule"
    _description = "Receipt Rule"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "weighing_location_id, division_id, product_id"

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
    weighing_location_id = fields.Many2one(
        "wt.weighing.location",
        string="Weighing Location",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    allowed_division_ids = fields.Many2many(
        "wt.division",
        compute="_compute_allowed_division_ids",
        string="Allowed Divisions",
    )
    allowed_product_ids = fields.Many2many(
        "product.product",
        compute="_compute_allowed_product_ids",
        string="Allowed Products",
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
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        ondelete="restrict",
        domain="[('id', 'in', allowed_product_ids)]",
        index=True,
        tracking=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Warehouse",
        required=True,
        ondelete="restrict",
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Location",
        required=True,
        ondelete="restrict",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
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

    _sql_constraints = [
        (
            "receipt_rule_uniq",
            "unique(weighing_location_id, division_id, product_id)",
            "Receipt Rule must be unique per company, weighing location, division, and product.",
        ),
    ]

    @api.depends("weighing_location_id", "division_id", "product_id")
    def _compute_name(self):
        for mapping in self:
            mapping.name = "%s - %s - %s" % (
                mapping.weighing_location_id.name or "",
                mapping.division_id.name or "",
                mapping.product_id.display_name or "",
            )

    @api.depends("weighing_location_id")
    def _compute_allowed_division_ids(self):
        for mapping in self:
            mapping.allowed_division_ids = mapping.weighing_location_id.allowed_division_ids

    @api.depends("company_id")
    def _compute_allowed_product_ids(self):
        product_config = self.env["wt.product"].sudo()
        for mapping in self:
            if not mapping.company_id:
                mapping.allowed_product_ids = self.env["product.product"].browse()
                continue
            mapping.allowed_product_ids = product_config.search(
                [("company_id", "=", mapping.company_id.id)]
            ).mapped("product_id")

    @api.onchange("weighing_location_id")
    def _onchange_weighing_location_id(self):
        for mapping in self:
            mapping.division_id = False
            mapping.product_id = False
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
        "weighing_location_id",
        "division_id",
        "product_id",
    )
    def _check_unique_company_location_division_product(self):
        for mapping in self:
            if not (
                mapping.company_id
                and mapping.weighing_location_id
                and mapping.division_id
                and mapping.product_id
            ):
                continue

            duplicate = self.search(
                [
                    ("id", "!=", mapping.id),
                    ("company_id", "=", mapping.company_id.id),
                    ("weighing_location_id", "=", mapping.weighing_location_id.id),
                    ("division_id", "=", mapping.division_id.id),
                    ("product_id", "=", mapping.product_id.id),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _(
                        "Receipt Rule already exists for company '%(company)s', "
                        "weighing location '%(location)s', division '%(division)s', "
                        "and product '%(product)s'. Please use the existing rule "
                        "or change one of those values."
                    )
                    % {
                        "company": mapping.company_id.display_name,
                        "location": mapping.weighing_location_id.display_name,
                        "division": mapping.division_id.display_name,
                        "product": mapping.product_id.display_name,
                    }
                )

    @api.constrains(
        "company_id",
        "weighing_location_id",
        "division_id",
        "product_id",
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

            product_company = mapping.product_id.product_tmpl_id.company_id
            if product_company and product_company != mapping.company_id:
                raise ValidationError(
                    _("Product must belong to the same company or be a global product.")
                )

            product_configured = not mapping.product_id or not mapping.company_id
            if mapping.product_id and mapping.company_id:
                product_configured = self.env["wt.product"].sudo().search_count(
                    [
                        ("company_id", "=", mapping.company_id.id),
                        ("product_id", "=", mapping.product_id.id),
                    ]
                )
            if not product_configured:
                raise ValidationError(
                    _("Product must be configured in Product for the same company.")
                )

            if mapping.warehouse_id and mapping.warehouse_id.company_id != mapping.company_id:
                raise ValidationError(_("Warehouse must belong to the same company."))

            location_company = mapping.location_id.company_id
            if location_company and location_company != mapping.company_id:
                raise ValidationError(
                    _("Location must belong to the same company or be a shared location.")
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
