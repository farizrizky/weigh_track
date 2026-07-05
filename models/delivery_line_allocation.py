# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DeliveryLineAllocation(models.Model):
    _name = "wt.delivery.line.allocation"
    _description = "Alokasi Selisih Timbang Pengiriman"
    _order = "move_line_id, id"

    move_line_id = fields.Many2one(
        "stock.move.line",
        string="Baris Timbang",
        required=True,
        ondelete="cascade",
        index=True,
    )
    wt_delivery_id = fields.Many2one(
        "wt.delivery",
        related="move_line_id.wt_delivery_id",
        store=True,
        index=True,
        string="Tugas Pengiriman",
        readonly=True,
    )
    reason_id = fields.Many2one(
        "wt.stock.opname.difference.reason",
        string="Alasan",
        required=True,
        domain="[('active', '=', True)]",
    )
    qty = fields.Float(
        string="Qty Alokasi",
        digits="Product Unit of Measure",
        required=True,
    )
    location_dest_id = fields.Many2one(
        "stock.location",
        string="Lokasi Tujuan",
        required=True,
        domain="[('usage', 'not in', ['view'])]",
        help="Lokasi tujuan scrap untuk alokasi ini (default dari alasan).",
    )
    note = fields.Char(
        string="Catatan",
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="No. Lot",
        related="move_line_id.lot_id",
        readonly=True,
        store=False,
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="Satuan",
        related="move_line_id.product_uom_id",
        readonly=True,
    )

    @api.onchange("reason_id")
    def _onchange_reason_id(self):
        """Auto-fill lokasi dari reason. Auto-fill qty dengan sisa unallocated."""
        if self.reason_id and self.reason_id.location_dest_id:
            self.location_dest_id = self.reason_id.location_dest_id

        if self.reason_id and self.move_line_id and not self._origin.id:
            already_allocated = sum(a.qty for a in self.move_line_id.wt_allocation_ids)
            diff_abs = abs(self.move_line_id.wt_difference_qty)
            remaining = max(0.0, diff_abs - already_allocated)
            if remaining > 0:
                self.qty = remaining

    @api.constrains("qty")
    def _check_qty_positive(self):
        for rec in self:
            if rec.qty <= 0:
                raise ValidationError(_(
                    "Qty alokasi harus lebih dari nol.\n"
                    "Lot: %s | Alasan: %s"
                ) % (rec.move_line_id.lot_id.name or rec.move_line_id.product_id.name,
                     rec.reason_id.name))

    @api.constrains("qty", "move_line_id")
    def _check_total_not_exceed_difference(self):
        for rec in self:
            ml = rec.move_line_id
            if not ml or not ml.wt_difference_qty:
                continue
            diff_abs = abs(ml.wt_difference_qty)
            total_allocated = sum(ml.wt_allocation_ids.mapped("qty"))
            if total_allocated > diff_abs + 0.001:
                raise ValidationError(_(
                    "Total alokasi (%.4f) melebihi selisih (%.4f) untuk lot %s.\n"
                    "Harap sesuaikan qty alokasi agar tidak melebihi selisih."
                ) % (total_allocated, diff_abs,
                     ml.lot_id.name or ml.product_id.display_name))
