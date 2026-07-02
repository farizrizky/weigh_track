# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..constants.product_types import ProductType


class ProductionReceipt(models.Model):
    _name = "wt.production.receipt"
    _description = "Production Receipt"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "production_date desc, id desc"

    STATE_SELECTION = [
        ("draft", "Draft"),
        ("processed", "Processed"),
        ("validated", "Validated"),
        ("cancelled", "Cancelled"),
    ]

    name = fields.Char(
        string="Number",
        default="/",
        readonly=True,
        copy=False,
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )
    production_date = fields.Date(
        string="Production Date",
        required=True,
        index=True,
        tracking=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Division",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    line_ids = fields.One2many(
        "wt.production.receipt.line",
        "receipt_id",
        string="Weighing",
        copy=False,
    )
    stock_picking_ids = fields.One2many(
        "stock.picking",
        "production_receipt_id",
        string="Inventory Receipts",
        readonly=True,
        copy=False,
    )
    reverse_picking_ids = fields.One2many(
        "stock.picking",
        "production_receipt_reverse_id",
        string="Inventory Reversals",
        readonly=True,
        copy=False,
    )
    stock_picking_count = fields.Integer(
        string="Inventory Receipt Count",
        compute="_compute_stock_picking_count",
    )
    reverse_picking_count = fields.Integer(
        string="Inventory Reversal Count",
        compute="_compute_stock_picking_count",
    )
    total_weighing = fields.Integer(
        string="Total Weighing",
        compute="_compute_totals",
        store=True,
    )
    total_bag = fields.Integer(
        string="Total Bag",
        compute="_compute_totals",
        store=True,
        tracking=True,
    )
    total_stock_weight = fields.Float(
        string="Total Stock Weight",
        compute="_compute_totals",
        store=True,
        tracking=True,
    )
    data_problem_count = fields.Integer(
        string="Data Problem Count",
        compute="_compute_totals",
        store=True,
    )
    state = fields.Selection(
        STATE_SELECTION,
        string="Status",
        default="draft",
        required=True,
        index=True,
        tracking=True,
    )
    validated_at = fields.Datetime(
        string="Validated At",
        readonly=True,
        copy=False,
        tracking=True,
    )
    validated_by_id = fields.Many2one(
        "res.users",
        string="Validated By",
        readonly=True,
        copy=False,
        tracking=True,
    )
    cancel_reason = fields.Text(
        string="Cancel Reason",
        readonly=True,
        copy=False,
        tracking=True,
    )
    cancelled_at = fields.Datetime(
        string="Cancelled At",
        readonly=True,
        copy=False,
        tracking=True,
    )
    cancelled_by_id = fields.Many2one(
        "res.users",
        string="Cancelled By",
        readonly=True,
        copy=False,
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        sequence_model = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "/":
                sequence_date = (
                    fields.Date.to_date(vals["production_date"])
                    if vals.get("production_date")
                    else fields.Date.context_today(self)
                )
                vals["name"] = sequence_model.next_by_code(
                    "wt.production.receipt",
                    sequence_date=sequence_date,
                )
                if not vals["name"]:
                    raise ValidationError(
                        _("Production Receipt sequence is not configured.")
                    )
        return super().create(vals_list)

    @api.depends(
        "line_ids",
        "line_ids.total_bag",
        "line_ids.stock_weight",
        "line_ids.has_data_problem",
    )
    def _compute_totals(self):
        for receipt in self:
            receipt.total_weighing = len(receipt.line_ids)
            receipt.total_bag = sum(receipt.line_ids.mapped("total_bag"))
            receipt.total_stock_weight = sum(receipt.line_ids.mapped("stock_weight"))
            problem_lines = receipt.line_ids.filtered("has_data_problem")
            receipt.data_problem_count = len(problem_lines)

    def _compute_stock_picking_count(self):
        for receipt in self:
            receipt.stock_picking_count = len(receipt.stock_picking_ids)
            receipt.reverse_picking_count = len(receipt.reverse_picking_ids)

    def write(self, vals):
        locked = self.filtered(lambda receipt: receipt.state == "validated")
        protected_fields = {
            "company_id",
            "production_date",
            "division_id",
            "line_ids",
            "state",
        }
        if (
            locked
            and protected_fields & set(vals)
            and not self.env.context.get("allow_production_receipt_update")
        ):
            raise ValidationError(_("Validated Production Receipt cannot be changed."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda receipt: receipt.state == "validated"):
            raise ValidationError(_("Validated Production Receipt cannot be deleted."))
        draft_lines = self.mapped("line_ids").filtered(
            lambda line: line.receipt_id.state in ("draft", "processed")
        )
        if draft_lines:
            draft_lines.unlink()
        return super().unlink()

    @api.constrains("company_id", "division_id")
    def _check_division_company(self):
        for receipt in self:
            if (
                receipt.company_id
                and receipt.division_id
                and receipt.division_id.company_id != receipt.company_id
            ):
                raise ValidationError(_("Division must belong to the selected company."))

    def action_process(self):
        for receipt in self:
            receipt._action_process_one()

    def _action_process_one(self):
        self.ensure_one()
        if self.state not in ("draft", "processed"):
            raise ValidationError(
                _("Only draft or processed Production Receipt can be processed.")
            )
        self._check_process_required()

        candidates = self._get_process_candidates()
        existing_weighing_ids = set(self.line_ids.mapped("weighing_cup_lump_id").ids)
        new_weighings = candidates.filtered(
            lambda detail: detail.id not in existing_weighing_ids
        )
        if not candidates:
            raise ValidationError(_("No weighing data found for this Production Receipt."))

        line_model = self.env["wt.production.receipt.line"]
        for weighing in new_weighings:
            line_model.create(
                {
                    "receipt_id": self.id,
                    "weighing_cup_lump_id": weighing.id,
                }
            )

        if new_weighings:
            new_weighings.with_context(
                allow_production_receipt_update=True
            ).write(
                {
                    "receipt_status": "in_production_receipt",
                    "production_receipt_id": self.id,
                }
            )
        self.write({"state": "processed"})

    def _check_process_required(self):
        self.ensure_one()
        missing = []
        for field_name, label in (
            ("company_id", _("Company")),
            ("production_date", _("Production Date")),
            ("division_id", _("Division")),
        ):
            if not self[field_name]:
                missing.append(label)
        if missing:
            raise ValidationError(
                _("Please complete required fields before process: %s.")
                % ", ".join(missing)
            )

    def _get_process_candidates(self):
        self.ensure_one()
        active_line_weighing_ids = self.env["wt.production.receipt.line"].search(
            [
                ("receipt_id.state", "!=", "cancelled"),
                ("receipt_id", "!=", self.id),
            ]
        ).mapped("weighing_cup_lump_id").ids
        domain = [
            ("company_id", "=", self.company_id.id),
            ("division_id", "=", self.division_id.id),
            ("production_date", "=", self.production_date),
            ("product_type", "=", ProductType.CUP_LUMP),
            ("id", "not in", active_line_weighing_ids or [0]),
        ]
        return self.env["wt.weighing.cup.lump"].search(domain)

    def action_validate(self):
        for receipt in self:
            receipt._action_validate_one()

    def _action_validate_one(self):
        self.ensure_one()
        if self.state not in ("processed", "draft"):
            raise ValidationError(
                _("Only draft or processed Production Receipt can be validated.")
            )
        if not self.line_ids:
            raise ValidationError(_("Production Receipt must have at least one line."))

        self._check_process_required()
        self._check_line_consistency()
        weighings = self.line_ids.mapped("weighing_cup_lump_id")
        weighings._check_required_for_validate()
        weighings.action_recheck_data_problem()
        self.line_ids._refresh_from_weighing()
        self._check_line_consistency()

        problem_lines = self.line_ids.filtered("has_data_problem")
        if problem_lines:
            raise ValidationError(
                _("Production Receipt still has weighing lines with data problem.")
            )
        self._check_duplicate_lines()
        self._create_inventory_receipts()

        now = fields.Datetime.now()
        self.with_context(allow_production_receipt_update=True).write(
            {
                "state": "validated",
                "validated_at": now,
                "validated_by_id": self.env.user.id,
            }
        )
        weighings.with_context(allow_production_receipt_update=True).write(
            {
                "receipt_status": "receipt_validated",
                "production_receipt_id": self.id,
            }
        )

    def _check_line_consistency(self):
        self.ensure_one()
        invalid_lines = self.line_ids.filtered(
            lambda line: line.company_id != self.company_id
            or line.production_date != self.production_date
            or line.division_id != self.division_id
        )
        if invalid_lines:
            raise ValidationError(
                _("Production Receipt lines must match the header scope.")
            )

    def _check_duplicate_lines(self):
        self.ensure_one()
        weighing_ids = self.line_ids.mapped("weighing_cup_lump_id").ids
        if len(weighing_ids) != len(set(weighing_ids)):
            raise ValidationError(_("Production Receipt cannot have duplicate lines."))

    def _create_inventory_receipts(self):
        self.ensure_one()
        active_pickings = self.stock_picking_ids.filtered(
            lambda picking: picking.state != "cancel"
        )
        if active_pickings:
            raise ValidationError(
                _("Inventory Receipt already exists for this Production Receipt.")
            )

        clerk = self.division_id.clerk_id
        if not clerk:
            raise ValidationError(
                _("Please configure Clerk on division '%s'.")
                % self.division_id.display_name
            )

        line_groups = self._get_inventory_receipt_line_groups()
        pickings = self.env["stock.picking"]
        for receipt_rule, lines in line_groups:
            pickings |= self._create_inventory_receipt_for_rule(
                receipt_rule,
                lines,
                clerk,
            )
        return pickings

    def _get_inventory_receipt_line_groups(self):
        self.ensure_one()
        grouped_lines = {}
        for line in self.line_ids:
            if not line.receipt_rule_id:
                raise ValidationError(
                    _("Receipt Rule is missing on weighing '%s'.")
                    % line.weighing_cup_lump_id.display_name
                )
            if not line.product_id:
                raise ValidationError(
                    _("Product is missing on weighing '%s'.")
                    % line.weighing_cup_lump_id.display_name
                )
            if line.stock_weight <= 0:
                raise ValidationError(
                    _("Stock Weight must be greater than zero on weighing '%s'.")
                    % line.weighing_cup_lump_id.display_name
                )
            receipt_rule_id = line.receipt_rule_id.id
            if receipt_rule_id not in grouped_lines:
                grouped_lines[receipt_rule_id] = {
                    "receipt_rule": line.receipt_rule_id,
                    "lines": self.env[line._name],
                }
            grouped_lines[receipt_rule_id]["lines"] |= line
        return [
            (values["receipt_rule"], values["lines"])
            for values in grouped_lines.values()
        ]

    def _create_inventory_receipt_for_rule(self, receipt_rule, lines, clerk):
        self.ensure_one()
        product = receipt_rule.product_id
        if product.tracking != "lot":
            raise ValidationError(
                _("Product '%s' must use lot tracking before Production Receipt can create inventory lot.")
                % product.display_name
            )
        if any(line.product_id != product for line in lines):
            raise ValidationError(
                _("All weighing lines in one Receipt Rule must use the same product.")
            )

        picking_type = receipt_rule.operation_type_id
        destination_location = receipt_rule.location_id
        source_location = self._get_receipt_source_location(picking_type)
        total_quantity = sum(lines.mapped("stock_weight"))
        lot = self._get_or_create_inventory_lot(product)
        partner = self._get_employee_partner(clerk)

        picking_model = self.env["stock.picking"].sudo().with_company(self.company_id)
        picking = picking_model.create(
            {
                "picking_type_id": picking_type.id,
                "partner_id": partner.id if partner else False,
                "receive_from_employee_id": clerk.id,
                "location_id": source_location.id,
                "location_dest_id": destination_location.id,
                "origin": self.name,
                "production_receipt_id": self.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "product_uom_qty": total_quantity,
                            "product_uom": product.uom_id.id,
                            "location_id": source_location.id,
                            "location_dest_id": destination_location.id,
                        },
                    )
                ],
            }
        )
        picking.action_confirm()
        move = picking.move_ids.filtered(
            lambda stock_move: stock_move.product_id == product
        )[:1]
        if not move:
            raise ValidationError(
                _("Inventory move could not be created for product '%s'.")
                % product.display_name
            )
        self._set_inventory_done_quantity(
            picking,
            move,
            lot,
            total_quantity,
            source_location,
            destination_location,
        )
        picking.with_context(skip_backorder=True).button_validate()
        if picking.state != "done":
            raise ValidationError(
                _("Inventory Receipt '%s' could not be validated automatically.")
                % picking.display_name
            )
        return picking

    def _get_receipt_source_location(self, picking_type):
        self.ensure_one()
        source_location = picking_type.default_location_src_id
        if source_location:
            return source_location
        source_location = self.env.ref(
            "stock.stock_location_suppliers",
            raise_if_not_found=False,
        )
        if not source_location:
            raise ValidationError(
                _("Source Location is not configured on Operation Type '%s'.")
                % picking_type.display_name
            )
        return source_location

    def _get_or_create_inventory_lot(self, product):
        self.ensure_one()
        lot_name = self._get_inventory_lot_name()
        lot_model = self.env["stock.lot"].sudo().with_company(self.company_id)
        lot = lot_model.search(
            [
                ("name", "=", lot_name),
                ("product_id", "=", product.id),
                ("company_id", "in", [False, self.company_id.id]),
            ],
            limit=1,
        )
        if lot:
            return lot
        return lot_model.create(
            {
                "name": lot_name,
                "product_id": product.id,
                "company_id": self.company_id.id,
                "division_id": self.division_id.id,
                "production_date": self.production_date,
            }
        )

    def _get_inventory_lot_name(self):
        self.ensure_one()
        product_code = self._clean_lot_component(ProductType.CUP_LUMP)
        division_code = self._clean_lot_component(self.division_id.code)
        production_date = fields.Date.to_date(self.production_date).strftime("%Y%m%d")
        return "%s-%s-%s" % (product_code, division_code, production_date)

    def _clean_lot_component(self, value):
        value = (value or "").strip()
        return value.replace("/", "-").replace("\\", "-").replace(" ", "-")

    def _get_employee_partner(self, employee):
        self.ensure_one()
        for field_name in ("work_contact_id", "address_home_id"):
            if field_name in employee._fields and employee[field_name]:
                return employee[field_name]
        if "user_id" in employee._fields and employee.user_id.partner_id:
            return employee.user_id.partner_id
        return self.env["res.partner"]

    def _set_inventory_done_quantity(
        self,
        picking,
        move,
        lot,
        quantity,
        source_location,
        destination_location,
    ):
        move_line_model = self.env["stock.move.line"].sudo().with_company(
            self.company_id
        )
        move.move_line_ids.filtered(
            lambda line: line.state not in ("done", "cancel")
        ).unlink()
        quantity_field = (
            "quantity"
            if "quantity" in move_line_model._fields
            else "qty_done"
        )
        move_line_values = {
            "picking_id": picking.id,
            "move_id": move.id,
            "company_id": self.company_id.id,
            "product_id": move.product_id.id,
            "product_uom_id": move.product_uom.id,
            "location_id": source_location.id,
            "location_dest_id": destination_location.id,
            "lot_id": lot.id,
            quantity_field: quantity,
        }
        if "picked" in move_line_model._fields:
            move_line_values["picked"] = True
        move_line_model.create(move_line_values)

    def action_cancel(self):
        for receipt in self:
            if receipt.state == "cancelled":
                continue
            if receipt.state != "validated":
                raise ValidationError(
                    _("Only validated Production Receipt can be cancelled.")
                )
            receipt._create_inventory_reversals()
            receipt.line_ids.mapped("weighing_cup_lump_id").with_context(
                allow_production_receipt_update=True
            ).write({"receipt_status": "receipt_cancelled"})
            receipt.with_context(allow_production_receipt_update=True).write(
                {
                    "state": "cancelled",
                    "cancelled_at": fields.Datetime.now(),
                    "cancelled_by_id": self.env.user.id,
                }
            )

    def _create_inventory_reversals(self):
        self.ensure_one()
        original_pickings = self.stock_picking_ids.filtered(
            lambda picking: picking.state == "done"
        )
        if not original_pickings:
            return self.env["stock.picking"]
        active_reversals = self.reverse_picking_ids.filtered(
            lambda picking: picking.state != "cancel"
        )
        if active_reversals:
            raise ValidationError(
                _("Inventory Reversal already exists for this Production Receipt.")
            )
        self._check_inventory_reversal_stock_available(original_pickings)

        reversals = self.env["stock.picking"]
        for picking in original_pickings:
            reversals |= self._create_inventory_reversal_for_picking(picking)
        return reversals

    def _check_inventory_reversal_stock_available(self, original_pickings):
        self.ensure_one()
        original_lines = original_pickings.move_line_ids.filtered(
            lambda line: line.state == "done" and line.lot_id and line.quantity > 0
        )
        if not original_lines:
            return

        grouped_lines = {}
        for line in original_lines:
            location = line.location_dest_id
            key = (line.product_id.id, line.lot_id.id, location.id)
            grouped_lines.setdefault(
                key,
                {
                    "product": line.product_id,
                    "lot": line.lot_id,
                    "location": location,
                    "quantity": 0.0,
                },
            )
            grouped_lines[key]["quantity"] += line.product_uom_id._compute_quantity(
                line.quantity,
                line.product_id.uom_id,
                round=False,
            )

        quant_model = self.env["stock.quant"].sudo()
        for values in grouped_lines.values():
            product = values["product"]
            lot = values["lot"]
            location = values["location"]
            required_quantity = values["quantity"]
            available_quantity = quant_model._get_available_quantity(
                product,
                location,
                lot_id=lot,
                strict=True,
            )
            if product.uom_id.compare(available_quantity, required_quantity) < 0:
                raise ValidationError(
                    _(
                        "Production Receipt cannot be cancelled because lot '%(lot)s' "
                        "only has %(available)s %(uom)s available at '%(location)s', "
                        "while %(required)s %(uom)s is required for reversal."
                    )
                    % {
                        "lot": lot.display_name,
                        "available": available_quantity,
                        "required": required_quantity,
                        "uom": product.uom_id.display_name,
                        "location": location.display_name,
                    }
                )

    def _create_inventory_reversal_for_picking(self, picking):
        self.ensure_one()
        reversal_lines = picking.move_line_ids.filtered(
            lambda line: line.state == "done" and line.lot_id and line.quantity > 0
        )
        if not reversal_lines:
            raise ValidationError(
                _("Inventory Receipt '%s' has no lot move line to reverse.")
                % picking.display_name
            )

        picking_type = picking.picking_type_id.return_picking_type_id or picking.picking_type_id
        source_location = picking.location_dest_id
        destination_location = picking.location_id
        partner = picking.partner_id
        picking_model = self.env["stock.picking"].sudo().with_company(self.company_id)
        reversal = picking_model.create(
            {
                "picking_type_id": picking_type.id,
                "partner_id": partner.id if partner else False,
                "receive_from_employee_id": picking.receive_from_employee_id.id,
                "location_id": source_location.id,
                "location_dest_id": destination_location.id,
                "origin": _("Cancel %(receipt)s / Return of %(picking)s")
                % {"receipt": self.name, "picking": picking.name},
                "return_id": picking.id,
                "production_receipt_reverse_id": self.id,
                "move_ids": self._prepare_inventory_reversal_move_commands(
                    reversal_lines,
                    picking_type,
                    source_location,
                    destination_location,
                ),
            }
        )
        reversal.action_confirm()
        self._set_inventory_reversal_done_quantities(
            reversal,
            reversal_lines,
            source_location,
            destination_location,
        )
        reversal.with_context(skip_backorder=True).button_validate()
        if reversal.state != "done":
            raise ValidationError(
                _("Inventory Reversal '%s' could not be validated automatically.")
                % reversal.display_name
            )
        return reversal

    def _prepare_inventory_reversal_move_commands(
        self,
        reversal_lines,
        picking_type,
        source_location,
        destination_location,
    ):
        commands = []
        grouped_lines = {}
        for line in reversal_lines:
            key = (line.product_id.id, line.product_uom_id.id)
            grouped_lines.setdefault(key, self.env[line._name])
            grouped_lines[key] |= line
        for lines in grouped_lines.values():
            product = lines[0].product_id
            uom = lines[0].product_uom_id
            commands.append(
                (
                    0,
                    0,
                    {
                        "product_id": product.id,
                        "product_uom_qty": sum(lines.mapped("quantity")),
                        "product_uom": uom.id,
                        "location_id": source_location.id,
                        "location_dest_id": destination_location.id,
                        "picking_type_id": picking_type.id,
                    },
                )
            )
        return commands

    def _set_inventory_reversal_done_quantities(
        self,
        reversal,
        original_lines,
        source_location,
        destination_location,
    ):
        move_line_model = self.env["stock.move.line"].sudo().with_company(
            self.company_id
        )
        quantity_field = (
            "quantity"
            if "quantity" in move_line_model._fields
            else "qty_done"
        )
        reversal.move_ids.move_line_ids.filtered(
            lambda line: line.state not in ("done", "cancel")
        ).unlink()
        for original_line in original_lines:
            move = reversal.move_ids.filtered(
                lambda stock_move: stock_move.product_id == original_line.product_id
                and stock_move.product_uom == original_line.product_uom_id
            )[:1]
            if not move:
                raise ValidationError(
                    _("Inventory reversal move is missing for product '%s'.")
                    % original_line.product_id.display_name
                )
            move_line_values = {
                "picking_id": reversal.id,
                "move_id": move.id,
                "company_id": self.company_id.id,
                "product_id": original_line.product_id.id,
                "product_uom_id": original_line.product_uom_id.id,
                "location_id": source_location.id,
                "location_dest_id": destination_location.id,
                "lot_id": original_line.lot_id.id,
                quantity_field: original_line.quantity,
            }
            if "picked" in move_line_model._fields:
                move_line_values["picked"] = True
            move_line_model.create(move_line_values)


