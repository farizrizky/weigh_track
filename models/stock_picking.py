# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    wt_delivery_id = fields.Many2one(
        "wt.delivery",
        string="Delivery Task",
        ondelete="set null",
        index=True,
        copy=False,
    )
    wt_operator_id = fields.Many2one(
        "hr.employee",
        string="Operator",
        index=True,
        copy=False,
        help="Operator yang bertanggung jawab atas Delivery Order ini.",
    )
    wt_push_done = fields.Boolean(
        string="Push Completed",
        default=False,
        copy=False,
        help="Ditandai True secara otomatis saat operator selesai push semua data timbang via API.",
    )
    wt_push_done_at = fields.Datetime(
        string="Push Completed At",
        readonly=True,
        copy=False,
        help="Waktu operator menyelesaikan push data timbang.",
    )

    # ── Alokasi Selisih (via move lines) ─────────────────────────────────────
    def button_validate(self):
        """Blokir validasi manual jika DO ini berasal dari Tugas Pengiriman WeighTrack."""
        if not self.env.context.get("wt_force_validate"):
            for picking in self:
                if picking.wt_delivery_id:
                    raise UserError(_(
                        "DO ini dibuat dari Tugas Pengiriman '%s'.\n\n"
                        "Validasi hanya bisa dilakukan melalui tombol 'Validasi & Kirim' "
                        "di dokumen Tugas Pengiriman WeighTrack."
                    ) % picking.origin)
        result = super().button_validate()
        if not self.env.context.get("wt_skip_delivery_backdate_sync"):
            for picking in self.filtered(
                lambda record: record.wt_delivery_id and record.state == "done"
            ):
                picking.wt_delivery_id._sync_picking_effective_date(picking)
        return result

    def action_view_stock_return_picking(self):
        """Mencegah retur DO individual jika berasal dari Tugas Pengiriman WeighTrack."""
        for picking in self:
            if picking.wt_delivery_id:
                raise UserError(_(
                    "DO ini dibuat dari Tugas Pengiriman '%s'.\n\n"
                    "Proses retur hanya dapat dilakukan melalui tombol 'Retur Pengiriman' "
                    "di dokumen Tugas Pengiriman WeighTrack."
                ) % picking.origin)
        return super().action_view_stock_return_picking()
    production_receipt_id = fields.Many2one(
        "wt.production.receipt",
        string="Production Receipt",
        readonly=True,
        copy=False,
        index=True,
    )
    production_receipt_reverse_id = fields.Many2one(
        "wt.production.receipt",
        string="Production Receipt Reversal",
        readonly=True,
        copy=False,
        index=True,
    )
    receive_from_employee_id = fields.Many2one(
        "hr.employee",
        string="Receive From",
        readonly=True,
        copy=False,
        index=True,
    )
