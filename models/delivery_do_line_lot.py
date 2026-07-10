# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DeliveryDoLineLot(models.Model):
    _name = "wt.delivery.do.line.lot"
    _description = "Rincian Lot Rencana DO"
    _order = "do_line_id, id"

    do_line_id = fields.Many2one(
        "wt.delivery.do.line",
        string="Baris Rencana DO",
        required=False,
        ondelete="cascade",
        index=True,
    )
    delivery_id = fields.Many2one(
        "wt.delivery",
        related="do_line_id.delivery_id",
        store=True,
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="do_line_id.company_id",
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.product",
        related="do_line_id.product_id",
        store=True,
        readonly=True,
    )
    route_id = fields.Many2one(
        "wt.delivery.route",
        related="do_line_id.route_id",
        store=True,
        readonly=True,
        string="Rute Transit",
    )
    picking_type_id = fields.Many2one(
        "stock.picking.type",
        related="do_line_id.picking_type_id",
        store=True,
        readonly=True,
        string="Tipe Operasi",
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Nomor Lot",
        required=True,
        domain="[('product_id', '=', product_id), '|', ('company_id', '=', company_id), ('company_id', '=', False)]",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Lokasi",
        compute="_compute_location_id",
        help="Lokasi fisik tempat lot berada saat ini.",
    )
    qty_available = fields.Float(
        string="Stok Bebas (kg)",
        compute="_compute_qty_available",
        digits="Product Unit of Measure",
        help="Kuantitas stok lot bebas (siap pakai) saat ini.",
    )
    wt_qty_on_hand = fields.Float(
        string="Stok Fisik (kg)",
        compute="_compute_qty_available",
        digits="Product Unit of Measure",
        help="Kuantitas stok lot fisik di tangan saat ini.",
    )
    wt_qty_reserved = fields.Float(
        string="Terpesan (kg)",
        compute="_compute_qty_available",
        digits="Product Unit of Measure",
        help="Kuantitas stok lot yang sedang dipesan/direservasi oleh transaksi lain.",
    )
    qty = fields.Float(
        string="Demand (kg)",
        digits="Product Unit of Measure",
        required=True,
        help="Kuantitas rencana yang akan diambil dari lot ini.",
    )
    wt_original_qty = fields.Float(
        string="Demand Awal (kg)",
        digits="Product Unit of Measure",
        help="Kuantitas demand rencana awal sebelum adjustment.",
    )

    wt_physical_qty = fields.Float(
        string="Berat Fisik (kg)",
        digits="Product Unit of Measure",
        default=0.0,
        help="Berat fisik hasil timbang dari timbangan (di-update via API).",
    )
    wt_difference_qty = fields.Float(
        string="Selisih (kg)",
        compute="_compute_wt_difference_qty",
        store=True,
        digits="Product Unit of Measure",
        help="Berat fisik dikurangi demand awal.",
    )
    wt_skip_line = fields.Boolean(
        string="Lewati",
        default=False,
        help="Centang untuk melewati baris ini saat validasi.",
    )
    wt_note = fields.Char(
        string="Catatan Timbang",
    )
    wt_adjustment_applied = fields.Boolean(
        string="Adjustment Diterapkan",
        default=False,
        readonly=True,
        copy=False,
    )
    wt_is_pulled = fields.Boolean(
        string="Sudah Di-Push",
        default=False,
        copy=False,
    )

    # ── Alokasi Selisih ───────────────────────────────────────────────────────
    wt_allocation_ids = fields.One2many(
        "wt.delivery.line.allocation",
        "do_lot_line_id",
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


    @api.depends("wt_physical_qty", "wt_original_qty", "qty")
    def _compute_wt_difference_qty(self):
        for line in self:
            demand = line.wt_original_qty if line.wt_original_qty > 0.0 else line.qty
            line.wt_difference_qty = line.wt_physical_qty - demand

    @api.depends(
        "lot_id",
        "do_line_id.location_id",
        "product_id",
        "do_line_id.lot_line_ids.qty",
        "do_line_id.lot_line_ids.lot_id",
    )
    def _compute_qty_available(self):
        for rec in self:
            if rec.lot_id and rec.do_line_id.location_id and rec.product_id:
                locations = self.env["stock.location"].search([("id", "child_of", rec.do_line_id.location_id.id)])
                quants = self.env["stock.quant"].search([
                    ("product_id", "=", rec.product_id.id),
                    ("location_id", "in", locations.ids),
                    ("lot_id", "=", rec.lot_id.id),
                ])
                total_qty = sum(quants.mapped("quantity"))

                # Jangan hitung reserved_quantity dari stock.quant Odoo karena sistem ini
                # tidak menggunakan mekanisme reservasi Odoo standar (tidak ada picking
                # yang dibuat saat rencana DO). Reservasi dihitung secara manual dari
                # baris lot rencana DO yang aktif.
                # total_reserved sengaja dikosongkan untuk menghindari double-count
                # jika ada picking lama yang belum ter-cancel.

                # Hitung demand dari baris-baris LAIN dalam satu Rencana DO yang menggunakan
                # lot yang sama. Gunakan in-memory lot_line_ids (bukan query DB) agar
                # baris yang sedang dihapus (belum di-commit) tidak ikut dihitung.
                # Gunakan _origin untuk mendapatkan ID yang sudah tersimpan, agar baris
                # baru (ID negatif/virtual) tidak salah dikecualikan.
                origin_id = rec._origin.id if rec._origin else rec.id
                other_lines = rec.do_line_id.lot_line_ids.filtered(
                    lambda l: l.lot_id == rec.lot_id
                    and (l._origin.id if l._origin else l.id) != origin_id
                )
                other_planned_qty = sum(other_lines.mapped("qty"))

                # Hitung demand yang direncanakan di Tugas Pengiriman aktif lainnya.
                # Gunakan 2-step search untuk menghindari masalah nested M2O domain path
                # yang tidak reliable, terutama saat delivery baru belum tersimpan ke DB
                # (current_delivery_id = 0/False).
                #
                # Step 1: Cari do_lines dari delivery aktif (kecuali delivery saat ini).
                #         Pakai domain sederhana 1-level, lebih reliable di semua versi Odoo.
                current_delivery_id = (
                    rec.delivery_id.id
                    or rec.do_line_id.delivery_id.id
                    or False
                )
                active_do_line_domain = [
                    ("delivery_id.state", "in", ("draft", "confirmed", "in_progress", "completed")),
                ]
                if current_delivery_id:
                    active_do_line_domain.append(("delivery_id", "!=", current_delivery_id))

                active_do_lines = self.env["wt.delivery.do.line"].search(active_do_line_domain)

                # Step 2: Cari lot_lines untuk lot ini di do_lines yang ditemukan.
                #         Pakai ("do_line_id", "in", ids) — direct IN clause, pasti reliable.
                if active_do_lines:
                    other_active_lines = self.env["wt.delivery.do.line.lot"].search([
                        ("lot_id", "=", rec.lot_id.id),
                        ("do_line_id", "in", active_do_lines.ids),
                        ("wt_skip_line", "=", False),
                    ])
                    other_active_qty = sum(other_active_lines.mapped("qty"))
                else:
                    other_active_qty = 0.0

                rec.wt_qty_on_hand = total_qty
                rec.wt_qty_reserved = other_planned_qty + other_active_qty
                rec.qty_available = max(0.0, total_qty - rec.wt_qty_reserved)
            else:
                rec.wt_qty_on_hand = 0.0
                rec.wt_qty_reserved = 0.0
                rec.qty_available = 0.0

    @api.depends("lot_id", "do_line_id.location_id", "product_id")
    def _compute_location_id(self):
        for rec in self:
            if rec.lot_id and rec.do_line_id.location_id and rec.product_id:
                locations = self.env["stock.location"].search([("id", "child_of", rec.do_line_id.location_id.id)])
                quant = self.env["stock.quant"].search([
                    ("product_id", "=", rec.product_id.id),
                    ("location_id", "in", locations.ids),
                    ("lot_id", "=", rec.lot_id.id),
                    ("quantity", ">", 0),
                ], limit=1)
                rec.location_id = quant.location_id.id if quant else rec.do_line_id.location_id.id
            else:
                rec.location_id = False


    @api.depends("wt_difference_qty", "wt_allocation_ids.qty")
    def _compute_wt_allocation_qty(self):
        for line in self:
            allocated = sum(line.wt_allocation_ids.mapped("qty"))
            diff_abs = abs(line.wt_difference_qty)
            line.wt_allocated_qty = allocated
            line.wt_unallocated_qty = max(0.0, diff_abs - allocated)
            line.wt_is_fully_allocated = line.wt_unallocated_qty <= 0.001

    # ── ORM ───────────────────────────────────────────────────────────────────

    def unlink(self):
        """Saat lot line dihapus, pastikan picking parent (jika ada) di-unreserve
        agar reserved_quantity di stock.quant dibebaskan."""
        for rec in self:
            if rec.do_line_id and rec.do_line_id.picking_id:
                picking = rec.do_line_id.picking_id
                if picking.state not in ("done", "cancel"):
                    try:
                        picking.do_unreserve()
                    except Exception:
                        pass
        return super().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        """Jika lot baru ditambahkan saat delivery sudah 'completed',
        revert ke 'in_progress' agar operator bisa pull dan menimbang lot baru."""
        for vals in vals_list:
            if "qty" in vals and "wt_original_qty" not in vals:
                vals["wt_original_qty"] = vals["qty"]
        records = super().create(vals_list)
        deliveries = records.mapped("delivery_id").filtered(
            lambda d: d.state == "completed"
        )
        if deliveries:
            deliveries.write({"state": "in_progress"})
        return records

    def write(self, vals):
        if "qty" in vals and "wt_original_qty" not in vals and not vals.get("wt_adjustment_applied"):
            # Jika qty diubah manual oleh user (bukan dari adjustment),
            # rekam juga ke wt_original_qty untuk record yang belum di-adjust.
            for rec in self:
                if not rec.wt_adjustment_applied:
                    super(DeliveryDoLineLot, rec).write({"wt_original_qty": vals["qty"]})
        return super().write(vals)

    @api.constrains("qty")
    def _check_qty_positive(self):
        for rec in self:
            if rec.qty <= 0:
                raise ValidationError(_("Demand quantity untuk lot harus lebih dari nol."))



    def action_configure_allocation(self):
        """Buka popup alokasi selisih untuk lot rencana DO."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Alokasi Selisih (Rencana): %s") % (self.lot_id.name or self.product_id.display_name),
            "res_model": "wt.delivery.do.line.lot",
            "res_id": self.id,
            "view_mode": "form",
            "view_id": self.env.ref("weightrack.view_wt_delivery_do_lot_allocation_popup").id,
            "target": "new",
        }

