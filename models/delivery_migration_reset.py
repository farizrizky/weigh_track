# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class StockMoveMigrationReset(models.Model):
    _inherit = "stock.move"

    wt_is_migration_reset = fields.Boolean(
        string="Migration Reset Movement",
        default=False,
        readonly=True,
        copy=False,
        index=True,
    )
    wt_migration_reset_log_id = fields.Many2one(
        "wt.delivery.migration.reset.log",
        string="Delivery Migration Reset",
        readonly=True,
        copy=False,
        index=True,
        ondelete="restrict",
    )
    wt_migration_reset_role = fields.Selection(
        [
            ("original", "Original Movement"),
            ("reversal", "Reversal Movement"),
        ],
        string="Migration Reset Role",
        readonly=True,
        copy=False,
        index=True,
    )


class StockPickingMigrationReset(models.Model):
    _inherit = "stock.picking"

    wt_is_migration_reset = fields.Boolean(
        string="Migration Reset Transfer",
        default=False,
        readonly=True,
        copy=False,
        index=True,
    )
    wt_migration_reset_log_id = fields.Many2one(
        "wt.delivery.migration.reset.log",
        string="Delivery Migration Reset",
        readonly=True,
        copy=False,
        index=True,
        ondelete="restrict",
    )


class StockLotMigrationReset(models.Model):
    _inherit = "stock.lot"

    wt_is_migration_reset = fields.Boolean(
        string="Migration Reset Lot",
        default=False,
        readonly=True,
        copy=False,
        index=True,
    )
    wt_migration_reset_log_id = fields.Many2one(
        "wt.delivery.migration.reset.log",
        string="Delivery Migration Reset",
        readonly=True,
        copy=False,
        index=True,
        ondelete="restrict",
    )


