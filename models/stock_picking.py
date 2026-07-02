# -*- coding: utf-8 -*-

from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    production_receipt_id = fields.Many2one(
        "wt.production.receipt",
        string="Production Receipt",
        readonly=True,
        copy=False,
        index=True,
    )
    production_receipt_reverse_id = fields.Many2one(
        "wt.production.receipt",
        string="Production Receipt Reversal",
        readonly=True,
        copy=False,
        index=True,
    )
    receive_from_employee_id = fields.Many2one(
        "hr.employee",
        string="Receive From",
        readonly=True,
        copy=False,
        index=True,
    )
