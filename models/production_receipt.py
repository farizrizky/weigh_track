# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..constants.roles import Role


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
    received_date = fields.Date(
        string="Received Date",
        required=True,
        default=lambda self: fields.Date.context_today(self),
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
    clerk_employee_id = fields.Many2one(
        "hr.employee",
        string="Clerk",
        ondelete="restrict",
        domain="[('id', 'in', allowed_clerk_employee_ids)]",
        tracking=True,
    )
    allowed_clerk_employee_ids = fields.Many2many(
        "hr.employee",
        compute="_compute_allowed_clerk_employee_ids",
        string="Allowed Clerk Employees",
    )
    allowed_product_ids = fields.Many2many(
        "product.product",
        compute="_compute_allowed_product_ids",
        string="Allowed Products",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        default=lambda self: self._configured_product_for_company(self.env.company),
        ondelete="restrict",
        domain="[('id', 'in', allowed_product_ids)]",
        index=True,
        tracking=True,
    )
    allowed_operation_type_ids = fields.Many2many(
        "stock.picking.type",
        compute="_compute_allowed_destination_ids",
        string="Allowed Operation Types",
    )
    allowed_warehouse_ids = fields.Many2many(
        "stock.warehouse",
        compute="_compute_allowed_warehouse_ids",
        string="Allowed Warehouses",
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Warehouse",
        required=True,
        ondelete="restrict",
        domain="[('id', 'in', allowed_warehouse_ids)]",
        index=True,
        tracking=True,
    )
    operation_type_id = fields.Many2one(
        "stock.picking.type",
        string="Operation Type",
        ondelete="restrict",
        domain="[('id', 'in', allowed_operation_type_ids)]",
        index=True,
        tracking=True,
    )
    allowed_location_ids = fields.Many2many(
        "stock.location",
        compute="_compute_allowed_destination_ids",
        string="Allowed Locations",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Receiving Location",
        ondelete="restrict",
        domain="[('id', 'in', allowed_location_ids)]",
        index=True,
        tracking=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot",
        readonly=True,
        copy=False,
        index=True,
        tracking=True,
    )
    stock_picking_id = fields.Many2one(
        "stock.picking",
        string="Inventory Receipt",
        readonly=True,
        copy=False,
        index=True,
    )
    reverse_picking_id = fields.Many2one(
        "stock.picking",
        string="Inventory Reversal",
        readonly=True,
        copy=False,
        index=True,
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
    lot_ids = fields.Many2many(
        "stock.lot",
        compute="_compute_stock_picking_count",
        string="Lots",
    )
    lot_count = fields.Integer(
        string="Lot Count",
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
    note = fields.Text(
        string="Note",
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

    def init(self):
        self.env.cr.execute(
            """
            DO $$
            BEGIN
                IF to_regclass('wt_division') IS NOT NULL
                AND EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'wt_production_receipt'
                        AND column_name = 'clerk_employee_id'
                ) THEN
                    UPDATE wt_production_receipt AS receipt
                    SET clerk_employee_id = division.clerk_id
                    FROM wt_division AS division
                    WHERE receipt.division_id = division.id
                        AND receipt.clerk_employee_id IS NULL
                        AND division.clerk_id IS NOT NULL;
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'wt_production_receipt'
                        AND column_name = 'received_date'
                ) THEN
                    UPDATE wt_production_receipt
                    SET received_date = COALESCE(production_date, CURRENT_DATE)
                    WHERE received_date IS NULL;
                END IF;

                IF to_regclass('wt_product') IS NOT NULL
                AND EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'wt_production_receipt'
                        AND column_name = 'product_id'
                ) THEN
                    UPDATE wt_production_receipt AS receipt
                    SET product_id = product_config.product_id
                    FROM wt_product AS product_config
                    WHERE receipt.product_id IS NULL
                        AND product_config.company_id = receipt.company_id
                        AND product_config.active IS TRUE;
                END IF;

                IF to_regclass('stock_picking') IS NOT NULL
                AND EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'wt_production_receipt'
                        AND column_name = 'stock_picking_id'
                ) THEN
                    UPDATE wt_production_receipt AS receipt
                    SET stock_picking_id = picking.id
                    FROM (
                        SELECT DISTINCT ON (production_receipt_id)
                            id,
                            production_receipt_id
                        FROM stock_picking
                        WHERE production_receipt_id IS NOT NULL
                            AND state != 'cancel'
                        ORDER BY production_receipt_id, id
                    ) AS picking
                    WHERE picking.production_receipt_id = receipt.id
                        AND receipt.stock_picking_id IS NULL;
                END IF;

                IF to_regclass('stock_picking') IS NOT NULL
                AND EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'wt_production_receipt'
                        AND column_name = 'reverse_picking_id'
                ) THEN
                    UPDATE wt_production_receipt AS receipt
                    SET reverse_picking_id = picking.id
                    FROM (
                        SELECT DISTINCT ON (production_receipt_reverse_id)
                            id,
                            production_receipt_reverse_id
                        FROM stock_picking
                        WHERE production_receipt_reverse_id IS NOT NULL
                            AND state != 'cancel'
                        ORDER BY production_receipt_reverse_id, id
                    ) AS picking
                    WHERE picking.production_receipt_reverse_id = receipt.id
                        AND receipt.reverse_picking_id IS NULL;
                END IF;

                IF to_regclass('wt_production_receipt_line') IS NOT NULL
                AND to_regclass('wt_weighing') IS NOT NULL
                AND to_regclass('wt_receipt_rule') IS NOT NULL
                AND EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'wt_production_receipt'
                        AND column_name = 'operation_type_id'
                )
                AND EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'wt_production_receipt'
                        AND column_name = 'warehouse_id'
                )
                AND EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'wt_production_receipt'
                        AND column_name = 'location_id'
                )
                AND EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'wt_production_receipt_line'
                        AND column_name = 'weighing_id'
                ) THEN
                    UPDATE wt_production_receipt AS receipt
                    SET warehouse_id = destination.warehouse_id,
                        operation_type_id = destination.operation_type_id,
                        location_id = destination.location_id
                    FROM (
                        SELECT DISTINCT ON (line.receipt_id)
                            line.receipt_id,
                            rule.warehouse_id,
                            rule.operation_type_id,
                            rule.location_id
                        FROM wt_production_receipt_line AS line
                        JOIN wt_weighing AS weighing
                            ON weighing.id = line.weighing_id
                        JOIN wt_receipt_rule AS rule
                            ON rule.id = weighing.receipt_rule_id
                        WHERE rule.operation_type_id IS NOT NULL
                            AND rule.location_id IS NOT NULL
                        ORDER BY line.receipt_id, line.id
                    ) AS destination
                    WHERE destination.receipt_id = receipt.id
                        AND (
                            receipt.warehouse_id IS NULL
                            OR
                            receipt.operation_type_id IS NULL
                            OR receipt.location_id IS NULL
                        );
                END IF;

                IF to_regclass('stock_picking') IS NOT NULL
                AND to_regclass('stock_move_line') IS NOT NULL
                AND EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'wt_production_receipt'
                        AND column_name = 'lot_id'
                ) THEN
                    UPDATE wt_production_receipt AS receipt
                    SET lot_id = lot_line.lot_id
                    FROM (
                        SELECT DISTINCT ON (picking.production_receipt_id)
                            picking.production_receipt_id,
                            move_line.lot_id
                        FROM stock_picking AS picking
                        JOIN stock_move_line AS move_line
                            ON move_line.picking_id = picking.id
                        WHERE picking.production_receipt_id IS NOT NULL
                            AND move_line.lot_id IS NOT NULL
                        ORDER BY picking.production_receipt_id, move_line.id
                    ) AS lot_line
                    WHERE lot_line.production_receipt_id = receipt.id
                        AND receipt.lot_id IS NULL;
                END IF;
            END $$;
            """
        )

    @api.model_create_multi
    def create(self, vals_list):
        sequence_model = self.env["ir.sequence"]
        for vals in vals_list:
            company = self.env["res.company"].browse(
                vals.get("company_id") or self.env.company.id
            )
            if not vals.get("product_id"):
                product = self._configured_product_for_company(company)
                if product:
                    vals["product_id"] = product.id
            if vals.get("division_id"):
                division = self.env["wt.division"].browse(vals["division_id"])
                vals["clerk_employee_id"] = division.clerk_id.id
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
            receipt.lot_ids = receipt.line_ids.mapped("lot_id") | receipt.lot_id
            receipt.lot_count = len(receipt.lot_ids)

    def write(self, vals):
        if vals.get("division_id"):
            vals = dict(vals)
            division = self.env["wt.division"].browse(vals["division_id"])
            vals["clerk_employee_id"] = division.clerk_id.id
        elif (
            "clerk_employee_id" in vals
            and not self.env.context.get("allow_production_receipt_clerk_update")
        ):
            raise ValidationError(
                _("Clerk on Production Receipt is determined by Division and cannot be changed manually.")
            )
        locked = self.filtered(lambda receipt: receipt.state == "validated")
        protected_fields = {
            "company_id",
            "production_date",
            "received_date",
            "division_id",
            "clerk_employee_id",
            "product_id",
            "warehouse_id",
            "operation_type_id",
            "location_id",
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

    @api.onchange("division_id")
    def _onchange_division_id(self):
        for receipt in self:
            receipt.clerk_employee_id = receipt.division_id.clerk_id
            receipt.warehouse_id = False
            receipt.operation_type_id = False
            receipt.location_id = False

    @api.onchange("company_id")
    def _onchange_company_id(self):
        for receipt in self:
            product = receipt._configured_product_for_company(receipt.company_id)
            receipt.product_id = product
            receipt.warehouse_id = False
            receipt.operation_type_id = False
            receipt.location_id = False

    @api.onchange("warehouse_id")
    def _onchange_warehouse_id(self):
        for receipt in self:
            receipt.operation_type_id = False
            receipt.location_id = False

    @api.onchange("operation_type_id")
    def _onchange_operation_type_id(self):
        for receipt in self:
            if receipt.location_id and receipt.location_id not in receipt.allowed_location_ids:
                receipt.location_id = False

    @api.depends("company_id")
    def _compute_allowed_clerk_employee_ids(self):
        mapping_model = self.env["wt.employee.role"]
        for receipt in self:
            receipt.allowed_clerk_employee_ids = mapping_model.get_allowed_employees(
                receipt.company_id,
                Role.CLERK,
            )

    @api.depends("company_id")
    def _compute_allowed_product_ids(self):
        product_config_model = self.env["wt.product"].sudo()
        for receipt in self:
            if not receipt.company_id:
                receipt.allowed_product_ids = self.env["product.product"].browse()
                continue
            receipt.allowed_product_ids = product_config_model.search(
                [
                    ("company_id", "=", receipt.company_id.id),
                    ("active", "=", True),
                ]
            ).mapped("product_id")

    @api.depends("company_id", "division_id")
    def _compute_allowed_warehouse_ids(self):
        receipt_rule_model = self.env["wt.receipt.rule"].sudo()
        warehouse_model = self.env["stock.warehouse"]
        for receipt in self:
            if not receipt.company_id or not receipt.division_id:
                receipt.allowed_warehouse_ids = warehouse_model.browse()
                continue
            rules = receipt_rule_model.search(
                [
                    ("active", "=", True),
                    ("company_id", "=", receipt.company_id.id),
                    ("division_id", "=", receipt.division_id.id),
                ]
            )
            receipt.allowed_warehouse_ids = rules.mapped("warehouse_id")

    @api.depends("company_id", "division_id", "warehouse_id", "operation_type_id")
    def _compute_allowed_destination_ids(self):
        receipt_rule_model = self.env["wt.receipt.rule"].sudo()
        for receipt in self:
            if not receipt.company_id or not receipt.division_id or not receipt.warehouse_id:
                receipt.allowed_operation_type_ids = self.env["stock.picking.type"].browse()
                receipt.allowed_location_ids = self.env["stock.location"].browse()
                continue

            rules = receipt_rule_model.search(
                [
                    ("active", "=", True),
                    ("company_id", "=", receipt.company_id.id),
                    ("division_id", "=", receipt.division_id.id),
                    ("warehouse_id", "=", receipt.warehouse_id.id),
                ]
            )
            receipt.allowed_operation_type_ids = rules.mapped("operation_type_id")

            location_rules = rules
            if receipt.operation_type_id:
                location_rules = rules.filtered(
                    lambda rule: rule.operation_type_id == receipt.operation_type_id
                )
            receipt.allowed_location_ids = location_rules.mapped("location_id")

    def _configured_product_for_company(self, company):
        if not company:
            return self.env["product.product"].browse()
        product_config = self.env["wt.product"].sudo().search(
            [
                ("company_id", "=", company.id),
                ("active", "=", True),
            ],
            limit=1,
        )
        return product_config.product_id

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

    @api.constrains("production_date", "received_date")
    def _check_received_date_not_before_production_date(self):
        for receipt in self:
            if (
                receipt.production_date
                and receipt.received_date
                and receipt.received_date < receipt.production_date
            ):
                raise ValidationError(
                    _("Received Date cannot be before Production Date.")
                )

    @api.constrains("company_id", "clerk_employee_id")
    def _check_clerk_employee(self):
        for receipt in self:
            self.env["wt.employee.role"].check_employee_allowed(
                receipt.clerk_employee_id,
                receipt.company_id,
                Role.CLERK,
                _("Clerk"),
            )

    @api.constrains("company_id", "product_id")
    def _check_product_configured(self):
        for receipt in self:
            if not receipt.company_id or not receipt.product_id:
                continue
            product_company = receipt.product_id.product_tmpl_id.company_id
            if product_company and product_company != receipt.company_id:
                raise ValidationError(
                    _("Product must belong to the same company or be a global product.")
                )
            configured_product = receipt._configured_product_for_company(
                receipt.company_id
            )
            if receipt.product_id != configured_product:
                raise ValidationError(
                    _("Product must match the active Weighing Product for the company.")
                )

    @api.constrains(
        "company_id",
        "division_id",
        "warehouse_id",
        "operation_type_id",
        "location_id",
    )
    def _check_inventory_destination(self):
        for receipt in self:
            if not (
                receipt.company_id
                and receipt.division_id
                and receipt.warehouse_id
            ):
                continue

            warehouse = receipt.warehouse_id
            if warehouse.company_id != receipt.company_id:
                raise ValidationError(
                    _("Warehouse must belong to the same company.")
                )
            if warehouse.estate_id and warehouse.estate_id != receipt.division_id.estate_id:
                raise ValidationError(
                    _("Warehouse must belong to the same estate as the division.")
                )

            operation_company = receipt.operation_type_id.company_id
            if (
                receipt.operation_type_id
                and operation_company
                and operation_company != receipt.company_id
            ):
                raise ValidationError(
                    _("Operation type must belong to the same company.")
                )
            if (
                receipt.operation_type_id
                and receipt.operation_type_id.warehouse_id
                and receipt.operation_type_id.warehouse_id != warehouse
            ):
                raise ValidationError(
                    _("Operation type must belong to the selected warehouse.")
                )

            location_company = receipt.location_id.company_id
            if (
                receipt.location_id
                and location_company
                and location_company != receipt.company_id
            ):
                raise ValidationError(
                    _("Receiving Location must belong to the same company or be a shared location.")
                )

            if receipt.location_id and receipt.location_id.usage != "internal":
                raise ValidationError(
                    _("Receiving Location must be an internal stock location.")
                )

            if (
                receipt.location_id
                and not receipt._is_location_under_warehouse(receipt.location_id, warehouse)
            ):
                raise ValidationError(
                    _("Receiving Location must be under the selected warehouse.")
                )

            if not receipt._matching_receipt_rules():
                raise ValidationError(
                    _(
                        "No active Receipt Rule exists for this Production Receipt scope."
                    )
                )

    def _matching_receipt_rules(self):
        self.ensure_one()
        if not (
            self.company_id
            and self.division_id
            and self.warehouse_id
        ):
            return self.env["wt.receipt.rule"].browse()
        domain = [
            ("active", "=", True),
            ("company_id", "=", self.company_id.id),
            ("division_id", "=", self.division_id.id),
            ("warehouse_id", "=", self.warehouse_id.id),
        ]
        if self.operation_type_id:
            domain.append(("operation_type_id", "=", self.operation_type_id.id))
        if self.location_id:
            domain.append(("location_id", "=", self.location_id.id))
        return self.env["wt.receipt.rule"].sudo().search(domain)

    def _is_location_under_warehouse(self, location, warehouse):
        warehouse_root = warehouse.view_location_id
        if not location or not warehouse_root:
            return True
        if location == warehouse_root:
            return True
        if location.parent_path and warehouse_root.parent_path:
            return location.parent_path.startswith(warehouse_root.parent_path)
        parent = location.parent_id
        while parent:
            if parent == warehouse_root:
                return True
            parent = parent.parent_id
        return False

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
        existing_weighing_ids = set(self.line_ids.mapped("weighing_id").ids)
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
                    "weighing_id": weighing.id,
                }
            )

        if new_weighings:
            new_weighings.with_context(
                allow_production_receipt_update=True
            ).write(
                {
                    "state": "in_production_receipt",
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
            ("received_date", _("Received Date")),
            ("division_id", _("Division")),
            ("clerk_employee_id", _("Clerk")),
            ("product_id", _("Product")),
            ("warehouse_id", _("Warehouse")),
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
        receipt_rules = self._matching_receipt_rules()
        if not receipt_rules:
            raise ValidationError(
                _(
                    "No active Receipt Rule exists for this Production Receipt destination."
                )
            )
        active_line_weighing_ids = self.env["wt.production.receipt.line"].search(
            [
                ("receipt_id.state", "!=", "cancelled"),
                ("receipt_id", "!=", self.id),
            ]
        ).mapped("weighing_id").ids
        domain = [
            ("company_id", "=", self.company_id.id),
            ("division_id", "=", self.division_id.id),
            ("production_date", "=", self.production_date),
            ("product_id", "=", self.product_id.id),
            ("receipt_rule_id", "in", receipt_rules.ids),
            ("id", "not in", active_line_weighing_ids or [0]),
        ]
        return self.env["wt.weighing"].search(domain)

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
        weighings = self.line_ids.mapped("weighing_id")
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
                "state": "receipt_validated",
                "production_receipt_id": self.id,
            }
        )

    def _check_line_consistency(self):
        self.ensure_one()
        invalid_lines = self.line_ids.filtered(
            lambda line: line.company_id != self.company_id
            or line.production_date != self.production_date
            or line.division_id != self.division_id
            or line.product_id != self.product_id
            or not line.receipt_rule_id
            or line.receipt_rule_id.warehouse_id != self.warehouse_id
            or (
                self.operation_type_id
                and line.receipt_rule_id.operation_type_id != self.operation_type_id
            )
            or (
                self.location_id
                and line.receipt_rule_id.location_id != self.location_id
            )
        )
        if invalid_lines:
            raise ValidationError(
                _("Production Receipt lines must match the header scope.")
            )

    def _check_duplicate_lines(self):
        self.ensure_one()
        weighing_ids = self.line_ids.mapped("weighing_id").ids
        if len(weighing_ids) != len(set(weighing_ids)):
            raise ValidationError(_("Production Receipt cannot have duplicate lines."))

    def _create_inventory_receipts(self):
        self.ensure_one()
        active_picking = self.stock_picking_ids.filtered(
            lambda picking: picking.state != "cancel"
        )
        if active_picking:
            raise ValidationError(
                _("Inventory Receipt already exists for this Production Receipt.")
            )

        clerk = self.clerk_employee_id
        if not clerk:
            raise ValidationError(
                _("Please set Clerk on this Production Receipt.")
            )

        for line in self.line_ids:
            if not line.receipt_rule_id:
                raise ValidationError(
                    _("Receipt Rule is missing on weighing '%s'.")
                    % line.weighing_id.display_name
                )
            if not line.product_id:
                raise ValidationError(
                    _("Product is missing on weighing '%s'.")
                    % line.weighing_id.display_name
                )
            if line.stock_weight <= 0:
                raise ValidationError(
                    _("Stock Weight must be greater than zero on weighing '%s'.")
                    % line.weighing_id.display_name
                )

        created_pickings = self.env["stock.picking"]
        for lines in self._group_lines_for_inventory_receipt().values():
            picking = self._create_inventory_receipt(clerk, lines)
            created_pickings |= picking
        return created_pickings

    def _group_lines_for_inventory_receipt(self):
        self.ensure_one()
        grouped_lines = {}
        for line in self.line_ids:
            rule = line.receipt_rule_id
            key = (
                rule.operation_type_id.id,
                rule.location_id.id,
                line.product_id.id,
            )
            grouped_lines.setdefault(key, self.env[line._name])
            grouped_lines[key] |= line
        return grouped_lines

    def _create_inventory_receipt(self, clerk, lines):
        self.ensure_one()
        product = lines[0].product_id
        if product.tracking != "lot":
            raise ValidationError(
                _("Product '%s' must use lot tracking before Production Receipt can create inventory lot.")
                % product.display_name
            )

        picking_type = lines[0].receipt_rule_id.operation_type_id
        destination_location = lines[0].receipt_rule_id.location_id
        source_location = self._get_receipt_source_location(picking_type)
        total_quantity = sum(lines.mapped("stock_weight"))
        lot = self._get_or_create_inventory_lot(product, destination_location)
        partner = self._get_employee_partner(clerk)
        received_datetime = self._get_received_datetime()

        picking_model = self.env["stock.picking"].sudo().with_company(self.company_id)
        move_values = {
            "product_id": product.id,
            "product_uom_qty": total_quantity,
            "product_uom": product.uom_id.id,
            "location_id": source_location.id,
            "location_dest_id": destination_location.id,
        }
        if received_datetime and "date" in self.env["stock.move"]._fields:
            move_values["date"] = received_datetime
        picking_values = {
            "picking_type_id": picking_type.id,
            "partner_id": partner.id if partner else False,
            "receive_from_employee_id": clerk.id,
            "location_id": source_location.id,
            "location_dest_id": destination_location.id,
            "origin": self.name,
            "production_receipt_id": self.id,
            "move_ids": [(0, 0, move_values)],
        }
        if received_datetime and "scheduled_date" in picking_model._fields:
            picking_values["scheduled_date"] = received_datetime
        picking = picking_model.create(picking_values)
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
        self._sync_inventory_receipt_dates(picking, received_datetime)
        if picking.state != "done":
            raise ValidationError(
                _("Inventory Receipt '%s' could not be validated automatically.")
                % picking.display_name
            )
        lines.write(
            {
                "stock_picking_id": picking.id,
                "lot_id": lot.id,
            }
        )
        self.with_context(allow_production_receipt_update=True).write(
            {"stock_picking_id": picking.id}
        )
        return picking

    def _get_received_datetime(self):
        self.ensure_one()
        received_date = fields.Date.to_date(self.received_date)
        if not received_date:
            return False
        return fields.Datetime.to_datetime(received_date)

    def _sync_inventory_receipt_dates(self, picking, received_datetime):
        if not received_datetime:
            return
        values = {}
        if "scheduled_date" in picking._fields:
            values["scheduled_date"] = received_datetime
        if "date_done" in picking._fields:
            values["date_done"] = received_datetime
        if values:
            picking.sudo().write(values)

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

    def _get_or_create_inventory_lot(self, product, destination_location):
        self.ensure_one()
        lot_model = self.env["stock.lot"].sudo().with_company(self.company_id)
        lot = lot_model.search(
            [
                ("product_id", "=", product.id),
                ("company_id", "in", [False, self.company_id.id]),
                ("division_id", "=", self.division_id.id),
                ("production_date", "=", self.production_date),
                ("wt_receiving_location_id", "=", destination_location.id),
            ],
            order="id",
            limit=1,
        )
        if lot:
            return lot
        return self._create_inventory_lot(product, destination_location)

    def _create_inventory_lot(self, product, destination_location):
        self.ensure_one()
        lot_name = self._get_inventory_lot_name(product)
        lot_model = self.env["stock.lot"].sudo().with_company(self.company_id)
        return lot_model.create(
            {
                "name": lot_name,
                "product_id": product.id,
                "company_id": self.company_id.id,
                "wt_lot_type": "production",
                "division_id": self.division_id.id,
                "production_date": self.production_date,
                "wt_receiving_location_id": destination_location.id,
            }
        )

    def _get_inventory_lot_name(self, product):
        self.ensure_one()
        prefix = self._get_inventory_lot_prefix()
        next_number = self._get_next_inventory_lot_number(product, prefix)
        return "%s%03d" % (prefix, next_number)

    def _get_inventory_lot_prefix(self):
        self.ensure_one()
        division_code = self._clean_lot_component(self.division_id.code)
        production_date = fields.Date.to_date(self.production_date).strftime("%Y%m%d")
        return "LOT/%s/%s/" % (division_code, production_date)

    def _get_next_inventory_lot_number(self, product, prefix):
        self.ensure_one()
        lot_model = self.env["stock.lot"].sudo().with_company(self.company_id)
        lots = lot_model.search(
            [
                ("name", "=like", prefix + "%"),
                ("product_id", "=", product.id),
                ("company_id", "in", [False, self.company_id.id]),
            ],
            order="name desc",
        )
        last_number = 0
        prefix_length = len(prefix)
        for lot in lots:
            suffix = lot.name[prefix_length:]
            if suffix.isdigit():
                last_number = max(last_number, int(suffix))
        next_number = last_number + 1
        if next_number > 999:
            raise ValidationError(
                _("Inventory lot sequence for '%s' has reached the 999 limit.")
                % prefix.rstrip("/")
            )
        return next_number

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
        self.ensure_one()
        if self.state == "cancelled":
            return False
        if self.state != "validated":
            raise ValidationError(
                _("Only validated Production Receipt can be cancelled.")
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Cancel Production Receipt"),
            "res_model": "wt.production.receipt.cancel.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_receipt_id": self.id,
            },
        }

    def action_confirm_cancel(self, reason):
        if not reason:
            raise ValidationError(_("Cancel reason is required."))
        for receipt in self:
            if receipt.state == "cancelled":
                continue
            if receipt.state != "validated":
                raise ValidationError(
                    _("Only validated Production Receipt can be cancelled.")
                )
            receipt._create_inventory_reversals()
            receipt.line_ids.mapped("weighing_id").with_context(
                allow_production_receipt_update=True
            ).write({"state": "receipt_cancelled"})
            receipt.with_context(allow_production_receipt_update=True).write(
                {
                    "state": "cancelled",
                    "cancelled_at": fields.Datetime.now(),
                    "cancelled_by_id": self.env.user.id,
                    "cancel_reason": reason,
                }
            )

    def _create_inventory_reversals(self):
        self.ensure_one()
        original_pickings = self.stock_picking_ids.filtered(
            lambda picking: picking.state == "done"
        )
        if not original_pickings:
            return self.env["stock.picking"]
        active_reversal = self.reverse_picking_ids.filtered(
            lambda picking: picking.state != "cancel"
        )
        if active_reversal:
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
        self.line_ids.filtered(lambda line: line.stock_picking_id == picking).write(
            {"reverse_picking_id": reversal.id}
        )
        self.with_context(allow_production_receipt_update=True).write(
            {"reverse_picking_id": reversal.id}
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

    def action_view_inventory_receipts(self):
        self.ensure_one()
        return self._get_related_action(
            _("Inventory Receipts"),
            "stock.picking",
            self.stock_picking_ids.ids,
        )

    def action_view_inventory_reversals(self):
        self.ensure_one()
        return self._get_related_action(
            _("Inventory Reversals"),
            "stock.picking",
            self.reverse_picking_ids.ids,
        )

    def action_view_lots(self):
        self.ensure_one()
        return self._get_related_action(
            _("Lots"),
            "stock.lot",
            self.lot_ids.ids,
        )

    def _get_related_action(self, name, model, record_ids):
        action = {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": model,
            "view_mode": "list,form",
            "domain": [("id", "in", record_ids or [0])],
            "context": {"create": False},
        }
        if len(record_ids) == 1:
            action.update(
                {
                    "view_mode": "form",
                    "res_id": record_ids[0],
                }
            )
        return action


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
    weighing_id = fields.Many2one(
        "wt.weighing",
        string="Weighing",
        required=True,
        ondelete="restrict",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="weighing_id.company_id",
        store=True,
        readonly=True,
    )
    production_date = fields.Date(
        string="Production Date",
        related="weighing_id.production_date",
        store=True,
        readonly=True,
    )
    weighing_date = fields.Datetime(
        string="Weighing Date",
        related="weighing_id.weighing_date",
        store=True,
        readonly=True,
    )
    estate_id = fields.Many2one(
        "wt.estate",
        string="Estate",
        related="weighing_id.estate_id",
        store=True,
        readonly=True,
    )
    weighing_location_id = fields.Many2one(
        "wt.weighing.location",
        string="Weighing Location",
        related="weighing_id.weighing_location_id",
        store=True,
        readonly=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Division",
        related="weighing_id.division_id",
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        related="weighing_id.product_id",
        store=True,
        readonly=True,
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="UoM",
        related="weighing_id.uom_id",
        store=True,
        readonly=True,
    )
    receipt_rule_id = fields.Many2one(
        "wt.receipt.rule",
        string="Receipt Rule",
        related="weighing_id.receipt_rule_id",
        store=True,
        readonly=True,
    )
    operator_employee_id = fields.Many2one(
        "hr.employee",
        string="Operator",
        related="weighing_id.operator_employee_id",
        store=True,
        readonly=True,
    )
    clerk_employee_id = fields.Many2one(
        "hr.employee",
        string="Clerk",
        related="weighing_id.clerk_employee_id",
        store=True,
        readonly=True,
    )
    foreman_employee_id = fields.Many2one(
        "hr.employee",
        string="Foreman",
        related="weighing_id.foreman_employee_id",
        store=True,
        readonly=True,
    )
    tapper_employee_id = fields.Many2one(
        "hr.employee",
        string="Tapper",
        related="weighing_id.tapper_employee_id",
        store=True,
        readonly=True,
    )
    total_bag = fields.Integer(
        string="Total Bag",
        related="weighing_id.total_bag",
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
        related="weighing_id.has_data_problem",
        store=True,
        readonly=True,
    )
    data_problem_code = fields.Selection(
        related="weighing_id.data_problem_code",
        store=True,
        readonly=True,
    )
    data_problem_note = fields.Text(
        string="Data Problem Note",
        related="weighing_id.data_problem_note",
        readonly=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Warehouse",
        related="receipt_rule_id.warehouse_id",
        store=True,
        readonly=True,
    )
    operation_type_id = fields.Many2one(
        "stock.picking.type",
        string="Operation Type",
        related="receipt_rule_id.operation_type_id",
        store=True,
        readonly=True,
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Receiving Location",
        related="receipt_rule_id.location_id",
        store=True,
        readonly=True,
    )
    stock_picking_id = fields.Many2one(
        "stock.picking",
        string="Inventory Receipt",
        readonly=True,
        copy=False,
        index=True,
    )
    reverse_picking_id = fields.Many2one(
        "stock.picking",
        string="Inventory Reversal",
        readonly=True,
        copy=False,
        index=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot",
        readonly=True,
        copy=False,
        index=True,
    )

    @api.depends(
        "weighing_id",
        "weighing_id.net_weight",
        "weighing_id.production_weight",
        "weighing_id.reject_weight",
        "weighing_id.slab_weight",
        "weighing_id.shrinkage_tolerance_weight",
    )
    def _compute_stock_weight(self):
        for line in self:
            line.stock_weight = line.weighing_id.net_weight or 0.0

    @api.constrains("receipt_id", "weighing_id")
    def _check_unique_active_weighing(self):
        for line in self:
            if not line.weighing_id or not line.receipt_id:
                continue
            duplicate = self.search(
                [
                    ("id", "!=", line.id),
                    ("weighing_id", "=", line.weighing_id.id),
                    ("receipt_id.state", "!=", "cancelled"),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _("Weighing already exists in an active Production Receipt.")
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
            and line.weighing_id
            and line.weighing_id.production_receipt_id == line.receipt_id
            and line.weighing_id.state == "in_production_receipt"
        )
        weighings = lines_to_release.mapped("weighing_id")
        if weighings:
            weighings.with_context(allow_production_receipt_update=True).write(
                {
                    "state": "not_receipted",
                    "production_receipt_id": False,
                }
            )

    def _refresh_from_weighing(self):
        for line in self:
            line._compute_stock_weight()
