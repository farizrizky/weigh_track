# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..constants.product_type import ProductType


class Product(models.Model):
    _name = "wt.product"
    _description = "Product"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "company_id, product_type, product_id"

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )
    product_type = fields.Selection(
        selection=ProductType.SELECTION,
        string="Product Type",
        required=True,
        index=True,
        tracking=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        ondelete="restrict",
        domain="['|', ('product_tmpl_id.company_id', '=', False), ('product_tmpl_id.company_id', '=', company_id)]",
        tracking=True,
    )

    _sql_constraints = [
        (
            "company_product_type_uniq",
            "unique(company_id, product_type)",
            "Product mapping must be unique per company and product type.",
        ),
    ]

    @api.depends("company_id", "product_type", "product_id")
    def _compute_name(self):
        product_type_labels = dict(ProductType.SELECTION)
        for mapping in self:
            label = product_type_labels.get(mapping.product_type, mapping.product_type or "")
            product_name = mapping.product_id.display_name if mapping.product_id else ""
            mapping.name = "%s - %s - %s" % (
                mapping.company_id.name or "",
                label,
                product_name,
            )

    @api.constrains("company_id", "product_id")
    def _check_product_company(self):
        for mapping in self:
            if not mapping.product_id:
                continue
            product_company = mapping.product_id.product_tmpl_id.company_id
            if product_company and product_company != mapping.company_id:
                raise ValidationError(
                    _("Product must belong to the same company or be a global product.")
                )

    @api.constrains("company_id", "product_type")
    def _check_unique_company_product_type(self):
        for mapping in self:
            if not mapping.company_id or not mapping.product_type:
                continue
            duplicate = self.search(
                [
                    ("id", "!=", mapping.id),
                    ("company_id", "=", mapping.company_id.id),
                    ("product_type", "=", mapping.product_type),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _("Only one product mapping is allowed per company and product type.")
                )
