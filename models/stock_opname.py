# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..constants.roles import Role


class StockOpname(models.Model):
    _name = "wt.stock.opname"
    _description = "Stock Opname"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    STATE_SELECTION = [
        ("draft", "Draft"),
        ("assigned", "Ditugaskan"),
        ("in_progress", "Dalam Proses"),
        ("completed", "Selesai"),
        ("applied", "Diterapkan"),
        ("cancelled", "Dibatalkan"),
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
    allowed_division_ids = fields.Many2many(
        "wt.division",
        compute="_compute_allowed_division_ids",
        string="Allowed Divisions",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Lokasi",
        required=True,
        domain="[('id', 'in', allowed_location_ids)]",
        tracking=True,
    )
    allowed_location_ids = fields.Many2many(
        "stock.location",
        compute="_compute_allowed_location_ids",
        string="Allowed Locations",
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Divisi",
        required=True,
        domain="[('id', 'in', allowed_division_ids)]",
        tracking=True,
    )
    operator_employee_id = fields.Many2one(
        "hr.employee",
        string="Operator",
        required=True,
        domain="[('id', 'in', allowed_operator_employee_ids)]",
        tracking=True,
    )
    allowed_operator_employee_ids = fields.Many2many(
        "hr.employee",
        compute="_compute_allowed_operator_employee_ids",
        string="Allowed Operators",
    )
    date = fields.Date(
        string="Tanggal",
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
    note = fields.Text(
        string="Catatan",
        tracking=True,
    )
    line_ids = fields.One2many(
        "wt.stock.opname.line",
        "opname_id",
        string="Data Stok",
        copy=True,
    )
    total_lot_count = fields.Integer(
        string="Total Lot",
        compute="_compute_totals",
        store=True,
    )
    total_theoretical_qty = fields.Float(
        string="Total Qty Teori",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    total_physical_qty = fields.Float(
        string="Total Qty Fisik",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    total_difference_qty = fields.Float(
        string="Total Selisih",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("wt.stock.opname") or _("New")
        return super().create(vals_list)

    @api.depends("warehouse_id", "company_id")
    def _compute_allowed_division_ids(self):
        Division = self.env["wt.division"]
        for opname in self:
            domain = [("active", "=", True)]
            if opname.company_id:
                domain.append(("company_id", "=", opname.company_id.id))
            if opname.warehouse_id and opname.warehouse_id.estate_id:
                domain.append(("estate_id", "=", opname.warehouse_id.estate_id.id))
            opname.allowed_division_ids = Division.search(domain)

    @api.depends("warehouse_id", "division_id")
    def _compute_allowed_location_ids(self):
        Location = self.env["stock.location"]
        Rule = self.env["wt.receipt.rule"]
        for opname in self:
            if not opname.warehouse_id or not opname.division_id:
                opname.allowed_location_ids = Location.browse()
                continue
            rules = Rule.search([
                ("active", "=", True),
                ("warehouse_id", "=", opname.warehouse_id.id),
                ("division_id", "=", opname.division_id.id),
            ])
            opname.allowed_location_ids = rules.mapped("location_id")

    def _get_matching_receipt_rules(self):
        self.ensure_one()
        if not (self.warehouse_id and self.division_id and self.location_id):
            return self.env["wt.receipt.rule"]
        return self.env["wt.receipt.rule"].search([
            ("active", "=", True),
            ("warehouse_id", "=", self.warehouse_id.id),
            ("division_id", "=", self.division_id.id),
            ("location_id", "=", self.location_id.id),
        ])

    @api.depends("warehouse_id", "division_id", "location_id")
    def _compute_allowed_operator_employee_ids(self):
        for opname in self:
            rules = opname._get_matching_receipt_rules()
            opname.allowed_operator_employee_ids = rules.mapped(
                "weighing_location_id.operator_id"
            ).filtered(
                lambda employee: employee
            )

    @api.depends(
        "line_ids",
        "line_ids.lot_id",
        "line_ids.count_status",
        "line_ids.theoretical_qty",
        "line_ids.physical_qty",
        "line_ids.difference_qty",
    )
    def _compute_totals(self):
        for opname in self:
            weighed_lines = opname.line_ids.filtered(lambda line: line.count_status == "weighed")
            opname.total_lot_count = len(set(opname.line_ids.mapped("lot_id").ids))
            opname.total_theoretical_qty = sum(opname.line_ids.mapped("theoretical_qty"))
            opname.total_physical_qty = sum(weighed_lines.mapped("physical_qty"))
            opname.total_difference_qty = sum(opname.line_ids.mapped("difference_qty"))

    @api.onchange("company_id")
    def _onchange_company_id(self):
        for opname in self:
            opname.warehouse_id = False
            opname.division_id = False
            opname.location_id = False
            opname.operator_employee_id = False

    @api.onchange("warehouse_id")
    def _onchange_warehouse_id(self):
        if self.warehouse_id:
            if self.division_id and self.division_id not in self.allowed_division_ids:
                self.division_id = False
            self.location_id = False
        else:
            self.division_id = False
            self.location_id = False

    @api.onchange("division_id")
    def _onchange_division_id(self):
        if self.location_id and self.location_id not in self.allowed_location_ids:
            self.location_id = False

    @api.onchange("warehouse_id", "location_id", "division_id")
    def _onchange_scope_fields(self):
        """Clear lines when location or division changes."""
        self.line_ids = [(5, 0, 0)]
        if (
            self.operator_employee_id
            and self.operator_employee_id not in self.allowed_operator_employee_ids
        ):
            self.operator_employee_id = False

    @api.constrains("warehouse_id", "division_id", "location_id", "operator_employee_id")
    def _check_scope_consistency(self):
        role_model = self.env["wt.employee.role"]
        for opname in self:
            if (
                opname.warehouse_id
                and opname.warehouse_id.estate_id
                and opname.division_id
                and opname.division_id.estate_id != opname.warehouse_id.estate_id
            ):
                raise ValidationError(_(
                    "Division must belong to the same estate as the selected warehouse."
                ))

            if opname.warehouse_id and opname.division_id and opname.location_id:
                rules = opname._get_matching_receipt_rules()
                if not rules:
                    raise ValidationError(_(
                        "Location must be configured in an active Receipt Rule for "
                        "the selected warehouse and division."
                    ))
                allowed_operators = rules.mapped("weighing_location_id.operator_id")
                if (
                    opname.operator_employee_id
                    and opname.operator_employee_id not in allowed_operators
                ):
                    raise ValidationError(_(
                        "Operator must match the weighing location operator from "
                        "the active Receipt Rule for the selected warehouse, "
                        "division, and location."
                    ))

            role_model.check_employee_allowed(
                opname.operator_employee_id,
                opname.company_id,
                Role.OPERATOR,
                _("Operator"),
            )

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

    def _all_lines_weighed(self):
        self.ensure_one()
        return bool(self.line_ids) and all(
            line.count_status == "weighed" for line in self.line_ids
        )

    def action_complete_if_ready(self):
        for opname in self:
            if not opname._all_lines_weighed():
                raise ValidationError(_(
                    "Stock opname can only be completed after all lines are weighed."
                ))
            opname.write({"state": "completed"})

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
            if not opname.line_ids.filtered(lambda line: line.lot_id):
                raise ValidationError(_(
                    "Stock Opname wajib memiliki minimal satu baris lot sebelum diterapkan."
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
                    "Silahkan tentukan alasan selisih stok yang terjadi."
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
                "inventory_name": _("Stock Opname"),
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

    COUNT_STATUS_SELECTION = [
        ("unweighed", "Belum Ditimbang"),
        ("weighed", "Sudah Ditimbang"),
    ]

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
    count_status = fields.Selection(
        COUNT_STATUS_SELECTION,
        string="Status",
        default="unweighed",
        required=True,
        index=True,
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

    def write(self, vals):
        if "physical_qty" in vals and "count_status" not in vals:
            vals = dict(vals, count_status="weighed")
        return super().write(vals)

    def unlink(self):
        applied_lines = self.filtered(lambda line: line.opname_id.state == "applied")
        if applied_lines:
            raise ValidationError(_(
                "Baris lot tidak dapat dihapus setelah Stock Opname diterapkan."
            ))
        return super().unlink()

    def init(self):
        self.env.cr.execute(
            """
            UPDATE wt_stock_opname_line AS line
            SET count_status = 'weighed'
            FROM wt_stock_opname AS opname
            WHERE line.opname_id = opname.id
                AND line.count_status IS NULL
                AND opname.state IN ('completed', 'applied')
            """
        )
        self.env.cr.execute(
            """
            UPDATE wt_stock_opname_line
            SET count_status = 'unweighed'
            WHERE count_status IS NULL
            """
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

    @api.depends("count_status", "physical_qty", "theoretical_qty")
    def _compute_difference_qty(self):
        for line in self:
            if line.count_status == "weighed":
                line.difference_qty = line.physical_qty - line.theoretical_qty
            else:
                line.difference_qty = 0.0

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
