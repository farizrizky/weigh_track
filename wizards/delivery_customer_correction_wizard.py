# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DeliveryCustomerCorrectionWizard(models.TransientModel):
    _name = "wt.delivery.customer.correction.wizard"
    _description = "Koreksi Customer Pengiriman"

    delivery_id = fields.Many2one(
        "wt.delivery",
        string="Delivery",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    current_partner_id = fields.Many2one(
        "res.partner",
        string="Customer Saat Ini",
        related="delivery_id.partner_id",
        readonly=True,
    )
    new_partner_id = fields.Many2one(
        "res.partner",
        string="Customer Baru",
        required=True,
    )
    reason = fields.Text(
        string="Alasan Koreksi",
        required=True,
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        delivery_id = values.get("delivery_id") or self.env.context.get(
            "default_delivery_id"
        )
        if delivery_id:
            delivery = self.env["wt.delivery"].browse(delivery_id)
            values.setdefault("new_partner_id", delivery.partner_id.id)
        return values

    def action_apply(self):
        self.ensure_one()
        delivery = self.delivery_id

        if delivery.state == "draft":
            raise ValidationError(_(
                "Koreksi customer hanya dapat dilakukan saat status bukan Draft."
            ))

        if not self.new_partner_id:
            raise ValidationError(_("Harap pilih customer baru."))

        if not (self.reason or "").strip():
            raise ValidationError(_("Alasan Koreksi wajib diisi."))

        old_partner = delivery.partner_id
        new_partner = self.new_partner_id

        # Update partner di delivery utama
        delivery.with_context(tracking_disable=False).write({
            "partner_id": new_partner.id,
        })

        # Update partner di semua do_line (termasuk yang sudah done)
        if delivery.do_line_ids:
            delivery.do_line_ids.write({"partner_id": new_partner.id})

        # Catat di chatter
        delivery.message_post(body=Markup(
            "Customer dikoreksi dari <b>%(old)s</b> menjadi <b>%(new)s</b> oleh %(user)s.<br/>"
            "Alasan: %(reason)s"
        ) % {
            "old": old_partner.display_name if old_partner else "-",
            "new": new_partner.display_name,
            "user": self.env.user.display_name,
            "reason": self.reason.strip(),
        })

        return {"type": "ir.actions.act_window_close"}
