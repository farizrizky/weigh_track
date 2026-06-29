# -*- coding: utf-8 -*-

from odoo import fields, models


class StockLot(models.Model):
    _inherit = "stock.lot"

    division_id = fields.Many2one(
        "wt.division",
        string="Division",
        ondelete="restrict",
        index=True,
    )
    production_date = fields.Date(
        string="Production Date",
        index=True,
    )
