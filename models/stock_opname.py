# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockOpname(models.Model):
    _name = "wt.stock.opname"
    _description = "Stock Opname"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    STATE_SELECTION = [
        ("draft", "Draft"),
        ("assigned", "Assigned"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("applied", "Applied"),
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
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Gudang",
        required=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Lokasi",
        required=True,
        domain="[('company_id', '=', company_id), ('usage', '=', 'internal')]",
        tracking=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Divisi",
        required=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    operator_employee_id = fields.Many2one(
        "hr.employee",
        string="Nama Operator",
        required=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    date = fields.Date(
        string="Tanggal Opname",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    state = fields.Selection(
        STATE_SELECTION,
        string="Status",
        default="draft",
        required=True,
        index=True,
        tracking=True,
    )
    line_ids = fields.One2many(
        "wt.stock.opname.line",
        "opname_id",
        string="Baris Opname",
        copy=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("wt.stock.opname") or _("New")
        return super().create(vals_list)

    @api.onchange("warehouse_id")
    def _onchange_warehouse_id(self):
        if self.warehouse_id:
            self.location_id = self.warehouse_id.lot_stock_id
        else:
            self.location_id = False

    @api.onchange("location_id", "division_id")
    def _onchange_location_division(self):
        """Clear lines when location or division changes."""
        self.line_ids = [(5, 0, 0)]

    def action_populate_lines(self):
        """Load stock lines from quants at the selected location (server-side)."""
        for opname in self:
            if opname.state != "draft":
                raise ValidationError(_("Lines can only be loaded on draft stock opname."))
            if not opname.location_id:
                raise ValidationError(_("Please select a location first."))

            # Remove existing lines
            opname.line_ids.unlink()

            quants = self.env["stock.quant"].sudo().search([
                ("location_id", "=", opname.location_id.id),
                ("lot_id", "!=", False),
                ("quantity", ">", 0),
            ])

            line_vals = []
            for quant in quants:
                if not quant.product_id or not quant.lot_id:
                    continue
                line_vals.append({
                    "opname_id": opname.id,
                    "product_id": quant.product_id.id,
                    "lot_id": quant.lot_id.id,
                    "uom_id": quant.product_id.uom_id.id,
                    "theoretical_qty": quant.quantity,
                    "physical_qty": 0.0,
                })

            if line_vals:
                self.env["wt.stock.opname.line"].sudo().create(line_vals)
            else:
                raise ValidationError(_(
                    "No lots with stock found at the selected location."
                ))

    def action_assign(self):
        for opname in self:
            if opname.state != "draft":
                raise ValidationError(_("Only draft stock opname can be processed/assigned."))
            valid_lines = opname.line_ids.filtered(lambda l: l.product_id and l.lot_id)
            if not valid_lines:
                raise ValidationError(_(
                    "There are no valid lot lines to process. "
                    "Please ensure the selected location has stock with lot numbers registered."
                ))
            opname.write({"state": "assigned"})

    def action_start(self):
        for opname in self:
            if opname.state != "assigned":
                raise ValidationError(_("Only assigned stock opname can be started."))
            opname.write({"state": "in_progress"})

    def action_cancel(self):
        for opname in self:
            if opname.state in ["applied"]:
                raise ValidationError(_("Cannot cancel an applied stock opname."))
            opname.write({"state": "cancelled"})

    def action_draft(self):
        for opname in self:
            if opname.state != "cancelled":
                raise ValidationError(_("Only cancelled stock opname can be set back to draft."))
            opname.write({"state": "draft"})

    def action_configure_difference(self):
        """Buka wizard Configure Difference untuk mengisi alokasi selisih."""
        self.ensure_one()
        if self.state != "completed":
            raise ValidationError(_(
                "Stock opname must be in Completed state to configure differences."
            ))
        return {
            "name": _("Configure Difference"),
            "type": "ir.actions.act_window",
            "res_model": "wt.stock.opname.apply.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_id": self.id,
                "active_model": "wt.stock.opname",
            },
        }

    def action_apply_inventory(self):
        """Apply stock adjustment.

        Jika line punya allocation_ids dan is_fully_allocated, maka buat
        stock.move terpisah per alokasi (ke location_dest dari alokasi).
        Jika difference_qty == 0, skip line tersebut.
        Jika ada line dengan selisih yang belum fully allocated → raise error.
        """
        for opname in self:
            if opname.state != "completed":
                raise ValidationError(_(
                    "Only completed stock opname can be applied to inventory."
                ))

            # Periksa apakah ada line selisih yang belum fully allocated
            unallocated_lines = opname.line_ids.filtered(
                lambda l: abs(l.difference_qty) > 0.001
                and not l.is_fully_allocated
            )
            if unallocated_lines:
                lots = ", ".join(unallocated_lines.mapped("lot_id.name"))
                raise ValidationError(_(
                    "Beberapa lot belum selesai dialokasikan selisihnya:\n%s\n\n"
                    "Klik ikon ⊕ pada baris yang bersangkutan untuk mengisi alokasi."
                ) % lots)

            for line in opname.line_ids:
                if abs(line.difference_qty) < 0.001:
                    # Tidak ada selisih — skip
                    continue

                if line.allocation_ids:
                    # ── Mode alokasi: buat stock.move per alokasi ──
                    opname._apply_line_with_allocations(line)
                else:
                    # ── Fallback: pakai quant inventory adjustment ──
                    opname._apply_line_quant(line)

            opname.write({"state": "applied"})

    def _apply_line_with_allocations(self, line):
        """Buat stock.move untuk setiap baris alokasi.

        Mengikuti persis pola Odoo 19 native dari stock.quant._apply_inventory()
        dan _get_inventory_move_values():
        - state = 'confirmed' langsung di vals (bukan _action_confirm())
        - picked = True di vals
        - Create dengan context inventory_mode=False
        - _action_done() dengan context ignore_dest_packages=True

        difference_qty = physical - theoretical:
        - negatif (defisit/susut) : stok keluar dari gudang → lokasi virtual susut
        - positif (surplus)       : masuk dari lokasi virtual → gudang
        """
        opname = self
        company = opname.company_id

        move_vals_list = []
        for alloc in line.allocation_ids:
            if line.difference_qty < 0:
                # Defisit/susut: GI-01/Stok/Divisi 1 → lokasi susut
                location_src = opname.location_id
                location_dest = alloc.location_dest_id
            else:
                # Surplus: lokasi virtual → GI-01/Stok/Divisi 1
                location_src = alloc.location_dest_id
                location_dest = opname.location_id

            move_vals_list.append({
                # Odoo 19: 'inventory_name' → field "Referensi" di histori pergerakan
                # 'origin' → field "Sumber" (Source Document)
                "state": "confirmed",
                "picked": True,
                "is_inventory": True,
                "inventory_name": opname.name,
                "product_id": line.product_id.id,
                "product_uom": line.uom_id.id,
                "product_uom_qty": alloc.qty,
                "location_id": location_src.id,
                "location_dest_id": location_dest.id,
                "company_id": company.id,
                "origin": opname.name,
                "move_line_ids": [(0, 0, {
                    "product_id": line.product_id.id,
                    "product_uom_id": line.uom_id.id,
                    "quantity": alloc.qty,
                    "lot_id": line.lot_id.id,
                    "location_id": location_src.id,
                    "location_dest_id": location_dest.id,
                    "company_id": company.id,
                })],
            })

        if move_vals_list:
            # Odoo 19: create dengan inventory_mode=False, done dengan ignore_dest_packages=True
            # Persis sama dengan cara Odoo native di stock.quant._apply_inventory()
            moves = self.env["stock.move"].sudo().with_context(
                inventory_mode=False
            ).create(move_vals_list)
            moves.with_context(ignore_dest_packages=True)._action_done()

    def _apply_line_quant(self, line):
        """Fallback: apply via quant inventory quantity (line tanpa alokasi)."""
        opname = self
        quant = self.env["stock.quant"].search([
            ("location_id", "=", opname.location_id.id),
            ("product_id", "=", line.product_id.id),
            ("lot_id", "=", line.lot_id.id),
        ], limit=1)

        if not quant:
            quant = self.env["stock.quant"].create({
                "location_id": opname.location_id.id,
                "product_id": line.product_id.id,
                "lot_id": line.lot_id.id,
                "inventory_quantity": line.physical_qty,
                "inventory_reference": opname.name,
            })
        else:
            quant.write({
                "inventory_quantity": line.physical_qty,
                "inventory_reference": opname.name,
            })

        quant.action_apply_inventory()



class StockOpnameLine(models.Model):
    _name = "wt.stock.opname.line"
    _description = "Stock Opname Line"

    opname_id = fields.Many2one(
        "wt.stock.opname",
        string="Stock Opname",
        ondelete="cascade",
        required=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Produk",
        required=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot/No. Seri",
        required=True,
        domain="[('product_id', '=', product_id)]",
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="Satuan",
        required=True,
    )
    theoretical_qty = fields.Float(
        string="Qty Teori",
        digits="Product Unit of Measure",
        readonly=True,
    )
    physical_qty = fields.Float(
        string="Qty Fisik",
        digits="Product Unit of Measure",
    )
    difference_qty = fields.Float(
        string="Selisih",
        compute="_compute_difference_qty",
        store=True,
        digits="Product Unit of Measure",
    )
    allocation_ids = fields.One2many(
        "wt.stock.opname.line.allocation",
        "line_id",
        string="Alokasi Selisih",
    )
    allocated_qty = fields.Float(
        string="Qty Teralokasi",
        compute="_compute_allocation_status",
        digits="Product Unit of Measure",
    )
    unallocated_qty = fields.Float(
        string="Qty Belum Teralokasi",
        compute="_compute_allocation_status",
        digits="Product Unit of Measure",
    )
    is_fully_allocated = fields.Boolean(
        string="Sepenuhnya Teralokasi",
        compute="_compute_allocation_status",
    )
    state = fields.Selection(
        related="opname_id.state",
        store=True,
    )
    stock_move_line_count = fields.Integer(
        string="Riwayat Perpindahan",
        compute="_compute_stock_move_line_count",
    )

    @api.depends("lot_id", "opname_id.location_id")
    def _compute_stock_move_line_count(self):
        MoveLines = self.env["stock.move.line"].sudo()
        for line in self:
            if line.lot_id and line.opname_id.location_id:
                line.stock_move_line_count = MoveLines.search_count([
                    ("lot_id", "=", line.lot_id.id),
                    ("state", "=", "done"),
                    "|",
                    ("location_id", "=", line.opname_id.location_id.id),
                    ("location_dest_id", "=", line.opname_id.location_id.id),
                ])
            else:
                line.stock_move_line_count = 0

    def action_view_stock_move_lines(self):
        self.ensure_one()
        return {
            "name": _("Stock Move History: %s") % self.lot_id.name,
            "type": "ir.actions.act_window",
            "res_model": "stock.move.line",
            "view_mode": "list,form",
            "domain": [
                ("lot_id", "=", self.lot_id.id),
                ("state", "=", "done"),
                "|",
                ("location_id", "=", self.opname_id.location_id.id),
                ("location_dest_id", "=", self.opname_id.location_id.id),
            ],
            "context": {
                "search_default_group_by_picking": 1,
            },
        }

    @api.onchange("allocation_ids")
    def _onchange_allocation_balance(self):
        """Ketika total alokasi melebihi selisih, otomatis kurangi baris PERTAMA.

        Ini memungkinkan workflow split:
        1. Baris pertama auto-fill penuh (= unallocated)
        2. User tambah baris baru dengan qty tertentu
        3. Baris pertama otomatis berkurang sebesar qty baris baru
        """
        if not self.allocation_ids or not self.difference_qty:
            return
        diff_abs = abs(self.difference_qty)
        total = sum(a.qty for a in self.allocation_ids)
        if total <= diff_abs + 0.001:
            return
        excess = total - diff_abs
        # Kurangi baris PERTAMA
        first = self.allocation_ids[0]
        first.qty = max(0.0, first.qty - excess)

    def action_configure_line_difference(self):
        """Buka popup form line ini untuk mengisi alokasi selisih.
        Bisa dibuka di state completed (edit) dan applied (view only).
        """
        self.ensure_one()
        if self.state not in ["completed", "applied"]:
            state_label = dict(self.opname_id.STATE_SELECTION).get(self.state, self.state)
            raise ValidationError(_(
                "Alokasi selisih hanya bisa dilihat/diatur ketika status 'Completed' atau 'Applied'.\n"
                "Status saat ini: %s"
            ) % state_label)
        if abs(self.difference_qty) < 0.001:
            raise ValidationError(_(
                "Lot %s tidak memiliki selisih — alokasi tidak diperlukan."
            ) % self.lot_id.name)
        return {
            "name": _("Alokasi Selisih: %s") % self.lot_id.name,
            "type": "ir.actions.act_window",
            "res_model": "wt.stock.opname.line",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
            "views": [(False, "form")],
            "context": {
                "form_view_ref": "weightrack.view_wt_stock_opname_line_allocation_popup",
            },
        }

    @api.depends("physical_qty", "theoretical_qty")
    def _compute_difference_qty(self):
        for line in self:
            line.difference_qty = line.physical_qty - line.theoretical_qty

    @api.depends("allocation_ids.qty", "difference_qty")
    def _compute_allocation_status(self):
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        for line in self:
            diff_abs = abs(line.difference_qty)
            allocated = sum(line.allocation_ids.mapped("qty"))
            line.allocated_qty = allocated
            line.unallocated_qty = round(diff_abs - allocated, precision)
            if diff_abs < 10 ** (-precision):
                # Tidak ada selisih — dianggap fully allocated
                line.is_fully_allocated = True
            else:
                line.is_fully_allocated = (
                    abs(allocated - diff_abs) <= 10 ** (-precision)
                )
