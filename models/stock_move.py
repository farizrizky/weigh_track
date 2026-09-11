# -*- coding: utf-8 -*-

from odoo import fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    wt_delivery_id = fields.Many2one(
        "wt.delivery",
        string="WeighTrack Delivery",
        index=True,
        copy=False,
        ondelete="set null",
    )
    wt_delivery_do_line_id = fields.Many2one(
        "wt.delivery.do.line",
        string="WeighTrack Delivery Plan Line",
        index=True,
        copy=False,
        ondelete="set null",
    )
    wt_is_delivery_rollback = fields.Boolean(
        string="Delivery Rollback Movement",
        default=False,
        index=True,
        copy=False,
    )
    wt_reversal_of_move_id = fields.Many2one(
        "stock.move",
        string="Reversal of Stock Move",
        index=True,
        copy=False,
        ondelete="restrict",
    )
    wt_exclude_from_weightrack_reports = fields.Boolean(
        string="Exclude from WeighTrack Reports",
        default=False,
        index=True,
        copy=False,
        help=(
            "When enabled, this move is retained for Inventory/Accounting audit "
            "but ignored by WeighTrack operational reports."
        ),
    )