class ProductionReceiptLine(models.Model):
    _name = "wt.production.receipt.line"
    _description = "Production Receipt Line"
    _order = "receipt_id, id"

    receipt_id = fields.Many2one(
        "wt.production.receipt",
        string="Production Receipt",
        required=True,
        ondelete="cascade",
        index=True,
    )
    receipt_state = fields.Selection(
        related="receipt_id.state",
        store=True,
        readonly=True,
    )
    weighing_cup_lump_id = fields.Many2one(
        "wt.weighing.cup.lump",
        string="Weighing Cup Lump",
        required=True,
        ondelete="restrict",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="weighing_cup_lump_id.company_id",
        store=True,
        readonly=True,
    )
    product_type = fields.Selection(
        ProductType.SELECTION,
        string="Product Type",
        related="weighing_cup_lump_id.product_type",
        store=True,
        readonly=True,
    )
    production_date = fields.Date(
        string="Production Date",
        related="weighing_cup_lump_id.production_date",
        store=True,
        readonly=True,
    )
    weighing_date = fields.Datetime(
        string="Weighing Date",
        related="weighing_cup_lump_id.weighing_date",
        store=True,
        readonly=True,
    )
    estate_id = fields.Many2one(
        "wt.estate",
        string="Estate",
        related="weighing_cup_lump_id.estate_id",
        store=True,
        readonly=True,
    )
    weighing_location_id = fields.Many2one(
        "wt.weighing.location",
        string="Weighing Location",
        related="weighing_cup_lump_id.weighing_location_id",
        store=True,
        readonly=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Division",
        related="weighing_cup_lump_id.division_id",
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        related="weighing_cup_lump_id.product_id",
        store=True,
        readonly=True,
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="UoM",
        related="weighing_cup_lump_id.uom_id",
        store=True,
        readonly=True,
    )
    receipt_rule_id = fields.Many2one(
        "wt.receipt.rule",
        string="Receipt Rule",
        related="weighing_cup_lump_id.receipt_rule_id",
        store=True,
        readonly=True,
    )
    operator_employee_id = fields.Many2one(
        "hr.employee",
        string="Operator",
        related="weighing_cup_lump_id.operator_employee_id",
        store=True,
        readonly=True,
    )
    clerk_employee_id = fields.Many2one(
        "hr.employee",
        string="Clerk",
        related="weighing_cup_lump_id.clerk_employee_id",
        store=True,
        readonly=True,
    )
    foreman_employee_id = fields.Many2one(
        "hr.employee",
        string="Foreman",
        related="weighing_cup_lump_id.foreman_employee_id",
        store=True,
        readonly=True,
    )
    tapper_employee_id = fields.Many2one(
        "hr.employee",
        string="Tapper",
        related="weighing_cup_lump_id.tapper_employee_id",
        store=True,
        readonly=True,
    )
    total_bag = fields.Integer(
        string="Total Bag",
        related="weighing_cup_lump_id.total_bag",
        store=True,
        readonly=True,
    )
    stock_weight = fields.Float(
        string="Stock Weight",
        compute="_compute_stock_weight",
        store=True,
    )
    has_data_problem = fields.Boolean(
        string="Has Data Problem",
        related="weighing_cup_lump_id.has_data_problem",
        store=True,
        readonly=True,
    )
    data_problem_code = fields.Selection(
        related="weighing_cup_lump_id.data_problem_code",
        store=True,
        readonly=True,
    )
    data_problem_note = fields.Text(
        string="Data Problem Note",
        related="weighing_cup_lump_id.data_problem_note",
        readonly=True,
    )

    @api.depends(
        "weighing_cup_lump_id",
        "weighing_cup_lump_id.net_weight",
        "weighing_cup_lump_id.production_weight",
        "weighing_cup_lump_id.reject_weight",
        "weighing_cup_lump_id.slab_weight",
        "weighing_cup_lump_id.shrinkage_tolerance_weight",
    )
    def _compute_stock_weight(self):
        for line in self:
            field_name = ProductType.STOCK_QUANTITY_FIELD.get(ProductType.CUP_LUMP)
            if not field_name or field_name not in line.weighing_cup_lump_id._fields:
                line.stock_weight = 0.0
                continue
            line.stock_weight = line.weighing_cup_lump_id[field_name] or 0.0

    @api.constrains("receipt_id", "weighing_cup_lump_id")
    def _check_unique_active_weighing(self):
        for line in self:
            if not line.weighing_cup_lump_id or not line.receipt_id:
                continue
            duplicate = self.search(
                [
                    ("id", "!=", line.id),
                    ("weighing_cup_lump_id", "=", line.weighing_cup_lump_id.id),
                    ("receipt_id.state", "!=", "cancelled"),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _("Weighing Cup Lump already exists in an active Production Receipt.")
                )

    def unlink(self):
        if self.filtered(lambda line: line.receipt_id.state == "validated"):
            raise ValidationError(
                _("Cannot release weighing from a validated Production Receipt.")
            )
        self._release_unvalidated_weighing()
        return super().unlink()

    def _release_unvalidated_weighing(self):
        lines_to_release = self.filtered(
            lambda line: line.receipt_id.state in ("draft", "processed")
            and line.weighing_cup_lump_id
            and line.weighing_cup_lump_id.production_receipt_id == line.receipt_id
            and line.weighing_cup_lump_id.receipt_status == "in_production_receipt"
        )
        weighings = lines_to_release.mapped("weighing_cup_lump_id")
        if weighings:
            weighings.with_context(allow_production_receipt_update=True).write(
                {
                    "receipt_status": "not_receipted",
                    "production_receipt_id": False,
                }
            )

    def _refresh_from_weighing(self):
        for line in self:
            line._compute_stock_weight()
