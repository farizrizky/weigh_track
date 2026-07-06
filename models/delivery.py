# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


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
    # DOs yang dibuat langsung dari dokumen ini (via wt_delivery_id pada stock.picking)
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
    # Detail timbang: move lines dari semua DO yang terhubung
    # (via related field wt_delivery_id pada stock.move.line)
    move_line_ids = fields.One2many(
        "stock.move.line",
        "wt_delivery_id",
        string="Semua Detail Timbang",
    )
    # Detail timbang yang sudah di-pull oleh operator (tampil di tab Detail Timbang).
    # Lot yang baru di-reserve Odoo (belum di-pull) TIDAK tampil di sini,
    # sehingga admin bebas mengubah perincian DO sebelum operator pull ulang.
    pulled_move_line_ids = fields.One2many(
        "stock.move.line",
        "wt_delivery_id",
        domain=[("wt_is_pulled", "=", True), ("quantity", ">", 0)],
        string="Detail Timbang",
    )
    # Lot yang belum di-push ke operator — muncul saat Odoo re-reserve
    # ke lot lain setelah Apply Adjustment mengurangi stok lot asal.
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
        help="True jika ada move line aktif (qty > 0) yang belum pernah di-pull "
             "oleh operator — biasanya karena Odoo re-reserve dari lot lain setelah "
             "Apply Adjustment mengurangi stok lot asal.",
    )
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
        help="True jika ada minimal 1 baris dengan selisih yang sudah teralokasi penuh "
             "dan belum diterapkan adjustment-nya.",
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

    @api.depends(
        "move_line_ids.quantity",
        "move_line_ids.wt_physical_qty",
        "move_line_ids.wt_original_demand_qty",
        "move_line_ids.wt_is_pulled",
    )
    def _compute_totals(self):
        for rec in self:
            # Hanya hitung baris yang sudah di-pull operator
            active_lines = rec.move_line_ids.filtered(
                lambda l: l.wt_is_pulled and (l.quantity > 0 or l.wt_original_demand_qty > 0)
            )
            # Gunakan demand asli jika sudah tersimpan (setelah validasi)
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
    )
    def _compute_has_adjustable_lines(self):
        for rec in self:
            # Tombol Apply Adjustment hanya muncul untuk baris yang sudah di-pull
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

    @api.depends(
        "move_line_ids.wt_is_pulled",
        "move_line_ids.quantity",
    )
    def _compute_wt_has_unpulled_lines(self):
        for rec in self:
            rec.wt_has_unpulled_lines = any(
                not l.wt_is_pulled and l.quantity > 0
                for l in rec.move_line_ids
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("wt.delivery") or _("New")
        return super().create(vals_list)

    # ─────────────────────────────────── Smart Button ───

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

    # ─────────────────────────────────── Apply Adjustment ───

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

        # Cari baris yang siap di-adjust
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
        # PENTING: wt_difference_qty dibaca SEBELUM Step 2 mengubah quantity,
        # karena wt_difference_qty adalah computed field yang bergantung pada
        # quantity. Jika quantity diubah lebih dulu, wt_difference_qty akan
        # ter-recompute menjadi 0 dan arah lokasi akan terbalik (susut → stok
        # masuk, bukan stok keluar).
        company = self.company_id
        move_vals_list = []
        for line in adjustable_lines:
            for alloc in line.wt_allocation_ids:
                # Selisih negatif (susut): stok keluar dari gudang ke lokasi susut
                # Selisih positif (lebih): stok masuk dari lokasi virtual ke gudang
                if line.wt_difference_qty < 0:
                    location_src = line.location_id
                    location_dest = alloc.location_dest_id
                else:
                    location_src = alloc.location_dest_id
                    location_dest = line.location_id

                move_vals_list.append({
                    # Odoo 19: 'inventory_name' → field "Referensi" di histori pergerakan
                    # format: "WTDEL/... / No.Lot / Alasan"
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
        #
        # Kita menggunakan ORM standard write() agar Odoo me-recompute semua cache,
        # dependensi, dan forecast_availability dengan benar.
        #
        # Untuk stock.move, kita pass context `do_not_unreserve=True` agar Odoo
        # tidak memicu _do_unreserve() yang akan menghapus record stock.move.line.
        # Dengan cara ini, semua data timbang dan alokasi buatan operator tetap aman.

        cr = self.env.cr

        shrinkage_lines = adjustable_lines.filtered(
            lambda l: l.wt_difference_qty < 0
        )

        # Hitung product_uom_qty baru = sum physical qty per move
        move_update_map = {}   # {move_id: new_product_uom_qty}
        for line in shrinkage_lines:
            move = line.move_id
            if move and move.state not in ("done", "cancel") and move.id not in move_update_map:
                total_physical = sum(ml.wt_physical_qty for ml in move.move_line_ids)
                if total_physical < move.product_uom_qty:
                    move_update_map[move.id] = total_physical

        # Step 2a: Turunkan quantity move_line via standard write()
        # Ini akan otomatis meng-update reserved_quantity di stock_quant via ORM.
        for line in shrinkage_lines:
            line.sudo().write({"quantity": line.wt_physical_qty})

        # Step 2b: Turunkan demand (product_uom_qty) via standard write()
        # Gunakan context 'do_not_unreserve' agar move line tidak di-unlink.
        for move_id, new_qty in move_update_map.items():
            self.env["stock.move"].browse(move_id).sudo().with_context(do_not_unreserve=True).write(
                {"product_uom_qty": new_qty}
            )

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
        # Cukup panggil action_assign() untuk me-refresh status picking di UI.
        affected_pickings = adjustable_lines.mapped("picking_id").filtered(
            lambda p: p.state not in ("done", "cancel", "draft")
        )
        if affected_pickings:
            affected_pickings.sudo().with_context(
                mail_notrack=True,
            ).action_assign()

        # Tandai baris sebagai sudah di-adjust
        adjustable_lines.sudo().write({"wt_adjustment_applied": True})

        # Catat di chatter
        lots = ", ".join(
            l.lot_id.name or l.product_id.display_name
            for l in adjustable_lines
        )
        self.message_post(
            body=_(
                "<b>Apply Adjustment</b> diterapkan oleh %s.<br/>"
                "Lot/Produk yang diproses: %s"
            ) % (self.env.user.name, lots)
        )

    # ─────────────────────────────────── Workflow ───

    def action_confirm(self):
        for delivery in self:
            if delivery.state != "draft":
                raise ValidationError(_("Hanya Draft yang bisa dikonfirmasi."))
            if not delivery.picking_ids:
                raise ValidationError(_("Tambahkan minimal satu DO sebelum konfirmasi."))
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
        for delivery in self:
            if delivery.state != "in_progress":
                raise ValidationError(_("Hanya In Progress yang bisa diselesaikan."))

            # Blokir jika ada baris dengan selisih yang belum teralokasi penuh.
            # Alokasi harus diisi sebelum Selesai Timbang agar proses Apply
            # Adjustment dan Validasi dapat berjalan dengan benar.
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

            # Blokir jika ada baris yang sudah teralokasi penuh tapi Apply Adjustment
            # belum dilakukan. Koreksi stok HARUS diterapkan sebelum pengiriman
            # dianggap selesai agar stok gudang langsung akurat.
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

            # Blokir jika ada lot baru yang belum di-pull operator.
            # Lot ini biasanya muncul karena Odoo auto-reserve ke lot lain
            # setelah Apply Adjustment mengurangi stok lot asal.
            # Operator wajib Pull Tugas ulang agar bisa menimbang lot tersebut
            # sebelum pengiriman bisa diselesaikan.
            #
            # Gunakan display_notification + reload (bukan ValidationError) agar
            # form di-reload setelah notifikasi ditutup → banner peringatan muncul
            # otomatis tanpa perlu refresh manual.
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
        for delivery in self:
            delivery._action_validate_one()

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
        # Baris yang sudah di-apply via tombol Apply Adjustment (wt_adjustment_applied=True)
        # di-skip agar tidak double-adjust.
        # Stock move dibuat TANPA picking_id agar tidak muncul sebagai baris
        # tambahan di dalam DO.
        adjustments_to_create = []
        for line in active_lines:
            if abs(line.wt_difference_qty) <= 0.001:
                continue
            if line.wt_adjustment_applied:
                continue  # Sudah di-apply sebelumnya, skip
            for alloc in line.wt_allocation_ids:
                if line.wt_difference_qty < 0:
                    location_src = line.location_id
                    location_dest = alloc.location_dest_id
                else:
                    location_src = alloc.location_dest_id
                    location_dest = line.location_id
                adjustments_to_create.append({
                    # Odoo 19: 'inventory_name' → field "Referensi" di histori pergerakan
                    # format: "WTDEL/... / No.Lot / Alasan"
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
        # agar Odoo tidak membuat backorder/split line untuk selisih susut.
        # Selisih sudah ditangani oleh scrap (Step 3).
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
                # Cancel backorder (sisa demand yang tidak terpenuhi)
                backorder_pickings = self.env["stock.picking"].search([
                    ("backorder_id", "=", picking.id),
                    ("state", "!=", "done"),
                ])
                backorder_pickings.action_cancel()

        # Step 3: Buat stock move adjustment SETELAH DO selesai
        # (hanya untuk baris yang belum di-apply sebelumnya)
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
            if delivery.state == "validated":
                raise ValidationError(_(("Dokumen yang sudah divalidasi tidak dapat dibatalkan.")))
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
