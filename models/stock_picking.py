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
    wt_push_done = fields.Boolean(
        string="Push Selesai",
        default=False,
        copy=False,
        help="Ditandai True secara otomatis saat operator selesai push semua data timbang via API.",
    )
    wt_push_done_at = fields.Datetime(
        string="Waktu Push Selesai",
        readonly=True,
        copy=False,
        help="Waktu operator menyelesaikan push data timbang.",
    )
