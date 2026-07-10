# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockOpnameApplyWizard(models.TransientModel):
    """
    Wizard pre-apply: user mengisi alokasi selisih (per reason + location)
    untuk setiap opname line yang punya difference_qty != 0, kemudian
    menekan "Apply Stock Adjustment" untuk membuat stock moves sesuai alokasi.
    """
    _name = "wt.stock.opname.apply.wizard"
    _description = "Stock Opname — Configure & Apply Difference Wizard"

    opname_id = fields.Many2one(
        "wt.stock.opname",
        string="Stock Opname",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    wizard_line_ids = fields.One2many(
        "wt.stock.opname.apply.wizard.line",
        "wizard_id",
        string="Opname Lines",
    )

    # ------------------------------------------------------------------
    # Default / constructor
    # ------------------------------------------------------------------

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        opname_id = self.env.context.get("active_id")
        if not opname_id:
            return res
        opname = self.env["wt.stock.opname"].browse(opname_id)
        if opname.state != "completed":
            raise ValidationError(
                _("Stock opname must be in Completed state to configure differences.")
            )

        wizard_lines = []
        for line in opname.line_ids:
            # Ambil alokasi yang sudah ada (jika user buka wizard kedua kali)
            existing_allocs = []
            for alloc in line.allocation_ids:
                existing_allocs.append((0, 0, {
                    "reason_id": alloc.reason_id.id,
                    "qty": alloc.qty,
                    "location_dest_id": alloc.location_dest_id.id,
                    "note": alloc.note,
                }))
            wizard_lines.append((0, 0, {
                "opname_line_id": line.id,
                "product_id": line.product_id.id,
                "lot_id": line.lot_id.id,
                "uom_id": line.uom_id.id,
                "theoretical_qty": line.theoretical_qty,
                "physical_qty": line.physical_qty,
                "difference_qty": line.difference_qty,
                "allocation_ids": existing_allocs,
            }))

        res["opname_id"] = opname_id
        res["wizard_line_ids"] = wizard_lines
        return res

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_confirm_allocations(self):
        """Simpan alokasi ke model permanen, lalu tutup wizard."""
        self.ensure_one()
        self._validate_allocations()

        for wline in self.wizard_line_ids:
            line = wline.opname_line_id
            # Hapus alokasi lama lalu tulis ulang dari wizard
            line.allocation_ids.unlink()
            for walloc in wline.allocation_ids:
                self.env["wt.stock.opname.line.allocation"].create({
                    "line_id": line.id,
                    "reason_id": walloc.reason_id.id,
                    "qty": walloc.qty,
                    "location_dest_id": walloc.location_dest_id.id,
                    "note": walloc.note or "",
                })
        return {"type": "ir.actions.act_window_close"}

    def action_apply(self):
        """Simpan alokasi + langsung apply stock adjustment."""
        self.ensure_one()
        self._validate_allocations()

        # Simpan alokasi
        for wline in self.wizard_line_ids:
            line = wline.opname_line_id
            line.allocation_ids.unlink()
            for walloc in wline.allocation_ids:
                self.env["wt.stock.opname.line.allocation"].create({
                    "line_id": line.id,
                    "reason_id": walloc.reason_id.id,
                    "qty": walloc.qty,
                    "location_dest_id": walloc.location_dest_id.id,
                    "note": walloc.note or "",
                })

        # Apply inventory — delegasikan ke opname
        self.opname_id.action_apply_inventory()
        return {"type": "ir.actions.act_window_close"}

    # ------------------------------------------------------------------
    # Validation helper
    # ------------------------------------------------------------------

    def _validate_allocations(self):
        """Pastikan setiap line dengan selisih sudah fully allocated."""
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        errors = []
        for wline in self.wizard_line_ids:
            diff = abs(round(wline.difference_qty, precision))
            if diff == 0.0:
                continue  # Line nol — skip, tidak perlu alokasi
            allocated = round(
                sum(a.qty for a in wline.allocation_ids), precision
            )
            if abs(allocated - diff) > 10 ** (-precision):
                errors.append(
                    _("• Lot %s (%s): selisih %.4f, dialokasikan %.4f")
                    % (
                        wline.lot_id.name,
                        wline.product_id.display_name,
                        diff,
                        allocated,
                    )
                )
        if errors:
            raise ValidationError(
                _("Alokasi belum balance untuk beberapa baris:\n\n%s")
                % "\n".join(errors)
            )


class StockOpnameApplyWizardLine(models.TransientModel):
    """Satu baris opname di dalam wizard."""
    _name = "wt.stock.opname.apply.wizard.line"
    _description = "Stock Opname Apply Wizard — Line"
    _order = "id"

    wizard_id = fields.Many2one(
        "wt.stock.opname.apply.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    opname_line_id = fields.Many2one(
        "wt.stock.opname.line",
        string="Opname Line",
        required=True,
        readonly=True,
    )
    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    lot_id = fields.Many2one("stock.lot", string="Lot/SN", readonly=True)
    uom_id = fields.Many2one("uom.uom", string="UoM", readonly=True)
    theoretical_qty = fields.Float(
        string="Theoretical", digits="Product Unit of Measure", readonly=True
    )
    physical_qty = fields.Float(
        string="Physical", digits="Product Unit of Measure", readonly=True
    )
    difference_qty = fields.Float(
        string="Difference", digits="Product Unit of Measure", readonly=True
    )
    has_difference = fields.Boolean(
        string="Has Difference", compute="_compute_has_difference"
    )
    allocated_qty = fields.Float(
        string="Allocated", digits="Product Unit of Measure",
        compute="_compute_allocated_qty",
    )
    unallocated_qty = fields.Float(
        string="Unallocated", digits="Product Unit of Measure",
        compute="_compute_allocated_qty",
    )
    is_fully_allocated = fields.Boolean(
        string="Fully Allocated", compute="_compute_allocated_qty"
    )
    allocation_ids = fields.One2many(
        "wt.stock.opname.apply.wizard.allocation",
        "wizard_line_id",
        string="Allocations",
    )

    @api.depends("difference_qty")
    def _compute_has_difference(self):
        for rec in self:
            rec.has_difference = abs(rec.difference_qty) > 0.0

    @api.depends("allocation_ids.qty", "difference_qty")
    def _compute_allocated_qty(self):
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        for rec in self:
            allocated = sum(a.qty for a in rec.allocation_ids)
            diff_abs = abs(rec.difference_qty)
            rec.allocated_qty = allocated
            rec.unallocated_qty = round(diff_abs - allocated, precision)
            rec.is_fully_allocated = (
                diff_abs == 0.0
                or abs(allocated - diff_abs) <= 10 ** (-precision)
            )


class StockOpnameApplyWizardAllocation(models.TransientModel):
    """Satu baris alokasi selisih di dalam wizard."""
    _name = "wt.stock.opname.apply.wizard.allocation"
    _description = "Stock Opname Apply Wizard — Allocation"
    _order = "id"

    wizard_line_id = fields.Many2one(
        "wt.stock.opname.apply.wizard.line",
        string="Wizard Line",
        required=True,
        ondelete="cascade",
    )
    reason_id = fields.Many2one(
        "wt.stock.opname.difference.reason",
        string="Reason",
        required=True,
        domain="[('active', '=', True)]",
    )
    qty = fields.Float(
        string="Qty",
        digits="Product Unit of Measure",
        required=True,
    )
    location_dest_id = fields.Many2one(
        "stock.location",
        string="Dest. Location",
        required=True,
        domain="[('usage', 'in', ['virtual', 'inventory', 'internal'])]",
    )
    note = fields.Char(string="Note")
    uom_id = fields.Many2one(
        "uom.uom",
        string="UoM",
        related="wizard_line_id.uom_id",
        readonly=True,
    )

    @api.onchange("reason_id")
    def _onchange_reason_id(self):
        if self.reason_id and self.reason_id.location_dest_id:
            self.location_dest_id = self.reason_id.location_dest_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            reason = self.env["wt.stock.opname.difference.reason"].browse(
                vals.get("reason_id")
            )
            if reason and reason.location_dest_id:
                vals["location_dest_id"] = reason.location_dest_id.id
        return super().create(vals_list)

    def write(self, vals):
        if "reason_id" in vals:
            reason = self.env["wt.stock.opname.difference.reason"].browse(vals["reason_id"])
            vals = dict(vals)
            if reason and reason.location_dest_id:
                vals["location_dest_id"] = reason.location_dest_id.id
            return super().write(vals)
        if "location_dest_id" in vals:
            vals = dict(vals)
            vals.pop("location_dest_id", None)
            if not vals:
                return True
        return super().write(vals)

    @api.constrains("qty")
    def _check_qty_positive(self):
        for rec in self:
            if rec.qty <= 0:
                raise ValidationError(
                    _("Allocation qty must be greater than zero.")
                )
