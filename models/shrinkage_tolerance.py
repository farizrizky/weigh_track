# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..constants.product_types import ProductType


class ShrinkageTolerance(models.Model):
    _name = "wt.shrinkage.tolerance"
    _description = "Shrinkage Tolerance"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "company_id, product_type, division_id"

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
    product_type = fields.Selection(
        selection=ProductType.SELECTION,
        string="Product Type",
        required=True,
        index=True,
        tracking=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Division",
        required=True,
        ondelete="restrict",
        domain="[('company_id', '=', company_id)]",
        index=True,
        tracking=True,
    )
    shrinkage_tolerance_percentage = fields.Float(
        string="Shrinkage Tolerance (%)",
        required=True,
        tracking=True,
        help="Maximum allowed production shrinkage percentage when production date differs from warehouse weighing date.",
    )

    def init(self):
        self.env.cr.execute(
            """
            ALTER TABLE wt_shrinkage_tolerance
            DROP CONSTRAINT IF EXISTS wt_shrinkage_tolerance_company_product_type_division_uniq
            """
        )
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS wt_shrinkage_tolerance_scope_active_uniq
            ON wt_shrinkage_tolerance (company_id, product_type, division_id)
            WHERE active
            """
        )

    @api.depends("company_id", "product_type", "division_id")
    def _compute_name(self):
        product_type_labels = dict(ProductType.SELECTION)
        for tolerance in self:
            label = product_type_labels.get(
                tolerance.product_type,
                tolerance.product_type or "",
            )
            tolerance.name = "%s - %s - %s" % (
                tolerance.company_id.name or "",
                label,
                tolerance.division_id.name or "",
            )

    @api.constrains("company_id", "division_id")
    def _check_division_company(self):
        for tolerance in self:
            if (
                tolerance.division_id
                and tolerance.company_id
                and tolerance.division_id.company_id != tolerance.company_id
            ):
                raise ValidationError(
                    _("Division must belong to the same company.")
                )

    @api.constrains(
        "company_id",
        "product_type",
        "division_id",
        "active",
    )
    def _check_unique_company_product_type_division(self):
        for tolerance in self:
            if not (
                tolerance.active
                and tolerance.company_id
                and tolerance.product_type
                and tolerance.division_id
            ):
                continue
            duplicate = self.search(
                [
                    ("id", "!=", tolerance.id),
                    ("company_id", "=", tolerance.company_id.id),
                    ("product_type", "=", tolerance.product_type),
                    ("division_id", "=", tolerance.division_id.id),
                    ("active", "=", True),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _(
                        "Shrinkage tolerance already exists for company '%(company)s', "
                        "product type '%(product_type)s', and division '%(division)s'."
                    )
                    % {
                        "company": tolerance.company_id.display_name,
                        "product_type": dict(ProductType.SELECTION).get(
                            tolerance.product_type,
                            tolerance.product_type,
                        ),
                        "division": tolerance.division_id.display_name,
                    }
                )

    @api.constrains("shrinkage_tolerance_percentage")
    def _check_shrinkage_tolerance_percentage(self):
        for tolerance in self:
            percentage = tolerance.shrinkage_tolerance_percentage
            if percentage < 0 or percentage > 100:
                raise ValidationError(
                    _("Shrinkage tolerance percentage must be between 0 and 100.")
                )
