# -*- coding: utf-8 -*-

from datetime import datetime, time

from pytz import UTC, timezone

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class StockMove(models.Model):
    _inherit = "stock.move"

    wt_inventory_lot_names = fields.Char(
        string="Lot/Serial Numbers",
        compute="_compute_wt_inventory_selection_info",
    )
    wt_inventory_done_quantity = fields.Float(
        string="Done Quantity",
        compute="_compute_wt_inventory_selection_info",
        digits="Product Unit of Measure",
    )

    @api.depends("move_line_ids.lot_id", "move_line_ids.quantity")
    def _compute_wt_inventory_selection_info(self):
        for move in self:
            move.wt_inventory_lot_names = ", ".join(
                move.move_line_ids.mapped("lot_id.name")
            )
            move.wt_inventory_done_quantity = sum(
                move.move_line_ids.mapped("quantity")
            )


class StockMovementDateCorrection(models.Model):
    _name = "wt.stock.movement.date.correction"
    _description = "Stock Movement Date Correction"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "applied_at desc, id desc"

    name = fields.Char(string="Number", required=True, readonly=True, copy=False, default=lambda self: _("New"))
    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company, index=True, tracking=True,
    )
    source_type = fields.Selection(
        [
            ("delivery", "Delivery Order"),
            ("production_receipt", "Production Receipt"),
            ("stock_opname", "Stock Opname"),
            ("inventory_adjustment", "Stock Adjustment"),
        ],
        string="Source Type", required=True, tracking=True,
    )
    delivery_id = fields.Many2one(
        "wt.delivery", string="Delivery Order", ondelete="restrict", tracking=True,
    )
    production_receipt_id = fields.Many2one(
        "wt.production.receipt", string="Production Receipt",
        ondelete="restrict", tracking=True,
    )
    stock_opname_id = fields.Many2one(
        "wt.stock.opname", string="Stock Opname", ondelete="restrict", tracking=True,
    )
    inventory_adjustment_move_ids = fields.Many2many(
        "stock.move", "wt_stock_date_correction_inventory_move_rel",
        "correction_id", "move_id", string="Stock Adjustment Movements",
        copy=False, tracking=True,
    )
    inventory_reference = fields.Char(
        string="Inventory Reference",
        compute="_compute_inventory_reference",
        store=True,
    )
    old_date = fields.Date(string="Previous Date", readonly=True, copy=False, tracking=True)
    effective_date = fields.Date(string="New Effective Date", required=True, tracking=True)
    reason = fields.Text(string="Correction Reason", required=True, tracking=True)
    picking_ids = fields.Many2many(
        "stock.picking", "wt_stock_date_correction_picking_rel",
        "correction_id", "picking_id", string="Affected Transfers",
        readonly=True, copy=False,
    )
    move_ids = fields.Many2many(
        "stock.move", "wt_stock_date_correction_move_rel",
        "correction_id", "move_id", string="Affected Stock Movements",
        readonly=True, copy=False,
    )
    picking_count = fields.Integer(string="Transfer Count", compute="_compute_counts")
    move_count = fields.Integer(string="Stock Movement Count", compute="_compute_counts")
    state = fields.Selection(
        [("draft", "Draft"), ("applied", "Applied"), ("cancelled", "Cancelled")],
        string="Status", required=True, default="draft", tracking=True,
    )
    applied_at = fields.Datetime(string="Applied At", readonly=True, copy=False, tracking=True)
    applied_by_id = fields.Many2one(
        "res.users", string="Applied By", readonly=True, copy=False, tracking=True,
    )

    @api.depends("picking_ids", "move_ids")
    def _compute_counts(self):
        for correction in self:
            correction.picking_count = len(correction.picking_ids)
            correction.move_count = len(correction.move_ids)

    @api.depends(
        "inventory_adjustment_move_ids.inventory_name",
        "inventory_adjustment_move_ids.origin",
    )
    def _compute_inventory_reference(self):
        for correction in self:
            references = {
                move.inventory_name or move.origin
                for move in correction.inventory_adjustment_move_ids
                if move.inventory_name or move.origin
            }
            correction.inventory_reference = ", ".join(sorted(references))

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if not values.get("name") or values.get("name") == _("New"):
                values["name"] = (
                    self.env["ir.sequence"].next_by_code(
                        "wt.stock.movement.date.correction"
                    ) or _("New")
                )
        records = super().create(vals_list)
        records._refresh_affected_records()
        return records

    def write(self, values):
        protected_fields = {
            "company_id", "source_type", "delivery_id", "production_receipt_id",
            "stock_opname_id", "inventory_adjustment_move_ids",
            "effective_date", "reason",
            "picking_ids", "move_ids",
        }
        if self.filtered(lambda record: record.state != "draft") and protected_fields & set(values):
            raise ValidationError(_("An applied or cancelled correction cannot be changed."))
        result = super().write(values)
        if {
            "source_type", "delivery_id", "production_receipt_id", "stock_opname_id",
            "inventory_adjustment_move_ids",
        } & set(values):
            self._refresh_affected_records()
        return result

    def unlink(self):
        if self.filtered(lambda record: record.state == "applied"):
            raise ValidationError(_("An applied correction cannot be deleted."))
        return super().unlink()

    @api.onchange("source_type")
    def _onchange_source_type(self):
        for correction in self:
            if correction.source_type != "delivery":
                correction.delivery_id = False
            if correction.source_type != "production_receipt":
                correction.production_receipt_id = False
            if correction.source_type != "stock_opname":
                correction.stock_opname_id = False
            if correction.source_type != "inventory_adjustment":
                correction.inventory_adjustment_move_ids = False
            correction.picking_ids = False
            correction.move_ids = False

    @api.onchange("delivery_id", "production_receipt_id", "stock_opname_id")
    def _onchange_source_document(self):
        for correction in self:
            source = correction._get_source_record()
            if not source:
                correction.picking_ids = False
                correction.move_ids = False
                continue
            correction.company_id = source.company_id
            correction.effective_date = correction._get_source_date(source)
            pickings, moves = correction._get_affected_records(source)
            correction.picking_ids = pickings
            correction.move_ids = moves

    @api.onchange("inventory_adjustment_move_ids")
    def _onchange_inventory_adjustment_move_ids(self):
        for correction in self.filtered(
            lambda record: record.source_type == "inventory_adjustment"
        ):
            moves = correction.inventory_adjustment_move_ids
            correction.picking_ids = False
            correction.move_ids = moves
            if not moves:
                continue
            correction.company_id = moves[0].company_id
            movement_dates = correction._get_inventory_movement_dates(moves)
            if len(movement_dates) == 1:
                correction.effective_date = next(iter(movement_dates))

    @api.constrains(
        "source_type", "delivery_id", "production_receipt_id", "stock_opname_id",
        "inventory_adjustment_move_ids", "company_id",
    )
    def _check_source_document(self):
        for correction in self:
            selected = [
                bool(correction.delivery_id),
                bool(correction.production_receipt_id),
                bool(correction.stock_opname_id),
            ]
            if correction.source_type == "inventory_adjustment":
                if (
                    any(selected)
                    or not correction.inventory_adjustment_move_ids
                ):
                    raise ValidationError(_(
                        "Select at least one Stock Adjustment movement and do not select another source document."
                    ))
                correction._validate_inventory_adjustment_moves()
                continue
            if correction.inventory_adjustment_move_ids:
                raise ValidationError(_(
                    "Stock Adjustment movements can only be selected for the Stock Adjustment source type."
                ))
            if sum(selected) != 1 or not correction._get_source_record():
                raise ValidationError(_(
                    "Select exactly one source document matching the source type."
                ))
            if correction.company_id != correction._get_source_record().company_id:
                raise ValidationError(_(
                    "The correction company must match the source document company."
                ))

    def _get_source_record(self):
        self.ensure_one()
        return {
            "delivery": self.delivery_id,
            "production_receipt": self.production_receipt_id,
            "stock_opname": self.stock_opname_id,
            "inventory_adjustment": self.env["stock.move"],
        }.get(self.source_type, self.env["wt.delivery"])

    def _get_inventory_movement_dates(self, moves=None):
        self.ensure_one()
        moves = moves or self.inventory_adjustment_move_ids
        business_timezone = self._get_business_timezone()
        movement_dates = set()
        for move in moves.filtered("date"):
            movement_datetime = fields.Datetime.to_datetime(move.date)
            if movement_datetime.tzinfo is None:
                movement_datetime = UTC.localize(movement_datetime)
            movement_dates.add(
                movement_datetime.astimezone(business_timezone).date()
            )
        return movement_dates

    def _validate_inventory_adjustment_moves(self):
        self.ensure_one()
        moves = self.inventory_adjustment_move_ids
        if not moves:
            raise ValidationError(_(
                "Select at least one Stock Adjustment movement."
            ))
        invalid_moves = moves.filtered(
            lambda move: move.state != "done"
            or not move.is_inventory
            or bool(move.picking_id)
        )
        if invalid_moves:
            raise ValidationError(_(
                "Only completed inventory movements without a transfer can be selected."
            ))
        if moves.filtered(lambda move: move.company_id != self.company_id):
            raise ValidationError(_(
                "All selected inventory movements must belong to the correction company."
            ))
        movement_dates = self._get_inventory_movement_dates(moves)
        if len(movement_dates) != 1:
            raise ValidationError(_(
                "All selected inventory movements must have the same current movement date."
            ))

        source_references = list({
            reference
            for move in moves
            for reference in (move.origin, move.inventory_name)
            if reference
        })
        if not source_references:
            return
        source_models = (
            "wt.delivery",
            "wt.production.receipt",
            "wt.stock.opname",
        )
        if any(
            self.env[model_name].search_count([("name", "in", source_references)])
            for model_name in source_models
        ):
            raise ValidationError(_(
                "Movements generated by a WeighTrack document must be corrected from their source document."
            ))

    def _get_source_date(self, source=None):
        self.ensure_one()
        if self.source_type == "inventory_adjustment":
            movement_dates = self._get_inventory_movement_dates()
            return next(iter(movement_dates)) if len(movement_dates) == 1 else False
        return source.received_date if self.source_type == "production_receipt" else source.date

    def _get_affected_records(self, source=None):
        self.ensure_one()
        source = source or self._get_source_record()
        Picking = self.env["stock.picking"]
        Move = self.env["stock.move"]
        if self.source_type == "inventory_adjustment":
            return Picking, self.inventory_adjustment_move_ids
        if not source:
            return Picking, Move
        if self.source_type == "delivery":
            pickings = source.picking_ids.filtered(lambda picking: picking.state == "done")
            direct_moves = Move.search([
                ("state", "=", "done"), ("picking_id", "=", False),
                ("origin", "=", source.name), ("is_inventory", "=", True),
            ])
            moves = pickings.move_ids.filtered(lambda move: move.state == "done") | direct_moves
            return pickings, moves
        if self.source_type == "production_receipt":
            pickings = source.stock_picking_id.filtered(lambda picking: picking.state == "done")
            return pickings, pickings.move_ids.filtered(lambda move: move.state == "done")
        moves = Move.search([
            ("state", "=", "done"), ("company_id", "=", source.company_id.id),
            ("is_inventory", "=", True), "|",
            ("origin", "=", source.name), ("inventory_name", "=", source.name),
        ])
        return Picking, moves

    def _refresh_affected_records(self):
        for correction in self:
            source = correction._get_source_record()
            pickings, moves = correction._get_affected_records(source)
            correction.with_context(tracking_disable=True).write({
                "picking_ids": [(6, 0, pickings.ids)],
                "move_ids": [(6, 0, moves.ids)],
            })

    def action_load_movements(self):
        self.ensure_one()
        if self.state != "draft":
            raise ValidationError(_("Only a draft correction can reload stock movements."))
        self._refresh_affected_records()
        return True

    def _get_business_timezone(self):
        self.ensure_one()
        timezone_name = self.company_id.partner_id.tz or self.env.user.tz or "UTC"
        try:
            return timezone(timezone_name)
        except Exception:
            return UTC

    def _get_business_today(self):
        self.ensure_one()
        now_utc = UTC.localize(fields.Datetime.now())
        return now_utc.astimezone(self._get_business_timezone()).date()

    def _get_effective_datetime(self):
        self.ensure_one()
        local_datetime = self._get_business_timezone().localize(
            datetime.combine(fields.Date.to_date(self.effective_date), time(hour=12))
        )
        return local_datetime.astimezone(UTC).replace(tzinfo=None)

    def _validate_source_state(self, source):
        if self.source_type == "inventory_adjustment":
            self._validate_inventory_adjustment_moves()
            return
        valid_state = {
            "delivery": "done",
            "production_receipt": "validated",
            "stock_opname": "applied",
        }[self.source_type]
        if source.state != valid_state:
            raise ValidationError(_(
                "The selected source document must be completed before its movement date can be corrected."
            ))

    def _check_posted_valuation_entries(self, moves):
        if not moves or "stock.valuation.layer" not in self.env.registry.models:
            return
        ValuationLayer = self.env["stock.valuation.layer"].sudo()
        if not {"stock_move_id", "account_move_id"}.issubset(ValuationLayer._fields):
            return
        if ValuationLayer.search([
            ("stock_move_id", "in", moves.ids),
            ("account_move_id.state", "=", "posted"),
        ], limit=1):
            raise ValidationError(_(
                "The movement date cannot be corrected because an affected movement already has a posted valuation journal entry."
            ))

    def _check_historical_stock(self, moves, effective_datetime):
        move_lines = moves.mapped("move_line_ids").filtered(
            lambda line: line.state == "done" and line.quantity > 0
        )
        outgoing_keys = {
            (line.product_id.id, line.lot_id.id or 0, line.location_id.id)
            for line in move_lines
            if line.location_id.usage == "internal"
        }
        MoveLine = self.env["stock.move.line"].sudo()
        Location = self.env["stock.location"].sudo()
        for product_id, lot_id, location_id in outgoing_keys:
            product = self.env["product.product"].browse(product_id)
            lot = self.env["stock.lot"].browse(lot_id) if lot_id else False
            location = Location.browse(location_id)
            location_ids = set(Location.search([("id", "child_of", location.id)]).ids)
            prior_lines = MoveLine.search([
                ("state", "=", "done"), ("company_id", "=", self.company_id.id),
                ("product_id", "=", product.id), ("lot_id", "=", lot.id if lot else False),
                ("date", "<=", effective_datetime), ("id", "not in", move_lines.ids),
                "|", ("location_id", "in", list(location_ids)),
                ("location_dest_id", "in", list(location_ids)),
            ])

            def net_quantity(lines):
                incoming = sum(
                    line.quantity for line in lines
                    if line.location_dest_id.id in location_ids
                    and line.location_id.id not in location_ids
                )
                outgoing = sum(
                    line.quantity for line in lines
                    if line.location_id.id in location_ids
                    and line.location_dest_id.id not in location_ids
                )
                return incoming - outgoing

            available = net_quantity(prior_lines)
            affected_delta = net_quantity(move_lines.filtered(
                lambda line: line.product_id == product
                and (line.lot_id.id or 0) == lot_id
            ))
            if float_compare(
                available + affected_delta, 0.0,
                precision_rounding=product.uom_id.rounding,
            ) < 0:
                raise ValidationError(_(
                    "The correction would make historical stock negative for lot %(lot)s at %(location)s."
                ) % {
                    "lot": lot.display_name if lot else _("Without Lot"),
                    "location": location.display_name,
                })

    def _sync_moves(self, moves, effective_datetime):
        context = {
            "tracking_disable": True, "mail_notrack": True,
            "wt_skip_delivery_backdate_sync": True,
        }
        moves.sudo().with_context(**context).write({"date": effective_datetime})
        move_lines = moves.mapped("move_line_ids")
        if move_lines and "date" in move_lines._fields:
            move_lines.sudo().with_context(**context).write({"date": effective_datetime})

    def _sync_pickings(self, pickings, effective_datetime):
        if not pickings:
            return
        values = {"scheduled_date": effective_datetime}
        if "date_done" in pickings._fields:
            values["date_done"] = effective_datetime
        pickings.sudo().with_context(
            tracking_disable=True, mail_notrack=True,
            wt_skip_delivery_backdate_sync=True,
        ).write(values)

    def action_apply(self):
        for correction in self:
            if correction.state != "draft":
                raise ValidationError(_("Only a draft correction can be applied."))
            if not self.env.user.has_group("weightrack.group_admin"):
                raise ValidationError(_(
                    "Only a WeighTrack Administrator can correct movement dates."
                ))
            if not (correction.reason or "").strip():
                raise ValidationError(_("Correction Reason is required."))
            source = correction._get_source_record()
            correction._validate_source_state(source)
            current_date = correction._get_source_date(source)
            if correction.effective_date == current_date:
                raise ValidationError(_(
                    "The new effective date must differ from the current movement date."
                ))
            if correction.effective_date > correction._get_business_today():
                raise ValidationError(_("The effective date cannot be in the future."))
            if (
                correction.source_type == "production_receipt"
                and correction.effective_date < source.production_date
            ):
                raise ValidationError(_("Received Date cannot be earlier than Production Date."))

            correction._refresh_affected_records()
            moves = correction.move_ids
            pickings = correction.picking_ids
            if not moves:
                raise ValidationError(_(
                    "No completed stock movement was found for the selected source."
                ))
            correction._check_posted_valuation_entries(moves)
            effective_datetime = correction._get_effective_datetime()
            correction._check_historical_stock(moves, effective_datetime)
            old_date = current_date

            if correction.source_type == "delivery":
                source.with_context(wt_allow_backdate_update=True).write({
                    "date": correction.effective_date,
                    "backdate_reason": correction.reason.strip(),
                    "backdate_effective_at": effective_datetime,
                    "backdate_applied_at": fields.Datetime.now(),
                    "backdate_applied_by_id": self.env.user.id,
                })
                source.do_line_ids.write({"scheduled_date": effective_datetime})
                source.do_line_ids.mapped("generated_transit_lot_id").sudo().write({
                    "wt_transit_date": correction.effective_date,
                })
            elif correction.source_type == "production_receipt":
                source.with_context(allow_production_receipt_update=True).write({
                    "received_date": correction.effective_date,
                })
            elif correction.source_type == "stock_opname":
                source.with_context(wt_allow_stock_opname_date_update=True).write({
                    "date": correction.effective_date,
                })

            correction._sync_pickings(pickings, effective_datetime)
            correction._sync_moves(moves, effective_datetime)
            correction.with_context(tracking_disable=True).write({
                "old_date": old_date, "state": "applied",
                "applied_at": fields.Datetime.now(), "applied_by_id": self.env.user.id,
            })
            message_target = source or correction
            message_target.message_post(body=_(
                "Stock movement date corrected from %(old_date)s to %(new_date)s by %(user)s. Reason: %(reason)s"
            ) % {
                "old_date": old_date, "new_date": correction.effective_date,
                "user": self.env.user.display_name, "reason": correction.reason.strip(),
            })
        return True

    def action_cancel(self):
        drafts = self.filtered(lambda correction: correction.state == "draft")
        if len(drafts) != len(self):
            raise ValidationError(_("Only a draft correction can be cancelled."))
        drafts.write({"state": "cancelled"})
        return True
