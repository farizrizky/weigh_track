# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Product(models.Model):
    _name = "wt.product"
    _description = "Weighing Product"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "company_id, product_id"

    active = fields.Boolean(default=True, tracking=True)
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
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        ondelete="restrict",
        domain="['|', ('product_tmpl_id.company_id', '=', False), ('product_tmpl_id.company_id', '=', company_id)]",
        tracking=True,
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="UoM",
        related="product_id.uom_id",
        store=True,
        readonly=True,
    )

    @api.depends("company_id", "product_id")
    def _compute_name(self):
        for mapping in self:
            product_name = mapping.product_id.display_name if mapping.product_id else ""
            mapping.name = "%s - %s" % (
                mapping.company_id.name or "",
                product_name,
            )

    def init(self):
        self.env.cr.execute(
            """
            ALTER TABLE wt_product
            DROP CONSTRAINT IF EXISTS wt_product_company_product_type_uniq
            """
        )
        self.env.cr.execute(
            """
            DROP INDEX IF EXISTS wt_product_company_product_type_active_uniq
            """
        )
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS wt_product_company_active_uniq
            ON wt_product (company_id)
            WHERE active
            """
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

    @api.constrains("company_id", "active")
    def _check_unique_company(self):
        for mapping in self:
            if not (mapping.active and mapping.company_id):
                continue
            duplicate = self.search(
                [
                    ("id", "!=", mapping.id),
                    ("company_id", "=", mapping.company_id.id),
                    ("active", "=", True),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _("Only one weighing product is allowed per company.")
                )
