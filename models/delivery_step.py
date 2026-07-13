# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DeliveryStep(models.Model):
    _name = "wt.delivery.step"
    _description = "Step Pengiriman Per Gudang"
    _order = "delivery_id, sequence, id"

    STATE_SELECTION = [
        ("pending", "Menunggu"),
        ("weighing", "Proses Timbang"),
        ("weighing_done", "Timbang Selesai"),
        ("done", "Selesai"),
        ("cancelled", "Dibatalkan"),
    ]

    delivery_id = fields.Many2one(
        "wt.delivery",
        string="Delivery Plan",
        required=True,
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
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Gudang",
        required=True,
    )
    source_location_ids = fields.Many2many(
        "stock.location",
        "wt_delivery_step_source_loc_rel",
        "step_id",
        "location_id",
        string="Lokasi Asal",
        domain="[('usage', '=', 'internal')]",
        help="Lokasi stok asal di gudang ini (bisa lebih dari satu).",
    )
    transit_location_id = fields.Many2one(
        "stock.location",
        string="Lokasi Transit Tujuan",
        domain="[('usage', 'in', ['internal', 'transit'])]",
        help="Diisi otomatis dari konfigurasi rute. Kosongkan jika step ini adalah step terakhir.",
    )
    requested_qty = fields.Float(
        string="Kebutuhan (kg)",
        digits="Product Unit of Measure",
        help="Total kuantitas yang dibutuhkan dari gudang/lokasi ini.",
    )
    net_qty = fields.Float(
        string="Berat Fisik Aktual (kg)",
        digits="Product Unit of Measure",
        readonly=True,
        copy=False,
        help="Total berat fisik aktual hasil timbangan setelah susut di step ini.",
    )
    weighing_ids = fields.One2many(
        "wt.weighing",
        "delivery_step_id",
        string="Sesi Timbang",
    )
    weighing_count = fields.Integer(
        string="Jumlah Sesi Timbang",
        compute="_compute_weighing_count",
    )
    picking_id = fields.Many2one(
        "stock.picking",
        string="Dokumen Picking",
        readonly=True,
        copy=False,
        help="Dokumen picking (Internal Transfer atau Outgoing DO) yang dibuat untuk step ini.",
    )
    picking_state = fields.Selection(
        related="picking_id.state",
        string="Status Picking",
        readonly=True,
    )
    is_last_step = fields.Boolean(
        string="Step Terakhir",
        help=(
            "Jika dicentang, validasi step ini akan membuat Outgoing DO ke customer. "
            "Jika tidak, akan membuat Internal Transfer ke lokasi transit."
        ),
    )
    state = fields.Selection(
        STATE_SELECTION,
        string="Status",
        default="pending",
        required=True,
        index=True,
        tracking=True,
    )
    note = fields.Text(string="Catatan")

    # ── Computed ──────────────────────────────────────────────────────────────

    def _compute_weighing_count(self):
        for rec in self:
            rec.weighing_count = len(rec.weighing_ids)

    # ── Onchange ──────────────────────────────────────────────────────────────

    @api.onchange("source_location_ids")
    def _onchange_source_location_ids(self):
        """Auto-fill transit_location dari konfigurasi rute jika hanya 1 lokasi asal."""
        company_id = self.company_id.id or self.env.company.id
        if len(self.source_location_ids) == 1:
            route = self.env["wt.delivery.route"].search([
                ("source_location_id", "=", self.source_location_ids[0].id),
                ("company_id", "=", company_id),
                ("active", "=", True),
            ], limit=1)
            if route:
                self.transit_location_id = route.transit_location_id
        elif len(self.source_location_ids) > 1:
            # Cek apakah semua lokasi menuju transit yang sama
            routes = self.env["wt.delivery.route"].search([
                ("source_location_id", "in", self.source_location_ids.ids),
                ("company_id", "=", company_id),
                ("active", "=", True),
            ])
            transit_locations = routes.mapped("transit_location_id")
            if len(transit_locations) == 1:
                self.transit_location_id = transit_locations[0]
            else:
                self.transit_location_id = False


    @api.onchange("warehouse_id")
    def _onchange_warehouse_id(self):
        """Reset lokasi saat gudang berubah."""
        if self.warehouse_id:
            self.source_location_ids = False
            self.transit_location_id = False

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_view_weighings(self):
        """Buka daftar sesi timbang untuk step ini."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Sesi Timbang"),
            "res_model": "wt.weighing",
            "view_mode": "list,form",
            "domain": [("delivery_step_id", "=", self.id)],
            "context": {"default_delivery_step_id": self.id},
        }

    def action_view_picking(self):
        """Buka DO/Transfer yang terbuat dari step ini."""
        self.ensure_one()
        if not self.picking_id:
            return
        return {
            "type": "ir.actions.act_window",
            "name": _("Transfer"),
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": self.picking_id.id,
        }

    def action_start_weighing(self):
        """
        Mulai sesi timbang untuk step ini.
        State: pending → weighing.
        """
        for step in self:
            if step.state != "pending":
                raise ValidationError(_(
                    "Hanya step dengan status 'Menunggu' yang bisa dimulai."
                ))
            if step.delivery_id.state not in ("confirmed", "in_progress"):
                raise ValidationError(_(
                    "Delivery Plan harus dalam status Confirmed atau In Progress."
                ))
            step.write({"state": "weighing"})
            # Set delivery ke in_progress jika masih confirmed
            if step.delivery_id.state == "confirmed":
                step.delivery_id.write({"state": "in_progress"})

    def action_finish_weighing(self):
        """
        Tandai penimbangan sebagai selesai.
        State: weighing → weighing_done.
        """
        for step in self:
            if step.state != "weighing":
                raise ValidationError(_(
                    "Hanya step yang sedang timbang yang bisa diselesaikan."
                ))
            step.write({"state": "weighing_done"})

    def action_validate_step(self):
        """
        Validasi step:
        - Jika bukan last step: buat Internal Transfer ke transit_location_id.
        - Jika last step: buat Outgoing DO ke customer.
        State: weighing_done → done.
        """
        for step in self:
            step._action_validate_step_one()

    def _action_validate_step_one(self):
        self.ensure_one()
        if self.state != "weighing_done":
            raise ValidationError(_(
                "Step harus dalam status 'Timbang Selesai' sebelum bisa divalidasi."
            ))

        if self.is_last_step:
            picking = self._create_outgoing_do()
        else:
            picking = self._create_internal_transfer()

        self.write({
            "picking_id": picking.id,
            "state": "done",
        })

        # Link picking ke delivery header via wt_delivery_id
        picking.write({"wt_delivery_id": self.delivery_id.id})

        # Jika ini step terakhir, set delivery ke done
        if self.is_last_step:
            self.delivery_id.write({
                "state": "done",
                "final_picking_id": picking.id,
            })

        return picking

    # ── Internal Transfer ─────────────────────────────────────────────────────

    def _create_internal_transfer(self):
        """
        Buat Internal Transfer dari source_location_ids → transit_location_id.
        Menggunakan picking_type internal dari warehouse step ini.
        """
        self.ensure_one()
        delivery = self.delivery_id
        warehouse = self.warehouse_id

        if not self.transit_location_id:
            raise ValidationError(_(
                "Step '%s' tidak memiliki Lokasi Transit Tujuan.\n"
                "Isi field 'Lokasi Transit Tujuan' atau konfigurasi Rute Lokasi Gudang "
                "di menu Konfigurasi."
            ) % self.name_get()[0][1])

        if not self.source_location_ids:
            raise ValidationError(_(
                "Step '%s' tidak memiliki Lokasi Sumber.\n"
                "Tambahkan minimal satu lokasi sumber."
            ) % self.name_get()[0][1])

        # Picking type: internal transfer dari warehouse ini
        picking_type = self.env["stock.picking.type"].search([
            ("code", "=", "internal"),
            ("company_id", "=", delivery.company_id.id),
            ("warehouse_id", "=", warehouse.id),
        ], limit=1)
        if not picking_type:
            raise ValidationError(_(
                "Gudang '%s' tidak memiliki tipe operasi Internal Transfer."
            ) % warehouse.name)

        product = self._get_step_product()

        # Satu picking, satu move per source location
        qty_total = self.net_qty if self.net_qty > 0 else self.requested_qty
        qty_per_loc = qty_total / max(len(self.source_location_ids), 1)
        move_vals = []
        for loc in self.source_location_ids:
            move_vals.append((0, 0, {
                "description_picking": product.display_name,
                "inventory_name": _("Pengiriman"),
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_qty": qty_per_loc,
                "location_id": loc.id,
                "location_dest_id": self.transit_location_id.id,
                "company_id": delivery.company_id.id,
                "origin": delivery.name,
            }))

        picking = self.env["stock.picking"].sudo().create({
            "picking_type_id": picking_type.id,
            "location_id": self.source_location_ids[0].id,
            "location_dest_id": self.transit_location_id.id,
            "origin": delivery.name,
            "company_id": delivery.company_id.id,
            "move_ids": move_vals,
        })
        picking.action_confirm()
        picking.action_assign()

        delivery.message_post(
            body=_(
                "<b>Internal Transfer dibuat</b>: "
                "<a href='/web#id=%d&model=stock.picking'>%s</a><br/>"
                "Step: %s | Qty: %.2f kg → %s"
            ) % (
                picking.id, picking.name,
                self.name_get()[0][1],
                qty_total,
                self.transit_location_id.complete_name,
            )
        )
        return picking

    # ── Final Outgoing DO ─────────────────────────────────────────────────────

    def _create_outgoing_do(self):
        """
        Buat Outgoing DO ke customer dari step terakhir.
        Sumber: source_location_ids + transit dari step sebelumnya.
        """
        self.ensure_one()
        delivery = self.delivery_id
        warehouse = self.warehouse_id

        if not delivery.partner_id:
            raise ValidationError(_(
                "Pengiriman '%s' belum memiliki Customer/Partner.\n"
                "Isi field 'Customer' di header delivery sebelum memvalidasi step terakhir."
            ) % delivery.name)

        picking_type = self.env["stock.picking.type"].search([
            ("code", "=", "outgoing"),
            ("company_id", "=", delivery.company_id.id),
            ("warehouse_id", "=", warehouse.id),
        ], limit=1)
        if not picking_type:
            raise ValidationError(_(
                "Gudang '%s' tidak memiliki tipe operasi Outgoing."
            ) % warehouse.name)

        dest_location = picking_type.default_location_dest_id or self.env.ref(
            "stock.stock_location_customers", raise_if_not_found=False
        )
        if not dest_location:
            raise ValidationError(_("Tidak dapat menentukan lokasi tujuan customer."))

        product = self._get_step_product()

        # Bangun daftar (lokasi, qty) berdasarkan step sebelumnya + stok gudang ini
        move_vals = self._build_last_step_move_vals(product, dest_location)

        picking = self.env["stock.picking"].sudo().create({
            "picking_type_id": picking_type.id,
            "location_id": self.source_location_ids[0].id if self.source_location_ids else dest_location.id,
            "location_dest_id": dest_location.id,
            "partner_id": delivery.partner_id.id,
            "origin": delivery.name,
            "company_id": delivery.company_id.id,
            "move_ids": move_vals,
        })
        picking.action_confirm()
        picking.action_assign()

        total_qty = sum(m[2]["product_uom_qty"] for m in move_vals)
        delivery.message_post(
            body=_(
                "<b>Outgoing DO Final dibuat</b>: "
                "<a href='/web#id=%d&model=stock.picking'>%s</a><br/>"
                "Step: %s | Customer: %s | Total Qty: %.2f kg"
            ) % (
                picking.id, picking.name,
                self.name_get()[0][1],
                delivery.partner_id.name,
                total_qty,
            )
        )
        return picking

    def _build_last_step_move_vals(self, product, dest_location):
        """
        Bangun move_vals untuk step terakhir:
        - Transit dari step-step sebelumnya yang sudah done
        - Sisa dari source_location_ids step ini
        """
        self.ensure_one()
        delivery = self.delivery_id
        move_vals = []

        # Kumpulkan transit qty dari step sebelumnya
        prev_steps = delivery.warehouse_step_ids.filtered(
            lambda s: s.sequence < self.sequence and s.state == "done"
        ).sorted("sequence")

        total_transit_qty = 0.0
        for prev in prev_steps:
            if prev.transit_location_id and prev.net_qty > 0:
                move_vals.append((0, 0, {
                    "description_picking": _("%s (Transit dari %s)") % (
                        product.display_name,
                        prev.warehouse_id.name,
                    ),
                    "inventory_name": _("Pengiriman"),
                    "product_id": product.id,
                    "product_uom": product.uom_id.id,
                    "product_uom_qty": prev.net_qty,
                    "location_id": prev.transit_location_id.id,
                    "location_dest_id": dest_location.id,
                    "company_id": delivery.company_id.id,
                    "origin": delivery.name,
                }))
                total_transit_qty += prev.net_qty

        # Sisanya dari stok gudang ini (source_location_ids)
        own_qty = max(0.0, (self.net_qty or self.requested_qty) - total_transit_qty)
        if own_qty > 0 and self.source_location_ids:
            qty_per_loc = own_qty / len(self.source_location_ids)
            for loc in self.source_location_ids:
                move_vals.append((0, 0, {
                    "description_picking": _("%s (Stok %s)") % (product.display_name, loc.complete_name),
                    "inventory_name": _("Pengiriman"),
                    "product_id": product.id,
                    "product_uom": product.uom_id.id,
                    "product_uom_qty": qty_per_loc,
                    "location_id": loc.id,
                    "location_dest_id": dest_location.id,
                    "company_id": delivery.company_id.id,
                    "origin": delivery.name,
                }))

        if not move_vals:
            raise ValidationError(_(
                "Tidak ada sumber barang yang bisa dibuat untuk Outgoing DO.\n"
                "Pastikan step ini memiliki Lokasi Sumber atau step sebelumnya "
                "sudah memiliki net_qty > 0."
            ))

        return move_vals

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_step_product(self):
        """
        Ambil produk dari sesi timbang atau dari delivery header.
        """
        self.ensure_one()
        # Coba dari weighing
        if self.weighing_ids:
            product = self.weighing_ids[0].product_id
            if product:
                return product
        # Dari delivery header (jika ada field product_id)
        delivery = self.delivery_id
        if hasattr(delivery, "product_id") and delivery.product_id:
            return delivery.product_id
        raise ValidationError(_(
            "Tidak dapat menentukan produk untuk step ini.\n"
            "Pastikan sesi timbang sudah memiliki data produk, "
            "atau tambahkan field 'Produk' pada Delivery Plan."
        ))

    def name_get(self):
        result = []
        for rec in self:
            label = "Step %d — %s" % (rec.sequence, rec.warehouse_id.name or "")
            result.append((rec.id, label))
        return result
