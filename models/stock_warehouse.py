# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    estate_id = fields.Many2one(
        "wt.estate",
        string="Estate",
        ondelete="restrict",
        index=True,
        domain="[('company_id', '=', company_id)]",
    )

    @api.onchange("company_id")
    def _onchange_company_id_weightrack_estate(self):
        for warehouse in self:
            if (
                warehouse.estate_id
                and warehouse.company_id
                and warehouse.estate_id.company_id != warehouse.company_id
            ):
                warehouse.estate_id = False

    @api.constrains("company_id", "estate_id")
    def _check_estate_company(self):
        for warehouse in self:
            if (
                warehouse.estate_id
                and warehouse.company_id
                and warehouse.estate_id.company_id != warehouse.company_id
            ):
                raise ValidationError(
                    _("Warehouse estate must belong to the same company.")
                )
