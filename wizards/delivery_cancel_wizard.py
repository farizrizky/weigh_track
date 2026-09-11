# -*- coding: utf-8 -*-

from odoo import fields, models


class DeliveryCancelWizard(models.TransientModel):
    _name = "wt.delivery.cancel.wizard"
    _description = "Delivery Stock Rollback Wizard"

    delivery_id = fields.Many2one(
        "wt.delivery",
        string="Tugas Pengiriman",
        required=True,
        readonly=True,
    )
    reason = fields.Text(
        string="Alasan Pembatalan",
        required=True,
    )

    def action_confirm(self):
        self.ensure_one()
        self.delivery_id.action_confirm_cancel(self.reason)
        return {"type": "ir.actions.act_window_close"}
