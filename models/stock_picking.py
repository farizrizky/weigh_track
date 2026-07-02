# -*- coding: utf-8 -*-

from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    wt_delivery_id = fields.Many2one(
        "wt.delivery",
        string="Tugas Pengiriman",
        ondelete="set null",
        index=True,
        copy=False,
    )
    wt_operator_id = fields.Many2one(
        "hr.employee",
        string="Operator",
        index=True,
        copy=False,
        help="Operator yang bertanggung jawab atas Delivery Order ini.",
    )
