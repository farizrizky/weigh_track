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
        string="Delivery Task",
        required=False,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
    )
    company_id = fields.Many2one(
        "res.company",
        related="delivery_id.company_id",
        store=True,
        readonly=True,
    )
    delivery_state = fields.Selection(
        related="delivery_id.state",
        string="Delivery State",
        store=True,
        readonly=True,
    )

    # â”€â”€ Konfigurasi DO â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    picking_type_id = fields.Many2one(
        "stock.picking.type",
        string="Operation Type",
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
        string="Product",
        required=True,
        help="Produk yang akan dikirim dalam DO ini.",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Source Location",
        domain="[('usage', '=', 'internal')]",
        help="Lokasi asal stok.",
    )
    location_dest_id = fields.Many2one(
        "stock.location",
        string="Destination Location",
        domain="[('usage', 'in', ['internal', 'transit', 'customer'])]",
        help="Lokasi tujuan. Auto-isi dari Rute Transit untuk Transfer Internal.",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Partner / Destination Address",
        help="Alamat tujuan. Kosongkan untuk menggunakan customer di header.",
    )
    scheduled_date = fields.Datetime(
        string="Scheduled Date",
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
        string="Handover Date",
    )
    handover_date_text = fields.Char(
        string="Handover Date (Text)",
        compute="_compute_handover_date_text",
    )
    handover_day_date_text = fields.Char(
        string="Handover Day and Date (Text)",
        compute="_compute_handover_date_text",
    )
    driver_name = fields.Char(
        string="Driver Name",
    )
    vehicle_plate = fields.Char(
        string="License Plate",
    )
    tare_qty = fields.Float(
        string="Tare (kg)",
        digits="Product Unit of Measure",
    )
    delivery_letter_no = fields.Char(
        string="Delivery Letter Number",
    )
    delivery_letter_date = fields.Date(
        string="Delivery Letter Date",
    )
    delivery_letter_date_text = fields.Char(
        string="Delivery Letter Date (Text)",
        compute="_compute_delivery_letter_date_text",
    )
    so_number = fields.Char(
        string="SO Number",
    )
    document_do_number = fields.Char(
        string="DO Number",
        help="Defaults from the Delivery Task number, but can be changed manually for the document.",
    )
    receiver_name = fields.Char(
        string="Receiver Name",
    )
    receiver_address = fields.Text(
        string="Receiver Address",
    )
    despatch_slip_no = fields.Char(
        string="Despatch Slip Number",
    )
    actual_physical_qty = fields.Float(
        string="Actual Physical Weight (kg)",
        compute="_compute_weight_summary",
        digits="Product Unit of Measure",
    )
    net_qty = fields.Float(
        string="Net Weight (kg)",
        compute="_compute_weight_summary",
        digits="Product Unit of Measure",
    )
    gross_qty = fields.Float(
        string="Gross Weight (kg)",
        compute="_compute_weight_summary",
        digits="Product Unit of Measure",
    )

    # ————————————————————————————————— Rincian Lot (Sub-form/Perincian Lot) —————————————————————————————————
    lot_line_ids = fields.One2many(
        "wt.delivery.do.line.lot",
        "do_line_id",
        string="Lot Details",
        copy=True,
    )

    @api.onchange("lot_line_ids")
    def _onchange_lot_line_ids_status(self):
        for line in self.lot_line_ids:
            if line.wt_is_cancelled:
                line.wt_weighing_status = "cancelled"
            elif not line._has_weighing_input() or line.qty <= 0.0:
                line.wt_weighing_status = "not_pulled"
            elif line.wt_weighing_source:
                line.wt_weighing_status = "weighed"
            else:
                line.wt_weighing_status = "unweighed"

    # â”€â”€ Info Rute â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    route_id = fields.Many2one(
        "wt.delivery.route",
        string="Route",
        help="Pilih Rute untuk mengisi otomatis lokasi sumber dan tujuan.",
    )
    route_line_id = fields.Many2one(
        "wt.delivery.route.line",
        string="Route Line",
        domain="[('route_id', '=', route_id)]",
        help="Baris rute pengiriman yang menjadi sumber konfigurasi operasi.",
    )
    route_type = fields.Selection(
        related="route_line_id.route_type",
        string="Route Type",
        readonly=True,
        store=True,
    )

    # â”€â”€ Hasil generate (terisi setelah Validasi) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    picking_id = fields.Many2one(
        "stock.picking",
        string="Created DO",
        readonly=True,
        copy=False,
        help="DO yang dibuat dari baris ini saat Validasi.",
    )
    return_picking_id = fields.Many2one(
        "stock.picking",
        string="Inventory Return",
        readonly=True,
        copy=False,
        index=True,
        help="Inventory return document created when this delivery line is returned.",
    )
    picking_state = fields.Selection(
        related="picking_id.state",
        string="DO Status",
        readonly=True,
    )
    route_process_status = fields.Selection(
        [
            ("preparation", "Preparation"),
            ("in_process", "In Process"),
            ("done", "Done"),
        ],
        string="DO Status",
        compute="_compute_route_process_status",
        store=False,
    )
    can_validate_line = fields.Boolean(
        string="Can Validate",
        compute="_compute_route_process_status",
        store=False,
    )
    generated_transit_lot_id = fields.Many2one(
        "stock.lot",
        string="Transit Lot",
        readonly=True,
        copy=False,
        index=True,
        help="Lot baru yang terbentuk saat rute transit divalidasi.",
    )

    # â”€â”€ Computed â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @api.depends("lot_line_ids.qty", "lot_line_ids.wt_is_cancelled")
    def _compute_demand_qty(self):
        for rec in self:
            active_lots = rec.lot_line_ids.filtered(lambda l: not l.wt_is_cancelled)
            if active_lots:
                rec.demand_qty = sum(active_lots.mapped("qty"))
            elif rec.lot_line_ids:
                rec.demand_qty = 0.0

    @api.depends("tare_qty", "lot_line_ids.wt_physical_qty", "lot_line_ids.wt_is_cancelled")
    def _compute_weight_summary(self):
        for rec in self:
            active_lots = rec.lot_line_ids.filtered(lambda l: not l.wt_is_cancelled)
            physical_qty = sum(active_lots.mapped("wt_physical_qty"))
            rec.actual_physical_qty = physical_qty
            rec.net_qty = physical_qty
            rec.gross_qty = (rec.tare_qty or 0.0) + physical_qty if physical_qty or rec.tare_qty else 0.0

    @api.depends(
        "sequence",
        "picking_id.state",
        "lot_line_ids.qty",
        "lot_line_ids.wt_is_pulled",
        "lot_line_ids.wt_weighing_status",
        "lot_line_ids.wt_difference_qty",
        "lot_line_ids.wt_is_fully_allocated",
        "delivery_id.do_line_ids.sequence",
        "delivery_id.do_line_ids.picking_id.state",
    )
    def _compute_route_process_status(self):
        for rec in self:
            if rec.picking_id and rec.picking_id.state == "done":
                rec.route_process_status = "done"
                rec.can_validate_line = False
                continue

            rec.can_validate_line = rec._is_current_validation_turn()
            rec.route_process_status = "in_process" if rec.can_validate_line else "preparation"

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
        day_names = {
            0: "Senin",
            1: "Selasa",
            2: "Rabu",
            3: "Kamis",
            4: "Jumat",
            5: "Sabtu",
            6: "Minggu",
        }
        for rec in self:
            if rec.handover_date:
                date_value = fields.Date.to_date(rec.handover_date)
                rec.handover_date_text = "%s %s %s" % (
                    date_value.day,
                    month_names[date_value.month],
                    date_value.year,
                )
                rec.handover_day_date_text = "%s, %s" % (
                    day_names[date_value.weekday()],
                    rec.handover_date_text,
                )
            else:
                rec.handover_date_text = False
                rec.handover_day_date_text = False

    @api.depends("delivery_letter_date")
    def _compute_delivery_letter_date_text(self):
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
            if rec.delivery_letter_date:
                date_value = fields.Date.to_date(rec.delivery_letter_date)
                rec.delivery_letter_date_text = "%s %s %s" % (
                    date_value.day,
                    month_names[date_value.month],
                    date_value.year,
                )
            else:
                rec.delivery_letter_date_text = False

    # â”€â”€ Onchange â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @api.onchange("route_line_id")
    def _onchange_route_line_id(self):
        """Isi konfigurasi operasi dari baris master rute."""
        if self.route_line_id:
            self.route_id = self.route_line_id.route_id
            self.picking_type_id = self.route_line_id.picking_type_id
            self.location_id = self.route_line_id.location_id
            self.location_dest_id = self.route_line_id.location_dest_id

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
        TIDAK mengubah route_id â€” route ditentukan oleh user, bukan dari lokasi.
        """
        if not self.location_id:
            return
        if self.route_line_id:
            self.location_dest_id = self.route_line_id.location_dest_id

    def _prepare_auto_lot_allocation(self, requested_qty, excluded_lot_ids=None):
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
            ("delivery_id.state", "in", ("draft", "confirmed", "in_progress")),
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
            ])
            for planned_line in planned_lot_lines:
                planned_reserved_by_lot[planned_line.lot_id.id] = (
                    planned_reserved_by_lot.get(planned_line.lot_id.id, 0.0)
                    + planned_line.qty
                )

        excluded_lot_ids = set(excluded_lot_ids or [])
        remaining_need = requested_qty
        lot_vals = []
        for quant in quants:
            if remaining_need <= 0:
                break
            if quant.lot_id.id in excluded_lot_ids:
                continue

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

    # â”€â”€ Default get â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        delivery_id = self.env.context.get("default_delivery_id")
        if delivery_id:
            delivery = self.env["wt.delivery"].browse(delivery_id)
            if delivery.route_id:
                res["route_id"] = delivery.route_id.id
            if delivery.partner_id:
                res["partner_id"] = delivery.partner_id.id
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

    # â”€â”€ Validasi â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _validate_before_generate(self):
        """Validasi kelengkapan data sebelum generate picking."""
        self.ensure_one()
        missing = []
        active_lot_lines = self.lot_line_ids.filtered(lambda l: not l.wt_is_cancelled)
        if not self.route_line_id:
            missing.append(_("Baris Rute"))
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
        if not self.partner_id:
            missing.append(_("Kontak Penerima"))
        if self.demand_qty <= 0:
            missing.append(_("Demand (kg) harus > 0"))
        requires_transit_lot = self._requires_transit_lot_source()
        if self._is_transit_route() and not active_lot_lines:
            missing.append(_("Lot asal untuk rute transit"))
        if requires_transit_lot and not active_lot_lines:
            missing.append(_("Lot transit"))
        if missing:
            raise ValidationError(_(
                "Baris DO urutan %d belum lengkap, isi dahulu:\n%s"
            ) % (self.sequence, "\n".join("â€¢ " + m for m in missing)))

        if requires_transit_lot and active_lot_lines:
            expected_transit_lots = self._get_expected_transit_lots()

            missing_expected_lots = expected_transit_lots - active_lot_lines.mapped("lot_id")
            if missing_expected_lots:
                lot_names = ", ".join(missing_expected_lots.mapped("name"))
                raise ValidationError(_(
                    "Baris DO urutan %d wajib meload Lot Transit dari rute sebelumnya.\n"
                    "Lot Transit yang belum masuk: %s"
                ) % (self.sequence, lot_names))

            expected_qty_by_lot = self._get_expected_transit_lot_qty_map()
            for expected_lot in expected_transit_lots:
                required_qty = expected_qty_by_lot.get(expected_lot.id, 0.0)
                expected_lot_lines = active_lot_lines.filtered(lambda l: l.lot_id == expected_lot)
                selected_qty = sum(expected_lot_lines.mapped("qty"))
                if required_qty > 0.0 and selected_qty + 0.001 < required_qty:
                    original_qty = sum(
                        lot_line.wt_original_qty if lot_line.wt_original_qty > 0.0 else lot_line.qty
                        for lot_line in expected_lot_lines
                    )
                    if original_qty + 0.001 >= required_qty and len(expected_lot_lines) == 1:
                        expected_lot_lines.sudo().write({"qty": required_qty})
                        selected_qty = required_qty
                    else:
                        raise ValidationError(_(
                            "Baris DO urutan %d wajib membawa Lot Transit %s minimal %.4f kg. "
                            "Demand yang ada saat ini %.4f kg."
                        ) % (self.sequence, expected_lot.name, required_qty, selected_qty))

        lot_lines_to_weigh = active_lot_lines.filtered(lambda l: l.qty > 0.0)
        unpulled_lots = lot_lines_to_weigh.filtered(
            lambda lot: not lot._has_weighing_input()
        )
        if unpulled_lots:
            lot_names = ", ".join(
                l.lot_id.name or l.product_id.name
                for l in unpulled_lots
            )
            raise ValidationError(_(
                "Baris DO urutan %d tidak dapat divalidasi karena masih ada lot "
                "yang belum di-pull oleh operator: %s.\n"
                "Minta operator Pull Tugas ulang sebelum validasi Rencana DO."
            ) % (self.sequence, lot_names))

        unweighed_lots = lot_lines_to_weigh.filtered(
            lambda l: l.wt_weighing_status != "weighed"
        )
        if unweighed_lots:
            lot_names = ", ".join(
                l.lot_id.name or l.product_id.name
                for l in unweighed_lots
            )
            raise ValidationError(_(
                "Baris DO urutan %d tidak dapat divalidasi karena masih ada lot "
                "yang belum ditimbang: %s.\n"
                "Lakukan penimbangan dari aplikasi sebelum validasi Rencana DO."
            ) % (self.sequence, lot_names))

        # Cek jika ada lot yang memiliki selisih timbang tapi belum teralokasi penuh
        unallocated_lots = self.lot_line_ids.filtered(
            lambda l: abs(l.wt_difference_qty) > 0.001 and not l.wt_is_fully_allocated
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

    def _check_backdated_stock_availability(self, effective_datetime):
        """Prevent a backdated delivery from creating negative historical stock."""
        self.ensure_one()
        if not effective_datetime:
            return
        MoveLine = self.env["stock.move.line"].sudo().with_company(self.company_id)
        shortages = []
        source_location = self.location_id or self.picking_type_id.default_location_src_id
        for lot_line in self.lot_line_ids.filtered(lambda line: line.qty > 0.0):
            exact_location = self._get_lot_line_source_location(
                lot_line, source_location
            )
            common_domain = [
                ("state", "=", "done"),
                ("company_id", "=", self.company_id.id),
                ("product_id", "=", lot_line.product_id.id),
                ("lot_id", "=", lot_line.lot_id.id),
                ("date", "<=", effective_datetime),
            ]
            incoming = MoveLine.search(
                common_domain + [("location_dest_id", "child_of", exact_location.id)]
            )
            outgoing = MoveLine.search(
                common_domain + [("location_id", "child_of", exact_location.id)]
            )
            historical_qty = sum(incoming.mapped("quantity")) - sum(
                outgoing.mapped("quantity")
            )
            required_qty = (
                lot_line.wt_original_qty
                if lot_line.wt_original_qty > 0.0
                else lot_line.qty
            )
            if historical_qty + 0.001 < required_qty:
                shortages.append(
                    "%s / %s: %.4f kg available, %.4f kg required" % (
                        lot_line.lot_id.display_name,
                        exact_location.display_name,
                        historical_qty,
                        required_qty,
                    )
                )
        if shortages:
            raise ValidationError(_(
                "The delivery cannot be backdated because stock was insufficient on the effective date:\n%s\n\n"
                "Backdate the source receipt/opening stock first, then validate this delivery again."
            ) % "\n".join("- " + shortage for shortage in shortages))

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

    def _locations_overlap(self, location_a, location_b):
        """Return True when either location is inside the other's hierarchy."""
        if not location_a or not location_b or not location_a.parent_path or not location_b.parent_path:
            return False
        return (
            location_a.parent_path.startswith(location_b.parent_path)
            or location_b.parent_path.startswith(location_a.parent_path)
        )

    def _requires_transit_lot_source(self):
        """Return True when this line must consume a transit lot."""
        self.ensure_one()
        if not self.location_id:
            return False
        if self.location_id.usage == "transit":
            return True
        return bool(self._get_expected_transit_source_lines())

    def _get_previous_route_lines(self):
        self.ensure_one()
        if not self.delivery_id:
            return self.env["wt.delivery.do.line"]
        return self.delivery_id.do_line_ids.filtered(
            lambda line: line.id != self.id
            and ((line.sequence or 0), (line.id or 0)) < ((self.sequence or 0), (self.id or 0))
        ).sorted(lambda line: (line.sequence or 0, line.id or 0))

    def _get_expected_transit_source_lines(self):
        """Previous transit route lines whose generated lot must feed this line."""
        self.ensure_one()
        previous_transit_lines = self._get_previous_route_lines().filtered(
            lambda line: line._is_transit_route() and line.generated_transit_lot_id
        )
        if not previous_transit_lines:
            return previous_transit_lines

        if self.location_id and self.location_id.parent_path:
            matching_lines = previous_transit_lines.filtered(
                lambda line: self._locations_overlap(self.location_id, line.location_dest_id)
            )
            if matching_lines:
                return matching_lines[-1:]

        return previous_transit_lines[-1:]

    def _get_expected_transit_lots(self):
        """Transit lots generated by previous route lines that should feed this line."""
        self.ensure_one()
        return self._get_expected_transit_source_lines().mapped("generated_transit_lot_id")

    def _get_expected_transit_lot_qty_map(self):
        """Minimum required qty for each expected transit lot on this route line."""
        self.ensure_one()
        qty_by_lot = {}
        for source_line in self._get_expected_transit_source_lines():
            lot = source_line.generated_transit_lot_id
            if not lot:
                continue
            active_lot_lines = source_line.lot_line_ids.filtered(lambda l: not l.wt_is_cancelled)
            qty = sum(
                lot_line.wt_physical_qty if lot_line.wt_weighing_source else lot_line.qty
                for lot_line in active_lot_lines
            )
            if qty <= 0.0:
                qty = source_line.demand_qty
            qty_by_lot[lot.id] = qty_by_lot.get(lot.id, 0.0) + qty
        return qty_by_lot


    def _prepare_required_transit_lot_values(self):
        """Values for transit lots that must be carried by this route line."""
        self.ensure_one()
        values = []
        qty_by_lot = self._get_expected_transit_lot_qty_map()
        for source_line in self._get_expected_transit_source_lines():
            lot = source_line.generated_transit_lot_id
            if not lot:
                continue
            qty = qty_by_lot.get(lot.id, 0.0)
            if qty <= 0.0:
                continue
            values.append({
                "lot_id": lot.id,
                "qty": qty,
                "source_location_id": (source_line.location_dest_id or self.location_id).id,
            })
        return values

    def wt_get_report_plan_lot_lines(self):
        """Lots shown as planned stock-out source in the delivery order report."""
        self.ensure_one()
        direct_non_transit_lots = self.lot_line_ids.filtered(
            lambda lot_line: lot_line.qty > 0.0
            and lot_line.lot_id.wt_lot_type != "transit"
        )
        is_customer_line = (
            self.picking_type_id.code == "outgoing"
            or self.location_dest_id.usage == "customer"
        )
        if not is_customer_line:
            return direct_non_transit_lots

        source_non_transit_lots = self._get_expected_transit_source_lines().mapped(
            "lot_line_ids"
        ).filtered(
            lambda lot_line: lot_line.qty > 0.0
            and lot_line.lot_id.wt_lot_type != "transit"
        )
        return source_non_transit_lots or direct_non_transit_lots

    def wt_get_report_plan_qty(self):
        """Quantity for the Rencana column in the delivery order report."""
        self.ensure_one()
        is_customer_line = (
            self.picking_type_id.code == "outgoing"
            or self.location_dest_id.usage == "customer"
        )
        if not is_customer_line:
            return self.demand_qty

        report_lots = self.wt_get_report_plan_lot_lines()
        return sum(report_lots.mapped("qty")) if report_lots else self.demand_qty

    def _is_transit_route(self):
        self.ensure_one()
        return self.route_type == "transit" or self.route_line_id.route_type == "transit"

    # â”€â”€ ORM â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @api.model_create_multi
    def create(self, vals_list):
        """Saat do_line dibuat, auto-save parent delivery agar header ikut tersimpan."""
        new_vals_list = []
        seen_keys = set()
        for vals in vals_list:
            vals = self._apply_route_line_vals(vals)
            delivery = self.env["wt.delivery"].browse(vals.get("delivery_id")) if vals.get("delivery_id") else False
            if delivery and delivery.route_id and not vals.get("route_line_id"):
                raise ValidationError(_(
                    "Baris Rute pada Tugas Pengiriman harus berasal dari master Rute. "
                    "Pilih Rute di header untuk memuat baris rute."
                ))

            # Dedup: jika do_line dengan route_line_id yang sama sudah ada untuk
            # delivery ini, jangan buat ulang. Ini mencegah duplikasi saat OWL
            # mengirim perintah (0,0,...) untuk do_line yang sudah tersimpan di DB
            # setelah auto-save dipicu oleh tombol type="object" (mis. Muat Lot).
            route_line_id = vals.get("route_line_id")
            delivery_id = vals.get("delivery_id")
            if route_line_id and delivery_id:
                if (delivery_id, route_line_id) in seen_keys:
                    continue
                seen_keys.add((delivery_id, route_line_id))
                existing = self.search([
                    ("delivery_id", "=", delivery_id),
                    ("route_line_id", "=", route_line_id),
                ], limit=1)
                if existing:
                    # Sudah ada → skip, tidak perlu membuat baris baru
                    continue

            if not vals.get("product_id"):
                company = (
                    delivery.company_id
                    if delivery
                    else (self.env["res.company"].browse(vals.get("company_id")) if vals.get("company_id") else self.env.company)
                )
                product = self.env["wt.product"].get_active_product(company)
                if product:
                    vals["product_id"] = product.id
            if (
                delivery
                and not vals.get("document_do_number")
                and delivery.name
                and delivery.name != _("New")
            ):
                vals["document_do_number"] = delivery.name
            new_vals_list.append(vals)

        if not new_vals_list:
            return self.env["wt.delivery.do.line"]
        records = super().create(new_vals_list)
        # Trigger write pada delivery agar frontend tahu record berubah
        # dan agar timestamp write_date diperbarui
        delivery_ids = records.mapped("delivery_id").filtered(lambda d: d.id)
        if delivery_ids:
            delivery_ids.write({"write_date": fields.Datetime.now()})
        return records

    def write(self, vals):
        """Saat do_line di-update, pastikan delivery juga di-touch."""
        if "lot_line_ids" in vals:
            for line in self:
                for cmd in vals["lot_line_ids"]:
                    if isinstance(cmd, (tuple, list)):
                        cmd_type = cmd[0]
                        if cmd_type in (2, 3):
                            lot_rec = self.env["wt.delivery.do.line.lot"].browse(cmd[1])
                            if lot_rec.exists() and lot_rec._has_weighing_input():
                                raise ValidationError(_(
                                    "Baris lot '%s' tidak dapat dihapus karena statusnya sudah di-pull oleh operator timbang."
                                ) % (lot_rec.lot_id.name or lot_rec.display_name))
                        elif cmd_type == 5:
                            pulled = line.lot_line_ids.filtered(lambda l: l._has_weighing_input())
                            if pulled:
                                names = ", ".join(pulled.mapped(lambda l: l.lot_id.name or l.display_name))
                                raise ValidationError(_(
                                    "Baris lot (%s) tidak dapat dihapus karena statusnya sudah di-pull oleh operator timbang."
                                ) % names)
        vals = self._apply_route_line_vals(vals)
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

    def _apply_route_line_vals(self, vals):
        vals = dict(vals)
        route_line_id = vals.get("route_line_id")
        if route_line_id:
            route_line = self.env["wt.delivery.route.line"].browse(route_line_id)
            vals.setdefault("route_id", route_line.route_id.id)
            vals.setdefault("picking_type_id", route_line.picking_type_id.id)
            vals.setdefault("location_id", route_line.location_id.id)
            vals.setdefault("location_dest_id", route_line.location_dest_id.id)
        return vals

    def _check_sequence_ready_for_validation(self):
        """Prevent validating a route line before earlier route lines are done."""
        self.ensure_one()
        previous_lines = self._get_unfinished_previous_lines()
        if not previous_lines:
            return

        sequences = ", ".join(
            str(line.sequence)
            for line in previous_lines.sorted(lambda line: (line.sequence or 0, line.id or 0))
        )
        raise ValidationError(_(
            "Validasi Rencana DO harus dilakukan bertahap sesuai urutan rute. "
            "Selesaikan baris rute sebelumnya terlebih dahulu: %s"
        ) % sequences)

    def _get_unfinished_previous_lines(self):
        self.ensure_one()
        if not self.delivery_id or not self.delivery_id.do_line_ids:
            return self.env["wt.delivery.do.line"]

        current_key = (self.sequence or 0, self.id or 0)
        return self.delivery_id.do_line_ids.filtered(
            lambda candidate: candidate.id != self.id
            and ((candidate.sequence or 0), (candidate.id or 0)) < current_key
            and (not candidate.picking_id or candidate.picking_id.state != "done")
        )

    def _is_current_validation_turn(self):
        self.ensure_one()
        return not self._get_unfinished_previous_lines()

    def _is_ready_for_validation_status(self):
        self.ensure_one()
        active_lots = self.lot_line_ids.filtered(lambda l: l.qty > 0.0 and not l.wt_is_cancelled)
        if not active_lots:
            return False
        if any(not lot._has_weighing_input() for lot in active_lots):
            return False
        if any(lot.wt_weighing_status != "weighed" for lot in active_lots):
            return False
        return not any(
            abs(lot.wt_difference_qty) > 0.001 and not lot.wt_is_fully_allocated
            for lot in active_lots
        )

    # â”€â”€ Business Logic â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _apply_line_adjustments(self, active_lot_lines, source_location):
        self.ensure_one()
        adjustable_lines = active_lot_lines.filtered(
            lambda line: abs(line.wt_difference_qty) > 0.001
            and line.wt_is_fully_allocated
            and not line.wt_adjustment_applied
        )
        if not adjustable_lines:
            return

        move_vals_list = []
        for line in adjustable_lines:
            exact_loc = self._get_lot_line_source_location(line, source_location)
            for alloc in line.wt_allocation_ids:
                if line.wt_difference_qty < 0:
                    location_src = exact_loc
                    location_dest = alloc.location_dest_id
                else:
                    location_src = alloc.location_dest_id
                    location_dest = exact_loc

                move_vals_list.append({
                    "inventory_name": _("Pengiriman"),
                    "description_picking": "%s / %s" % (
                        line.lot_id.name or line.product_id.display_name,
                        alloc.reason_id.name,
                    ),
                    "state": "confirmed",
                    "picked": True,
                    "is_inventory": True,
                    "product_id": line.product_id.id,
                    "product_uom": line.product_id.uom_id.id,
                    "product_uom_qty": alloc.qty,
                    "location_id": location_src.id,
                    "location_dest_id": location_dest.id,
                    "company_id": line.company_id.id,
                    "origin": self.delivery_id.name,
                    "move_line_ids": [(0, 0, {
                        "product_id": line.product_id.id,
                        "product_uom_id": line.product_id.uom_id.id,
                        "quantity": alloc.qty,
                        "lot_id": line.lot_id.id if line.lot_id else False,
                        "location_id": location_src.id,
                        "location_dest_id": location_dest.id,
                        "company_id": line.company_id.id,
                    })],
                })

        if move_vals_list:
            effective_datetime = self.delivery_id._ensure_backdate_metadata()
            ctx = dict(
                inventory_mode=False,
                tracking_disable=True,
                mail_notrack=True,
                no_recompute=True,
                ignore_dest_packages=True,
            )
            if effective_datetime:
                ctx["force_period_date"] = self.delivery_id.date
            moves = self.env["stock.move"].sudo().with_context(**ctx).create(move_vals_list)
            moves.with_context(**ctx)._action_done()
            self.delivery_id._sync_moves_effective_date(moves, effective_datetime)

        for line in adjustable_lines:
            # Demand tetap menjadi angka rencana/kontrol rantai DO.
            # Berat aktual pengiriman diambil dari wt_physical_qty saat membuat move line,
            # sehingga susut normal tidak menurunkan demand lot transit wajib.
            line.sudo().write({"wt_adjustment_applied": True})

        lots = ", ".join(
            line.lot_id.name or line.product_id.display_name
            for line in adjustable_lines
        )
        self.delivery_id.message_post(body=_(
            "Penyesuaian stok otomatis diterapkan saat validasi Rencana DO urutan %s. "
            "Rincian lot yang diproses: %s"
        ) % (self.sequence, lots))

    def _action_create_done_picking(self):
        """
        Buat stock.picking dari baris ini dan langsung validasi ke status 'done'.
        Dipanggil saat baris Rencana DO divalidasi.
        """
        self.ensure_one()
        delivery = self.delivery_id
        effective_datetime = delivery._ensure_backdate_metadata()

        if self.picking_id and self.picking_id.state == "done":
            return self.picking_id

        self._check_sequence_ready_for_validation()
        self._validate_before_generate()
        self._check_backdated_stock_availability(effective_datetime)

        src_location = self.location_id or self.picking_type_id.default_location_src_id
        dest_location = self.location_dest_id or self.picking_type_id.default_location_dest_id
        partner = (
            self.partner_id
            or delivery.partner_id
            or False
        )
        product = self.product_id
        active_lot_lines = self.lot_line_ids.filtered(lambda l: not l.wt_is_cancelled)

        # Hitung total physical qty
        if active_lot_lines:
            total_physical = sum(
                (lot_line.wt_physical_qty if lot_line.wt_weighing_source else lot_line.qty)
                for lot_line in active_lot_lines
            )
        else:
            total_physical = self.demand_qty

        self._apply_line_adjustments(active_lot_lines, src_location)

        # Cek jika baris rute ini adalah rute transit.
        is_transit_merge = self._is_transit_route()

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
            "scheduled_date": (
                effective_datetime
                or self.scheduled_date
                or fields.Datetime.now()
            ),
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
            transit_date = delivery.date or fields.Date.context_today(self)
            today_str = transit_date.strftime("%Y%m%d")
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
                qty_done = lot_line.wt_physical_qty if lot_line.wt_weighing_source else lot_line.qty
                if qty_done <= 0.0:
                    continue
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
            self.sudo().write({"generated_transit_lot_id": new_lot.id})
        else:
            move = picking.move_ids[:1]
            if self.lot_line_ids:
                for lot_line in self.lot_line_ids:
                    qty_done = lot_line.wt_physical_qty if lot_line.wt_weighing_source else lot_line.qty
                    if qty_done <= 0.0:
                        continue
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

        # Validasi langsung ke done â€” tanpa backorder karena demand sudah disesuaikan ke fisik
        validation_context = {
            "skip_backorder": True,
            "no_backorder": True,
            "skip_immediate": True,
            "wt_force_validate": True,
        }
        if effective_datetime:
            validation_context["force_period_date"] = delivery.date
        picking.with_context(
            **validation_context
        ).button_validate()
        delivery._sync_picking_effective_date(picking, effective_datetime)

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
        if is_transit_merge and self.generated_transit_lot_id:
            self._load_generated_transit_lot_to_next_line(total_physical)
        elif self.picking_type_id.code == "outgoing":
            delivery.write({"state": "delivered"})
        elif delivery.state == "confirmed":
            delivery.write({"state": "in_progress"})
        return picking

    def _load_generated_transit_lot_to_next_line(self, qty):
        self.ensure_one()
        transit_lot = self.generated_transit_lot_id
        if not transit_lot or not self.delivery_id or not self.location_dest_id:
            return

        later_lines = self.delivery_id.do_line_ids.filtered(
            lambda line: line.id != self.id
            and not (line.picking_id and line.picking_id.state == "done")
            and ((line.sequence or 0), (line.id or 0)) > ((self.sequence or 0), (self.id or 0))
        ).sorted(lambda line: (line.sequence or 0, line.id or 0))
        if not later_lines:
            self.delivery_id.message_post(body=_(
                "Lot Transit %s sudah terbentuk dari Rencana DO urutan %s, "
                "tetapi tidak ada baris rute berikutnya yang bisa diload."
            ) % (transit_lot.name, self.sequence))
            return

        matching_lines = later_lines.filtered(
            lambda line: self._locations_overlap(line.location_id, self.location_dest_id)
        )
        next_line = matching_lines[:1]
        if not next_line:
            self.delivery_id.message_post(body=_(
                "Lot Transit %s sudah terbentuk dari Rencana DO urutan %s, "
                "tetapi tidak otomatis diload karena tidak ada rute berikutnya dengan "
                "Lokasi Sumber yang satu rantai dengan Lokasi Transit %s."
            ) % (
                transit_lot.name,
                self.sequence,
                self.location_dest_id.display_name,
            ))
            return

        lot_qty = qty or next_line.demand_qty or 0.0
        if lot_qty <= 0.0:
            return

        existing_line = next_line.lot_line_ids.filtered(lambda line: line.lot_id == transit_lot)[:1]
        if existing_line:
            if existing_line.qty + 0.001 < lot_qty:
                existing_line.sudo().write({
                    "qty": lot_qty,
                    "source_location_id": self.location_dest_id.id,
                })
                self.delivery_id.message_post(body=_(
                    "Demand Lot Transit %s pada Rencana DO urutan %s disesuaikan menjadi %.4f kg."
                ) % (transit_lot.name, next_line.sequence, lot_qty))
            return

        next_line.sudo().write({
            "lot_line_ids": [(0, 0, {
                "lot_id": transit_lot.id,
                "qty": lot_qty,
                "source_location_id": self.location_dest_id.id,
            })],
        })
        self.delivery_id.message_post(body=_(
            "Lot Transit %s otomatis diload ke Rencana DO urutan %s."
        ) % (transit_lot.name, next_line.sequence))

    @api.constrains("lot_line_ids", "lot_line_ids.qty", "lot_line_ids.lot_id", "lot_line_ids.wt_is_cancelled")
    def _check_lot_stock_limits(self):
        for line in self:
            active_lots = line.lot_line_ids.filtered(lambda l: not l.wt_is_cancelled)
            if not active_lots:
                continue
            # Kelompokkan baris berdasarkan lot_id
            lot_groups = {}
            for lot_line in active_lots:
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
                # (2) cari lot_lines di do_lines tersebut pakai direct IN clause (kecualikan lot yang dibatalkan).
                current_delivery_id_c = line._get_persisted_delivery_id()
                active_do_line_domain_c = [
                    ("delivery_id.state", "in", ("draft", "confirmed", "in_progress")),
                ]
                if current_delivery_id_c:
                    active_do_line_domain_c.append(("delivery_id", "!=", current_delivery_id_c))
                active_do_lines_c = self.env["wt.delivery.do.line"].search(active_do_line_domain_c)
                if active_do_lines_c:
                    other_active_lines = self.env["wt.delivery.do.line.lot"].search([
                        ("lot_id", "=", lot.id),
                        ("do_line_id", "in", active_do_lines_c.ids),
                        ("wt_is_cancelled", "=", False),
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
        # Validasi jika baris lot yang sudah di-pull dihapus secara interaktif di UI
        warning_result = None
        if self._origin:
            persisted_pulled_lots = self._origin.lot_line_ids.filtered(lambda l: l._has_weighing_input())
            current_origin_ids = {l._origin.id for l in self.lot_line_ids if l._origin}
            deleted_pulled = persisted_pulled_lots.filtered(lambda p: p.id not in current_origin_ids)
            if deleted_pulled:
                # Pulihkan kembali baris lot yang sudah di-pull agar tidak hilang di layar UI
                self.lot_line_ids = self.lot_line_ids | deleted_pulled
                names = ", ".join(deleted_pulled.mapped(lambda l: l.lot_id.name or l.display_name))
                warning_result = {
                    "title": _("Tidak Dapat Dihapus"),
                    "message": _(
                        "Baris lot '%s' tidak dapat dihapus karena statusnya sudah di-pull oleh operator timbang."
                    ) % names,
                }

        # Validasi interaktif saat user mengedit atau menambah lot di UI (sebelum disave ke DB)
        active_onchange_lots = self.lot_line_ids.filtered(lambda l: not l.wt_is_cancelled)
        if not active_onchange_lots:
            return {"warning": warning_result} if warning_result else None
        
        # Kelompokkan baris berdasarkan lot_id
        lot_groups = {}
        for lot_line in active_onchange_lots:
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
            # Gunakan 2-step search yang sama seperti di _compute_qty_available (kecualikan lot yang dibatalkan).
            current_delivery_id_o = self._get_persisted_delivery_id()
            active_do_line_domain_o = [
                ("delivery_id.state", "in", ("draft", "confirmed", "in_progress")),
            ]
            if current_delivery_id_o:
                active_do_line_domain_o.append(("delivery_id", "!=", current_delivery_id_o))
            active_do_lines_o = self.env["wt.delivery.do.line"].search(active_do_line_domain_o)
            if active_do_lines_o:
                other_active_lines = self.env["wt.delivery.do.line.lot"].search([
                    ("lot_id", "=", lot.id),
                    ("do_line_id", "in", active_do_lines_o.ids),
                    ("wt_is_cancelled", "=", False),
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

        if warning_result:
            return {"warning": warning_result}

    def action_validate_line(self):
        """Validasi baris DO ini secara mandiri (membuat & memvalidasi stock.picking)."""
        for line in self:
            if line.delivery_id.state not in ("confirmed", "in_progress"):
                raise ValidationError(_("Rencana DO hanya bisa divalidasi saat Tugas Pengiriman berstatus Confirmed atau In Progress."))
            if line.picking_id and line.picking_id.state == "done":
                raise ValidationError(_("Baris DO ini sudah divalidasi."))
            line._check_sequence_ready_for_validation()
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

    def action_print_surat_jalan(self):
        """Print Surat Jalan untuk baris Rencana DO."""
        self.ensure_one()
        if self.picking_state != "done":
            raise ValidationError(_("Surat Jalan hanya bisa dicetak setelah Rencana DO divalidasi."))
        return self.env.ref("weightrack.action_report_surat_jalan_line").report_action(self)

    def _get_surat_jalan_company(self):
        """Return company for Surat Jalan without depending on the delivery header."""
        self.ensure_one()
        return (
            self.picking_type_id.company_id
            or self.picking_id.company_id
            or self.env.company
        )
    def _get_surat_jalan_lines(self):
        """Return Surat Jalan item rows for this delivery line."""
        self.ensure_one()
        product = self.product_id
        if not product:
            return []
        has_weighed_lines = any(l.wt_weighing_source for l in self.lot_line_ids)
        qty = self.actual_physical_qty if has_weighed_lines else self.demand_qty
        return [{
            "code": product.default_code or "",
            "name": product.display_name,
            "qty": qty,
            "uom": product.uom_id.name or "",
        }]

    def action_open_handover_details(self):
        """Buka popup edit informasi dokumen meskipun Rencana DO sudah readonly."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Document Information"),
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

        required_transit_vals = self._prepare_required_transit_lot_values()
        required_lot_ids = {vals["lot_id"] for vals in required_transit_vals}
        required_qty = sum(vals["qty"] for vals in required_transit_vals)
        if self.demand_qty <= 0 and required_qty <= 0:
            raise ValidationError(_("Masukkan Demand (kg) terlebih dahulu sebelum melakukan auto-alokasi."))

        requested_qty = max(self.demand_qty, required_qty)

        # Hapus rincian non-transit wajib, tetapi pertahankan lot transit wajib
        # agar rantai pengiriman tidak bisa meninggalkan celah.
        removable_lots = self.lot_line_ids.filtered(lambda line: line.lot_id.id not in required_lot_ids)
        if removable_lots:
            removable_lots.unlink()

        lot_commands = []
        for vals in required_transit_vals:
            existing_line = self.lot_line_ids.filtered(lambda line: line.lot_id.id == vals["lot_id"])[:1]
            if existing_line:
                if existing_line.qty + 0.001 < vals["qty"]:
                    existing_line.sudo().write({
                        "qty": vals["qty"],
                        "source_location_id": vals["source_location_id"],
                    })
                continue
            lot_commands.append((0, 0, vals))

        remaining_target = max(0.0, requested_qty - required_qty)
        lot_vals, remaining_need = self._prepare_auto_lot_allocation(
            remaining_target,
            excluded_lot_ids=required_lot_ids,
        )
        lot_commands.extend(lot_vals)

        if lot_commands:
            self.write({"lot_line_ids": lot_commands})

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
                ) % (rec.route_line_id.display_name or rec.picking_type_id.display_name))
        return super().unlink()