class DeliveryMigrationResetLog(models.Model):
    _name = "wt.delivery.migration.reset.log"
    _description = "Delivery Migration Reset Log"
    _order = "reset_at desc, id desc"

    name = fields.Char(
        string="Reset Number",
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _("New"),
    )
    delivery_id = fields.Many2one(
        "wt.delivery",
        string="Delivery Task",
        required=True,
        readonly=True,
        index=True,
        ondelete="restrict",
    )
    delivery_name = fields.Char(
        string="Delivery Number",
        required=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        readonly=True,
        index=True,
    )
    reset_by_id = fields.Many2one(
        "res.users",
        string="Reset By",
        required=True,
        readonly=True,
        default=lambda self: self.env.user,
    )
    reset_at = fields.Datetime(
        string="Reset At",
        required=True,
        readonly=True,
        default=fields.Datetime.now,
    )
    reason = fields.Text(
        string="Reset Reason",
        required=True,
        readonly=True,
    )
    original_state = fields.Selection(
        selection=lambda self: self.env["wt.delivery"]._fields["state"].selection,
        string="Original Status",
        required=True,
        readonly=True,
    )
    movement_count = fields.Integer(
        string="Original Movement Count",
        readonly=True,
    )
    reversal_movement_count = fields.Integer(
        string="Reversal Movement Count",
        readonly=True,
    )
    picking_count = fields.Integer(
        string="Transfer Count",
        readonly=True,
    )
    transit_lot_count = fields.Integer(
        string="Transit Lot Count",
        readonly=True,
    )
    shrinkage_quantity = fields.Float(
        string="Restored Shrinkage",
        readonly=True,
        digits="Product Unit of Measure",
    )
    total_reversed_quantity = fields.Float(
        string="Total Reversed Quantity",
        readonly=True,
        digits="Product Unit of Measure",
    )
    stock_snapshot_before = fields.Json(
        string="Stock Snapshot Before Reset",
        readonly=True,
    )
    stock_snapshot_after = fields.Json(
        string="Stock Snapshot After Reset",
        readonly=True,
    )
    move_ids = fields.One2many(
        "stock.move",
        "wt_migration_reset_log_id",
        string="Related Movements",
        readonly=True,
    )
    picking_ids = fields.One2many(
        "stock.picking",
        "wt_migration_reset_log_id",
        string="Related Transfers",
        readonly=True,
    )
    transit_lot_ids = fields.One2many(
        "stock.lot",
        "wt_migration_reset_log_id",
        string="Related Transit Lots",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get("name", _("New")) == _("New"):
                values["name"] = (
                    self.env["ir.sequence"].next_by_code(
                        "wt.delivery.migration.reset"
                    )
                    or _("New")
                )
        return super().create(vals_list)


class DeliveryMigrationReset(models.Model):
    _inherit = "wt.delivery"

    migration_reset_log_ids = fields.One2many(
        "wt.delivery.migration.reset.log",
        "delivery_id",
        string="Migration Reset Logs",
        readonly=True,
    )
    migration_reset_count = fields.Integer(
        string="Migration Reset Count",
        compute="_compute_migration_reset_count",
    )

    @api.depends("migration_reset_log_ids")
    def _compute_migration_reset_count(self):
        for delivery in self:
            delivery.migration_reset_count = len(delivery.migration_reset_log_ids)

    def action_view_migration_reset_logs(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "weightrack.action_wt_delivery_migration_reset_log"
        )
        action["domain"] = [("delivery_id", "=", self.id)]
        action["context"] = {"default_delivery_id": self.id}
        return action

    def action_open_migration_reset(self):
        self.ensure_one()
        self._check_migration_reset_allowed()
        return {
            "name": _("Reset Delivery for Migration"),
            "type": "ir.actions.act_window",
            "res_model": "wt.delivery.migration.reset.wizard",
            "view_mode": "form",
            "view_id": self.env.ref(
                "weightrack.view_wt_delivery_migration_reset_wizard_form"
            ).id,
            "target": "new",
            "context": {
                "default_delivery_id": self.id,
            },
        }

    def _check_migration_reset_allowed(self):
        self.ensure_one()
        if not self.env.user.has_group("weightrack.group_admin"):
            raise ValidationError(
                _("Only a WeighTrack Administrator can reset a delivery for migration.")
            )
        if self.state != "done":
            raise ValidationError(
                _("Only a completed delivery can be reset for migration.")
            )
        if self.wt_is_returned:
            raise ValidationError(
                _(
                    "A returned delivery cannot be reset for migration. "
                    "Review its return movements first."
                )
            )

    def _get_migration_reset_original_pickings(self):
        self.ensure_one()
        return self.picking_ids.filtered(
            lambda picking: picking.state == "done"
            and not picking.wt_is_migration_reset
        )

    def _get_migration_reset_original_moves(self):
        self.ensure_one()
        pickings = self._get_migration_reset_original_pickings()
        moves = pickings.move_ids.filtered(
            lambda move: move.state == "done"
            and not move.wt_is_migration_reset
        )
        standalone_moves = self.env["stock.move"].sudo().search(
            [
                ("company_id", "=", self.company_id.id),
                ("origin", "=", self.name),
                ("picking_id", "=", False),
                ("state", "=", "done"),
                ("wt_is_migration_reset", "=", False),
            ]
        )
        return moves | standalone_moves

    def _get_migration_reset_transit_lots(self):
        self.ensure_one()
        return self.do_line_ids.mapped("generated_transit_lot_id").filtered(
            lambda lot: not lot.wt_is_migration_reset
        )

    def _check_migration_reset_dependencies(self, moves, transit_lots):
        self.ensure_one()
        if not moves:
            raise ValidationError(
                _("No completed stock movement was found for this delivery.")
            )
        move_lines = moves.move_line_ids.filtered(lambda line: line.quantity > 0.0)
        missing_lot_lines = move_lines.filtered(lambda line: not line.lot_id)
        if missing_lot_lines:
            raise ValidationError(
                _(
                    "Migration reset cannot continue because some delivery movements "
                    "do not contain a lot number."
                )
            )
        packaged_lines = move_lines.filtered(
            lambda line: line.package_id or line.result_package_id or line.owner_id
        )
        if packaged_lines:
            raise ValidationError(
                _(
                    "Migration reset does not support owner or package movements. "
                    "Remove the package dependency before resetting this delivery."
                )
            )
        if transit_lots:
            external_lines = self.env["stock.move.line"].sudo().search(
                [
                    ("lot_id", "in", transit_lots.ids),
                    ("move_id.state", "=", "done"),
                    ("move_id", "not in", moves.ids),
                    ("move_id.wt_is_migration_reset", "=", False),
                    ("quantity", ">", 0.0),
                ],
                limit=1,
            )
            if external_lines:
                raise ValidationError(
                    _(
                        "Transit lot %(lot)s has been used by another stock movement "
                        "(%(movement)s). Reset that downstream transaction first."
                    )
                    % {
                        "lot": external_lines.lot_id.display_name,
                        "movement": external_lines.move_id.display_name,
                    }
                )

    def _get_quant_quantity(self, product, location, lot):
        self.ensure_one()
        quants = self.env["stock.quant"].sudo().search(
            [
                ("product_id", "=", product.id),
                ("location_id", "=", location.id),
                ("lot_id", "=", lot.id),
            ]
        )
        return sum(quants.mapped("quantity"))

    def _prepare_migration_reset_quantities(self, move_lines):
        self.ensure_one()
        balances = {}
        records = {}

        def get_key(line, location):
            key = (line.product_id.id, location.id, line.lot_id.id)
            records[key] = (line.product_id, location, line.lot_id)
            if key not in balances:
                balances[key] = self._get_quant_quantity(
                    line.product_id,
                    location,
                    line.lot_id,
                )
            return key

        ordered_lines = move_lines.sorted(lambda line: line.id, reverse=True)
        for line in ordered_lines:
            quantity = line.quantity or 0.0
            if quantity <= 0.0:
                continue
            reverse_source_key = get_key(line, line.location_dest_id)
            reverse_destination_key = get_key(line, line.location_id)
            rounding = line.product_id.uom_id.rounding
            if (
                float_compare(
                    balances[reverse_source_key],
                    quantity,
                    precision_rounding=rounding,
                )
                < 0
            ):
                product, location, lot = records[reverse_source_key]
                raise ValidationError(
                    _(
                        "Stock is no longer sufficient to reverse delivery %(delivery)s.\n"
                        "Lot: %(lot)s\n"
                        "Location: %(location)s\n"
                        "Required: %(required).4f\n"
                        "Available: %(available).4f"
                    )
                    % {
                        "delivery": self.name,
                        "lot": lot.display_name,
                        "location": location.display_name,
                        "required": quantity,
                        "available": balances[reverse_source_key],
                    }
                )
            balances[reverse_source_key] -= quantity
            balances[reverse_destination_key] += quantity

        return ordered_lines, balances, records

    def _snapshot_migration_reset_quantities(self, balances, records):
        values = []
        for key in sorted(balances):
            product, location, lot = records[key]
            values.append(
                {
                    "product_id": product.id,
                    "product": product.display_name,
                    "location_id": location.id,
                    "location": location.display_name,
                    "lot_id": lot.id,
                    "lot": lot.display_name,
                    "quantity": balances[key],
                }
            )
        return values

    def _create_migration_reset_reversal_move(self, move_line, reset_log):
        self.ensure_one()
        quantity = move_line.quantity or 0.0
        move_values = {
            "description_picking": _(
                "Migration reset %(reset)s: %(movement)s"
            )
            % {
                "reset": reset_log.name,
                "movement": move_line.move_id.display_name,
            },
            "inventory_name": _("Delivery Migration Reset"),
            "state": "confirmed",
            "picked": True,
            "is_inventory": move_line.move_id.is_inventory,
            "product_id": move_line.product_id.id,
            "product_uom": move_line.product_uom_id.id,
            "product_uom_qty": quantity,
            "location_id": move_line.location_dest_id.id,
            "location_dest_id": move_line.location_id.id,
            "company_id": self.company_id.id,
            "origin": reset_log.name,
            "origin_returned_move_id": move_line.move_id.id,
            "wt_is_migration_reset": True,
            "wt_migration_reset_log_id": reset_log.id,
            "wt_migration_reset_role": "reversal",
            "move_line_ids": [
                (
                    0,
                    0,
                    {
                        "product_id": move_line.product_id.id,
                        "product_uom_id": move_line.product_uom_id.id,
                        "quantity": quantity,
                        "picked": True,
                        "lot_id": move_line.lot_id.id,
                        "location_id": move_line.location_dest_id.id,
                        "location_dest_id": move_line.location_id.id,
                        "company_id": self.company_id.id,
                    },
                )
            ],
        }
        if "to_refund" in self.env["stock.move"]._fields:
            move_values["to_refund"] = True
        reverse_move = (
            self.env["stock.move"]
            .sudo()
            .with_company(self.company_id)
            .create(move_values)
        )
        reverse_move.with_context(
            inventory_mode=False,
            tracking_disable=True,
            mail_notrack=True,
            ignore_dest_packages=True,
        )._action_done()
        return reverse_move

    def _verify_migration_reset_quantities(self, expected_balances, records):
        self.ensure_one()
        mismatches = []
        for key, expected_quantity in expected_balances.items():
            product, location, lot = records[key]
            actual_quantity = self._get_quant_quantity(product, location, lot)
            if (
                float_compare(
                    actual_quantity,
                    expected_quantity,
                    precision_rounding=product.uom_id.rounding,
                )
                != 0
            ):
                mismatches.append(
                    _(
                        "%(lot)s at %(location)s: expected %(expected).4f, "
                        "actual %(actual).4f"
                    )
                    % {
                        "lot": lot.display_name,
                        "location": location.display_name,
                        "expected": expected_quantity,
                        "actual": actual_quantity,
                    }
                )
        if mismatches:
            raise ValidationError(
                _("Stock verification failed after migration reset:\n%s")
                % "\n".join(mismatches)
            )

    def _reset_migration_delivery_data(self, transit_lots, reset_log):
        self.ensure_one()
        all_lot_lines = self.do_line_ids.mapped("lot_line_ids")
        transit_lot_lines = all_lot_lines.filtered(
            lambda line: line.lot_id in transit_lots
        )
        source_lot_lines = all_lot_lines - transit_lot_lines

        self.do_line_ids.sudo().write(
            {
                "picking_id": False,
                "return_picking_id": False,
                "generated_transit_lot_id": False,
            }
        )
        all_lot_lines.mapped("wt_allocation_ids").sudo().unlink()
        if transit_lot_lines:
            transit_lot_lines.sudo().unlink()
        for line in source_lot_lines:
            line.sudo().write(
                {
                    "qty": line.wt_original_qty or line.qty,
                    "wt_physical_qty": 0.0,
                    "wt_weighed_at": False,
                    "wt_note": False,
                    "wt_weighing_source": False,
                    "wt_manual_input_by_id": False,
                    "wt_manual_input_at": False,
                    "wt_manual_reason": False,
                    "wt_adjustment_applied": False,
                    "wt_is_pulled": False,
                }
            )

        if transit_lots:
            transit_values = {
                "wt_is_migration_reset": True,
                "wt_migration_reset_log_id": reset_log.id,
                "wt_transit_state": "closed",
            }
            if "active" in transit_lots._fields:
                transit_values["active"] = False
            transit_lots.sudo().write(transit_values)

        original_pickings = reset_log.picking_ids
        original_pickings.sudo().write(
            {
                "wt_delivery_id": False,
            }
        )
        self.sudo().write(
            {
                "state": "draft",
                "final_picking_id": False,
                "validated_at": False,
                "validated_by_id": False,
                "wt_is_returned": False,
                "wt_return_reason": False,
                "backdate_effective_at": False,
                "backdate_applied_at": False,
                "backdate_applied_by_id": False,
            }
        )

    def _invalidate_migration_reset_reports(self):
        self.ensure_one()
        transient_report_models = (
            "wt.storage.shrinkage.report",
            "wt.stock.out.report",
            "wt.shipping.report",
            "wt.daily.stock.report",
        )
        for model_name in transient_report_models:
            model = self.env[model_name].sudo()
            if "company_id" in model._fields:
                model.search([("company_id", "=", self.company_id.id)]).unlink()

        analysis_domain = [("company_id", "=", self.company_id.id)]
        if self.date:
            analysis_domain.append(("report_date", ">=", self.date))
        self.env["wt.daily.stock.analysis"].sudo().search(analysis_domain).unlink()

    def _action_migration_reset(self, reason):
        self.ensure_one()
        self._check_migration_reset_allowed()
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError(_("Reset reason is required."))

        self.env.cr.execute(
            "SELECT id FROM wt_delivery WHERE id = %s FOR UPDATE",
            [self.id],
        )
        original_pickings = self._get_migration_reset_original_pickings()
        original_moves = self._get_migration_reset_original_moves()
        transit_lots = self._get_migration_reset_transit_lots()
        self._check_migration_reset_dependencies(original_moves, transit_lots)

        move_lines = original_moves.move_line_ids.filtered(
            lambda line: line.quantity > 0.0
        )
        ordered_lines, expected_balances, balance_records = (
            self._prepare_migration_reset_quantities(move_lines)
        )
        before_balances = {
            key: self._get_quant_quantity(*balance_records[key])
            for key in balance_records
        }
        shrinkage_location = self.env.ref(
            "weightrack.stock_location_wt_inventory_loss_susut",
            raise_if_not_found=False,
        )
        shrinkage_location_ids = set()
        if shrinkage_location:
            shrinkage_location_ids = set(
                self.env["stock.location"].sudo().search(
                    [("id", "child_of", shrinkage_location.id)]
                ).ids
            )
        shrinkage_quantity = sum(
            line.quantity
            for line in move_lines
            if line.location_dest_id.id in shrinkage_location_ids
            and not self.do_line_ids.filtered(
                lambda route_line: route_line.generated_transit_lot_id
                and route_line.picking_id == line.picking_id
            )
        )

        reset_log = self.env["wt.delivery.migration.reset.log"].sudo().create(
            {
                "delivery_id": self.id,
                "delivery_name": self.name,
                "company_id": self.company_id.id,
                "reset_by_id": self.env.user.id,
                "reset_at": fields.Datetime.now(),
                "reason": reason,
                "original_state": self.state,
                "movement_count": len(original_moves),
                "picking_count": len(original_pickings),
                "transit_lot_count": len(transit_lots),
                "shrinkage_quantity": shrinkage_quantity,
                "total_reversed_quantity": sum(move_lines.mapped("quantity")),
                "stock_snapshot_before": self._snapshot_migration_reset_quantities(
                    before_balances,
                    balance_records,
                ),
            }
        )
        original_moves.sudo().write(
            {
                "wt_is_migration_reset": True,
                "wt_migration_reset_log_id": reset_log.id,
                "wt_migration_reset_role": "original",
            }
        )
        original_pickings.sudo().write(
            {
                "wt_is_migration_reset": True,
                "wt_migration_reset_log_id": reset_log.id,
            }
        )

        reversal_moves = self.env["stock.move"]
        for move_line in ordered_lines:
            reversal_moves |= self._create_migration_reset_reversal_move(
                move_line,
                reset_log,
            )

        self._verify_migration_reset_quantities(
            expected_balances,
            balance_records,
        )
        reset_log.sudo().write(
            {
                "reversal_movement_count": len(reversal_moves),
                "stock_snapshot_after": (
                    self._snapshot_migration_reset_quantities(
                        expected_balances,
                        balance_records,
                    )
                ),
            }
        )
        self._reset_migration_delivery_data(transit_lots, reset_log)
        self._invalidate_migration_reset_reports()
        self.message_post(
            body=_(
                "<b>Delivery Migration Reset Completed</b><br/>"
                "Reset Number: %(reset)s<br/>"
                "Reason: %(reason)s<br/>"
                "%(movement_count)s original movements were reversed and excluded "
                "from WeighTrack reports."
            )
            % {
                "reset": reset_log.name,
                "reason": reason,
                "movement_count": len(original_moves),
            }
        )
        return reset_log
