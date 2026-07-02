# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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
    # Baris detail penimbangan (dipopulate dari move lines DO)
    line_ids = fields.One2many(
        "wt.delivery.line",
        "delivery_id",
        string="Detail Timbang",
        copy=False,
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

    @api.depends("line_ids.demand_qty", "line_ids.physical_qty", "line_ids.difference_qty")
    def _compute_totals(self):
        for rec in self:
            rec.total_demand_qty = sum(rec.line_ids.mapped("demand_qty"))
            rec.total_physical_qty = sum(rec.line_ids.mapped("physical_qty"))
            rec.total_difference_qty = sum(rec.line_ids.mapped("difference_qty"))

    def _compute_picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids)

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

    # ─────────────────────────────────── Workflow ───

    def action_populate_lines(self):
        """Muat baris detail penimbangan dari move lines semua DO yang terhubung."""
        for delivery in self:
            if delivery.state not in ("draft", "confirmed"):
                raise ValidationError(_("Baris hanya bisa dimuat saat status Draft atau Confirmed."))
            if not delivery.picking_ids:
                raise ValidationError(_("Belum ada DO yang terhubung. Tambahkan DO terlebih dahulu."))

            ready_pickings = delivery.picking_ids.filtered(lambda p: p.state == "assigned")
            if not ready_pickings:
                raise ValidationError(_(
                    "Tidak ada DO dengan status Ready. "
                    "Konfirmasi dan lakukan reservasi DO terlebih dahulu."
                ))

            # Hapus baris yang belum punya physical_qty
            delivery.line_ids.filtered(lambda l: l.physical_qty == 0.0).unlink()
            existing_move_line_ids = delivery.line_ids.mapped("move_line_id").ids

            line_vals = []
            for picking in ready_pickings:
                for move_line in picking.move_line_ids.filtered(
                    lambda ml: ml.reserved_qty > 0 and ml.id not in existing_move_line_ids
                ):
                    line_vals.append({
                        "delivery_id": delivery.id,
                        "picking_id": picking.id,
                        "move_line_id": move_line.id,
                        "product_id": move_line.product_id.id,
                        "lot_id": move_line.lot_id.id if move_line.lot_id else False,
                        "uom_id": move_line.product_uom_id.id,
                        "demand_qty": move_line.reserved_qty,
                        "physical_qty": 0.0,
                    })

            if not line_vals and not delivery.line_ids:
                raise ValidationError(_(
                    "Tidak ada baris yang dapat dimuat. "
                    "Pastikan DO sudah Ready dan memiliki reservasi stok."
                ))
            if line_vals:
                self.env["wt.delivery.line"].create(line_vals)

    def action_confirm(self):
        for delivery in self:
            if delivery.state != "draft":
                raise ValidationError(_("Hanya Draft yang bisa dikonfirmasi."))
            if not delivery.picking_ids:
                raise ValidationError(_("Tambahkan minimal satu DO sebelum konfirmasi."))
            delivery.write({"state": "confirmed"})

    def action_start(self):
        for delivery in self:
            if delivery.state != "confirmed":
                raise ValidationError(_("Hanya Confirmed yang bisa dimulai."))
            delivery.write({"state": "in_progress"})

    def action_complete(self):
        for delivery in self:
            if delivery.state not in ("confirmed", "in_progress"):
                raise ValidationError(_("Status tidak valid untuk diselesaikan."))
            delivery.write({"state": "completed"})

    def action_validate(self):
        for delivery in self:
            delivery._action_validate_one()

    def _action_validate_one(self):
        self.ensure_one()
        if self.state != "completed":
            raise ValidationError(_("Hanya Completed yang bisa divalidasi."))

        unset_lines = self.line_ids.filtered(
            lambda l: l.physical_qty == 0.0 and not l.skip_line
        )
        if unset_lines:
            raise ValidationError(_(
                "Beberapa baris belum memiliki berat fisik.\n"
                "Isi berat fisik atau centang 'Lewati' terlebih dahulu."
            ))

        pickings_to_validate = self.line_ids.mapped("picking_id")
        for picking in pickings_to_validate:
            lines_for_picking = self.line_ids.filtered(lambda l: l.picking_id == picking)
            for line in lines_for_picking:
                if line.skip_line:
                    continue
                line._apply_weighing_to_do()

            if picking.state not in ("done", "cancel"):
                picking.with_context(skip_immediate=True)._action_done()
                backorder_pickings = self.env["stock.picking"].search([
                    ("backorder_id", "=", picking.id),
                    ("state", "!=", "done"),
                ])
                backorder_pickings.action_cancel()

        self.write({
            "state": "validated",
            "validated_at": fields.Datetime.now(),
            "validated_by_id": self.env.user.id,
        })

    def action_cancel(self):
        for delivery in self:
            if delivery.state == "validated":
                raise ValidationError(_("Dokumen yang sudah divalidasi tidak dapat dibatalkan."))
            delivery.write({"state": "cancelled"})

    def action_draft(self):
        for delivery in self:
            if delivery.state != "cancelled":
                raise ValidationError(_("Hanya yang dibatalkan yang bisa dikembalikan ke Draft."))
            delivery.write({"state": "draft"})


