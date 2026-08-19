# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DeliveryDoLineLot(models.Model):
    _name = "wt.delivery.do.line.lot"
    _description = "Rincian Lot Rencana DO"
    _order = "do_line_id, id"

    do_line_id = fields.Many2one(
        "wt.delivery.do.line",
        string="Delivery Plan Line",
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
    delivery_state = fields.Selection(
        related="delivery_id.state",
        string="Delivery State",
        readonly=True,
    )
    picking_state = fields.Selection(
        related="do_line_id.picking_state",
        string="Picking State",
        readonly=True,
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
        string="Transit Route",
    )
    picking_type_id = fields.Many2one(
        "stock.picking.type",
        related="do_line_id.picking_type_id",
        store=True,
        readonly=True,
        string="Operation Type",
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot Number",
        required=True,
        domain="[('product_id', '=', product_id), '|', ('company_id', '=', company_id), ('company_id', '=', False)]",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Location",
        compute="_compute_location_id",
        help="Lokasi fisik tempat lot berada saat ini.",
    )
    source_location_id = fields.Many2one(
        "stock.location",
        string="Physical Source Location",
        readonly=True,
        copy=False,
        ondelete="restrict",
        help="Lokasi fisik quant yang dipilih saat lot dialokasikan dari lokasi sumber DO.",
    )
    allowed_weighing_location_ids = fields.Many2many(
        "wt.weighing.location",
        compute="_compute_allowed_weighing_location_ids",
        string="Allowed Weighing Locations",
    )
    weighing_location_id = fields.Many2one(
        "wt.weighing.location",
        string="Weighing Location",
        domain="[('id', 'in', allowed_weighing_location_ids)]",
        ondelete="restrict",
    )
    operator_id = fields.Many2one(
        "hr.employee",
        string="Operator",
        related="weighing_location_id.operator_id",
        store=True,
        readonly=True,
    )
    qty_available = fields.Float(
        string="Available Stock (kg)",
        compute="_compute_qty_available",
        digits="Product Unit of Measure",
        help="Kuantitas stok lot bebas (siap pakai) saat ini.",
    )
    wt_qty_on_hand = fields.Float(
        string="Physical Stock (kg)",
        compute="_compute_qty_available",
        digits="Product Unit of Measure",
        help="Kuantitas stok lot fisik di tangan saat ini.",
    )
    wt_qty_reserved = fields.Float(
        string="Reserved (kg)",
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
        string="Original Demand (kg)",
        digits="Product Unit of Measure",
        help="Kuantitas demand rencana awal sebelum adjustment.",
    )

    wt_physical_qty = fields.Float(
        string="Physical Weight (kg)",
        digits="Product Unit of Measure",
        default=0.0,
        help="Berat fisik hasil timbang dari timbangan (di-update via API).",
    )
    wt_weighed_at = fields.Datetime(
        string="Weighed At",
        copy=False,
        help="Waktu timbang aktual yang dikirim dari aplikasi timbangan.",
    )
    wt_weighing_status = fields.Selection(
        [
            ("not_pulled", "Not Pulled"),
            ("unweighed", "Unweighed"),
            ("weighed", "Weighed"),
            ("cancelled", "Dibatalkan"),
        ],
        string="Weighing Status",
        compute="_compute_wt_weighing_status",
        store=True,
    )
    wt_difference_qty = fields.Float(
        string="Difference (kg)",
        compute="_compute_wt_difference_qty",
        store=True,
        digits="Product Unit of Measure",
        help="Berat fisik dikurangi demand awal.",
    )
    wt_note = fields.Char(
        string="Weighing Note",
    )
    wt_weighing_source = fields.Selection(
        [
            ("device", "Device"),
            ("manual", "Manual"),
        ],
        string="Weighing Source",
        readonly=True,
        copy=False,
        index=True,
    )
    wt_manual_input_by_id = fields.Many2one(
        "res.users",
        string="Manual Input By",
        readonly=True,
        copy=False,
    )
    wt_manual_input_at = fields.Datetime(
        string="Manual Input At",
        readonly=True,
        copy=False,
    )
    wt_manual_reason = fields.Text(
        string="Manual Input Reason",
        readonly=True,
        copy=False,
    )
    wt_adjustment_applied = fields.Boolean(
        string="Adjustment Applied",
        default=False,
        readonly=True,
        copy=False,
    )
    wt_is_pulled = fields.Boolean(
        string="Pulled",
        default=False,
        copy=False,
    )
    wt_is_cancelled = fields.Boolean(
        string="Cancelled",
        default=False,
        copy=False,
        index=True,
    )

    # ── Alokasi Selisih ───────────────────────────────────────────────────────
    wt_allocation_ids = fields.One2many(
        "wt.delivery.line.allocation",
        "do_lot_line_id",
        string="Difference Allocation",
    )
    wt_allocated_qty = fields.Float(
        string="Allocated (kg)",
        compute="_compute_wt_allocation_qty",
        store=True,
        digits="Product Unit of Measure",
    )
    wt_unallocated_qty = fields.Float(
        string="Unallocated (kg)",
        compute="_compute_wt_allocation_qty",
        store=True,
        digits="Product Unit of Measure",
    )
    wt_is_fully_allocated = fields.Boolean(
        string="Fully Allocated",
        compute="_compute_wt_allocation_qty",
        store=True,
    )

    # ── Cakupan Demand ────────────────────────────────────────────────────────
    wt_demand_coverage = fields.Selection(
        [("all", "Semua"), ("partial", "Sebagian")],
        string="Cakupan Demand",
        compute="_compute_wt_demand_coverage",
        help="'Semua' jika demand >= stok bebas (ambil semua stok lot), 'Sebagian' jika hanya sebagian stok yang diambil.",
    )


    @api.depends("qty", "qty_available", "lot_id")
    def _compute_wt_demand_coverage(self):
        for rec in self:
            if not rec.lot_id or rec.qty <= 0:
                rec.wt_demand_coverage = False
            elif rec.qty >= rec.qty_available:
                rec.wt_demand_coverage = "all"
            else:
                rec.wt_demand_coverage = "partial"

    def _has_weighing_input(self):
        self.ensure_one()
        return self.wt_is_pulled or bool(self.wt_weighing_source)

    @api.depends(
        "wt_is_pulled",
        "wt_weighing_source",
        "wt_physical_qty",
        "wt_original_qty",
        "qty",
        "wt_weighed_at",
    )
    def _compute_wt_difference_qty(self):
        for line in self:
            if not line.wt_weighing_source or line.qty <= 0.0:
                line.wt_difference_qty = 0.0
                continue
            demand = line.wt_original_qty if line.wt_original_qty > 0.0 else line.qty
            line.wt_difference_qty = line.wt_physical_qty - demand

    @api.depends("wt_is_pulled", "wt_weighing_source", "wt_physical_qty", "qty", "wt_is_cancelled")
    def _compute_wt_weighing_status(self):
        for line in self:
            if line.wt_is_cancelled:
                line.wt_weighing_status = "cancelled"
            elif not line._has_weighing_input() or line.qty <= 0.0:
                line.wt_weighing_status = "not_pulled"
            elif line.wt_weighing_source:
                line.wt_weighing_status = "weighed"
            else:
                line.wt_weighing_status = "unweighed"

    @api.depends(
        "lot_id",
        "do_line_id.location_id",
        "product_id",
        "do_line_id.lot_line_ids.qty",
        "do_line_id.lot_line_ids.lot_id",
        "do_line_id.lot_line_ids.wt_is_cancelled",
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
                # lot yang sama (dan tidak berstatus cancel). Gunakan in-memory lot_line_ids (bukan query DB) agar
                # baris yang sedang dihapus (belum di-commit) tidak ikut dihitung.
                # Gunakan _origin untuk mendapatkan ID yang sudah tersimpan, agar baris
                # baru (ID negatif/virtual) tidak salah dikecualikan.
                origin_id = rec._origin.id if rec._origin else rec.id
                other_lines = rec.do_line_id.lot_line_ids.filtered(
                    lambda l: l.lot_id == rec.lot_id
                    and not l.wt_is_cancelled
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
                    rec.do_line_id._get_persisted_delivery_id()
                    if rec.do_line_id
                    else False
                )
                active_do_line_domain = [
                    ("delivery_id.state", "in", ("draft", "confirmed", "in_progress")),
                ]
                if current_delivery_id:
                    active_do_line_domain.append(("delivery_id", "!=", current_delivery_id))

                active_do_lines = self.env["wt.delivery.do.line"].search(active_do_line_domain)

                # Step 2: Cari lot_lines untuk lot ini di do_lines yang ditemukan (kecualikan lot yang dibatalkan).
                #         Pakai ("do_line_id", "in", ids) — direct IN clause, pasti reliable.
                if active_do_lines:
                    other_active_lines = self.env["wt.delivery.do.line.lot"].search([
                        ("lot_id", "=", rec.lot_id.id),
                        ("do_line_id", "in", active_do_lines.ids),
                        ("wt_is_cancelled", "=", False),
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

    @api.depends("source_location_id", "lot_id", "do_line_id.location_id", "product_id")
    def _compute_location_id(self):
        for rec in self:
            if rec.source_location_id:
                rec.location_id = rec.source_location_id
                continue
            if rec.lot_id and rec.do_line_id.location_id and rec.product_id:
                quant = self.env["stock.quant"].sudo().with_company(rec.company_id).search([
                    ("product_id", "=", rec.product_id.id),
                    ("location_id", "child_of", rec.do_line_id.location_id.id),
                    ("lot_id", "=", rec.lot_id.id),
                    ("quantity", ">", 0),
                ], order="location_id, id", limit=1)
                rec.location_id = quant.location_id.id if quant else rec.do_line_id.location_id.id
            else:
                rec.location_id = False

    @api.depends("company_id", "lot_id", "lot_id.division_id", "location_id")
    def _compute_allowed_weighing_location_ids(self):
        rule_model = self.env["wt.receipt.rule"]
        location_model = self.env["wt.weighing.location"]
        for rec in self:
            if not rec.company_id:
                rec.allowed_weighing_location_ids = location_model.browse()
                continue

            rules = rule_model.search([
                ("active", "=", True),
                ("company_id", "=", rec.company_id.id),
            ])
            if rec.lot_id.division_id:
                rules = rules.filtered(lambda rule: rule.division_id == rec.lot_id.division_id)
            if rec.location_id and rec.location_id.parent_path:
                rules = rules.filtered(
                    lambda rule: rule.location_id
                    and rule.location_id.parent_path
                    and rec.location_id.parent_path.startswith(rule.location_id.parent_path)
                )

            weighing_locations = rules.mapped("weighing_location_id")
            if not weighing_locations:
                weighing_locations = location_model.search([
                    ("active", "=", True),
                    ("company_id", "=", rec.company_id.id),
                ])
            rec.allowed_weighing_location_ids = weighing_locations

    @api.onchange("lot_id", "location_id", "company_id")
    def _onchange_lot_weighing_location(self):
        for rec in self:
            allowed_locations = rec.allowed_weighing_location_ids
            if rec.weighing_location_id and rec.weighing_location_id not in allowed_locations:
                rec.weighing_location_id = False
            if not rec.weighing_location_id and len(allowed_locations) == 1:
                rec.weighing_location_id = allowed_locations[:1]

    @api.constrains("weighing_location_id", "company_id")
    def _check_weighing_location_company(self):
        for rec in self:
            if (
                rec.weighing_location_id
                and rec.company_id
                and rec.weighing_location_id.company_id != rec.company_id
            ):
                raise ValidationError(_("Weighing location must belong to the same company."))


    @api.depends("wt_difference_qty", "wt_allocation_ids.qty")
    def _compute_wt_allocation_qty(self):
        for line in self:
            allocated = sum(line.wt_allocation_ids.mapped("qty"))
            diff_abs = abs(line.wt_difference_qty)
            line.wt_allocated_qty = allocated
            line.wt_unallocated_qty = max(0.0, diff_abs - allocated)
            line.wt_is_fully_allocated = line.wt_unallocated_qty <= 0.001

    # ── ORM ───────────────────────────────────────────────────────────────────

    def _is_required_transit_lot(self):
        self.ensure_one()
        return bool(
            self.do_line_id
            and self.lot_id
            and self.lot_id in self.do_line_id._get_expected_transit_lots()
        )

    def _get_required_transit_qty(self):
        self.ensure_one()
        if not self.do_line_id or not self.lot_id:
            return 0.0
        return self.do_line_id._get_expected_transit_lot_qty_map().get(self.lot_id.id, 0.0)

    def unlink(self):
        """Saat lot line dihapus, pastikan picking parent (jika ada) di-unreserve
        agar reserved_quantity di stock.quant dibebaskan."""
        for rec in self:
            if rec._is_required_transit_lot():
                raise ValidationError(_(
                    "Lot Transit %s wajib dipakai oleh rute pengiriman berikutnya dan tidak dapat dihapus."
                ) % (rec.lot_id.name or rec.display_name))
            if rec._has_weighing_input():
                raise ValidationError(_(
                    "Baris lot %s tidak dapat dihapus karena statusnya sudah di-pull oleh operator timbang."
                ) % (rec.lot_id.name or rec.display_name))
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
        for vals in vals_list:
            if "qty" in vals and "wt_original_qty" not in vals:
                vals["wt_original_qty"] = vals["qty"]
        records = super().create(vals_list)
        records._set_default_weighing_location_if_unique()
        return records

    def write(self, vals):
        if "do_line_id" in vals and not vals["do_line_id"]:
            for rec in self:
                if rec._has_weighing_input():
                    raise ValidationError(_(
                        "Baris lot '%s' tidak dapat dihapus karena statusnya sudah di-pull oleh operator timbang."
                    ) % (rec.lot_id.name or rec.display_name))
        if "qty" in vals and "wt_original_qty" not in vals and not vals.get("wt_adjustment_applied"):
            # Jika qty diubah manual oleh user (bukan dari adjustment),
            # rekam juga ke wt_original_qty untuk record yang belum di-adjust.
            for rec in self:
                if not rec.wt_adjustment_applied:
                    super(DeliveryDoLineLot, rec).write({"wt_original_qty": vals["qty"]})
        res = super().write(vals)
        if any(key in vals for key in ("lot_id", "do_line_id", "weighing_location_id")):
            self._set_default_weighing_location_if_unique()
        return res

    def _set_default_weighing_location_if_unique(self):
        for rec in self:
            if (
                not rec.source_location_id
                and rec.lot_id
                and rec.do_line_id.location_id
                and rec.product_id
            ):
                quant = self.env["stock.quant"].sudo().with_company(rec.company_id).search([
                    ("product_id", "=", rec.product_id.id),
                    ("location_id", "child_of", rec.do_line_id.location_id.id),
                    ("lot_id", "=", rec.lot_id.id),
                    ("quantity", ">", 0),
                ], order="location_id, id", limit=1)
                if quant:
                    rec.source_location_id = quant.location_id.id
            if rec.weighing_location_id:
                continue
            allowed_locations = rec.allowed_weighing_location_ids
            if len(allowed_locations) == 1:
                rec.weighing_location_id = allowed_locations.id

    @api.constrains("qty")
    def _check_qty_positive(self):
        for rec in self:
            if rec.qty <= 0:
                raise ValidationError(_("Demand quantity untuk lot harus lebih dari nol."))
            required_qty = rec._get_required_transit_qty()
            if required_qty > 0.0 and rec.qty + 0.001 < required_qty:
                raise ValidationError(_(
                    "Demand Lot Transit %s tidak boleh kurang dari berat transit yang masuk (%.4f kg)."
                ) % (rec.lot_id.name or rec.display_name, required_qty))



    def action_remove_line(self):
        """Hapus baris lot yang belum di-pull."""
        self.ensure_one()
        if self._has_weighing_input():
            raise ValidationError(_(
                "Baris lot '%s' tidak dapat dihapus karena statusnya sudah di-pull oleh operator timbang."
            ) % (self.lot_id.name or self.display_name))
        return self.unlink()

    def action_cancel_lot(self):
        """Batalkan baris lot rencana DO yang sudah di-pull."""
        for rec in self:
            if rec.do_line_id and rec.do_line_id.picking_id and rec.do_line_id.picking_id.state == "done":
                raise ValidationError(_("Tidak dapat membatalkan lot karena Rencana DO sudah selesai divalidasi."))
            rec.write({
                "wt_is_cancelled": True,
                "wt_weighing_status": "cancelled",
            })
            if rec.delivery_id:
                rec.delivery_id.modified(["do_lot_line_ids", "total_demand_qty", "total_physical_qty", "total_difference_qty"])
        return False

    def action_uncancel_lot(self):
        """Aktifkan kembali baris lot rencana DO yang sebelumnya dibatalkan."""
        for rec in self:
            if rec.do_line_id and rec.do_line_id.picking_id and rec.do_line_id.picking_id.state == "done":
                raise ValidationError(_("Tidak dapat mengaktifkan kembali lot karena Rencana DO sudah selesai divalidasi."))
            rec.write({
                "wt_is_cancelled": False,
            })
            rec._compute_wt_weighing_status()
            if rec.delivery_id:
                rec.delivery_id.modified(["do_lot_line_ids", "total_demand_qty", "total_physical_qty", "total_difference_qty"])
        return False

    def action_configure_allocation(self):
        """Buka popup alokasi selisih untuk lot rencana DO."""
        self.ensure_one()
        if self.wt_weighing_status != "weighed":
            raise ValidationError(_("Cannot allocate difference before the delivery lot line is weighed."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Alokasi Selisih (Rencana): %s") % (self.lot_id.name or self.product_id.display_name),
            "res_model": "wt.delivery.do.line.lot",
            "res_id": self.id,
            "view_mode": "form",
            "view_id": self.env.ref("weightrack.view_wt_delivery_do_lot_allocation_popup").id,
            "target": "new",
        }
