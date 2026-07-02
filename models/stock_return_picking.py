# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError


class StockReturnPicking(models.TransientModel):
    _inherit = "stock.return.picking"

    def _check_weightrack_manual_return_allowed(self):
        if self.env.context.get("allow_production_receipt_return"):
            return
        blocked = self.filtered(
            lambda wizard: wizard.picking_id.production_receipt_id
            or wizard.picking_id.production_receipt_reverse_id
        )
        if blocked:
            raise UserError(
                _(
                    "Inventory Receipt from Production Receipt cannot be returned "
                    "manually. Please cancel it from the Production Receipt document."
                )
            )

    def action_create_returns(self):
        self._check_weightrack_manual_return_allowed()
        return super().action_create_returns()

    def action_create_returns_all(self):
        self._check_weightrack_manual_return_allowed()
        return super().action_create_returns_all()