class DeliveryLine(models.Model):
    _name = "wt.delivery.line"
    _description = "Detail Timbang Pengiriman"
    _order = "delivery_id, picking_id, id"

    delivery_id = fields.Many2one(
        "wt.delivery",
        string="Tugas Pengiriman",
        required=True,
        ondelete="cascade",
        index=True,
    )
    delivery_state = fields.Selection(
        related="delivery_id.state",
        store=True,
        readonly=True,
    )
    picking_id = fields.Many2one(
        "stock.picking",
        string="Delivery Order (DO)",
        required=True,
        ondelete="restrict",
        index=True,
        readonly=True,
    )
    picking_name = fields.Char(
        string="Nomor DO",
        related="picking_id.name",
        store=True,
        readonly=True,
    )
    operator_employee_id = fields.Many2one(
        "hr.employee",
        string="Operator Tujuan",
        index=True,
    )
    move_line_id = fields.Many2one(
        "stock.move.line",
        string="Move Line DO",
        ondelete="restrict",
        index=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Produk",
        required=True,
        readonly=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot/No. Seri",
        readonly=True,
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="Satuan",
        required=True,
        readonly=True,
    )
    demand_qty = fields.Float(
        string="Demand (kg)",
        digits="Product Unit of Measure",
        readonly=True,
    )
    physical_qty = fields.Float(
        string="Berat Fisik (kg)",
        digits="Product Unit of Measure",
    )
    difference_qty = fields.Float(
        string="Selisih (kg)",
        compute="_compute_difference_qty",
        store=True,
        digits="Product Unit of Measure",
    )
    reason_id = fields.Many2one(
        "wt.stock.opname.difference.reason",
        string="Alasan Selisih",
        domain="[('active', '=', True)]",
    )
    note = fields.Char(
        string="Catatan",
    )
    skip_line = fields.Boolean(
        string="Lewati",
        default=False,
        help="Centang untuk melewati baris ini saat validasi.",
    )

    @api.depends("physical_qty", "demand_qty")
    def _compute_difference_qty(self):
        for line in self:
            line.difference_qty = line.physical_qty - line.demand_qty

    @api.constrains("physical_qty", "demand_qty")
    def _check_physical_qty(self):
        for line in self:
            if line.skip_line:
                continue
            if line.physical_qty < 0:
                raise ValidationError(_("Berat fisik tidak boleh negatif."))
            if line.physical_qty > line.demand_qty:
                raise ValidationError(_(
                    "Berat fisik (%.4f) tidak boleh melebihi demand (%.4f)."
                ) % (line.physical_qty, line.demand_qty))

    @api.constrains("difference_qty", "reason_id")
    def _check_reason_required(self):
        for line in self:
            if line.skip_line:
                continue
            has_diff = abs(line.difference_qty) > 0.001
            if has_diff and not line.reason_id:
                raise ValidationError(_(
                    "Alasan selisih wajib diisi (selisih: %.4f kg)."
                ) % abs(line.difference_qty))

    def _apply_weighing_to_do(self):
        """Update qty_done pada move_line DO dan buat scrap untuk selisih."""
        self.ensure_one()
        if self.skip_line:
            return

        move_line = self.move_line_id
        if not move_line:
            move_line = self.picking_id.move_line_ids.filtered(
                lambda ml: ml.product_id == self.product_id
                and (not self.lot_id or ml.lot_id == self.lot_id)
            )[:1]
            if move_line:
                self.write({"move_line_id": move_line.id})

        if not move_line:
            raise ValidationError(_(
                "Move Line tidak ditemukan pada DO %s."
            ) % self.picking_id.name)

        move_line.sudo().write({"quantity": self.physical_qty})

        diff = abs(self.difference_qty)
        if diff > 0.001 and self.reason_id and self.reason_id.location_dest_id:
            picking = self.picking_id
            scrap = self.env["stock.scrap"].sudo().create({
                "product_id": self.product_id.id,
                "product_uom_id": self.uom_id.id,
                "scrap_qty": diff,
                "lot_id": self.lot_id.id if self.lot_id else False,
                "location_id": picking.location_id.id,
                "scrap_location_id": self.reason_id.location_dest_id.id,
                "company_id": self.delivery_id.company_id.id,
                "picking_id": picking.id,
                "origin": "%s / %s" % (self.delivery_id.name, picking.name),
            })
            scrap.action_validate()
