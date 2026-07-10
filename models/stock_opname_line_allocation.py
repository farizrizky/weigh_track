# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockOpnameLineAllocation(models.Model):
    _name = "wt.stock.opname.line.allocation"
    _description = "Stock Opname Line Difference Allocation"
    _order = "line_id, id"

    line_id = fields.Many2one(
        "wt.stock.opname.line",
        string="Baris Opname",
        ondelete="cascade",
        required=True,
        index=True,
    )
    opname_id = fields.Many2one(
        "wt.stock.opname",
        string="Stock Opname",
        related="line_id.opname_id",
        store=True,
        index=True,
    )
    reason_id = fields.Many2one(
        "wt.stock.opname.difference.reason",
        string="Alasan",
        required=True,
        domain="[('active', '=', True)]",
    )
    qty = fields.Float(
        string="Qty",
        digits="Product Unit of Measure",
        required=True,
    )

    @api.onchange("reason_id")
    def _onchange_reason_id(self):
        """Auto-fill location dari reason default.
        Jika record baru, auto-fill qty dengan sisa unallocated dari parent line.
        """
        if self.reason_id and self.reason_id.location_dest_id:
            self.location_dest_id = self.reason_id.location_dest_id

        # Auto-fill qty hanya untuk baris baru (belum pernah disimpan)
        if self.reason_id and self.line_id and not self._origin.id:
            # Hitung sisa yang belum dialokasikan
            already_allocated = sum(
                a.qty for a in self.line_id.allocation_ids
            )
            diff_abs = abs(self.line_id.difference_qty)
            remaining = max(0.0, diff_abs - already_allocated)
            if remaining > 0:
                self.qty = remaining

    location_dest_id = fields.Many2one(
        "stock.location",
        string="Lokasi Tujuan",
        required=True,
        domain="[('usage', 'not in', ['view'])]",
        help="Lokasi tujuan untuk alokasi ini (default dari alasan).",
    )
    note = fields.Char(
        string="Catatan",
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="Satuan",
        related="line_id.uom_id",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            reason = self.env["wt.stock.opname.difference.reason"].browse(
                vals.get("reason_id")
            )
            if reason and reason.location_dest_id:
                vals["location_dest_id"] = reason.location_dest_id.id
        return super().create(vals_list)

    def write(self, vals):
        if "reason_id" in vals:
            reason = self.env["wt.stock.opname.difference.reason"].browse(vals["reason_id"])
            vals = dict(vals)
            if reason and reason.location_dest_id:
                vals["location_dest_id"] = reason.location_dest_id.id
            return super().write(vals)
        if "location_dest_id" in vals:
            vals = dict(vals)
            vals.pop("location_dest_id", None)
            if not vals:
                return True
        return super().write(vals)

    @api.constrains("qty")
    def _check_qty_positive(self):
        """Qty alokasi harus lebih dari nol."""
        for rec in self:
            if rec.qty <= 0:
                raise ValidationError(_(
                    "Qty alokasi harus lebih dari nol.\n"
                    "Lot: %s | Alasan: %s"
                ) % (rec.line_id.lot_id.name, rec.reason_id.name))

    @api.constrains("qty", "line_id")
    def _check_total_not_exceed_difference(self):
        """Total alokasi tidak boleh melebihi abs(difference_qty)."""
        for rec in self:
            line = rec.line_id
            if not line or not line.difference_qty:
                continue
            diff_abs = abs(line.difference_qty)
            total_allocated = sum(line.allocation_ids.mapped("qty"))
            if total_allocated > diff_abs + 0.001:
                raise ValidationError(_(
                    "Total alokasi (%.4f) melebihi selisih stok (%.4f) untuk lot %s.\n"
                    "Harap sesuaikan qty alokasi agar tidak melebihi selisih."
                ) % (total_allocated, diff_abs, line.lot_id.name))
