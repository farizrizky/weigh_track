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
        string="Number",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Warehouse",
        required=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Location",
        required=True,
        domain="[('company_id', '=', company_id), ('usage', '=', 'internal')]",
        tracking=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Division",
        required=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    operator_employee_id = fields.Many2one(
        "hr.employee",
        string="Operator Name",
        required=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    date = fields.Date(
        string="Opname Date",
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
        string="Opname Lines",
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

    def action_apply_inventory(self):
        for opname in self:
            if opname.state != "completed":
                raise ValidationError(_("Only completed stock opname can be applied to inventory."))
            
            for line in opname.line_ids:
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
                    })
                else:
                    quant.inventory_quantity = line.physical_qty
                
                quant.action_apply_inventory()
                
            opname.write({"state": "applied"})


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
        string="Product",
        required=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot/Serial Number",
        required=True,
        domain="[('product_id', '=', product_id)]",
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="UoM",
        required=True,
    )
    theoretical_qty = fields.Float(
        string="Theoretical Qty",
        digits="Product Unit of Measure",
        readonly=True,
    )
    physical_qty = fields.Float(
        string="Physical Qty",
        digits="Product Unit of Measure",
    )
    difference_qty = fields.Float(
        string="Difference",
        compute="_compute_difference_qty",
        store=True,
        digits="Product Unit of Measure",
    )
    state = fields.Selection(
        related="opname_id.state",
        store=True,
    )
    stock_move_line_count = fields.Integer(
        string="Move History",
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

    @api.depends("physical_qty", "theoretical_qty")
    def _compute_difference_qty(self):
        for line in self:
            line.difference_qty = line.physical_qty - line.theoretical_qty
