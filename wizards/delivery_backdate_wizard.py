# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DeliveryBackdateWizard(models.TransientModel):
    _name = "wt.delivery.backdate.wizard"
    _description = "Correct Delivery Effective Date"

    delivery_id = fields.Many2one(
        "wt.delivery",
        string="Delivery",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    current_date = fields.Date(
        string="Current Effective Date",
        related="delivery_id.date",
        readonly=True,
    )
    effective_date = fields.Date(
        string="New Effective Date",
        required=True,
    )
    reason = fields.Text(
        string="Correction Reason",
        required=True,
    )
    picking_ids = fields.Many2many(
        "stock.picking",
        string="Affected Transfers",
        compute="_compute_affected_records",
    )
    move_ids = fields.Many2many(
        "stock.move",
        string="Affected Stock Movements",
        compute="_compute_affected_records",
    )
    picking_count = fields.Integer(
        string="Transfer Count",
        compute="_compute_affected_records",
    )
    move_count = fields.Integer(
        string="Stock Movement Count",
        compute="_compute_affected_records",
    )

    @api.depends("delivery_id")
    def _compute_affected_records(self):
        StockMove = self.env["stock.move"]
        for wizard in self:
            if not wizard.delivery_id:
                wizard.picking_ids = False
                wizard.move_ids = False
                wizard.picking_count = 0
                wizard.move_count = 0
                continue
            pickings = wizard.delivery_id.picking_ids.filtered(
                lambda picking: picking.state == "done"
            )
            direct_moves = StockMove.search([
                ("state", "=", "done"),
                ("picking_id", "=", False),
                ("origin", "=", wizard.delivery_id.name),
                ("is_inventory", "=", True),
            ])
            moves = pickings.move_ids.filtered(
                lambda move: move.state == "done"
            ) | direct_moves
            wizard.picking_ids = pickings
            wizard.move_ids = moves
            wizard.picking_count = len(pickings)
            wizard.move_count = len(moves)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        delivery_id = values.get("delivery_id") or self.env.context.get(
            "default_delivery_id"
        )
        if delivery_id:
            delivery = self.env["wt.delivery"].browse(delivery_id)
            values.setdefault("effective_date", delivery.date)
        return values

    def _check_posted_valuation_entries(self):
        self.ensure_one()
        if not self.move_ids or "stock.valuation.layer" not in self.env.registry.models:
            return
        ValuationLayer = self.env["stock.valuation.layer"].sudo()
        if not {"stock_move_id", "account_move_id"}.issubset(
            ValuationLayer._fields
        ):
            return
        posted_layers = ValuationLayer.search([
            ("stock_move_id", "in", self.move_ids.ids),
            ("account_move_id.state", "=", "posted"),
        ], limit=1)
        if posted_layers:
            raise ValidationError(_(
                "The effective date cannot be corrected because at least one affected stock movement "
                "already has a posted valuation journal entry. Reverse or correct the accounting entry first."
            ))

    def action_apply(self):
        self.ensure_one()
        delivery = self.delivery_id
        if not self.env.user.has_group("weightrack.group_admin"):
            raise ValidationError(_(
                "Only a WeighTrack Administrator can correct an effective delivery date."
            ))
        if delivery.state != "done":
            raise ValidationError(_(
                "Effective date correction is only available for a completed delivery."
            ))
        today = delivery._get_business_today()
        if self.effective_date >= today:
            raise ValidationError(_(
                "The corrected effective date must be earlier than today."
            ))
        if not (self.reason or "").strip():
            raise ValidationError(_("Correction Reason is required."))
        if not self.move_ids:
            raise ValidationError(_(
                "No completed stock movement was found for this delivery."
            ))

        self._check_posted_valuation_entries()
        old_date = delivery.date
        effective_datetime = delivery._get_planned_movement_datetime(
            self.effective_date
        )
        delivery.with_context(wt_allow_backdate_update=True).write({
            "date": self.effective_date,
            "backdate_reason": self.reason.strip(),
            "backdate_effective_at": effective_datetime,
            "backdate_applied_at": fields.Datetime.now(),
            "backdate_applied_by_id": self.env.user.id,
        })
        delivery.do_line_ids.write({"scheduled_date": effective_datetime})
        for picking in self.picking_ids:
            delivery._sync_picking_effective_date(picking, effective_datetime)

        direct_moves = self.move_ids.filtered(lambda move: not move.picking_id)
        delivery._sync_moves_effective_date(direct_moves, effective_datetime)
        delivery.do_line_ids.mapped("generated_transit_lot_id").sudo().write({
            "wt_transit_date": self.effective_date,
        })
        delivery.message_post(body=_(
            "Effective delivery date corrected from %(old_date)s to %(new_date)s by %(user)s. "
            "Reason: %(reason)s"
        ) % {
            "old_date": old_date,
            "new_date": self.effective_date,
            "user": self.env.user.display_name,
            "reason": self.reason.strip(),
        })
        return {"type": "ir.actions.act_window_close"}
