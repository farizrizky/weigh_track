# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DeliveryLineAllocation(models.Model):
    _name = "wt.delivery.line.allocation"
    _description = "Alokasi Selisih Timbang Pengiriman"
    _order = "id"

    do_lot_line_id = fields.Many2one(
        "wt.delivery.do.line.lot",
        string="Delivery Plan Lot Line",
        required=True,
        ondelete="cascade",
        index=True,
    )
    wt_delivery_id = fields.Many2one(
        "wt.delivery",
        string="Delivery Task",
        compute="_compute_wt_delivery_id",
        store=True,
        index=True,
        readonly=True,
    )
    reason_id = fields.Many2one(
        "wt.stock.opname.difference.reason",
        string="Reason",
        required=True,
        domain="[('active', '=', True)]",
    )
    qty = fields.Float(
        string="Allocation Qty",
        digits="Product Unit of Measure",
        required=True,
    )
    location_dest_id = fields.Many2one(
        "stock.location",
        string="Destination Location",
        required=True,
        domain="[('usage', 'not in', ['view'])]",
        help="Lokasi tujuan scrap untuk alokasi ini (default dari alasan).",
    )
    note = fields.Char(
        string="Notes",
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot No.",
        compute="_compute_lot_uom",
        readonly=True,
        store=False,
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="Unit",
        compute="_compute_lot_uom",
        readonly=True,
        store=False,
    )

    @api.depends("do_lot_line_id")
    def _compute_wt_delivery_id(self):
        for rec in self:
            if rec.do_lot_line_id:
                rec.wt_delivery_id = rec.do_lot_line_id.delivery_id
            else:
                rec.wt_delivery_id = False

    @api.depends("do_lot_line_id")
    def _compute_lot_uom(self):
        for rec in self:
            if rec.do_lot_line_id:
                rec.lot_id = rec.do_lot_line_id.lot_id
                rec.uom_id = rec.do_lot_line_id.product_id.uom_id
            else:
                rec.lot_id = False
                rec.uom_id = False

    @api.onchange("reason_id")
    def _onchange_reason_id(self):
        """Auto-fill lokasi dari reason. Auto-fill qty dengan sisa unallocated."""
        if self.reason_id and self.reason_id.location_dest_id:
            self.location_dest_id = self.reason_id.location_dest_id

        if self.reason_id and self.do_lot_line_id and not self._origin.id:
            already_allocated = sum(a.qty for a in self.do_lot_line_id.wt_allocation_ids)
            diff_abs = abs(self.do_lot_line_id.wt_difference_qty)
            remaining = max(0.0, diff_abs - already_allocated)
            if remaining > 0:
                self.qty = remaining

    @api.constrains("qty")
    def _check_qty_positive(self):
        for rec in self:
            if rec.qty <= 0:
                lot_name = rec.lot_id.name or rec.do_lot_line_id.product_id.name
                raise ValidationError(_(
                    "Qty alokasi harus lebih dari nol.\n"
                    "Lot: %s | Alasan: %s"
                ) % (lot_name, rec.reason_id.name))

    @api.constrains("qty", "do_lot_line_id")
    def _check_total_not_exceed_difference(self):
        for rec in self:
            if rec.do_lot_line_id and rec.do_lot_line_id.wt_weighing_status != "weighed":
                raise ValidationError(_("Cannot allocate difference before the delivery lot line is weighed."))
            if rec.do_lot_line_id:
                ll = rec.do_lot_line_id
                diff_abs = abs(ll.wt_difference_qty)
                total_allocated = sum(ll.wt_allocation_ids.mapped("qty"))
                if total_allocated > diff_abs + 0.001:
                    raise ValidationError(_(
                        "Total alokasi (%.4f) melebihi selisih (%.4f) untuk lot %s.\n"
                        "Harap sesuaikan qty alokasi agar tidak melebihi selisih."
                    ) % (total_allocated, diff_abs, ll.lot_id.name or ll.product_id.display_name))
