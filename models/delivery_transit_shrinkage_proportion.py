# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DeliveryTransitShrinkageProportion(models.Model):
    _name = "wt.delivery.transit.shrinkage.proportion"
    _description = "Proporsi Susut Transit per Lot"
    _order = "delivery_id, do_lot_line_id"

    delivery_id = fields.Many2one(
        "wt.delivery",
        string="Delivery Task",
        required=True,
        ondelete="cascade",
        index=True,
    )
    do_lot_line_id = fields.Many2one(
        "wt.delivery.do.line.lot",
        string="Lot Line",
        required=True,
        ondelete="cascade",
        index=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        related="do_lot_line_id.lot_id",
        string="Lot Number",
        store=True,
        readonly=True,
    )
    do_line_id = fields.Many2one(
        "wt.delivery.do.line",
        related="do_lot_line_id.do_line_id",
        string="Route Line",
        store=True,
        readonly=True,
    )
    route_type = fields.Selection(
        related="do_line_id.route_type",
        string="Route Type",
        store=True,
        readonly=True,
    )
    physical_qty = fields.Float(
        related="do_lot_line_id.wt_physical_qty",
        string="Berat Fisik (kg)",
        store=True,
        readonly=True,
        digits="Product Unit of Measure",
    )
    proportion_qty = fields.Float(
        string="Proporsi Susut (kg)",
        digits="Product Unit of Measure",
        default=0.0,
        help="Jumlah susut transit yang dialokasikan ke lot ini.",
    )
    delivery_state = fields.Selection(
        related="delivery_id.state",
        string="Status DO",
        store=False,
        readonly=True,
    )

    _sql_constraints = [
        (
            "do_lot_line_unique",
            "unique(delivery_id, do_lot_line_id)",
            "Setiap lot hanya boleh muncul satu kali dalam proporsi susut transit.",
        )
    ]

    @api.constrains("proportion_qty")
    def _check_proportion_qty_non_negative(self):
        for rec in self:
            if rec.proportion_qty < -0.001:
                raise ValidationError(_(
                    "Proporsi susut untuk lot %s tidak boleh negatif."
                ) % (rec.lot_id.name or rec.do_lot_line_id.product_id.display_name))

    def write(self, vals):
        res = super().write(vals)
        # Jika nilai proporsi diubah, reset status tersimpan di delivery parent
        if "proportion_qty" in vals:
            deliveries = self.mapped("delivery_id").filtered("transit_shrinkage_proportion_saved")
            if deliveries:
                deliveries.sudo().write({"transit_shrinkage_proportion_saved": False})
        return res
