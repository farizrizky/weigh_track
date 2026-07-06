# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductionReceiptCancelWizard(models.TransientModel):
    _name = "wt.production.receipt.cancel.wizard"
    _description = "Production Receipt Cancel Wizard"

    receipt_id = fields.Many2one(
        "wt.production.receipt",
        string="Production Receipt",
        required=True,
        readonly=True,
    )
    reason = fields.Text(
        string="Reason",
        required=True,
    )

    def action_confirm(self):
        self.ensure_one()
        self.receipt_id.action_confirm_cancel(self.reason)
        return {"type": "ir.actions.act_window_close"}
