# -*- coding: utf-8 -*-

from pytz import UTC
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DeliveryManualWeighingWizard(models.TransientModel):
    _name = "wt.delivery.manual.weighing.wizard"
    _description = "Manual Delivery Weighing"

    delivery_id = fields.Many2one(
        "wt.delivery",
        string="Delivery",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    effective_date = fields.Date(
        string="Effective Date",
        related="delivery_id.date",
        readonly=True,
    )
    reason = fields.Text(
        string="Manual Input Reason",
        required=True,
    )
    line_ids = fields.One2many(
        "wt.delivery.manual.weighing.wizard.line",
        "wizard_id",
        string="Weighing Data",
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        delivery_id = values.get("delivery_id") or self.env.context.get(
            "default_delivery_id"
        )
        if not delivery_id:
            return values

        delivery = self.env["wt.delivery"].browse(delivery_id).exists()
        if not delivery:
            return values
        effective_datetime = (
            delivery.backdate_effective_at
            or delivery._get_planned_movement_datetime()
        )
        commands = []
        for lot_line in delivery._get_manual_weighing_candidates().sorted(
            lambda line: (
                line.do_line_id.sequence or 0,
                line.lot_id.name or "",
                line.id,
            )
        ):
            weighing_location = lot_line.weighing_location_id
            if not weighing_location and len(lot_line.allowed_weighing_location_ids) == 1:
                weighing_location = lot_line.allowed_weighing_location_ids[:1]
            commands.append((0, 0, {
                "selected": True,
                "do_lot_line_id": lot_line.id,
                "weighing_location_id": weighing_location.id,
                "weighed_at": effective_datetime,
            }))
        values["delivery_id"] = delivery.id
        values["line_ids"] = commands
        return values

    def _validate_delivery(self):
        self.ensure_one()
        delivery = self.delivery_id
        if not self.env.user.has_group("weightrack.group_admin"):
            raise ValidationError(_(
                "Only a WeighTrack Administrator can enter manual delivery weighing data."
            ))
        if not delivery.is_backdated:
            raise ValidationError(_(
                "Manual weighing input is only available for a backdated delivery."
            ))
        if delivery.state not in ("confirmed", "in_progress"):
            raise ValidationError(_(
                "Manual weighing input is only available while the delivery is Confirmed or In Progress."
            ))
        if not (self.reason or "").strip():
            raise ValidationError(_("Manual Input Reason is required."))

    def action_apply(self):
        self.ensure_one()
        self._validate_delivery()
        delivery = self.delivery_id
        selected_lines = self.line_ids.filtered("selected")
        if not selected_lines:
            raise ValidationError(_("Select at least one weighing line."))

        prepared_values = []
        for wizard_line in selected_lines:
            target = wizard_line.do_lot_line_id
            if not target or target.delivery_id != delivery:
                raise ValidationError(_(
                    "A selected weighing line no longer belongs to this delivery."
                ))
            if target.wt_physical_qty > 0.0 or target.wt_weighing_source:
                raise ValidationError(_(
                    "Lot %(lot)s already has weighing data and cannot be overwritten manually."
                ) % {"lot": target.lot_id.display_name})
            if target.wt_adjustment_applied:
                raise ValidationError(_(
                    "Lot %(lot)s already has an applied stock adjustment."
                ) % {"lot": target.lot_id.display_name})
            if wizard_line.physical_qty <= 0.0:
                raise ValidationError(_(
                    "Physical Weight must be greater than zero for lot %(lot)s."
                ) % {"lot": target.lot_id.display_name})
            if not wizard_line.weighing_location_id:
                raise ValidationError(_(
                    "Weighing Location is required for lot %(lot)s."
                ) % {"lot": target.lot_id.display_name})
            if (
                wizard_line.weighing_location_id
                not in target.allowed_weighing_location_ids
            ):
                raise ValidationError(_(
                    "Weighing Location is not allowed for lot %(lot)s."
                ) % {"lot": target.lot_id.display_name})
            if not wizard_line.operator_id:
                raise ValidationError(_(
                    "The selected Weighing Location has no Operator for lot %(lot)s."
                ) % {"lot": target.lot_id.display_name})
            if not wizard_line.weighed_at:
                raise ValidationError(_(
                    "Weighed At is required for lot %(lot)s."
                ) % {"lot": target.lot_id.display_name})

            weighed_datetime = fields.Datetime.to_datetime(wizard_line.weighed_at)
            local_date = UTC.localize(weighed_datetime).astimezone(
                delivery._get_business_timezone()
            ).date()
            if local_date != delivery.date:
                raise ValidationError(_(
                    "Weighed At for lot %(lot)s must be on the Delivery Effective Date %(date)s."
                ) % {
                    "lot": target.lot_id.display_name,
                    "date": delivery.date,
                })
            prepared_values.append((wizard_line, target))

        input_at = fields.Datetime.now()
        reason = self.reason.strip()
        detail_lines = []
        for wizard_line, target in prepared_values:
            target.write({
                "weighing_location_id": wizard_line.weighing_location_id.id,
                "wt_physical_qty": wizard_line.physical_qty,
                "wt_weighed_at": wizard_line.weighed_at,
                "wt_note": wizard_line.note or False,
                "wt_weighing_source": "manual",
                "wt_manual_input_by_id": self.env.user.id,
                "wt_manual_input_at": input_at,
                "wt_manual_reason": reason,
            })
            detail_lines.append(
                "%s: %.4f kg" % (
                    target.lot_id.display_name,
                    wizard_line.physical_qty,
                )
            )

        delivery.message_post(body=Markup(
            "<b>%s</b><br/>%s<br/><b>%s</b> %s"
        ) % (
            escape(_("Manual Delivery Weighing")),
            Markup("<br/>").join(escape(detail) for detail in detail_lines),
            escape(_("Reason:")),
            escape(reason),
        ))
        return {
            "type": "ir.actions.act_window",
            "res_model": "wt.delivery",
            "res_id": delivery.id,
            "view_mode": "form",
            "view_id": self.env.ref("weightrack.view_wt_delivery_form").id,
            "target": "current",
        }


class DeliveryManualWeighingWizardLine(models.TransientModel):
    _name = "wt.delivery.manual.weighing.wizard.line"
    _description = "Manual Delivery Weighing Line"
    _order = "id"

    wizard_id = fields.Many2one(
        "wt.delivery.manual.weighing.wizard",
        required=True,
        ondelete="cascade",
    )
    selected = fields.Boolean(
        string="Select",
        default=True,
    )
    do_lot_line_id = fields.Many2one(
        "wt.delivery.do.line.lot",
        string="Delivery Lot Line",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    do_line_id = fields.Many2one(
        "wt.delivery.do.line",
        string="Delivery Plan",
        related="do_lot_line_id.do_line_id",
        readonly=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot",
        related="do_lot_line_id.lot_id",
        readonly=True,
    )
    demand_qty = fields.Float(
        string="Demand (kg)",
        related="do_lot_line_id.qty",
        readonly=True,
    )
    allowed_weighing_location_ids = fields.Many2many(
        "wt.weighing.location",
        related="do_lot_line_id.allowed_weighing_location_ids",
        readonly=True,
    )
    weighing_location_id = fields.Many2one(
        "wt.weighing.location",
        string="Weighing Location",
        domain="[('id', 'in', allowed_weighing_location_ids)]",
    )
    operator_id = fields.Many2one(
        "hr.employee",
        string="Operator",
        related="weighing_location_id.operator_id",
        readonly=True,
    )
    physical_qty = fields.Float(
        string="Physical Weight (kg)",
        digits="Product Unit of Measure",
    )
    weighed_at = fields.Datetime(
        string="Weighed At",
    )
    note = fields.Char(
        string="Notes",
    )
