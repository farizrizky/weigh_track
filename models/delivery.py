# -*- coding: utf-8 -*-

from datetime import datetime, time

from pytz import UTC, timezone

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from markupsafe import Markup


class Delivery(models.Model):
    _name = "wt.delivery"
    _description = "Tugas Pengiriman (Weighing Delivery)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    STATE_SELECTION = [
        ("draft", "Draft"),
        ("confirmed", "Confirmed"),
        ("in_progress", "In Progress"),
        ("delivered", "Terkirim"),
        ("done", "Done"),
        ("returned", "Returned"),
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
        tracking=True,
    )
    date = fields.Date(
        string="Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    is_backdated = fields.Boolean(
        string="Backdated",
        compute="_compute_is_backdated",
    )
    backdate_reason = fields.Text(
        string="Backdate Reason",
        tracking=True,
        copy=False,
    )
    backdate_effective_at = fields.Datetime(
        string="Effective Movement Date",
        readonly=True,
        copy=False,
        tracking=True,
    )
    backdate_applied_at = fields.Datetime(
        string="Backdate Applied At",
        readonly=True,
        copy=False,
        tracking=True,
    )
    backdate_applied_by_id = fields.Many2one(
        "res.users",
        string="Backdate Applied By",
        readonly=True,
        copy=False,
        tracking=True,
    )
    date_text = fields.Char(
        string="Date (Text)",
        compute="_compute_date_text",
    )
    note = fields.Text(
        string="Notes",
    )

    # â”€â”€ Customer / Partner â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        domain="[('id', 'in', allowed_customer_partner_ids)]",
        tracking=True,
        help="Partner/Customer tujuan pengiriman akhir (untuk Outgoing DO final).",
    )
    allowed_customer_partner_ids = fields.Many2many(
        "res.partner",
        compute="_compute_allowed_customer_partner_ids",
        string="Allowed Customer Contacts",
    )
    route_id = fields.Many2one(
        "wt.delivery.route",
        string="Route",
        tracking=True,
        domain="[('company_id', '=', company_id)]",
        help="Rute pengiriman yang akan membentuk baris rencana pengiriman.",
    )

    # â”€â”€ Produk yang dikirim (opsional, digunakan sebagai fallback di step) â”€â”€â”€â”€
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        tracking=True,
    )

    # â”€â”€ Step-based multi-warehouse delivery â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    warehouse_step_ids = fields.One2many(
        "wt.delivery.step",
        "delivery_id",
        string="Warehouse Steps",
        copy=True,
    )

    # â”€â”€ Rencana DO (inline lines, dikonversi saat Konfirmasi) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    do_line_ids = fields.One2many(
        "wt.delivery.do.line",
        "delivery_id",
        string="Delivery Plan",
        copy=True,
    )
    step_count = fields.Integer(
        string="Step Count",
        compute="_compute_step_count",
    )

    # â”€â”€ Final outgoing DO ke customer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    final_picking_id = fields.Many2one(
        "stock.picking",
        string="Final DO",
        copy=False,
        readonly=True,
        help="Outgoing DO final ke customer, dibuat otomatis saat step terakhir divalidasi.",
    )

    # â”€â”€ DOs yang dibuat langsung dari dokumen ini â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # (via wt_delivery_id pada stock.picking â€” termasuk internal transfer + outgoing)
    picking_ids = fields.One2many(
        "stock.picking",
        "wt_delivery_id",
        string="Delivery Orders (DO)",
        copy=False,
    )
    picking_count = fields.Integer(
        string="DO Count",
        compute="_compute_picking_count",
    )

    # â”€â”€ Detail timbang (backward compat untuk alur lama) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    wt_has_unpulled_lines = fields.Boolean(
        string="Has Unpulled Lots",
        compute="_compute_wt_has_unpulled_lines",
        store=True,
        help=(
            "True jika ada lot rencana aktif (qty > 0) yang belum pernah di-pull "
            "oleh operator."
        ),
    )

    # â”€â”€ Detail Timbang Rencana DO (alur baru) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    do_lot_line_ids = fields.One2many(
        "wt.delivery.do.line.lot",
        "delivery_id",
        string="All Delivery Plan Lot Details",
    )
    pulled_do_lot_line_ids = fields.One2many(
        "wt.delivery.do.line.lot",
        compute="_compute_do_lot_line_ids",
        string="Weighing Details (Plan)",
    )
    unpulled_do_lot_line_ids = fields.One2many(
        "wt.delivery.do.line.lot",
        compute="_compute_do_lot_line_ids",
        string="Unpulled Planned Lots",
    )

    # â”€â”€ State & Totals â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    state = fields.Selection(
        STATE_SELECTION,
        string="Status",
        default="draft",
        required=True,
        index=True,
        tracking=True,
    )
    total_demand_qty = fields.Float(
        string="Total Planned Qty (kg)",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    total_physical_qty = fields.Float(
        string="Total Delivered Qty (kg)",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    total_difference_qty = fields.Float(
        string="Total Difference (kg)",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    total_initial_plan_qty = fields.Float(
        string="Total Initial Plan (kg)",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    total_production_weighed_qty = fields.Float(
        string="Total Production Weighing (kg)",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    production_weighing_difference_qty = fields.Float(
        string="Production Weighing Difference (kg)",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    total_transit_out_qty = fields.Float(
        string="Transit Out Weight (kg)",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    total_transit_in_qty = fields.Float(
        string="Transit In Weight (kg)",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    transit_weighing_difference_qty = fields.Float(
        string="Transit Weighing Difference (kg)",
        compute="_compute_totals",
        store=True,
        digits="Product Unit of Measure",
    )
    has_transit_route = fields.Boolean(
        string="Has Transit Route",
        compute="_compute_totals",
        store=True,
    )
    received_qty = fields.Float(
        string="Berat Diterima Customer (kg)",
        digits="Product Unit of Measure",
        tracking=True,
        copy=False,
    )
    received_difference_qty = fields.Float(
        string="Selisih Pengiriman (kg)",
        compute="_compute_received_difference_qty",
        store=True,
        digits="Product Unit of Measure",
    )
    shipping_weighing_difference_qty = fields.Float(
        string="Delivery Weighing Difference (kg)",
        compute="_compute_received_difference_qty",
        store=True,
        digits="Product Unit of Measure",
    )
    has_adjustable_lines = fields.Boolean(
        string="Has Adjustable Lines",
        compute="_compute_has_adjustable_lines",
        help=(
            "True jika ada minimal 1 baris dengan selisih yang sudah teralokasi penuh "
            "dan belum diterapkan adjustment-nya."
        ),
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
    wt_is_returned = fields.Boolean(
        string="Returned",
        default=False,
        copy=False,
        readonly=True,
    )
    wt_return_reason = fields.Text(
        string="Return Reason",
        readonly=True,
        copy=False,
    )

    # â”€â”€ Computed â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _get_configured_product(self):
        self.ensure_one()
        return self.env["wt.product"].get_active_product(self.company_id)

    @api.depends("company_id")
    def _compute_allowed_customer_partner_ids(self):
        customer_model = self.env["wt.customer"]
        for delivery in self:
            delivery.allowed_customer_partner_ids = customer_model.get_allowed_partners(
                delivery.company_id
            )

    def _is_allowed_customer_partner(self, partner=False):
        self.ensure_one()
        partner = partner or self.partner_id
        return self.env["wt.customer"].is_allowed_partner(self.company_id, partner)

    @api.constrains("company_id", "partner_id")
    def _check_customer_partner(self):
        for delivery in self:
            if delivery.partner_id and not delivery._is_allowed_customer_partner():
                raise ValidationError(_(
                    "Customer must be registered in WeighTrack Customer master."
                ))

    @api.onchange("company_id")
    def _onchange_company_id_set_product(self):
        for delivery in self:
            delivery.product_id = delivery._get_configured_product()
            if delivery.partner_id and not delivery._is_allowed_customer_partner():
                delivery.partner_id = False
            delivery.route_id = False
            delivery.do_line_ids = [(5, 0, 0)]

    def _prepare_route_do_line_commands(self, route):
        self.ensure_one()
        product = self.product_id or self._get_configured_product()
        scheduled_date = self._get_planned_movement_datetime()
        commands = [(5, 0, 0)]
        for route_line in route.line_ids.sorted("sequence"):
            commands.append((0, 0, {
                "sequence": route_line.sequence,
                "route_id": route.id,
                "route_line_id": route_line.id,
                "picking_type_id": route_line.picking_type_id.id,
                "product_id": product.id if product else False,
                "location_id": route_line.location_id.id,
                "location_dest_id": route_line.location_dest_id.id,
                "partner_id": self.partner_id.id if self.partner_id else False,
                "scheduled_date": scheduled_date,
                "document_do_number": self.name if self.name and self.name != _("New") else False,
            }))
        return commands

    @api.onchange("route_id")
    def _onchange_route_id_load_do_lines(self):
        for delivery in self:
            if not delivery.route_id:
                delivery.do_line_ids = [(5, 0, 0)]
                continue
            delivery.do_line_ids = delivery._prepare_route_do_line_commands(delivery.route_id)

    @api.onchange("partner_id")
    def _onchange_partner_id_update_do_lines(self):
        for delivery in self:
            if not delivery.partner_id:
                continue
            for line in delivery.do_line_ids:
                if not line.partner_id or line.partner_id != delivery.partner_id:
                    line.partner_id = delivery.partner_id

    @api.onchange("product_id")
    def _onchange_product_id_update_do_lines(self):
        for delivery in self:
            if not delivery.product_id:
                continue
            for line in delivery.do_line_ids:
                if not line.product_id or line.product_id != delivery.product_id:
                    line.product_id = delivery.product_id

    @api.onchange("date")
    def _onchange_date_update_do_lines(self):
        for delivery in self:
            scheduled_date = delivery._get_planned_movement_datetime()
            for line in delivery.do_line_ids:
                if line.picking_state != "done" and line.scheduled_date != scheduled_date:
                    line.scheduled_date = scheduled_date

    @api.depends(
        "do_line_ids.lot_line_ids.wt_is_pulled",
        "do_line_ids.lot_line_ids.wt_weighing_source",
        "do_line_ids.lot_line_ids.qty",
        "do_line_ids.lot_line_ids.wt_is_cancelled",
    )
    def _compute_do_lot_line_ids(self):
        for delivery in self:
            all_lots = delivery.do_line_ids.mapped("lot_line_ids")
            delivery.pulled_do_lot_line_ids = all_lots.filtered(
                lambda line: line._has_weighing_input() and line.qty > 0 and not line.wt_is_cancelled
            )
            delivery.unpulled_do_lot_line_ids = all_lots.filtered(
                lambda line: not line._has_weighing_input() and line.qty > 0 and not line.wt_is_cancelled
            )

    @api.onchange("do_line_ids")
    def _onchange_do_line_ids_sync_lots(self):
        for delivery in self:
            delivery._compute_totals()

    @api.depends(
        "do_line_ids.sequence",
        "do_line_ids.route_type",
        "do_line_ids.route_line_id.route_type",
        "do_line_ids.generated_transit_lot_id",
        "do_line_ids.lot_line_ids.qty",
        "do_line_ids.lot_line_ids.wt_original_qty",
        "do_line_ids.lot_line_ids.wt_physical_qty",
        "do_line_ids.lot_line_ids.wt_is_pulled",
        "do_line_ids.lot_line_ids.wt_weighing_source",
        "do_line_ids.lot_line_ids.lot_id",
        "do_line_ids.lot_line_ids.lot_id.wt_lot_type",
        "do_line_ids.lot_line_ids.wt_is_cancelled",
    )
    def _compute_totals(self):
        for rec in self:
            production_lines = rec._get_initial_production_lot_lines()
            weighed_production_lines = production_lines.filtered(
                lambda line: line._has_weighing_input()
                and line.wt_physical_qty > 0.0
            )
            initial_plan_qty = sum(
                line.wt_original_qty if line.wt_original_qty > 0.0 else line.qty
                for line in production_lines
            )
            production_weighed_qty = sum(
                weighed_production_lines.mapped("wt_physical_qty")
            )
            production_difference_qty = sum(
                (
                    line.wt_original_qty
                    if line.wt_original_qty > 0.0
                    else line.qty
                ) - line.wt_physical_qty
                for line in weighed_production_lines
            )

            active_lots = rec.do_lot_line_ids.filtered(
                lambda line: line._has_weighing_input() and not line.wt_is_cancelled
            )
            outgoing_lots = active_lots.filtered(
                lambda l: l.do_line_id.picking_type_id.code == "outgoing"
            )
            if outgoing_lots:
                rec.total_physical_qty = sum(outgoing_lots.mapped("wt_physical_qty"))
            else:
                rec.total_physical_qty = sum(active_lots.mapped("wt_physical_qty"))

            transit_out_qty, transit_in_qty, transit_difference_qty = (
                rec._get_transit_weighing_totals()
            )
            rec.total_initial_plan_qty = initial_plan_qty
            rec.total_production_weighed_qty = production_weighed_qty
            rec.production_weighing_difference_qty = production_difference_qty
            rec.total_transit_out_qty = transit_out_qty
            rec.total_transit_in_qty = transit_in_qty
            rec.transit_weighing_difference_qty = transit_difference_qty
            rec.has_transit_route = any(
                line._is_transit_route() for line in rec.do_line_ids
            )

            # Legacy totals remain available for API and older report consumers.
            rec.total_demand_qty = initial_plan_qty
            rec.total_difference_qty = rec.total_physical_qty - initial_plan_qty

    def _get_initial_production_lot_lines(self):
        self.ensure_one()
        result = self.env["wt.delivery.do.line.lot"]
        first_route_key_by_lot = {}
        for do_line in self.do_line_ids.sorted(
            lambda line: (line.sequence or 0, line.id or 0)
        ):
            route_key = (do_line.sequence or 0, do_line.id or 0)
            for lot_line in do_line.lot_line_ids.filtered(
                lambda line: line.qty > 0.0
                and line.lot_id.wt_lot_type == "production"
                and not line.wt_is_cancelled
            ):
                first_key = first_route_key_by_lot.setdefault(
                    lot_line.lot_id.id,
                    route_key,
                )
                if route_key == first_key:
                    result |= lot_line
        return result

    def _get_transit_weighing_totals(self):
        self.ensure_one()
        total_out = 0.0
        total_in = 0.0
        total_difference = 0.0
        ordered_lines = self.do_line_ids.sorted(
            lambda line: (line.sequence or 0, line.id or 0)
        )
        for source_line in ordered_lines.filtered(
            lambda line: line._is_transit_route()
        ):
            weighed_source_lots = source_line.lot_line_ids.filtered(
                lambda line: line.qty > 0.0
                and line._has_weighing_input()
                and line.wt_physical_qty > 0.0
            )
            transfer_out_qty = sum(
                weighed_source_lots.mapped("wt_physical_qty")
            )
            total_out += transfer_out_qty

            transit_lot = source_line.generated_transit_lot_id
            if not transit_lot:
                continue
            source_key = (source_line.sequence or 0, source_line.id or 0)
            destination_line = ordered_lines.filtered(
                lambda line: (
                    (line.sequence or 0, line.id or 0) > source_key
                    and transit_lot in line.lot_line_ids.mapped("lot_id")
                )
            )[:1]
            if not destination_line:
                continue
            weighed_destination_lots = destination_line.lot_line_ids.filtered(
                lambda line: line.lot_id == transit_lot
                and line._has_weighing_input()
                and line.wt_physical_qty > 0.0
            )
            if not weighed_destination_lots:
                continue
            transfer_in_qty = sum(
                weighed_destination_lots.mapped("wt_physical_qty")
            )
            total_in += transfer_in_qty
            total_difference += transfer_out_qty - transfer_in_qty
        return total_out, total_in, total_difference

    @api.depends("total_physical_qty", "received_qty")
    def _compute_received_difference_qty(self):
        for rec in self:
            rec.received_difference_qty = rec.total_physical_qty - rec.received_qty
            rec.shipping_weighing_difference_qty = rec.received_difference_qty

    @api.depends(
        "do_line_ids.lot_line_ids.wt_difference_qty",
        "do_line_ids.lot_line_ids.wt_is_fully_allocated",
        "do_line_ids.lot_line_ids.wt_adjustment_applied",
        "do_line_ids.lot_line_ids.wt_is_pulled",
        "do_line_ids.lot_line_ids.wt_weighing_source",
        "do_line_ids.lot_line_ids.wt_is_cancelled",
    )
    def _compute_has_adjustable_lines(self):
        for rec in self:
            rec.has_adjustable_lines = any(
                abs(l.wt_difference_qty) > 0.001
                and l.wt_is_fully_allocated
                and not l.wt_adjustment_applied
                and l._has_weighing_input()
                and not l.wt_is_cancelled
                for l in rec.do_lot_line_ids
            )

    def _compute_picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids)

    def _compute_step_count(self):
        for rec in self:
            rec.step_count = len(rec.warehouse_step_ids)

    @api.depends("date")
    def _compute_date_text(self):
        month_names = {
            1: "Januari",
            2: "Februari",
            3: "Maret",
            4: "April",
            5: "Mei",
            6: "Juni",
            7: "Juli",
            8: "Agustus",
            9: "September",
            10: "Oktober",
            11: "November",
            12: "Desember",
        }
        for rec in self:
            if rec.date:
                date_value = fields.Date.to_date(rec.date)
                rec.date_text = "%s %s %s" % (
                    date_value.day,
                    month_names[date_value.month],
                    date_value.year,
                )
            else:
                rec.date_text = False

    @api.depends("date", "create_date", "backdate_applied_at")
    def _compute_is_backdated(self):
        for delivery in self:
            reference_datetime = (
                delivery.backdate_applied_at or delivery.create_date
            )
            if reference_datetime:
                reference_datetime = fields.Datetime.to_datetime(
                    reference_datetime
                )
                if reference_datetime.tzinfo is None:
                    reference_datetime = UTC.localize(reference_datetime)
                reference_date = reference_datetime.astimezone(
                    delivery._get_business_timezone()
                ).date()
            else:
                # Unsaved records use today so the reason field appears as soon
                # as a user selects an earlier delivery date.
                reference_date = delivery._get_business_today()
            delivery.is_backdated = bool(
                delivery.date and delivery.date < reference_date
            )

    def _get_business_timezone(self):
        self.ensure_one()
        timezone_name = self.company_id.partner_id.tz or self.env.user.tz or "UTC"
        try:
            return timezone(timezone_name)
        except Exception:
            return UTC

    def _get_planned_movement_datetime(self, effective_date=None):
        """Return noon on the business date, stored as a naive UTC datetime."""
        self.ensure_one()
        business_date = fields.Date.to_date(effective_date or self.date)
        if not business_date:
            return fields.Datetime.now()
        local_datetime = self._get_business_timezone().localize(
            datetime.combine(business_date, time(hour=12))
        )
        return local_datetime.astimezone(UTC).replace(tzinfo=None)

    def _get_business_today(self):
        self.ensure_one()
        now_utc = UTC.localize(fields.Datetime.now())
        return now_utc.astimezone(self._get_business_timezone()).date()

    def _validate_effective_date(self):
        for delivery in self:
            today = delivery._get_business_today()
            if not delivery.date:
                continue
            if delivery.date > today:
                raise ValidationError(_("Delivery date cannot be in the future."))
            if delivery.is_backdated:
                if not self.env.user.has_group("weightrack.group_admin"):
                    raise ValidationError(_(
                        "Only a WeighTrack Administrator can process a backdated delivery."
                    ))
                if not (delivery.backdate_reason or "").strip():
                    raise ValidationError(_(
                        "Backdate Reason is required for a backdated delivery."
                    ))

    @api.constrains("date", "backdate_reason")
    def _check_effective_date(self):
        self._validate_effective_date()

    def _ensure_backdate_metadata(self):
        self.ensure_one()
        self._validate_effective_date()
        if not self.is_backdated:
            return False
        if not self.backdate_effective_at:
            self.with_context(wt_allow_backdate_update=True).write({
                "backdate_effective_at": self._get_planned_movement_datetime(),
                "backdate_applied_at": fields.Datetime.now(),
                "backdate_applied_by_id": self.env.user.id,
            })
        return self.backdate_effective_at

    def _sync_moves_effective_date(self, moves, effective_datetime=None):
        self.ensure_one()
        effective_datetime = effective_datetime or self._ensure_backdate_metadata()
        if not effective_datetime or not moves:
            return
        sync_context = {
            "tracking_disable": True,
            "mail_notrack": True,
            "wt_skip_delivery_backdate_sync": True,
        }
        moves.sudo().with_context(**sync_context).write({"date": effective_datetime})
        move_lines = moves.mapped("move_line_ids")
        if move_lines and "date" in move_lines._fields:
            move_lines.sudo().with_context(**sync_context).write({
                "date": effective_datetime,
            })

    def _sync_picking_effective_date(self, picking, effective_datetime=None):
        self.ensure_one()
        effective_datetime = effective_datetime or self._ensure_backdate_metadata()
        if not effective_datetime or not picking or picking.state != "done":
            return
        picking.sudo().with_context(
            tracking_disable=True,
            mail_notrack=True,
            wt_skip_delivery_backdate_sync=True,
        ).write({
            "scheduled_date": effective_datetime,
            "date_done": effective_datetime,
        })
        self._sync_moves_effective_date(picking.move_ids, effective_datetime)

    @api.depends(
        "do_line_ids.lot_line_ids.wt_is_pulled",
        "do_line_ids.lot_line_ids.wt_weighing_source",
        "do_line_ids.lot_line_ids.qty",
        "do_line_ids.lot_line_ids.wt_is_cancelled",
    )
    def _compute_wt_has_unpulled_lines(self):
        for rec in self:
            rec.wt_has_unpulled_lines = any(
                not l._has_weighing_input() and l.qty > 0 and not l.wt_is_cancelled
                for l in rec.do_lot_line_ids
            )

    # â”€â”€ ORM â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("wt.delivery") or _("New")
            if not vals.get("product_id"):
                company = (
                    self.env["res.company"].browse(vals["company_id"])
                    if vals.get("company_id")
                    else self.env.company
                )
                product = self.env["wt.product"].get_active_product(company)
                if product:
                    vals["product_id"] = product.id
        records = super().create(vals_list)
        for record in records:
            # Invalidate cache ORM agar pembacaan do_line_ids dari DB, bukan cache.
            # Ini mencegah false-negative saat onchange sudah menyertakan do_line_ids.
            record.invalidate_recordset(["do_line_ids"])
            if record.route_id and not record.do_line_ids:
                record.write({
                    "do_line_ids": record._prepare_route_do_line_commands(record.route_id),
                })
        return records

    def write(self, vals):
        if (
            {"date", "backdate_reason"} & set(vals)
            and not self.env.context.get("wt_allow_backdate_update")
        ):
            locked = self.filtered(
                lambda delivery: delivery.state != "draft" or delivery.picking_ids
            )
            if locked:
                raise ValidationError(_(
                    "Delivery Date and Backdate Reason can only be changed while the delivery is in Draft. "
                    "Use Correct Effective Date for a completed delivery."
                ))
        if "company_id" in vals and "product_id" not in vals:
            product = self.env["wt.product"].get_active_product(
                self.env["res.company"].browse(vals["company_id"])
            )
            if product:
                vals = dict(vals, product_id=product.id)
        route_changed = "route_id" in vals
        date_changed = "date" in vals
        do_lines_provided = "do_line_ids" in vals
        result = super().write(vals)
        if route_changed and not do_lines_provided:
            for record in self.filtered(lambda delivery: delivery.state == "draft"):
                if record.route_id:
                    record.write({
                        "do_line_ids": record._prepare_route_do_line_commands(record.route_id),
                    })
                elif record.do_line_ids:
                    record.write({"do_line_ids": [(5, 0, 0)]})
        if date_changed:
            for record in self.filtered(lambda delivery: delivery.state == "draft"):
                record.do_line_ids.filtered(
                    lambda route_line: route_line.picking_state != "done"
                ).write({
                    "scheduled_date": record._get_planned_movement_datetime(),
                })
        return result

    def init(self):
        super().init()
        self.env.cr.execute(
            """
            UPDATE wt_delivery
               SET state = CASE
                   WHEN state = 'validated' THEN 'done'
                   WHEN state = 'completed' THEN 'in_progress'
                   ELSE state
               END
             WHERE state IN ('validated', 'completed')
            """
        )

    # â”€â”€ Smart Buttons â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

    def action_open_customer_correction(self):
        """Buka wizard koreksi customer sebagai dialog popup."""
        self.ensure_one()
        if self.state == "draft":
            raise ValidationError(
                _("Koreksi customer hanya dapat dilakukan saat status bukan Draft.")
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Koreksi Customer"),
            "res_model": "wt.delivery.customer.correction.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_delivery_id": self.id,
            },
        }

    def action_open_received_qty_correction(self):
        """Buka wizard koreksi berat diterima customer sebagai dialog popup."""
        self.ensure_one()
        if self.state not in ("done", "returned"):
            raise ValidationError(
                _("Koreksi berat diterima hanya dapat dilakukan pada delivery dengan status Selesai atau Returned.")
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Koreksi Berat Diterima Customer"),
            "res_model": "wt.delivery.received.qty.correction.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_delivery_id": self.id,
            },
        }

    # Automatic stock adjustment, including the backward-compatible flow.

    def action_print_surat_jalan(self):
        """Backward-compatible entry point; Surat Jalan is printed per route line."""
        self.ensure_one()
        line = self._get_surat_jalan_document_line()
        if not line:
            raise ValidationError(_("Tidak ada baris Rencana DO yang dapat dicetak sebagai Surat Jalan."))
        return self.env.ref("weightrack.action_report_surat_jalan_line").report_action(line)

    def wt_get_report_customer_do_lines(self):
        """Customer-facing delivery lines used by the delivery order report."""
        self.ensure_one()
        return self.do_line_ids.filtered(
            lambda line: line.picking_type_id.code == "outgoing"
            or line.location_dest_id.usage == "customer"
        )

    def wt_get_report_customer_do_line(self):
        """Route line that carries customer document information for the report."""
        self.ensure_one()
        customer_lines = self.wt_get_report_customer_do_lines()
        return customer_lines[-1:] if customer_lines else self.env["wt.delivery.do.line"]

    def wt_get_report_customer_partner(self):
        """Customer contact displayed in the delivery order report."""
        self.ensure_one()
        customer_line = self.wt_get_report_customer_do_line()
        return customer_line.partner_id or self.partner_id

    def wt_get_report_delivery_address(self):
        """Delivery address displayed in the delivery order report."""
        self.ensure_one()
        customer_line = self.wt_get_report_customer_do_line()
        customer_partner = customer_line.partner_id or self.partner_id
        return (
            customer_line.receiver_address
            or customer_partner.contact_address
            or customer_line.location_dest_id.complete_name
            or "-"
        )

    def wt_get_report_used_lot_lines(self):
        """Used lot lines shown in the delivery order report totals."""
        self.ensure_one()
        return self.do_lot_line_ids.filtered(lambda lot_line: lot_line.qty > 0.0)

    def wt_get_report_total_demand_qty(self):
        """Planned quantity for the delivery order report header."""
        self.ensure_one()
        customer_lines = self.wt_get_report_customer_do_lines()
        if customer_lines:
            return sum(line.wt_get_report_plan_qty() for line in customer_lines)
        if self.total_demand_qty:
            return self.total_demand_qty
        return sum(self.do_line_ids.mapped("demand_qty"))

    def wt_get_report_total_physical_qty(self):
        """Delivered quantity for the delivery order report header."""
        self.ensure_one()
        if self.total_physical_qty:
            return self.total_physical_qty

        customer_lines = self.wt_get_report_customer_do_lines()
        report_lots = (
            customer_lines.mapped("lot_line_ids").filtered(lambda lot_line: lot_line.qty > 0.0)
            if customer_lines
            else self.wt_get_report_used_lot_lines()
        )
        return sum(
            lot_line.wt_physical_qty if lot_line.wt_weighing_source else lot_line.qty
            for lot_line in report_lots
        )

    def wt_get_report_delivered_goods_lines(self):
        """Product summary rows for the delivery order report."""
        self.ensure_one()
        return self._get_surat_jalan_lines()

    def _get_surat_jalan_lines(self):
        """Return aggregated delivery note lines; prefer outgoing/final delivery rows."""
        self.ensure_one()
        result = {}

        report_lines = self.do_line_ids.filtered(
            lambda line: line.picking_type_id.code == "outgoing"
        ) or self.do_line_ids
        for line in report_lines:
            product = line.product_id
            if not product:
                continue
            active_lots = line.lot_line_ids
            physical_qty = sum(active_lots.mapped("wt_physical_qty"))
            has_weighed_lots = any(l.wt_weighing_source for l in active_lots)
            qty = physical_qty if has_weighed_lots else line.demand_qty
            key = product.id
            if key not in result:
                result[key] = {
                    "code": product.default_code or "",
                    "name": product.display_name,
                    "qty": 0.0,
                    "uom": product.uom_id.name or "",
                }
            result[key]["qty"] += qty

        return list(result.values())

    def _get_surat_jalan_document_line(self):
        """Return the line that provides optional Surat Jalan document fields."""
        self.ensure_one()
        if not self.do_line_ids:
            return self.env["wt.delivery.do.line"]
        outgoing_lines = self.do_line_ids.filtered(
            lambda line: line.picking_type_id.code == "outgoing"
        )
        return (outgoing_lines or self.do_line_ids)[-1:]

    def _apply_adjustment_one(self):
        """Terapkan penyesuaian stok internal saat Delivery divalidasi."""
        self.ensure_one()
        if self.state not in ("confirmed", "in_progress"):
            raise UserError(_(
                "Penyesuaian stok otomatis hanya dapat diproses saat status Confirmed atau In Progress."
            ))

        adjustable_lines = self.do_lot_line_ids.filtered(
            lambda l: abs(l.wt_difference_qty) > 0.001
            and l.wt_is_fully_allocated
            and not l.wt_adjustment_applied
            and not l.wt_is_cancelled  # lot dibatalkan tidak menghasilkan pergerakan stok
        )
        if not adjustable_lines:
            raise UserError(_(
                "Tidak ada baris rencana lot dengan selisih yang sudah teralokasi penuh.\n"
                "Pastikan alokasi selisih sudah diisi untuk setiap baris yang punya selisih."
            ))

        company = self.company_id
        move_vals_list = []
        for line in adjustable_lines:
            for alloc in line.wt_allocation_ids:
                parent_loc = line.do_line_id.location_id
                exact_loc = line.source_location_id or parent_loc
                if not line.source_location_id and parent_loc and line.lot_id:
                    quant = self.env["stock.quant"].search([
                        ("product_id", "=", line.product_id.id),
                        ("location_id", "child_of", parent_loc.id),
                        ("lot_id", "=", line.lot_id.id),
                        ("quantity", ">", 0),
                    ], order="location_id, id", limit=1)
                    if quant:
                        exact_loc = quant.location_id

                if line.wt_difference_qty < 0:
                    location_src = exact_loc
                    location_dest = alloc.location_dest_id
                else:
                    location_src = alloc.location_dest_id
                    location_dest = exact_loc

                move_vals_list.append({
                    "inventory_name": _("Pengiriman"),
                    "description_picking": "%s / %s" % (
                        line.lot_id.name or line.product_id.display_name,
                        alloc.reason_id.name,
                    ),
                    "state": "confirmed",
                    "picked": True,
                    "is_inventory": True,
                    "product_id": line.product_id.id,
                    "product_uom": line.product_id.uom_id.id,
                    "product_uom_qty": alloc.qty,
                    "location_id": location_src.id,
                    "location_dest_id": location_dest.id,
                    "company_id": company.id,
                    "origin": self.name,
                    "move_line_ids": [(0, 0, {
                        "product_id": line.product_id.id,
                        "product_uom_id": line.product_id.uom_id.id,
                        "quantity": alloc.qty,
                        "lot_id": line.lot_id.id if line.lot_id else False,
                        "location_id": location_src.id,
                        "location_dest_id": location_dest.id,
                        "company_id": company.id,
                    })],
                })

        if move_vals_list:
            effective_datetime = self._ensure_backdate_metadata()
            ctx = dict(
                inventory_mode=False,
                tracking_disable=True,
                mail_notrack=True,
                no_recompute=True,
                ignore_dest_packages=True,
            )
            if effective_datetime:
                ctx["force_period_date"] = self.date
            moves = self.env["stock.move"].sudo().with_context(**ctx).create(move_vals_list)
            moves.with_context(**ctx)._action_done()
            self._sync_moves_effective_date(moves, effective_datetime)

        for line in adjustable_lines:
            write_vals = {"wt_adjustment_applied": True}
            if line.wt_physical_qty > 0:
                write_vals["qty"] = line.wt_physical_qty
            line.sudo().write(write_vals)

        lots = ", ".join(
            l.lot_id.name or l.product_id.display_name
            for l in adjustable_lines
        )
        self.message_post(
            body=Markup(_(
                "<b>Penyesuaian Stok Otomatis</b> diterapkan saat validasi oleh %s.<br/>"
                "Rincian Lot rencana yang diproses: %s"
            ) % (self.env.user.name, lots))
        )
    # â”€â”€ Workflow â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def action_confirm(self):
        for delivery in self:
            if delivery.state != "draft":
                raise ValidationError(_("Hanya Draft yang bisa dikonfirmasi."))
            delivery._validate_effective_date()
            if not delivery.partner_id:
                raise ValidationError(_("Customer wajib diisi sebelum pengiriman dikonfirmasi."))
            if not delivery._is_allowed_customer_partner():
                raise ValidationError(_(
                    "Customer must be registered in WeighTrack Customer master."
                ))
            if not delivery.route_id:
                raise ValidationError(_("Rute wajib diisi sebelum pengiriman dikonfirmasi."))
            if delivery.route_id and not delivery.do_line_ids:
                delivery.write({
                    "do_line_ids": delivery._prepare_route_do_line_commands(delivery.route_id),
                })

            # Baris Rencana DO wajib berasal dari Route.
            # Picking baru dibuat saat validasi baris Rencana DO
            if delivery.do_line_ids:
                # Draft hanya memastikan struktur rute sudah terbentuk.
                # Detail demand, kontak penerima, lot/operator diatur saat status Confirmed.
                incomplete = delivery.do_line_ids.filtered(
                    lambda l: not l.picking_type_id
                    or not l.product_id
                    or not l.route_line_id
                    or not l.location_id
                    or not l.location_dest_id
                )
                if incomplete:
                    seqs = ", ".join(str(l.sequence) for l in incomplete)
                    raise ValidationError(_(
                        "Baris rute berikut belum lengkap (Baris Rute / Tipe Operasi / Produk / Lokasi): %s"
                    ) % seqs)

                # Validasi: Wajib memiliki tepat 1 baris Outgoing (Order Pengiriman)
                outgoing_lines = delivery.do_line_ids.filtered(
                    lambda l: l.picking_type_id.code == "outgoing"
                )
                if len(outgoing_lines) != 1:
                    raise ValidationError(_(
                        "Tugas Pengiriman wajib memiliki tepat 1 baris Rencana DO "
                        "dengan Tipe Operasi 'Order Pengiriman' (Outgoing ke Customer)."
                    ))

                # Validasi: Setiap baris DO wajib memiliki lot aktif dan demand > 0
                zero_demand_lines = delivery.do_line_ids.filtered(
                    lambda l: l.demand_qty <= 0
                    or not l.lot_line_ids.filtered(lambda lot: not lot.wt_is_cancelled and lot.qty > 0)
                )
                if zero_demand_lines:
                    seqs = ", ".join(str(l.sequence) for l in zero_demand_lines)
                    raise ValidationError(_(
                        "Baris DO urutan %s belum memiliki rincian lot atau Demand (kg) masih 0.\n"
                        "Pastikan setiap baris DO sudah diatur lot dan demand-nya sebelum dikonfirmasi."
                    ) % seqs)

                delivery.write({"state": "confirmed"})
                continue

            raise ValidationError(_("Baris Rencana DO belum terbentuk. Pilih ulang Route untuk memuat baris rute."))

    def action_start(self):
        for delivery in self:
            if delivery.state != "confirmed":
                raise ValidationError(_("Hanya Confirmed yang bisa dimulai."))
            delivery.write({"state": "in_progress"})

    def action_complete(self):
        raise ValidationError(_(
            "Selesai Timbang tidak digunakan lagi. Validasi dilakukan bertahap "
            "dari tombol Validasi pada setiap baris Rencana DO."
        ))

    def action_validate(self):
        for delivery in self:
            if not delivery.do_line_ids:
                raise ValidationError(_("Rencana DO wajib memiliki baris rute sebelum divalidasi."))
            delivery._action_validate_do_lines()

    def _action_validate_do_lines(self):
        """Alur baru: buat semua DO dari do_line_ids langsung jadi 'done'."""
        self.ensure_one()
        if self.state not in ("confirmed", "in_progress"):
            raise ValidationError(_("Hanya Confirmed atau In Progress yang bisa divalidasi."))

        self._ensure_backdate_metadata()

        lines_to_generate = self.do_line_ids.filtered(
            lambda l: not l.picking_id or l.picking_id.state != "done"
        )

        for line in lines_to_generate.sorted("sequence"):
            line._action_create_done_picking()

        transit_lines_without_result = self.do_line_ids.filtered(
            lambda l: l._is_transit_route() and not l.generated_transit_lot_id
        )
        if transit_lines_without_result:
            seqs = ", ".join(str(l.sequence) for l in transit_lines_without_result)
            raise ValidationError(_(
                "Validasi belum bisa diselesaikan karena Lot Transit belum terbentuk "
                "pada baris Rencana DO transit berikut: %s"
            ) % seqs)

        self.write({"state": "delivered"})

        # Hitung jumlah picking baru yang digenerate pada langkah akhir ini
        generated_count = len(lines_to_generate)
        if generated_count > 0:
            msg = _(
                "<b>Validasi &amp; Kirim</b> dilakukan oleh %s.<br/>"
                "Dibuat %d Delivery Order baru dengan status Done."
            ) % (self.env.user.name, generated_count)
        else:
            msg = _(
                "<b>Validasi &amp; Kirim</b> dilakukan oleh %s.<br/>"
                "Semua Delivery Order sebelumnya sudah divalidasi secara manual."
            ) % self.env.user.name

        self.message_post(body=Markup(msg))

    def _get_manual_weighing_candidates(self):
        self.ensure_one()
        return self.do_lot_line_ids.filtered(
            lambda line: line.qty > 0.0
            and not line.wt_weighing_source
            and not line.wt_adjustment_applied
            and line.do_line_id.picking_state != "done"
            and (
                line.wt_weighing_source == "manual"
                or (
                    line.wt_physical_qty <= 0.0
                    and line.wt_weighing_source != "device"
                )
            )
        )

    def action_open_manual_weighing(self):
        self.ensure_one()
        if not self.env.user.has_group("weightrack.group_admin"):
            raise ValidationError(_(
                "Only a WeighTrack Administrator can enter manual delivery weighing data."
            ))
        if self.state not in ("confirmed", "in_progress"):
            raise ValidationError(_(
                "Manual weighing input is only available while the delivery is Confirmed or In Progress."
            ))
        if not self._get_manual_weighing_candidates():
            raise ValidationError(_(
                "No unweighed or manually weighed delivery lot is available for manual input."
            ))
        return {
            "name": _("Manual Delivery Weighing"),
            "type": "ir.actions.act_window",
            "res_model": "wt.delivery.manual.weighing.wizard",
            "view_mode": "form",
            "view_id": self.env.ref(
                "weightrack.view_wt_delivery_manual_weighing_wizard_form"
            ).id,
            "target": "new",
            "context": {
                "default_delivery_id": self.id,
            },
        }

    def action_open_backdate_correction(self):
        self.ensure_one()
        if not self.env.user.has_group("weightrack.group_admin"):
            raise ValidationError(_(
                "Only a WeighTrack Administrator can correct an effective delivery date."
            ))
        if self.state != "done":
            raise ValidationError(_(
                "Effective date correction is only available for a completed delivery."
            ))
        return {
            "name": _("Stock Movement Date Correction"),
            "type": "ir.actions.act_window",
            "res_model": "wt.stock.movement.date.correction",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_source_type": "delivery",
                "default_delivery_id": self.id,
                "default_effective_date": self.date,
                "default_company_id": self.company_id.id,
            },
        }

    def action_mark_done(self):
        """Selesaikan pengiriman dari status Terkirim setelah berat diterima diinput."""
        for delivery in self:
            if delivery.state != "delivered":
                raise ValidationError(_(
                    "Hanya pengiriman berstatus Terkirim yang dapat diselesaikan."
                ))
            if not delivery.received_qty or delivery.received_qty <= 0:
                raise ValidationError(_(
                    "Berat Diterima Customer (kg) wajib diisi sebelum menyelesaikan pengiriman."
                ))
            delivery.write({
                "state": "done",
                "validated_at": fields.Datetime.now(),
                "validated_by_id": self.env.user.id,
            })
            delivery.message_post(body=Markup(_(
                "<b>Pengiriman Selesai</b> dikonfirmasi oleh %s.<br/>"
                "Berat Diterima Customer: %s kg | Selisih Pengiriman: %s kg"
            ) % (
                self.env.user.name,
                delivery.received_qty,
                delivery.received_difference_qty,
            )))

    def action_return_delivery(self):
        """Buka popup wizard untuk memasukkan alasan retur sebelum memproses retur."""
        self.ensure_one()
        if self.wt_is_returned:
            raise ValidationError(_("Pengiriman ini sudah diretur."))
        if self.state not in ("delivered", "done"):
            raise ValidationError(_(
                "Retur hanya dapat dilakukan dari status Terkirim atau Selesai."
            ))

        # Cari picking yang berasosiasi dengan delivery ini yang statusnya 'done'
        pickings = self.picking_ids.filtered(lambda p: p.state == "done")
        if not pickings:
            raise ValidationError(_("Tidak ada DO selesai yang dapat diretur."))

        return {
            "name": _("Alasan Retur Pengiriman"),
            "type": "ir.actions.act_window",
            "res_model": "wt.delivery.return.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_delivery_id": self.id,
            }
        }

    def unlink(self):
        for delivery in self:
            if delivery.state != "draft":
                raise ValidationError(_(
                    "Tugas Pengiriman hanya dapat dihapus saat masih berstatus Draft."
                ))
        return super().unlink()

    def action_cancel(self):
        for delivery in self:
            if delivery.state in ("delivered", "done", "returned"):
                raise ValidationError(_(
                    "Dokumen yang sudah terkirim, selesai, atau diretur tidak dapat dibatalkan."
                ))
            done_pickings = delivery.picking_ids.filtered(lambda p: p.state == "done")
            if done_pickings:
                raise ValidationError(_(
                    "Tugas pengiriman ini sudah memiliki DO yang selesai dan tidak dapat "
                    "dibatalkan biasa. Gunakan proses Retur Pengiriman jika stok perlu "
                    "dikembalikan."
                ))
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
            if delivery.picking_ids.filtered(lambda p: p.state == "done"):
                raise ValidationError(_(
                    "Tugas pengiriman yang sudah memiliki DO selesai tidak dapat dikembalikan ke Draft."
                ))
            delivery.write({"state": "draft"})

