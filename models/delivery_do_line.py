# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from ..constants.roles import Role


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
        help="Operator yang bertanggung jawab atas Delivery Order ini.",
    )
    allowed_operator_ids = fields.Many2many(
        "hr.employee",
        compute="_compute_allowed_operator_ids",
        string="Allowed Operators",
    )

    @api.depends("location_id", "company_id", "picking_type_id", "picking_type_id.warehouse_id.estate_id")
    def _compute_allowed_operator_ids(self):
        for line in self:
            estate = line.picking_type_id.warehouse_id.estate_id
            
            if not line.location_id:
                # Fallback: Tampilkan operator di estate ini, jika tidak ada baru tampilkan seluruh operator di company
                operators = self.env["hr.employee"]
                if estate:
                    weighing_locs = self.env["wt.weighing.location"].search([
                        ("estate_id", "=", estate.id),
                        ("company_id", "=", line.company_id.id),
                    ])
                    operators = weighing_locs.mapped("operator_id")
                
                if not operators:
                    operators = self.env["wt.employee.role"].get_allowed_employees(
                        line.company_id,
                        Role.OPERATOR
                    )
                line.allowed_operator_ids = operators
                continue

            # Cari Aturan Penerimaan (Receipt Rule) yang memetakan lokasi sumber ini atau anaknya
            domain = [
                ("location_id", "child_of", line.location_id.id),
                ("company_id", "=", line.company_id.id),
            ]
            if estate:
                domain.append(("estate_id", "=", estate.id))
                
            rules = self.env["wt.receipt.rule"].search(domain)
            # Dapatkan Weighing Location-nya
            weighing_locations = rules.mapped("weighing_location_id")
            # Ambil operator aktif yang ditugaskan di Weighing Location tersebut
            operators = weighing_locations.mapped("operator_id")

            # Jika tidak ditemukan mapping atau operator tidak terdefinisi di Weighing Location,
            # fallback ke operator yang ditugaskan di estate ini
            if not operators and estate:
                weighing_locs = self.env["wt.weighing.location"].search([
                    ("estate_id", "=", estate.id),
                    ("company_id", "=", line.company_id.id),
                ])
                operators = weighing_locs.mapped("operator_id")

            # Jika masih kosong, fallback ke seluruh operator di company tersebut
            if not operators:
                operators = self.env["wt.employee.role"].get_allowed_employees(
                    line.company_id,
                    Role.OPERATOR
                )
            line.allowed_operator_ids = operators

    @api.onchange("location_id")
    def _onchange_location_id_clear_operator(self):
        for line in self:
            if line.operator_id and line.operator_id not in line.allowed_operator_ids:
                line.operator_id = False
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
    handover_date = fields.Date(
        string="Tanggal Berita Acara",
        default=fields.Date.context_today,
    )
    handover_date_text = fields.Char(
        string="Tanggal Berita Acara (Teks)",
        compute="_compute_handover_date_text",
    )
    vehicle_plate = fields.Char(
        string="Nomor Polisi",
    )
    sent_to_pt = fields.Char(
        string="Dikirim ke PT",
    )
    tare_qty = fields.Float(
        string="Tare (kg)",
        digits="Product Unit of Measure",
    )
    net_qty = fields.Float(
        string="Netto (kg)",
        compute="_compute_weight_summary",
        digits="Product Unit of Measure",
    )
    gross_qty = fields.Float(
        string="Bruto (kg)",
        compute="_compute_weight_summary",
        digits="Product Unit of Measure",
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
    generated_transit_lot_id = fields.Many2one(
        "stock.lot",
        string="Lot Transit",
        readonly=True,
        copy=False,
        index=True,
        help="Lot baru yang terbentuk saat rute transit divalidasi.",
    )

    # ── Computed ──────────────────────────────────────────────────────────────

    @api.depends("lot_line_ids.qty")
    def _compute_demand_qty(self):
        for rec in self:
            if rec.lot_line_ids:
                rec.demand_qty = sum(rec.lot_line_ids.mapped("qty"))

    @api.depends("demand_qty", "tare_qty", "lot_line_ids.wt_physical_qty", "lot_line_ids.wt_skip_line")
    def _compute_weight_summary(self):
        for rec in self:
            active_lots = rec.lot_line_ids.filtered(lambda lot: not lot.wt_skip_line)
            physical_qty = sum(active_lots.mapped("wt_physical_qty"))
            rec.net_qty = physical_qty if physical_qty > 0.0 else rec.demand_qty
            rec.gross_qty = rec.tare_qty + rec.net_qty

    @api.depends("handover_date")
    def _compute_handover_date_text(self):
        month_names = {
            1: "Januari",
            2: "Februari",
            3: "Maret",
            4: "April",
            5: "Mei",
            6: "Juni",
            7: "Juli",
            8: "Agustus",
            9: "September",
            10: "Oktober",
            11: "November",
            12: "Desember",
        }
        for rec in self:
            if rec.handover_date:
                date_value = fields.Date.to_date(rec.handover_date)
                rec.handover_date_text = "%s %s %s" % (
                    date_value.day,
                    month_names[date_value.month],
                    date_value.year,
                )
            else:
                rec.handover_date_text = False

    # ── Onchange ──────────────────────────────────────────────────────────────

    @api.onchange("route_id")
    def _onchange_route_id(self):
        """
        Auto-isi Tipe Operasi, Lokasi Sumber, dan Lokasi Tujuan dari Rute Transit.
        Route dipilih pertama; lokasi mengikuti mapping rute.
        Jika route dikosongkan, bersihkan semua field yang terisi otomatis.
        """
        if self.route_id:
            if self.route_id.picking_type_id:
                self.picking_type_id = self.route_id.picking_type_id
            if self.route_id.source_location_id:
                self.location_id = self.route_id.source_location_id
            if self.route_id.transit_location_id:
                self.location_dest_id = self.route_id.transit_location_id
        else:
            # Kosongkan field yang diisi otomatis oleh route
            self.picking_type_id = False
            self.location_id = False
            self.location_dest_id = False

    @api.onchange("picking_type_id")
    def _onchange_picking_type_id(self):
        """
        picking_type_id sekarang selalu diisi via route (readonly di view).
        Onchange ini hanya mengisi produk default dari konfigurasi wt.product.
        Pengisian lokasi tidak dilakukan di sini karena hanya route yang boleh mengisi.
        """
        if self.picking_type_id and not self.product_id:
            self.product_id = self._get_configured_product()

    @api.onchange("delivery_id", "company_id")
    def _onchange_delivery_company_set_product(self):
        for line in self:
            line.product_id = line._get_configured_product()

    def _get_configured_product(self):
        self.ensure_one()
        company = self.company_id or self.delivery_id.company_id or self.env.company
        return self.env["wt.product"].get_active_product(company)

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

    def _prepare_auto_lot_allocation(self, requested_qty):
        """Build lot-line commands from stock available in the complete source subtree.

        Each command keeps the exact physical location of the quant.  This is
        essential when one source location, such as ``SBY/Stock``, contains
        sibling storage branches that hold different lots.
        """
        self.ensure_one()
        quant_model = self.env["stock.quant"].sudo().with_company(self.company_id)
        quants = quant_model.search([
            ("product_id", "=", self.product_id.id),
            ("location_id", "child_of", self.location_id.id),
            ("quantity", ">", 0),
            ("lot_id", "!=", False),
        ])
        fallback_production_date = fields.Date.to_date("9999-12-31")
        quants = quants.sorted(
            key=lambda quant: (
                quant.lot_id.production_date is False,
                quant.lot_id.production_date or fallback_production_date,
                quant.lot_id.create_date or fields.Datetime.now(),
                quant.lot_id.name,
                quant.location_id.complete_name,
            )
        )

        # Rencana DO tidak membuat stock.picking saat masih draft. Karena itu,
        # reservasi dari Rencana DO lain belum selalu tercermin di
        # stock.quant.reserved_quantity. Samakan perhitungan ini dengan
        # _check_lot_stock_limits agar lot pertama tidak dialokasikan melebihi
        # stok bebasnya.
        current_delivery_id = self._get_persisted_delivery_id()
        active_do_line_domain = [
            ("delivery_id.state", "in", ("draft", "confirmed", "in_progress", "completed")),
        ]
        if current_delivery_id:
            active_do_line_domain.append(("delivery_id", "!=", current_delivery_id))
        active_do_lines = self.env["wt.delivery.do.line"].search(
            active_do_line_domain
        )
        planned_reserved_by_lot = {}
        if active_do_lines:
            planned_lot_lines = self.env["wt.delivery.do.line.lot"].sudo().search([
                ("do_line_id", "in", active_do_lines.ids),
                ("wt_skip_line", "=", False),
            ])
            for planned_line in planned_lot_lines:
                planned_reserved_by_lot[planned_line.lot_id.id] = (
                    planned_reserved_by_lot.get(planned_line.lot_id.id, 0.0)
                    + planned_line.qty
                )

        remaining_need = requested_qty
        lot_vals = []
        for quant in quants:
            if remaining_need <= 0:
                break

            planned_reserved_qty = planned_reserved_by_lot.get(quant.lot_id.id, 0.0)
            physical_available_qty = max(
                0.0,
                quant.quantity - quant.reserved_quantity,
            )
            available_qty = max(
                0.0,
                physical_available_qty - planned_reserved_qty,
            )
            # Satu lot dapat tersebar di beberapa sublokasi. Kurangi reservasi
            # rencana hanya sekali, dari quant pertama lot tersebut.
            planned_reserved_by_lot[quant.lot_id.id] = max(
                0.0,
                planned_reserved_qty - physical_available_qty,
            )
            if available_qty <= 0:
                continue

            take_qty = min(available_qty, remaining_need)
            lot_vals.append((0, 0, {
                "lot_id": quant.lot_id.id,
                "source_location_id": quant.location_id.id,
                "qty": take_qty,
            }))
            remaining_need -= take_qty

        return lot_vals, remaining_need

    def _get_persisted_delivery_id(self):
        """Return the database ID when this record is an onchange virtual copy."""
        self.ensure_one()
        return (
            self._origin.delivery_id.id
            or self.delivery_id._origin.id
            or (self.delivery_id.id if isinstance(self.delivery_id.id, int) else False)
        )

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
            else:
                product = self.env["wt.product"].get_active_product(delivery.company_id)
                if product:
                    res["product_id"] = product.id
        return res

    # ── Validasi ──────────────────────────────────────────────────────────────

    def _validate_before_generate(self):
        """Validasi kelengkapan data sebelum generate picking."""
        self.ensure_one()
        missing = []
        active_lot_lines = self.lot_line_ids.filtered(lambda l: not l.wt_skip_line)
        if not self.picking_type_id:
            missing.append(_("Tipe Operasi"))
        lot_operators = active_lot_lines.mapped("operator_id")
        if not lot_operators:
            missing.append(_("Operator"))
        if not self.product_id:
            missing.append(_("Produk"))
        if not self.location_id:
            missing.append(_("Lokasi Sumber"))
        if not self.location_dest_id:
            missing.append(_("Lokasi Tujuan"))
        if self.demand_qty <= 0:
            missing.append(_("Demand (kg) harus > 0"))
        requires_transit_lot = self._requires_transit_lot_source()
        if self.route_id.is_transit and not active_lot_lines:
            missing.append(_("Lot asal untuk rute transit"))
        if requires_transit_lot and not active_lot_lines:
            missing.append(_("Lot transit"))
        if missing:
            raise ValidationError(_(
                "Baris DO urutan %d belum lengkap, isi dahulu:\n%s"
            ) % (self.sequence, "\n".join("• " + m for m in missing)))

        if requires_transit_lot and active_lot_lines:
            non_transit_lots = active_lot_lines.filtered(
                lambda l: l.lot_id and l.lot_id.wt_lot_type != "transit"
            )
            if non_transit_lots:
                lot_names = ", ".join(non_transit_lots.mapped("lot_id.name"))
                raise ValidationError(_(
                    "Baris DO urutan %d mengambil stok dari lokasi transit. "
                    "Lot yang dipilih wajib Lot Transit.\n"
                    "Lot bukan transit: %s"
                ) % (self.sequence, lot_names))
            expected_transit_lots = self._get_expected_transit_lots()
            unexpected_lots = active_lot_lines.filtered(
                lambda l: expected_transit_lots and l.lot_id not in expected_transit_lots
            )
            if unexpected_lots:
                expected_names = ", ".join(expected_transit_lots.mapped("name"))
                unexpected_names = ", ".join(unexpected_lots.mapped("lot_id.name"))
                raise ValidationError(_(
                    "Baris DO urutan %d wajib memakai Lot Transit hasil rute transit sebelumnya.\n"
                    "Lot yang seharusnya dipakai: %s\n"
                    "Lot yang tidak sesuai: %s"
                ) % (self.sequence, expected_names, unexpected_names))

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

    def _get_lot_line_source_location(self, lot_line, source_location):
        """Return the physical source location selected for a planned lot."""
        self.ensure_one()
        physical_location = lot_line.source_location_id
        if physical_location and (
            physical_location == source_location
            or physical_location.parent_path.startswith(source_location.parent_path)
        ):
            return physical_location

        quant = self.env["stock.quant"].sudo().with_company(self.company_id).search([
            ("product_id", "=", self.product_id.id),
            ("location_id", "child_of", source_location.id),
            ("lot_id", "=", lot_line.lot_id.id),
            ("quantity", ">", 0),
        ], order="location_id, id", limit=1)
        return quant.location_id or source_location

    def _get_warehouse_for_location(self, location):
        self.ensure_one()
        if not location or not location.parent_path:
            return self.env["stock.warehouse"]
        warehouses = self.env["stock.warehouse"].sudo().search([
            ("company_id", "=", self.company_id.id),
        ])
        best_warehouse = self.env["stock.warehouse"]
        best_length = 0
        for warehouse in warehouses:
            parent_path = warehouse.view_location_id.parent_path
            if parent_path and location.parent_path.startswith(parent_path):
                path_length = len(parent_path)
                if path_length > best_length:
                    best_warehouse = warehouse
                    best_length = path_length
        return best_warehouse

    def _clean_lot_component(self, value):
        value = (value or "").strip()
        return value.replace("/", "-").replace("\\", "-").replace(" ", "-") or "TRANSIT"

    def _requires_transit_lot_source(self):
        """Return True when this line must consume a transit lot."""
        self.ensure_one()
        if not self.location_id:
            return False
        if self.location_id.usage == "transit":
            return True

        transit_destinations = self.delivery_id.do_line_ids.filtered(
            lambda l: l.id != self.id and l.route_id.is_transit and l.location_dest_id
        ).mapped("location_dest_id")
        return any(
            dest.parent_path
            and self.location_id.parent_path
            and self.location_id.parent_path.startswith(dest.parent_path)
            for dest in transit_destinations
        )

    def _get_expected_transit_lots(self):
        """Transit lots generated by previous transit lines into this source."""
        self.ensure_one()
        if not self.delivery_id or not self.location_id:
            return self.env["stock.lot"]
        transit_lines = self.delivery_id.do_line_ids.filtered(
            lambda l: l.id != self.id
            and l.route_id.is_transit
            and l.location_dest_id
            and l.generated_transit_lot_id
            and self.location_id.parent_path
            and l.location_dest_id.parent_path
            and self.location_id.parent_path.startswith(l.location_dest_id.parent_path)
        )
        return transit_lines.mapped("generated_transit_lot_id")

    # ── ORM ───────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        """Saat do_line dibuat, auto-save parent delivery agar header ikut tersimpan."""
        for vals in vals_list:
            if not vals.get("product_id"):
                delivery = self.env["wt.delivery"].browse(vals.get("delivery_id")) if vals.get("delivery_id") else False
                company = (
                    delivery.company_id
                    if delivery
                    else (self.env["res.company"].browse(vals.get("company_id")) if vals.get("company_id") else self.env.company)
                )
                product = self.env["wt.product"].get_active_product(company)
                if product:
                    vals["product_id"] = product.id
        records = super().create(vals_list)
        # Trigger write pada delivery agar frontend tahu record berubah
        # dan agar timestamp write_date diperbarui
        delivery_ids = records.mapped("delivery_id").filtered(lambda d: d.id)
        if delivery_ids:
            delivery_ids.write({"write_date": fields.Datetime.now()})
        return records

    def write(self, vals):
        """Saat do_line di-update, pastikan delivery juga di-touch."""
        if "delivery_id" in vals and "product_id" not in vals:
            delivery = self.env["wt.delivery"].browse(vals["delivery_id"])
            product = self.env["wt.product"].get_active_product(delivery.company_id)
            if product:
                vals = dict(vals, product_id=product.id)
        res = super().write(vals)
        delivery_ids = self.mapped("delivery_id").filtered(lambda d: d.id)
        if delivery_ids and any(k not in ("write_date", "write_uid") for k in vals):
            delivery_ids.write({"write_date": fields.Datetime.now()})
        return res

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
        active_lot_lines = self.lot_line_ids.filtered(lambda line: not line.wt_skip_line)

        # Hitung total physical qty
        if active_lot_lines:
            total_physical = sum(
                (lot_line.wt_physical_qty if lot_line.wt_physical_qty > 0.0 else lot_line.qty)
                for lot_line in active_lot_lines
            )
        else:
            total_physical = self.demand_qty

        # Cek jika rute ini adalah rute transit (is_transit)
        is_transit_merge = bool(self.route_id.is_transit)

        move_vals = []
        if is_transit_merge:
            # Cari inventory loss location
            inventory_loss_loc = self.env["stock.location"].sudo().search([
                ("usage", "=", "inventory"),
                ("company_id", "=", delivery.company_id.id),
            ], limit=1)
            if not inventory_loss_loc:
                inventory_loss_loc = self.env["stock.location"].sudo().search([
                    ("usage", "=", "inventory"),
                ], limit=1)

            # Move 1: Consume old lots (Src -> Inventory Loss)
            move_vals.append({
                "description_picking": f"Consume old lots for transit merge - {product.display_name}",
                "inventory_name": _("Pengiriman"),
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_qty": total_physical,
                "location_id": src_location.id,
                "location_dest_id": inventory_loss_loc.id,
                "company_id": delivery.company_id.id,
                "origin": delivery.name,
            })
            # Move 2: Produce new merged lot (Inventory Loss -> Dest)
            move_vals.append({
                "description_picking": f"Produce new merged lot for transit - {product.display_name}",
                "inventory_name": _("Pengiriman"),
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_qty": total_physical,
                "location_id": inventory_loss_loc.id,
                "location_dest_id": dest_location.id,
                "company_id": delivery.company_id.id,
                "origin": delivery.name,
            })
        else:
            # Normal direct internal transfer/delivery move
            move_vals.append({
                "description_picking": product.display_name,
                "inventory_name": _("Pengiriman"),
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_qty": total_physical,
                "location_id": src_location.id,
                "location_dest_id": dest_location.id,
                "company_id": delivery.company_id.id,
                "origin": delivery.name,
            })

        picking = self.env["stock.picking"].sudo().with_company(delivery.company_id).create({
            "picking_type_id": self.picking_type_id.id,
            "location_id": src_location.id,
            "location_dest_id": dest_location.id,
            "partner_id": partner.id if partner else False,
            "scheduled_date": self.scheduled_date or fields.Datetime.now(),
            "wt_delivery_id": delivery.id,
            "wt_operator_id": self.operator_id.id or (self.lot_line_ids.mapped("operator_id")[:1].id if self.lot_line_ids.mapped("operator_id") else False),
            "origin": delivery.name,
            "company_id": delivery.company_id.id,
            "move_ids": [(0, 0, val) for val in move_vals],
        })

        # Konfirmasi picking
        picking.action_confirm()

        # Odoo 19: Hapus default move line otomatis agar kita bisa force buat sesuai rincian lot kita
        picking.move_line_ids.unlink()

        if is_transit_merge:
            move_1 = picking.move_ids[0]
            move_2 = picking.move_ids[1]
            destination_warehouse = self._get_warehouse_for_location(dest_location)

            # Generate new lot
            today_str = fields.Date.today().strftime("%Y%m%d")
            destination_code = self._clean_lot_component(
                destination_warehouse.code or dest_location.name
            )
            prefix = f"TR/{destination_code}/{today_str}/"
            last_lot = self.env["stock.lot"].sudo().search([
                ("name", "=like", prefix + "%"),
                ("product_id", "=", product.id),
                ("company_id", "=", delivery.company_id.id),
            ], order="name desc", limit=1)
            if last_lot:
                try:
                    last_seq = int(last_lot.name.split("/")[-1])
                    new_seq = last_seq + 1
                except (ValueError, IndexError):
                    new_seq = 1
            else:
                new_seq = 1
            new_lot_name = f"{prefix}{new_seq:03d}"
            source_lots = active_lot_lines.mapped("lot_id")
            source_divisions = source_lots.mapped("division_id")
            source_production_dates = [
                lot.production_date for lot in source_lots if lot.production_date
            ]
            transit_date = fields.Date.context_today(self)

            new_lot = self.env["stock.lot"].sudo().create({
                "name": new_lot_name,
                "product_id": product.id,
                "company_id": delivery.company_id.id,
                "wt_lot_type": "transit",
                "wt_transit_state": "open",
                "division_id": source_divisions.id if len(source_divisions) == 1 else False,
                "production_date": min(source_production_dates) if source_production_dates else False,
                "wt_receiving_location_id": dest_location.id,
                "wt_source_delivery_id": delivery.id,
                "wt_source_picking_id": picking.id,
                "wt_transit_date": transit_date,
            })

            # 1. Consume old lots
            for lot_line in active_lot_lines:
                qty_done = lot_line.wt_physical_qty if lot_line.wt_physical_qty > 0.0 else lot_line.qty
                exact_loc = self._get_lot_line_source_location(lot_line, src_location)

                self.env["stock.move.line"].sudo().create({
                    "move_id": move_1.id,
                    "picking_id": picking.id,
                    "product_id": product.id,
                    "product_uom_id": product.uom_id.id,
                    "lot_id": lot_line.lot_id.id,
                    "quantity": qty_done,
                    "location_id": exact_loc.id,
                    "location_dest_id": inventory_loss_loc.id,
                    "company_id": delivery.company_id.id,
                })

            # 2. Produce new merged lot
            self.env["stock.move.line"].sudo().create({
                "move_id": move_2.id,
                "picking_id": picking.id,
                "product_id": product.id,
                "product_uom_id": product.uom_id.id,
                "lot_id": new_lot.id,
                "quantity": total_physical,
                "location_id": inventory_loss_loc.id,
                "location_dest_id": dest_location.id,
                "company_id": delivery.company_id.id,
            })
            self.generated_transit_lot_id = new_lot.id
        else:
            move = picking.move_ids[:1]
            if self.lot_line_ids:
                for lot_line in self.lot_line_ids:
                    if lot_line.wt_skip_line:
                        continue
                    qty_done = lot_line.wt_physical_qty if lot_line.wt_physical_qty > 0.0 else lot_line.qty
                    exact_loc = self._get_lot_line_source_location(lot_line, src_location)

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

    @api.constrains("lot_line_ids", "lot_line_ids.qty", "lot_line_ids.lot_id")
    def _check_lot_stock_limits(self):
        for line in self:
            if not line.lot_line_ids:
                continue
            # Kelompokkan baris berdasarkan lot_id
            lot_groups = {}
            for lot_line in line.lot_line_ids:
                if not lot_line.lot_id:
                    continue
                lot_groups.setdefault(lot_line.lot_id, []).append(lot_line)

            for lot, lot_lines in lot_groups.items():
                total_planned_qty = sum(l.qty for l in lot_lines)
                
                # Cari stok fisik di lokasi asal
                locations = self.env["stock.location"].search([("id", "child_of", line.location_id.id)])
                quants = self.env["stock.quant"].search([
                    ("product_id", "=", line.product_id.id),
                    ("location_id", "in", locations.ids),
                    ("lot_id", "=", lot.id),
                ])
                total_on_hand = sum(quants.mapped("quantity"))

                # Hitung demand yang direncanakan di Tugas Pengiriman aktif lainnya.
                # Gunakan 2-step search: (1) cari do_lines aktif dari delivery lain,
                # (2) cari lot_lines di do_lines tersebut pakai direct IN clause.
                current_delivery_id_c = line._get_persisted_delivery_id()
                active_do_line_domain_c = [
                    ("delivery_id.state", "in", ("draft", "confirmed", "in_progress", "completed")),
                ]
                if current_delivery_id_c:
                    active_do_line_domain_c.append(("delivery_id", "!=", current_delivery_id_c))
                active_do_lines_c = self.env["wt.delivery.do.line"].search(active_do_line_domain_c)
                if active_do_lines_c:
                    other_active_lines = self.env["wt.delivery.do.line.lot"].search([
                        ("lot_id", "=", lot.id),
                        ("do_line_id", "in", active_do_lines_c.ids),
                        ("wt_skip_line", "=", False),
                    ])
                    other_active_qty = sum(other_active_lines.mapped("qty"))
                else:
                    other_active_qty = 0.0
                
                if total_planned_qty + other_active_qty > total_on_hand:
                    available_qty = max(0.0, total_on_hand - other_active_qty)
                    raise ValidationError(_(
                        "Total rencana demand untuk Lot '%s' (%s kg) melebihi stok fisik bebas yang tersedia (%s kg).\n"
                        "Stok Fisik: %s kg, Sedang Dipesan di Tugas Pengiriman Lain: %s kg."
                    ) % (
                        lot.name,
                        f"{total_planned_qty:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                        f"{available_qty:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                        f"{total_on_hand:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                        f"{other_active_qty:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                    ))

    @api.onchange("lot_line_ids")
    def _onchange_lot_line_ids(self):
        # Validasi interaktif saat user mengedit atau menambah lot di UI (sebelum disave ke DB)
        if not self.lot_line_ids:
            return
        
        # Kelompokkan baris berdasarkan lot_id
        lot_groups = {}
        for lot_line in self.lot_line_ids:
            if not lot_line.lot_id:
                continue
            lot_groups.setdefault(lot_line.lot_id, []).append(lot_line)

        for lot, lot_lines in lot_groups.items():
            total_planned_qty = sum(l.qty for l in lot_lines)
            
            # Cari stok fisik di lokasi asal
            locations = self.env["stock.location"].search([("id", "child_of", self.location_id.id)])
            quants = self.env["stock.quant"].search([
                ("product_id", "=", self.product_id.id),
                ("location_id", "in", locations.ids),
                ("lot_id", "=", lot.id),
            ])
            total_on_hand = sum(quants.mapped("quantity"))

            # Hitung demand yang direncanakan di Tugas Pengiriman aktif lainnya.
            # Gunakan 2-step search yang sama seperti di _compute_qty_available.
            current_delivery_id_o = self._get_persisted_delivery_id()
            active_do_line_domain_o = [
                ("delivery_id.state", "in", ("draft", "confirmed", "in_progress", "completed")),
            ]
            if current_delivery_id_o:
                active_do_line_domain_o.append(("delivery_id", "!=", current_delivery_id_o))
            active_do_lines_o = self.env["wt.delivery.do.line"].search(active_do_line_domain_o)
            if active_do_lines_o:
                other_active_lines = self.env["wt.delivery.do.line.lot"].search([
                    ("lot_id", "=", lot.id),
                    ("do_line_id", "in", active_do_lines_o.ids),
                    ("wt_skip_line", "=", False),
                ])
                other_active_qty = sum(other_active_lines.mapped("qty"))
            else:
                other_active_qty = 0.0
            
            if total_planned_qty + other_active_qty > total_on_hand:
                available_qty = max(0.0, total_on_hand - other_active_qty)
                raise ValidationError(_(
                    "Total rencana demand untuk Lot '%s' (%s kg) melebihi stok fisik bebas yang tersedia (%s kg).\n"
                    "Stok Fisik: %s kg, Sedang Dipesan di Tugas Pengiriman Lain: %s kg."
                ) % (
                    lot.name,
                    f"{total_planned_qty:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                    f"{available_qty:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                    f"{total_on_hand:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                    f"{other_active_qty:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                ))

    def action_validate_line(self):
        """Validasi baris DO ini secara mandiri (membuat & memvalidasi stock.picking)."""
        for line in self:
            if line.picking_id and line.picking_id.state == "done":
                raise ValidationError(_("Baris DO ini sudah divalidasi."))
            line._action_create_done_picking()
        return True

    def action_print_despatch_slip(self):
        """Print DESPACT SLIP untuk baris Rencana DO yang sudah valid."""
        self.ensure_one()
        if self.picking_state != "done":
            raise ValidationError(_("Despatch Slip hanya bisa dicetak setelah Rencana DO divalidasi."))
        return self.env.ref("weightrack.action_report_despatch_slip").report_action(self)

    def action_print_handover_report(self):
        """Print Berita Acara Serah Terima Barang untuk baris Rencana DO."""
        self.ensure_one()
        if self.picking_state != "done":
            raise ValidationError(_("Berita Acara hanya bisa dicetak setelah Rencana DO divalidasi."))
        return self.env.ref("weightrack.action_report_delivery_handover").report_action(self)

    def action_print_seal_layout(self):
        """Print denah penyegelan untuk baris Rencana DO."""
        self.ensure_one()
        if self.picking_state != "done":
            raise ValidationError(_("Denah Penyegelan hanya bisa dicetak setelah Rencana DO divalidasi."))
        return self.env.ref("weightrack.action_report_seal_layout").report_action(self)

    def action_open_handover_details(self):
        """Buka popup edit khusus detail Berita Acara meskipun Rencana DO sudah readonly."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Detail Berita Acara"),
            "res_model": "wt.delivery.do.line",
            "res_id": self.id,
            "view_mode": "form",
            "view_id": self.env.ref("weightrack.view_wt_delivery_do_line_handover_form").id,
            "target": "new",
        }

    def action_auto_allocate_lots(self):
        """Mencari stok lot yang tersedia di lokasi sumber, lalu membuat rincian lot secara otomatis."""
        self.ensure_one()
        if not self.product_id or not self.location_id:
            raise ValidationError(_("Harap tentukan Produk dan Lokasi Sumber terlebih dahulu."))
        if self.demand_qty <= 0:
            raise ValidationError(_("Masukkan Demand (kg) terlebih dahulu sebelum melakukan auto-alokasi."))

        requested_qty = self.demand_qty

        # Hapus rincian lot lama
        self.lot_line_ids.unlink()

        lot_vals, remaining_need = self._prepare_auto_lot_allocation(requested_qty)

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
                    ) % (
                        requested_qty - remaining_need,
                        requested_qty,
                        remaining_need,
                        self.location_id.display_name,
                    ),
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
