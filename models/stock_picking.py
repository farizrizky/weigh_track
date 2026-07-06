# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    wt_delivery_id = fields.Many2one(
        "wt.delivery",
        string="Tugas Pengiriman",
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
        string="Push Selesai",
        default=False,
        copy=False,
        help="Ditandai True secara otomatis saat operator selesai push semua data timbang via API.",
    )
    wt_push_done_at = fields.Datetime(
        string="Waktu Push Selesai",
        readonly=True,
        copy=False,
        help="Waktu operator menyelesaikan push data timbang.",
    )

    # ── Alokasi Selisih (via move lines) ─────────────────────────────────────
    wt_allocation_ids = fields.Many2many(
        "wt.delivery.line.allocation",
        string="Alokasi Selisih",
        compute="_compute_wt_allocation_ids",
        help="Semua alokasi selisih timbang dari move lines pengiriman ini.",
    )
    wt_has_allocation = fields.Boolean(
        string="Ada Alokasi",
        compute="_compute_wt_allocation_ids",
        help="True jika terdapat alokasi selisih pada pengiriman ini.",
    )

    @api.depends("move_line_ids.wt_allocation_ids")
    def _compute_wt_allocation_ids(self):
        for picking in self:
            allocs = picking.move_line_ids.mapped("wt_allocation_ids")
            picking.wt_allocation_ids = allocs
            picking.wt_has_allocation = bool(allocs)

    def button_validate(self):
        """Blokir validasi manual jika DO ini berasal dari Tugas Pengiriman WeighTrack."""
        for picking in self:
            if picking.wt_delivery_id:
                raise UserError(_(
                    "DO ini dibuat dari Tugas Pengiriman '%s'.\n\n"
                    "Validasi hanya bisa dilakukan melalui tombol 'Validasi & Kirim' "
                    "di dokumen Tugas Pengiriman WeighTrack."
                ) % picking.origin)
        return super().button_validate()
