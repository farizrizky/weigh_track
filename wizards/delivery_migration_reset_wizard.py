# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DeliveryMigrationResetWizard(models.TransientModel):
    _name = "wt.delivery.migration.reset.wizard"
    _description = "Delivery Migration Reset Wizard"

    delivery_id = fields.Many2one(
        "wt.delivery",
        string="Delivery Task",
        required=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="delivery_id.company_id",
        readonly=True,
    )
    picking_count = fields.Integer(
        string="Transfer Count",
        compute="_compute_reset_summary",
    )
    movement_count = fields.Integer(
        string="Movement Count",
        compute="_compute_reset_summary",
    )
    transit_lot_count = fields.Integer(
        string="Transit Lot Count",
        compute="_compute_reset_summary",
    )
    shrinkage_quantity = fields.Float(
        string="Shrinkage to Restore",
        compute="_compute_reset_summary",
        digits="Product Unit of Measure",
    )
    reason = fields.Text(
        string="Reset Reason",
        required=True,
    )
    confirmation = fields.Char(
        string="Confirmation",
        required=True,
        help="Type the delivery number exactly to confirm the migration reset.",
    )

    @api.depends("delivery_id")
    def _compute_reset_summary(self):
        shrinkage_location = self.env.ref(
            "weightrack.stock_location_wt_inventory_loss_susut",
            raise_if_not_found=False,
        )
        shrinkage_location_ids = set()
        if shrinkage_location:
            shrinkage_location_ids = set(
                self.env["stock.location"].sudo().search(
                    [("id", "child_of", shrinkage_location.id)]
                ).ids
            )
        for wizard in self:
            delivery = wizard.delivery_id
            if not delivery:
                wizard.picking_count = 0
                wizard.movement_count = 0
                wizard.transit_lot_count = 0
                wizard.shrinkage_quantity = 0.0
                continue
            pickings = delivery._get_migration_reset_original_pickings()
            moves = delivery._get_migration_reset_original_moves()
            transit_lots = delivery._get_migration_reset_transit_lots()
            wizard.picking_count = len(pickings)
            wizard.movement_count = len(moves)
            wizard.transit_lot_count = len(transit_lots)
            wizard.shrinkage_quantity = sum(
                moves.move_line_ids.filtered(
                    lambda line: line.location_dest_id.id
                    in shrinkage_location_ids
                    and not (
                        line.move_id.description_picking or ""
                    ).startswith(
                        (
                            "Consume old lots for transit merge",
                            "Produce new merged lot for transit",
                        )
                    )
                ).mapped("quantity")
            )

    def action_confirm_reset(self):
        self.ensure_one()
        delivery = self.delivery_id
        if (self.confirmation or "").strip() != delivery.name:
            raise ValidationError(
                _(
                    "Confirmation does not match the delivery number. "
                    "Type %(delivery)s exactly."
                )
                % {"delivery": delivery.name}
            )
        delivery._action_migration_reset(self.reason)
        return {
            "type": "ir.actions.act_window",
            "name": _("Delivery Task"),
            "res_model": "wt.delivery",
            "res_id": delivery.id,
            "view_mode": "form",
            "target": "current",
        }
