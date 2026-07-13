# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockMoveLineWeighing(models.Model):
    _inherit = "stock.move.line"

    # ── Relasi ke Tugas Pengiriman (via picking) ──────────────────────────────
    wt_delivery_id = fields.Many2one(
        "wt.delivery",
        related="picking_id.wt_delivery_id",
        store=True,
        index=True,
        string="Tugas Pengiriman",
        readonly=True,
    )
    wt_delivery_state = fields.Selection(
        related="wt_delivery_id.state",
        string="Status Pengiriman",
        store=False,
        readonly=True,
        help="State delivery induk, digunakan untuk kontrol readonly di popup alokasi.",
    )

    # ── Field Penimbangan ─────────────────────────────────────────────────────
    wt_physical_qty = fields.Float(
        string="Berat Fisik (kg)",
        digits="Product Unit of Measure",
        default=0.0,
    )
    wt_original_demand_qty = fields.Float(
        string="Demand Awal (kg)",
        digits="Product Unit of Measure",
        default=0.0,
        help="Demand asli sebelum diubah oleh proses validasi. "
             "Diisi otomatis saat validasi dilakukan.",
    )
    wt_difference_qty = fields.Float(
        string="Selisih (kg)",
        compute="_compute_wt_difference_qty",
        store=True,
        digits="Product Unit of Measure",
        help="Berat fisik dikurangi demand asli. Negatif berarti kurang (susut).",
    )
    wt_skip_line = fields.Boolean(
        string="Lewati",
        default=False,
        help="Centang untuk melewati baris ini saat validasi pengiriman.",
    )
    wt_adjustment_applied = fields.Boolean(
        string="Adjustment Diterapkan",
        default=False,
        readonly=True,
        copy=False,
        help="True jika penyesuaian stok (susut) telah diterapkan otomatis saat validasi delivery. "
             "Baris ini akan dilewati agar tidak double-scrap.",
    )
    wt_is_pulled = fields.Boolean(
        string="Sudah Di-Pull",
        default=False,
        copy=False,
        help="True jika baris ini sudah pernah dikirim ke operator lewat Pull API. "
             "Hanya baris yang sudah di-pull yang ditampilkan di tab Detail Timbang, "
             "sehingga admin bebas mengubah perincian DO sebelum operator pull ulang.",
    )
    wt_note = fields.Char(
        string="Catatan Timbang",
    )

    # ── Alokasi Selisih ───────────────────────────────────────────────────────
    wt_allocation_ids = fields.One2many(
        "wt.delivery.line.allocation",
        "move_line_id",
        string="Alokasi Selisih",
    )
    wt_allocated_qty = fields.Float(
        string="Teralokasi (kg)",
        compute="_compute_wt_allocation_qty",
        store=True,
        digits="Product Unit of Measure",
    )
    wt_unallocated_qty = fields.Float(
        string="Belum Teralokasi (kg)",
        compute="_compute_wt_allocation_qty",
        store=True,
        digits="Product Unit of Measure",
    )
    wt_is_fully_allocated = fields.Boolean(
        string="Teralokasi Penuh",
        compute="_compute_wt_allocation_qty",
        store=True,
    )

    # ── Computed ──────────────────────────────────────────────────────────────

    @api.depends("wt_physical_qty", "quantity", "wt_original_demand_qty")
    def _compute_wt_difference_qty(self):
        for line in self:
            # Gunakan demand asli jika sudah disimpan (setelah validasi),
            # otherwise gunakan quantity saat ini.
            demand = line.wt_original_demand_qty if line.wt_original_demand_qty > 0.001 else line.quantity
            line.wt_difference_qty = line.wt_physical_qty - demand

    @api.depends("wt_allocation_ids.qty", "wt_difference_qty")
    def _compute_wt_allocation_qty(self):
        for line in self:
            diff_abs = abs(line.wt_difference_qty)
            allocated = sum(line.wt_allocation_ids.mapped("qty"))
            line.wt_allocated_qty = allocated
            line.wt_unallocated_qty = max(0.0, diff_abs - allocated)
            line.wt_is_fully_allocated = diff_abs <= 0.001 or (diff_abs - allocated) <= 0.001

    # ── Constraints ───────────────────────────────────────────────────────────

    @api.constrains("wt_physical_qty", "quantity")
    def _check_wt_physical_qty(self):
        for line in self:
            if not line.wt_delivery_id or line.wt_skip_line:
                continue
            if line.wt_physical_qty < 0:
                raise ValidationError(_(
                    "Berat fisik tidak boleh negatif pada lot %s."
                ) % (line.lot_id.name or line.product_id.name))
            if line.wt_physical_qty > line.quantity + 0.0001:
                raise ValidationError(_(
                    "Berat fisik (%.4f) tidak boleh melebihi demand (%.4f) "
                    "pada lot %s."
                ) % (line.wt_physical_qty, line.quantity,
                     line.lot_id.name or line.product_id.name))

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_configure_allocation(self):
        """Buka popup alokasi selisih untuk move line ini.
        Popup tampil readonly jika delivery sudah validated.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Alokasi Selisih: %s") % (self.lot_id.name or self.product_id.display_name),
            "res_model": "stock.move.line",
            "res_id": self.id,
            "view_mode": "form",
            "view_id": self.env.ref("weightrack.view_wt_delivery_line_allocation_popup").id,
            "target": "new",
        }

    # ── Business Logic ────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Setelah move line baru dibuat, paksa rekomputasi wt_has_unpulled_lines
        # pada parent wt.delivery dalam transaksi yang sama.
        # Tanpa ini, stored computed field mungkin tidak langsung ter-update
        # saat lot ditambahkan via popup stock.picking (Operasi Detail).
        deliveries = records.sudo().mapped("wt_delivery_id").filtered(bool)
        if deliveries:
            deliveries.sudo()._compute_wt_has_unpulled_lines()
        return records

    def write(self, vals):
        result = super().write(vals)
        # Rekomputasi juga saat quantity atau wt_is_pulled berubah,
        # karena keduanya adalah dependensi wt_has_unpulled_lines.
        if any(k in vals for k in ("quantity", "wt_is_pulled", "wt_physical_qty")):
            deliveries = self.sudo().mapped("wt_delivery_id").filtered(bool)
            if deliveries:
                deliveries.sudo()._compute_wt_has_unpulled_lines()
        return result

    def _apply_wt_weighing(self):
        """Set quantity move line ke berat fisik aktual atau 0 jika dilewati.
        Di Odoo 19, `picked` wajib di-set agar _action_done() memproses baris.
        Demand asli (quantity sebelum diubah) disimpan ke wt_original_demand_qty
        agar tetap bisa ditampilkan dan dihitung selisihnya setelah validasi.
        """
        self.ensure_one()
        if self.wt_skip_line:
            # Simpan demand asli jika belum tersimpan
            if not self.wt_original_demand_qty:
                self.sudo().write({"wt_original_demand_qty": self.quantity})
            self.sudo().write({
                "quantity": 0.0,
                "picked": False,
            })
            return
        # Simpan demand asli sebelum quantity ditimpa oleh berat fisik
        if not self.wt_original_demand_qty:
            self.sudo().write({"wt_original_demand_qty": self.quantity})
        self.sudo().write({
            "quantity": self.wt_physical_qty,
            "picked": True,   # Odoo 19: tandai baris sebagai sudah dipick
        })
