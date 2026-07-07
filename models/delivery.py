# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from markupsafe import Markup


class Delivery(models.Model):
    _name = "wt.delivery"
    _description = "Tugas Pengiriman (Weighing Delivery)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    STATE_SELECTION = [
        ("draft", "Draft"),
        ("confirmed", "Confirmed"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("validated", "Validated"),
        ("done", "Done"),
        ("cancelled", "Cancelled"),
    ]

    name = fields.Char(
        string="Nomor",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        required=True,
        index=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    date = fields.Date(
        string="Tanggal",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    note = fields.Text(
        string="Catatan",
    )

    # ── Customer / Partner ────────────────────────────────────────────────────
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        tracking=True,
        help="Partner/Customer tujuan pengiriman akhir (untuk Outgoing DO final).",
    )

    # ── Produk yang dikirim (opsional, digunakan sebagai fallback di step) ────
    product_id = fields.Many2one(
        "product.product",
        string="Produk",
        tracking=True,
    )

    # ── Step-based multi-warehouse delivery ───────────────────────────────────
    warehouse_step_ids = fields.One2many(
        "wt.delivery.step",
        "delivery_id",
        string="Warehouse Steps",
        copy=True,
    )

    # ── Rencana DO (inline lines, dikonversi saat Konfirmasi) ─────────────────
    do_line_ids = fields.One2many(
        "wt.delivery.do.line",
        "delivery_id",
        string="Rencana DO",
        copy=True,
    )
    step_count = fields.Integer(
        string="Jumlah Step",
        compute="_compute_step_count",
    )

    # ── Final outgoing DO ke customer ─────────────────────────────────────────
    final_picking_id = fields.Many2one(
        "stock.picking",
        string="Final DO",
        copy=False,
        readonly=True,
        help="Outgoing DO final ke customer, dibuat otomatis saat step terakhir divalidasi.",
    )

    # ── DOs yang dibuat langsung dari dokumen ini ─────────────────────────────
    # (via wt_delivery_id pada stock.picking — termasuk internal transfer + outgoing)
    picking_ids = fields.One2many(
        "stock.picking",
        "wt_delivery_id",
        string="Delivery Orders (DO)",
        copy=False,
    )
    picking_count = fields.Integer(
        string="Jumlah DO",
        compute="_compute_picking_count",
    )

    # ── Detail timbang (backward compat untuk alur lama) ─────────────────────
    move_line_ids = fields.One2many(
        "stock.move.line",
        "wt_delivery_id",
        string="Semua Detail Timbang",
    )
    pulled_move_line_ids = fields.One2many(
        "stock.move.line",
        "wt_delivery_id",
        domain=[("wt_is_pulled", "=", True), ("quantity", ">", 0)],
        string="Detail Timbang",
    )
    unpulled_move_line_ids = fields.One2many(
        "stock.move.line",
        "wt_delivery_id",
        domain=[("wt_is_pulled", "=", False), ("quantity", ">", 0)],
        string="Lot Belum Di-Push",
    )
    wt_has_unpulled_lines = fields.Boolean(
        string="Ada Lot Belum Di-Push",
        compute="_compute_wt_has_unpulled_lines",
        store=True,
        help=(
            "True jika ada move line aktif (qty > 0) yang belum pernah di-pull "
            "oleh operator — biasanya karena Odoo re-reserve dari lot lain setelah "
            "Apply Adjustment mengurangi stok lot asal."
        ),
    )

    # ── Detail Timbang Rencana DO (alur baru) ─────────────────────────────────
    do_lot_line_ids = fields.One2many(
        "wt.delivery.do.line.lot",
        compute="_compute_do_lot_line_ids",
        string="Semua Rincian Lot Rencana DO",
    )
    pulled_do_lot_line_ids = fields.One2many(
        "wt.delivery.do.line.lot",
        compute="_compute_do_lot_line_ids",
        string="Detail Timbang (Rencana)",
    )
    unpulled_do_lot_line_ids = fields.One2many(
        "wt.delivery.do.line.lot",
        compute="_compute_do_lot_line_ids",
        string="Lot Rencana Belum Di-Push",
    )

    # ── State & Totals ────────────────────────────────────────────────────────
    state = fields.Selection(
        STATE_SELECTION,
        string="Status",
        default="draft",
        required=True,
        index=True,
        tracking=True,
    )
    total_demand_qty = fields.Float(
        string="Total Demand (kg)",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    total_physical_qty = fields.Float(
        string="Total Fisik (kg)",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    total_difference_qty = fields.Float(
        string="Total Selisih (kg)",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    has_adjustable_lines = fields.Boolean(
        string="Ada Baris Bisa Di-Adjust",
        compute="_compute_has_adjustable_lines",
        help=(
            "True jika ada minimal 1 baris dengan selisih yang sudah teralokasi penuh "
            "dan belum diterapkan adjustment-nya."
        ),
    )
    validated_at = fields.Datetime(
        string="Divalidasi Pada",
        readonly=True,
        copy=False,
        tracking=True,
    )
    validated_by_id = fields.Many2one(
        "res.users",
        string="Divalidasi Oleh",
        readonly=True,
        copy=False,
        tracking=True,
    )

    # ── Computed ──────────────────────────────────────────────────────────────

    @api.depends("do_line_ids.lot_line_ids.wt_is_pulled", "do_line_ids.lot_line_ids.qty")
    def _compute_do_lot_line_ids(self):
        for delivery in self:
            all_lots = delivery.do_line_ids.mapped("lot_line_ids")
            delivery.do_lot_line_ids = all_lots
            delivery.pulled_do_lot_line_ids = all_lots.filtered(lambda l: l.wt_is_pulled and l.qty > 0)
            delivery.unpulled_do_lot_line_ids = all_lots.filtered(lambda l: not l.wt_is_pulled and l.qty > 0)

    @api.depends(
        "move_line_ids.quantity",
        "move_line_ids.wt_physical_qty",
        "move_line_ids.wt_original_demand_qty",
        "move_line_ids.wt_is_pulled",
        "do_line_ids.lot_line_ids.qty",
        "do_line_ids.lot_line_ids.wt_physical_qty",
        "do_line_ids.lot_line_ids.wt_is_pulled",
    )
    def _compute_totals(self):
        for rec in self:
            if rec.do_line_ids:
                # Alur baru (rencana DO -> rincian lot)
                active_lots = rec.do_lot_line_ids.filtered(lambda l: l.wt_is_pulled)
                rec.total_demand_qty = sum(active_lots.mapped("qty"))
                rec.total_physical_qty = sum(active_lots.mapped("wt_physical_qty"))
                rec.total_difference_qty = rec.total_physical_qty - rec.total_demand_qty
            else:
                # Alur lama (picking_ids -> move_line_ids)
                active_lines = rec.move_line_ids.filtered(
                    lambda l: l.wt_is_pulled and (l.quantity > 0 or l.wt_original_demand_qty > 0)
                )
                rec.total_demand_qty = sum(
                    l.wt_original_demand_qty if l.wt_original_demand_qty > 0.001 else l.quantity
                    for l in active_lines
                )
                rec.total_physical_qty = sum(active_lines.mapped("wt_physical_qty"))
                rec.total_difference_qty = rec.total_physical_qty - rec.total_demand_qty

    @api.depends(
        "move_line_ids.wt_difference_qty",
        "move_line_ids.wt_is_fully_allocated",
        "move_line_ids.wt_adjustment_applied",
        "move_line_ids.wt_is_pulled",
        "do_line_ids.lot_line_ids.wt_difference_qty",
        "do_line_ids.lot_line_ids.wt_is_fully_allocated",
        "do_line_ids.lot_line_ids.wt_adjustment_applied",
        "do_line_ids.lot_line_ids.wt_is_pulled",
    )
    def _compute_has_adjustable_lines(self):
        for rec in self:
            if rec.do_line_ids:
                rec.has_adjustable_lines = any(
                    abs(l.wt_difference_qty) > 0.001
                    and l.wt_is_fully_allocated
                    and not l.wt_adjustment_applied
                    and l.wt_is_pulled
                    for l in rec.do_lot_line_ids
                )
            else:
                rec.has_adjustable_lines = any(
                    abs(l.wt_difference_qty) > 0.001
                    and l.wt_is_fully_allocated
                    and not l.wt_adjustment_applied
                    and l.wt_is_pulled
                    for l in rec.move_line_ids
                )

    def _compute_picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids)

    def _compute_step_count(self):
        for rec in self:
            rec.step_count = len(rec.warehouse_step_ids)

    @api.depends(
        "move_line_ids.wt_is_pulled",
        "move_line_ids.quantity",
        "do_line_ids.lot_line_ids.wt_is_pulled",
        "do_line_ids.lot_line_ids.qty",
    )
    def _compute_wt_has_unpulled_lines(self):
        for rec in self:
            if rec.do_line_ids:
                rec.wt_has_unpulled_lines = any(
                    not l.wt_is_pulled and l.qty > 0
                    for l in rec.do_lot_line_ids
                )
            else:
                rec.wt_has_unpulled_lines = any(
                    not l.wt_is_pulled and l.quantity > 0
                    for l in rec.move_line_ids
                )

    # ── ORM ───────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("wt.delivery") or _("New")
        return super().create(vals_list)

    # ── Smart Buttons ─────────────────────────────────────────────────────────

    def action_view_pickings(self):
        """Buka daftar DO yang terhubung dengan dokumen pengiriman ini."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Delivery Orders"),
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("wt_delivery_id", "=", self.id)],
            "context": {
                "default_wt_delivery_id": self.id,
                "default_origin": self.name,
                "default_company_id": self.company_id.id,
            },
        }

    def action_new_picking(self):
        """Buka wizard buat DO baru sebagai dialog popup (tidak pindah halaman)."""
        self.ensure_one()
        if self.state not in ("draft", "confirmed"):
            raise ValidationError(
                _("DO baru hanya bisa ditambahkan saat status Draft atau Confirmed.")
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Buat Delivery Order (DO)"),
            "res_model": "wt.delivery.do.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_delivery_id": self.id,
            },
        }

    # ── Apply Adjustment (alur lama — backward compat) ────────────────────────

    def action_apply_adjustment(self):
        """Terapkan koreksi stok (susut) untuk semua baris Detail Timbang yang:
        - Memiliki selisih (wt_difference_qty != 0)
        - Sudah teralokasi penuh (wt_is_fully_allocated = True)
        - Belum pernah di-apply (wt_adjustment_applied = False)

        Stock move dibuat TANPA picking_id agar tidak muncul sebagai baris
        tambahan di dalam DO. Pola move mengikuti stock_opname._apply_line_with_allocations.

        Setelah apply, baris ditandai wt_adjustment_applied = True sehingga saat
        action_validate tidak double-scrap.
        """
        for delivery in self:
            delivery._apply_adjustment_one()

    def _apply_adjustment_one(self):
        self.ensure_one()
        if self.state not in ("in_progress", "completed"):
            raise UserError(_(
                "Apply Adjustment hanya bisa dilakukan saat status In Progress atau Completed."
            ))

        if self.do_line_ids:
            # Alur baru: menggunakan rincian lot rencana DO
            adjustable_lines = self.do_lot_line_ids.filtered(
                lambda l: abs(l.wt_difference_qty) > 0.001
                and l.wt_is_fully_allocated
                and not l.wt_adjustment_applied
            )
            if not adjustable_lines:
                raise UserError(_(
                    "Tidak ada baris rencana lot dengan selisih yang sudah teralokasi penuh.\n"
                    "Pastikan alokasi selisih sudah diisi untuk setiap baris yang punya selisih."
                ))

            company = self.company_id
            move_vals_list = []
            for line in adjustable_lines:
                for alloc in line.wt_allocation_ids:
                    # Cari lokasi fisik lot yang tepat (di bawah do_line_id.location_id)
                    parent_loc = line.do_line_id.location_id
                    exact_loc = parent_loc
                    if parent_loc and line.lot_id:
                        locations = self.env["stock.location"].search([("id", "child_of", parent_loc.id)])
                        quant = self.env["stock.quant"].search([
                            ("product_id", "=", line.product_id.id),
                            ("location_id", "in", locations.ids),
                            ("lot_id", "=", line.lot_id.id),
                            ("quantity", ">", 0),
                        ], limit=1)
                        if quant:
                            exact_loc = quant.location_id

                    if line.wt_difference_qty < 0:
                        location_src = exact_loc
                        location_dest = alloc.location_dest_id
                    else:
                        location_src = alloc.location_dest_id
                        location_dest = exact_loc

                    move_vals_list.append({
                        "inventory_name": "%s / %s / %s" % (
                            self.name,
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
                        "company_id": company.id,
                        "move_line_ids": [(0, 0, {
                            "product_id": line.product_id.id,
                            "product_uom_id": line.product_id.uom_id.id,
                            "quantity": alloc.qty,
                            "lot_id": line.lot_id.id if line.lot_id else False,
                            "location_id": location_src.id,
                            "location_dest_id": location_dest.id,
                            "company_id": company.id,
                        })],
                    })

            # Eksekusi stock move penyesuaian (scrap)
            if move_vals_list:
                ctx = dict(
                    inventory_mode=False,
                    tracking_disable=True,
                    mail_notrack=True,
                    no_recompute=True,
                    ignore_dest_packages=True,
                )
                moves = self.env["stock.move"].sudo().with_context(**ctx).create(move_vals_list)
                moves.with_context(**ctx)._action_done()

            # Update qty lot rencana ke berat fisik riil dan tandai adjustment diterapkan.
            # Tujuan: saat Validasi & Kirim, DO dibuat dengan demand = fisik aktual
            # sehingga tidak ada selisih demand → tidak ada backorder.
            for line in adjustable_lines:
                write_vals = {"wt_adjustment_applied": True}
                if line.wt_physical_qty > 0:
                    write_vals["qty"] = line.wt_physical_qty
                line.sudo().write(write_vals)

            lots = ", ".join(
                l.lot_id.name or l.product_id.display_name
                for l in adjustable_lines
            )
            self.message_post(
                body=Markup(_(
                    "<b>Apply Adjustment</b> diterapkan oleh %s.<br/>"
                    "Rincian Lot rencana yang diproses: %s"
                ) % (self.env.user.name, lots))
            )

        else:
            # Alur lama (backward compat)
            adjustable_lines = self.move_line_ids.filtered(
                lambda l: abs(l.wt_difference_qty) > 0.001
                and l.wt_is_fully_allocated
                and not l.wt_adjustment_applied
            )
            if not adjustable_lines:
                raise UserError(_(
                    "Tidak ada baris dengan selisih yang sudah teralokasi penuh.\n"
                    "Pastikan alokasi selisih sudah diisi untuk setiap baris yang punya selisih."
                ))

            # ── Step 1: Bangun move_vals_list DAHULU ─────────────────────────────
            company = self.company_id
            move_vals_list = []
            for line in adjustable_lines:
                for alloc in line.wt_allocation_ids:
                    if line.wt_difference_qty < 0:
                        location_src = line.location_id
                        location_dest = alloc.location_dest_id
                    else:
                        location_src = alloc.location_dest_id
                        location_dest = line.location_id

                    move_vals_list.append({
                        "inventory_name": "%s / %s / %s" % (
                            self.name,
                            line.lot_id.name or line.product_id.display_name,
                            alloc.reason_id.name,
                        ),
                        "state": "confirmed",
                        "picked": True,
                        "is_inventory": True,
                        "product_id": line.product_id.id,
                        "product_uom": line.product_uom_id.id,
                        "product_uom_qty": alloc.qty,
                        "location_id": location_src.id,
                        "location_dest_id": location_dest.id,
                        "company_id": company.id,
                        "origin": "%s / %s / %s" % (
                            self.name, line.picking_id.name, alloc.reason_id.name
                        ),
                        "move_line_ids": [(0, 0, {
                            "product_id": line.product_id.id,
                            "product_uom_id": line.product_uom_id.id,
                            "quantity": alloc.qty,
                            "lot_id": line.lot_id.id if line.lot_id else False,
                            "location_id": location_src.id,
                            "location_dest_id": location_dest.id,
                            "company_id": company.id,
                        })],
                    })

            # ── Step 2: Sesuaikan quantity move_line dan demand move ─────────────
            shrinkage_lines = adjustable_lines.filtered(
                lambda l: l.wt_difference_qty < 0
            )
            move_update_map = {}
            for line in shrinkage_lines:
                move = line.move_id
                if move and move.state not in ("done", "cancel") and move.id not in move_update_map:
                    total_physical = sum(ml.wt_physical_qty for ml in move.move_line_ids)
                    if total_physical < move.product_uom_qty:
                        move_update_map[move.id] = total_physical

            for line in shrinkage_lines:
                line.sudo().write({"quantity": line.wt_physical_qty})

            for move_id, new_qty in move_update_map.items():
                self.env["stock.move"].browse(move_id).sudo().with_context(
                    do_not_unreserve=True
                ).write({"product_uom_qty": new_qty})

            # ── Step 3: Eksekusi stock move penyesuaian ──────────────────────────
            if move_vals_list:
                ctx = dict(
                    inventory_mode=False,
                    tracking_disable=True,
                    mail_notrack=True,
                    no_recompute=True,
                    ignore_dest_packages=True,
                )
                moves = self.env["stock.move"].sudo().with_context(**ctx).create(move_vals_list)
                moves.with_context(**ctx)._action_done()

            # ── Step 4: Refresh ketersediaan picking ─────────────────────────────
            affected_pickings = adjustable_lines.mapped("picking_id").filtered(
                lambda p: p.state not in ("done", "cancel", "draft")
            )
            if affected_pickings:
                affected_pickings.sudo().with_context(mail_notrack=True).action_assign()

            adjustable_lines.sudo().write({"wt_adjustment_applied": True})

            lots = ", ".join(
                l.lot_id.name or l.product_id.display_name
                for l in adjustable_lines
            )
            self.message_post(
                body=Markup(_(
                    "<b>Apply Adjustment</b> diterapkan oleh %s.<br/>"
                    "Lot/Produk yang diproses: %s"
                ) % (self.env.user.name, lots))
            )

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_confirm(self):
        for delivery in self:
            if delivery.state != "draft":
                raise ValidationError(_("Hanya Draft yang bisa dikonfirmasi."))

            # Alur baru (multi-step): cukup ada warehouse_step_ids
            if delivery.warehouse_step_ids:
                delivery.write({"state": "confirmed"})
                continue

            # Alur inline do_line_ids: validasi kelengkapan, TIDAK buat picking di sini
            # Picking baru dibuat saat Validasi akhir (action_validate)
            if delivery.do_line_ids:
                # Cek minimal semua baris punya picking_type dan operator
                incomplete = delivery.do_line_ids.filtered(
                    lambda l: not l.picking_type_id or not l.operator_id or not l.product_id
                )
                if incomplete:
                    seqs = ", ".join(str(l.sequence) for l in incomplete)
                    raise ValidationError(_(
                        "Baris DO berikut belum lengkap (Tipe Operasi / Operator / Produk): %s"
                    ) % seqs)
                delivery.write({"state": "confirmed"})
                continue

            # Alur lama (backward compat): harus ada picking_ids
            if not delivery.picking_ids:
                raise ValidationError(_(
                    "Tambahkan minimal satu Warehouse Step, "
                    "Rencana DO, atau DO sebelum konfirmasi."
                ))
            # Validasi: semua DO harus punya operator
            pickings_without_operator = delivery.picking_ids.filtered(
                lambda p: not p.wt_operator_id
            )
            if pickings_without_operator:
                names = ", ".join(pickings_without_operator.mapped("name"))
                raise ValidationError(_(
                    "Semua Delivery Order harus memiliki operator sebelum dikonfirmasi.\n"
                    "DO tanpa operator: %s"
                ) % names)
            delivery.write({"state": "confirmed"})

    def action_start(self):
        for delivery in self:
            if delivery.state != "confirmed":
                raise ValidationError(_("Hanya Confirmed yang bisa dimulai."))
            delivery.write({"state": "in_progress"})

    def action_complete(self):
        """Selesai timbang di mode pengiriman."""
        for delivery in self:
            if delivery.state != "in_progress":
                raise ValidationError(_("Hanya In Progress yang bisa diselesaikan."))

            if delivery.do_line_ids:
                # Alur baru: menggunakan rincian lot rencana DO
                pulled_lots = delivery.do_lot_line_ids.filtered(
                    # Ambil baris yang sudah di-pull operator dan tidak di-skip
                    lambda l: l.wt_is_pulled and not l.wt_skip_line
                )
                unallocated = pulled_lots.filtered(
                    lambda l: abs(l.wt_difference_qty) > 0.001 and not l.wt_is_fully_allocated
                )
                if unallocated:
                    lot_details = "\n".join(
                        "- %s (sisa: %.4f kg)" % (
                            l.lot_id.name or l.product_id.name,
                            l.wt_unallocated_qty,
                        )
                        for l in unallocated
                    )
                    raise ValidationError(_(
                        "Tidak dapat menyelesaikan pengiriman karena selisih timbang "
                        "pada lot rencana berikut belum teralokasi penuh:\n\n"
                        "%s\n\n"
                        "Buka tab Detail Timbang -> klik ikon Alokasi pada baris "
                        "yang bersangkutan untuk mengisi alokasi selisih terlebih dahulu."
                    ) % lot_details)

                unapplied = pulled_lots.filtered(
                    lambda l: abs(l.wt_difference_qty) > 0.001
                    and l.wt_is_fully_allocated
                    and not l.wt_adjustment_applied
                )
                if unapplied:
                    lot_names = ", ".join(
                        l.lot_id.name or l.product_id.name
                        for l in unapplied
                    )
                    raise ValidationError(_(
                        "Tidak dapat menyelesaikan pengiriman karena Apply Adjustment "
                        "belum diterapkan pada lot rencana berikut:\n\n%s\n\n"
                        "Klik tombol 'Apply Adjustment' terlebih dahulu untuk "
                        "menerapkan koreksi stok sebelum Selesai Timbang."
                    ) % lot_names)

                if delivery.wt_has_unpulled_lines:
                    unpulled = delivery.unpulled_do_lot_line_ids
                    lot_names = ", ".join(
                        l.lot_id.name or l.product_id.name
                        for l in unpulled
                    )
                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "title": _("Selesai Timbang Gagal"),
                            "message": _(
                                "Terdapat lot rencana yang belum di-pull dan ditimbang "
                                "oleh operator: %s\n\n"
                                "Minta operator Pull Tugas ulang, lakukan penimbangan, "
                                "lalu coba Selesai Timbang kembali."
                            ) % lot_names,
                            "type": "danger",
                            "sticky": True,
                            "next": {"type": "ir.actions.client", "tag": "reload"},
                        },
                    }

            else:
                # Alur lama (backward compat)
                pulled_lines = delivery.move_line_ids.filtered(
                    lambda l: l.wt_is_pulled and not l.wt_skip_line
                )
                unallocated = pulled_lines.filtered(
                    lambda l: abs(l.wt_difference_qty) > 0.001 and not l.wt_is_fully_allocated
                )
                if unallocated:
                    lot_details = "\n".join(
                        "- %s (sisa: %.4f kg)" % (
                            l.lot_id.name or l.product_id.display_name,
                            l.wt_unallocated_qty,
                        )
                        for l in unallocated
                    )
                    raise ValidationError(_(
                        "Tidak dapat menyelesaikan pengiriman karena selisih timbang "
                        "pada lot berikut belum teralokasi penuh:\n\n"
                        "%s\n\n"
                        "Buka tab Detail Timbang → klik ikon Alokasi pada baris "
                        "yang bersangkutan untuk mengisi alokasi selisih terlebih dahulu."
                    ) % lot_details)

                unapplied = pulled_lines.filtered(
                    lambda l: abs(l.wt_difference_qty) > 0.001
                    and l.wt_is_fully_allocated
                    and not l.wt_adjustment_applied
                )
                if unapplied:
                    lot_names = ", ".join(
                        l.lot_id.name or l.product_id.display_name
                        for l in unapplied
                    )
                    raise ValidationError(_(
                        "Tidak dapat menyelesaikan pengiriman karena Apply Adjustment "
                        "belum diterapkan pada lot berikut:\n\n%s\n\n"
                        "Klik tombol 'Apply Adjustment' terlebih dahulu untuk "
                        "menerapkan koreksi stok sebelum Selesai Timbang."
                    ) % lot_names)

                if delivery.wt_has_unpulled_lines:
                    unpulled = delivery.unpulled_move_line_ids
                    lot_names = ", ".join(
                        l.lot_id.name or l.product_id.display_name
                        for l in unpulled
                    )
                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "title": _("Selesai Timbang Gagal"),
                            "message": _(
                                "Terdapat lot baru yang belum di-pull dan ditimbang "
                                "oleh operator: %s\n\n"
                                "Minta operator Pull Tugas ulang, lakukan penimbangan, "
                                "lalu coba Selesai Timbang kembali."
                            ) % lot_names,
                            "type": "danger",
                            "sticky": True,
                            "next": {"type": "ir.actions.client", "tag": "reload"},
                        },
                    }

            delivery.write({"state": "completed"})

    def action_validate(self):
        """Validasi pengiriman.

        Alur baru (do_line_ids):
        - Buat semua stock.picking dari do_line_ids langsung dengan status 'done'.
        - Picking TIDAK pernah ada sebelum langkah ini.

        Alur lama (picking_ids tanpa do_line_ids):
        - Validasi picking yang sudah ada (backward compat).
        """
        for delivery in self:
            if delivery.do_line_ids:
                delivery._action_validate_do_lines()
            else:
                delivery._action_validate_one()

    def _action_validate_do_lines(self):
        """Alur baru: buat semua DO dari do_line_ids langsung jadi 'done'."""
        self.ensure_one()
        if self.state != "completed":
            raise ValidationError(_("Hanya Completed yang bisa divalidasi."))

        lines_to_generate = self.do_line_ids.filtered(
            lambda l: not l.picking_id or l.picking_id.state != "done"
        )

        for line in lines_to_generate.sorted("sequence"):
            line._action_create_done_picking()

        self.write({
            "state": "done",
            "validated_at": fields.Datetime.now(),
            "validated_by_id": self.env.user.id,
        })
        
        # Hitung jumlah picking baru yang digenerate pada langkah akhir ini
        generated_count = len(lines_to_generate)
        if generated_count > 0:
            msg = _(
                "<b>Validasi &amp; Kirim</b> dilakukan oleh %s.<br/>"
                "Dibuat %d Delivery Order baru dengan status Done."
            ) % (self.env.user.name, generated_count)
        else:
            msg = _(
                "<b>Validasi &amp; Kirim</b> dilakukan oleh %s.<br/>"
                "Semua Delivery Order sebelumnya sudah divalidasi secara manual."
            ) % self.env.user.name

        self.message_post(body=Markup(msg))

    def _action_validate_one(self):
        self.ensure_one()
        if self.state != "completed":
            raise ValidationError(_("Hanya Completed yang bisa divalidasi."))

        # Move lines aktif: sudah di-pull operator, quantity > 0, tidak diskip
        active_lines = self.move_line_ids.filtered(
            lambda l: l.quantity > 0 and not l.wt_skip_line and l.wt_is_pulled
        )

        # Cek semua baris sudah punya berat fisik
        unset_lines = active_lines.filtered(lambda l: l.wt_physical_qty == 0.0)
        if unset_lines:
            lots = ", ".join(
                l.lot_id.name or l.product_id.display_name
                for l in unset_lines
            )
            raise ValidationError(_(
                "Beberapa baris belum memiliki berat fisik:\n%s\n\n"
                "Isi berat fisik atau centang 'Lewati' terlebih dahulu."
            ) % lots)

        # Cek semua selisih sudah teralokasi penuh
        lines_with_diff = active_lines.filtered(
            lambda l: abs(l.wt_difference_qty) > 0.001
        )
        unallocated = lines_with_diff.filtered(lambda l: not l.wt_is_fully_allocated)
        if unallocated:
            lots = ", ".join(
                "%s (sisa: %.4f kg)" % (
                    l.lot_id.name or l.product_id.display_name,
                    l.wt_unallocated_qty,
                )
                for l in unallocated
            )
            raise ValidationError(_(
                "Selisih belum teralokasi penuh pada:\n%s\n\n"
                "Buka 'Alokasi' pada tab Detail Timbang untuk mengisi alokasi selisih."
            ) % lots)

        # Kumpulkan data stock move adjustment SEBELUM quantity berubah.
        adjustments_to_create = []
        for line in active_lines:
            if abs(line.wt_difference_qty) <= 0.001:
                continue
            if line.wt_adjustment_applied:
                continue
            for alloc in line.wt_allocation_ids:
                if line.wt_difference_qty < 0:
                    location_src = line.location_id
                    location_dest = alloc.location_dest_id
                else:
                    location_src = alloc.location_dest_id
                    location_dest = line.location_id
                adjustments_to_create.append({
                    "inventory_name": "%s / %s / %s" % (
                        self.name,
                        line.lot_id.name or line.product_id.display_name,
                        alloc.reason_id.name,
                    ),
                    "state": "confirmed",
                    "picked": True,
                    "is_inventory": True,
                    "product_id": line.product_id.id,
                    "product_uom": line.product_uom_id.id,
                    "product_uom_qty": alloc.qty,
                    "location_id": location_src.id,
                    "location_dest_id": location_dest.id,
                    "company_id": line.company_id.id,
                    "origin": "%s / %s / %s" % (
                        self.name, line.picking_id.name, alloc.reason_id.name
                    ),
                    "move_line_ids": [(0, 0, {
                        "product_id": line.product_id.id,
                        "product_uom_id": line.product_uom_id.id,
                        "quantity": alloc.qty,
                        "lot_id": line.lot_id.id if line.lot_id else False,
                        "location_id": location_src.id,
                        "location_dest_id": location_dest.id,
                        "company_id": line.company_id.id,
                    })],
                })

        # Step 1: Set quantity = berat fisik di setiap move line
        for line in self.move_line_ids.filtered(lambda l: l.quantity > 0):
            line._apply_wt_weighing()

        # Step 1b: Update demand (product_uom_qty) setiap move ke jumlah fisik
        for picking in self.picking_ids:
            for move in picking.move_ids.filtered(
                lambda m: m.state not in ("done", "cancel")
            ):
                total_physical = sum(
                    ml.wt_physical_qty
                    for ml in move.move_line_ids
                    if not ml.wt_skip_line
                )
                if total_physical < move.product_uom_qty:
                    move.sudo().write({"product_uom_qty": total_physical})

        # Step 2: Validasi setiap picking (DO)
        for picking in self.picking_ids:
            if picking.state not in ("done", "cancel"):
                picking.with_context(skip_immediate=True)._action_done()
                backorder_pickings = self.env["stock.picking"].search([
                    ("backorder_id", "=", picking.id),
                    ("state", "!=", "done"),
                ])
                backorder_pickings.action_cancel()

        # Step 3: Buat stock move adjustment SETELAH DO selesai
        if adjustments_to_create:
            moves = self.env["stock.move"].sudo().with_context(
                inventory_mode=False
            ).create(adjustments_to_create)
            moves.with_context(ignore_dest_packages=True)._action_done()

        self.write({
            "state": "validated",
            "validated_at": fields.Datetime.now(),
            "validated_by_id": self.env.user.id,
        })

    def action_cancel(self):
        for delivery in self:
            if delivery.state in ("validated", "done"):
                raise ValidationError(_(
                    "Dokumen yang sudah divalidasi atau selesai tidak dapat dibatalkan."
                ))
            # Cancel semua DO yang terhubung dan belum selesai/dibatalkan
            pickings_to_cancel = delivery.picking_ids.filtered(
                lambda p: p.state not in ("done", "cancel")
            )
            if pickings_to_cancel:
                pickings_to_cancel.action_cancel()
            delivery.write({"state": "cancelled"})

    def action_draft(self):
        for delivery in self:
            if delivery.state != "cancelled":
                raise ValidationError(_("Hanya yang dibatalkan yang bisa dikembalikan ke Draft."))
            delivery.write({"state": "draft"})
