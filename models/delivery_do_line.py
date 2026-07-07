# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DeliveryDoLine(models.Model):
    _name = "wt.delivery.do.line"
    _description = "Rencana DO (Baris Perincian Delivery Order)"
    _order = "delivery_id, sequence, id"

    delivery_id = fields.Many2one(
        "wt.delivery",
        string="Tugas Pengiriman",
        required=False,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(
        string="Urutan",
        default=10,
    )
    company_id = fields.Many2one(
        "res.company",
        related="delivery_id.company_id",
        store=True,
        readonly=True,
    )

    # ── Konfigurasi DO ────────────────────────────────────────────────────────
    picking_type_id = fields.Many2one(
        "stock.picking.type",
        string="Tipe Operasi",
        required=True,
        domain="[('code', 'in', ['outgoing', 'internal']), ('company_id', '=', company_id)]",
    )
    operator_id = fields.Many2one(
        "hr.employee",
        string="Operator",
        required=True,
        help="Operator yang bertanggung jawab atas Delivery Order ini.",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Produk",
        required=True,
        help="Produk yang akan dikirim dalam DO ini.",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Lokasi Sumber",
        domain="[('usage', '=', 'internal')]",
        help="Lokasi asal stok.",
    )
    location_dest_id = fields.Many2one(
        "stock.location",
        string="Lokasi Tujuan",
        domain="[('usage', 'in', ['internal', 'transit', 'customer'])]",
        help="Lokasi tujuan. Auto-isi dari Rute Transit untuk Transfer Internal.",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Partner / Alamat Tujuan",
        help="Alamat tujuan. Kosongkan untuk menggunakan customer di header.",
    )
    scheduled_date = fields.Datetime(
        string="Tanggal Terjadwal",
        default=fields.Datetime.now,
    )
    demand_qty = fields.Float(
        string="Demand (kg)",
        compute="_compute_demand_qty",
        store=True,
        readonly=False,
        digits="Product Unit of Measure",
        help="Total kuantitas yang akan dikirim dalam DO ini. Otomatis terjumlah dari rincian lot jika diisi.",
    )

    # ── Rincian Lot (Sub-form/Perincian Lot) ──────────────────────────────────
    lot_line_ids = fields.One2many(
        "wt.delivery.do.line.lot",
        "do_line_id",
        string="Rincian Lot",
        copy=True,
    )

    # ── Info Rute ─────────────────────────────────────────────────────────────
    route_id = fields.Many2one(
        "wt.delivery.route",
        string="Rute",
        help="Pilih Rute untuk mengisi otomatis lokasi sumber dan tujuan.",
    )

    # ── Hasil generate (terisi setelah Validasi) ──────────────────────────────
    picking_id = fields.Many2one(
        "stock.picking",
        string="DO Terbentuk",
        readonly=True,
        copy=False,
        help="DO yang dibuat dari baris ini saat Validasi.",
    )
    picking_state = fields.Selection(
        related="picking_id.state",
        string="Status DO",
        readonly=True,
    )

    # ── Computed ──────────────────────────────────────────────────────────────

    @api.depends("lot_line_ids.qty")
    def _compute_demand_qty(self):
        for rec in self:
            if rec.lot_line_ids:
                rec.demand_qty = sum(rec.lot_line_ids.mapped("qty"))

    # ── Onchange ──────────────────────────────────────────────────────────────

    @api.onchange("route_id")
    def _onchange_route_id(self):
        """
        Auto-isi Tipe Operasi, Lokasi Sumber, dan Lokasi Tujuan dari Rute Transit.
        Route dipilih pertama; lokasi mengikuti mapping rute.
        """
        if self.route_id:
            if self.route_id.picking_type_id:
                self.picking_type_id = self.route_id.picking_type_id
            if self.route_id.source_location_id:
                self.location_id = self.route_id.source_location_id
            if self.route_id.transit_location_id:
                self.location_dest_id = self.route_id.transit_location_id

    @api.onchange("picking_type_id")
    def _onchange_picking_type_id(self):
        """
        Auto-isi lokasi sumber & tujuan dari tipe operasi.
        Jika route_id sudah dipilih, lokasi sudah diisi oleh _onchange_route_id
        sehingga lokasi TIDAK ditimpa dari default picking type.
        """
        if self.picking_type_id:
            # Jangan timpa lokasi kalau route_id sudah dipilih
            if not self.route_id:
                self.location_id = self.picking_type_id.default_location_src_id
                if self.picking_type_id.code == "outgoing":
                    self.location_dest_id = self.picking_type_id.default_location_dest_id
                else:
                    self.location_dest_id = False
            # Default produk dari header delivery jika belum diisi
            if not self.product_id and self.delivery_id.product_id:
                self.product_id = self.delivery_id.product_id

    @api.onchange("location_id")
    def _onchange_location_id(self):
        """
        Auto-isi lokasi tujuan dari rute ketika picking_type internal.
        TIDAK mengubah route_id — route ditentukan oleh user, bukan dari lokasi.
        """
        if not self.location_id:
            return
        if self.route_id and self.picking_type_id and self.picking_type_id.code == "internal":
            self.location_dest_id = self.route_id.transit_location_id

    @api.onchange("demand_qty", "product_id", "location_id")
    def _onchange_auto_allocate_lots(self):
        """Auto-alokasi lot secara in-memory saat demand_qty, product_id, atau location_id berubah."""
        if not self.product_id or not self.location_id or self.demand_qty <= 0:
            return

        # Hanya lakukan auto-alokasi jika lot_line_ids kosong (belum diisi manual)
        # atau jika demand_qty berubah dan total qty di lot_line_ids berbeda dengan demand_qty baru.
        total_lot_qty = sum(self.lot_line_ids.mapped("qty"))
        if self.lot_line_ids and abs(total_lot_qty - self.demand_qty) <= 0.001:
            return

        # Bersihkan lot_line_ids lama
        self.lot_line_ids = [(5, 0, 0)]

        # Cari quants di lokasi sumber (dan lokasi di bawahnya)
        locations = self.env["stock.location"].search([("id", "child_of", self.location_id.id)])
        quants = self.env["stock.quant"].search([
            ("product_id", "=", self.product_id.id),
            ("location_id", "in", locations.ids),
            ("quantity", ">", 0),
            ("lot_id", "!=", False),
        ])

        # Urutkan quants berdasarkan tanggal pembuatan lot (tertua dahulu / FIFO)
        quants = quants.sorted(key=lambda q: (q.lot_id.create_date or fields.Datetime.now(), q.lot_id.name))

        remaining_need = self.demand_qty
        lot_vals = []

        for quant in quants:
            if remaining_need <= 0:
                break

            # Stok tersedia = kuantitas fisik - kuantitas tereservasi
            avail_qty = quant.quantity - quant.reserved_quantity
            if avail_qty <= 0:
                continue

            take_qty = min(avail_qty, remaining_need)
            lot_vals.append((0, 0, {
                "lot_id": quant.lot_id.id,
                "qty": take_qty,
            }))
            remaining_need -= take_qty

        if lot_vals:
            self.lot_line_ids = lot_vals

    # ── Default get ───────────────────────────────────────────────────────────

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        delivery_id = self.env.context.get("default_delivery_id")
        if delivery_id:
            delivery = self.env["wt.delivery"].browse(delivery_id)
            picking_type = self.env["stock.picking.type"].search(
                [
                    ("code", "=", "outgoing"),
                    ("company_id", "=", delivery.company_id.id),
                ],
                limit=1,
            )
            if picking_type:
                res["picking_type_id"] = picking_type.id
                res["location_id"] = picking_type.default_location_src_id.id or False
                res["location_dest_id"] = picking_type.default_location_dest_id.id or False
            if delivery.product_id:
                res["product_id"] = delivery.product_id.id
        return res

    # ── Validasi ──────────────────────────────────────────────────────────────

    def _validate_before_generate(self):
        """Validasi kelengkapan data sebelum generate picking."""
        self.ensure_one()
        missing = []
        if not self.picking_type_id:
            missing.append(_("Tipe Operasi"))
        if not self.operator_id:
            missing.append(_("Operator"))
        if not self.product_id:
            missing.append(_("Produk"))
        if not self.location_id:
            missing.append(_("Lokasi Sumber"))
        if not self.location_dest_id:
            missing.append(_("Lokasi Tujuan"))
        if self.demand_qty <= 0:
            missing.append(_("Demand (kg) harus > 0"))
        if missing:
            raise ValidationError(_(
                "Baris DO urutan %d belum lengkap, isi dahulu:\n%s"
            ) % (self.sequence, "\n".join("• " + m for m in missing)))

        # Cek jika ada lot yang memiliki selisih timbang tapi belum teralokasi penuh
        unallocated_lots = self.lot_line_ids.filtered(
            lambda l: not l.wt_skip_line and abs(l.wt_difference_qty) > 0.001 and not l.wt_is_fully_allocated
        )
        if unallocated_lots:
            lot_details = "\n".join(
                "- %s (selisih: %.4f kg, sisa: %.4f kg)" % (
                    l.lot_id.name or l.product_id.name,
                    l.wt_difference_qty,
                    l.wt_unallocated_qty,
                )
                for l in unallocated_lots
            )
            raise ValidationError(_(
                "Baris DO urutan %d tidak dapat divalidasi karena selisih timbang "
                "pada lot rencana berikut belum teralokasi penuh:\n\n%s\n\n"
                "Silakan isi alokasi selisih terlebih dahulu untuk lot-lot tersebut."
            ) % (self.sequence, lot_details))

    # ── Business Logic ────────────────────────────────────────────────────────

    def _action_create_done_picking(self):
        """
        Buat stock.picking dari baris ini dan langsung validasi ke status 'done'.
        Dipanggil oleh wt.delivery.action_validate() saat semua proses selesai.
        """
        self.ensure_one()
        delivery = self.delivery_id

        if self.picking_id and self.picking_id.state == "done":
            return self.picking_id

        self._validate_before_generate()

        src_location = self.location_id or self.picking_type_id.default_location_src_id
        dest_location = self.location_dest_id or self.picking_type_id.default_location_dest_id
        partner = (
            self.partner_id
            or delivery.partner_id
            or False
        )
        product = self.product_id

        picking = self.env["stock.picking"].sudo().with_company(delivery.company_id).create({
            "picking_type_id": self.picking_type_id.id,
            "location_id": src_location.id,
            "location_dest_id": dest_location.id,
            "partner_id": partner.id if partner else False,
            "scheduled_date": self.scheduled_date or fields.Datetime.now(),
            "wt_delivery_id": delivery.id,
            "wt_operator_id": self.operator_id.id,
            "origin": delivery.name,
            "company_id": delivery.company_id.id,
            "move_ids": [(0, 0, {
                "description_picking": product.display_name,
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_qty": self.demand_qty,
                "location_id": src_location.id,
                "location_dest_id": dest_location.id,
                "company_id": delivery.company_id.id,
                "origin": delivery.name,
            })],
        })

        # Konfirmasi picking
        picking.action_confirm()

        # Odoo 19: Hapus default move line otomatis agar kita bisa force buat sesuai rincian lot kita
        picking.move_line_ids.unlink()
        move = picking.move_ids[:1]

        if self.lot_line_ids:
            for lot_line in self.lot_line_ids:
                if lot_line.wt_skip_line:
                    continue
                # Jika timbang kosong, default pakai demand
                qty_done = lot_line.wt_physical_qty if lot_line.wt_physical_qty > 0.0 else lot_line.qty
                # Cari lokasi fisik lot yang tepat (di bawah src_location)
                exact_loc = src_location
                locations = self.env["stock.location"].search([("id", "child_of", src_location.id)])
                quant = self.env["stock.quant"].search([
                    ("product_id", "=", product.id),
                    ("location_id", "in", locations.ids),
                    ("lot_id", "=", lot_line.lot_id.id),
                    ("quantity", ">", 0),
                ], limit=1)
                if quant:
                    exact_loc = quant.location_id

                self.env["stock.move.line"].sudo().create({
                    "move_id": move.id,
                    "picking_id": picking.id,
                    "product_id": product.id,
                    "product_uom_id": product.uom_id.id,
                    "lot_id": lot_line.lot_id.id,
                    "quantity": qty_done,
                    "location_id": exact_loc.id,
                    "location_dest_id": dest_location.id,
                    "company_id": delivery.company_id.id,
                })
        else:
            # Fallback jika tidak ada rincian lot sama sekali
            self.env["stock.move.line"].sudo().create({
                "move_id": move.id,
                "picking_id": picking.id,
                "product_id": product.id,
                "product_uom_id": product.uom_id.id,
                "quantity": self.demand_qty,
                "location_id": src_location.id,
                "location_dest_id": dest_location.id,
                "company_id": delivery.company_id.id,
            })

        # ── Sesuaikan demand move ke total qty fisik aktual ──────────────────
        # Ini mencegah Odoo membuat backorder karena demand > done.
        # Selisih (susut/rusak/hilang) sudah ditangani via alokasi adjustment terpisah.
        if self.lot_line_ids:
            total_physical = sum(
                (lot_line.wt_physical_qty if lot_line.wt_physical_qty > 0.0 else lot_line.qty)
                for lot_line in self.lot_line_ids
                if not lot_line.wt_skip_line
            )
        else:
            total_physical = self.demand_qty

        if total_physical > 0:
            move.sudo().with_context(do_not_unreserve=True).write({
                "product_uom_qty": total_physical,
            })

        # Validasi langsung ke done — tanpa backorder karena demand sudah disesuaikan ke fisik
        picking.with_context(
            skip_backorder=True,
            no_backorder=True,
            skip_immediate=True,
            wt_force_validate=True,
        ).button_validate()

        # Batalkan paksa backorder yang mungkin terbentuk (safety net)
        backorders = self.env["stock.picking"].search([
            ("backorder_id", "=", picking.id),
            ("state", "not in", ("done", "cancel")),
        ])
        if backorders:
            backorders.action_cancel()

        if picking.state != "done":
            raise ValidationError(_(
                "DO '%s' tidak bisa divalidasi otomatis. "
                "Periksa stok dan konfigurasi lokasi."
            ) % picking.display_name)

        self.picking_id = picking.id
        return picking

    def action_validate_line(self):
        """Validasi baris DO ini secara mandiri (membuat & memvalidasi stock.picking)."""
        for line in self:
            if line.picking_id and line.picking_id.state == "done":
                raise ValidationError(_("Baris DO ini sudah divalidasi."))
            line._action_create_done_picking()
        return True

    def action_auto_allocate_lots(self):
        """Mencari stok lot yang tersedia di lokasi sumber, lalu membuat rincian lot secara otomatis."""
        self.ensure_one()
        if not self.product_id or not self.location_id:
            raise ValidationError(_("Harap tentukan Produk dan Lokasi Sumber terlebih dahulu."))
        if self.demand_qty <= 0:
            raise ValidationError(_("Masukkan Demand (kg) terlebih dahulu sebelum melakukan auto-alokasi."))

        # Hapus rincian lot lama
        self.lot_line_ids.unlink()

        # Cari quants di lokasi sumber (dan lokasi di bawahnya)
        locations = self.env["stock.location"].search([("id", "child_of", self.location_id.id)])
        quants = self.env["stock.quant"].search([
            ("product_id", "=", self.product_id.id),
            ("location_id", "in", locations.ids),
            ("quantity", ">", 0),
            ("lot_id", "!=", False),
        ])

        # Urutkan quants berdasarkan tanggal pembuatan lot (tertua dahulu / FIFO)
        quants = quants.sorted(key=lambda q: (q.lot_id.create_date or fields.Datetime.now(), q.lot_id.name))

        remaining_need = self.demand_qty
        lot_vals = []

        for quant in quants:
            if remaining_need <= 0:
                break

            # Stok tersedia = kuantitas fisik - kuantitas tereservasi
            avail_qty = quant.quantity - quant.reserved_quantity
            if avail_qty <= 0:
                continue

            take_qty = min(avail_qty, remaining_need)
            lot_vals.append((0, 0, {
                "lot_id": quant.lot_id.id,
                "qty": take_qty,
            }))
            remaining_need -= take_qty

        if lot_vals:
            self.write({"lot_line_ids": lot_vals})

        # Kirimkan notifikasi jika stok kurang
        if remaining_need > 0:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Alokasi Stok Kurang"),
                    "message": _(
                        "Hanya berhasil mengalokasikan %.2f kg dari demand %.2f kg. "
                        "Sisa %.2f kg tidak memiliki alokasi lot karena kekurangan stok di lokasi %s."
                    ) % (self.demand_qty - remaining_need, self.demand_qty, remaining_need, self.location_id.display_name),
                    "type": "warning",
                    "sticky": True,
                }
            }

    def unlink(self):
        for rec in self:
            if rec.picking_id and rec.picking_id.state == "done":
                raise ValidationError(_(
                    "Baris DO Rute '%s' tidak dapat dihapus karena sudah divalidasi/selesai."
                ) % (rec.route_id.display_name or rec.picking_type_id.display_name))
        return super().unlink()

