# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DeliveryReceivedQtyCorrectionWizard(models.TransientModel):
    _name = "wt.delivery.received.qty.correction.wizard"
    _description = "Koreksi Berat Diterima Customer"

    delivery_id = fields.Many2one(
        "wt.delivery",
        string="Delivery",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    shipped_qty = fields.Float(
        string="Berat Terkirim (kg)",
        related="delivery_id.total_physical_qty",
        readonly=True,
        digits="Product Unit of Measure",
    )
    current_received_qty = fields.Float(
        string="Berat Diterima Saat Ini (kg)",
        related="delivery_id.received_qty",
        readonly=True,
        digits="Product Unit of Measure",
    )
    new_received_qty = fields.Float(
        string="Berat Diterima Baru (kg)",
        required=True,
        digits="Product Unit of Measure",
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
            values.setdefault("new_received_qty", delivery.received_qty or 0.0)
        return values

    def action_apply(self):
        self.ensure_one()
        delivery = self.delivery_id

        if delivery.state not in ("done", "returned"):
            raise ValidationError(_(
                "Koreksi berat diterima hanya dapat dilakukan pada delivery dengan status Selesai atau Returned."
            ))

        if self.new_received_qty < 0:
            raise ValidationError(_(
                "Berat diterima tidak boleh bernilai negatif."
            ))

        if not (self.reason or "").strip():
            raise ValidationError(_("Alasan Koreksi wajib diisi."))

        old_qty = delivery.received_qty or 0.0
        new_qty = self.new_received_qty

        delivery.with_context(tracking_disable=False).write({
            "received_qty": new_qty,
        })

        # Catat di chatter
        delivery.message_post(body=Markup(
            "Berat diterima customer dikoreksi dari <b>%(old).2f kg</b> menjadi <b>%(new).2f kg</b> "
            "(selisih: <b>%(diff).2f kg</b>) oleh %(user)s.<br/>"
            "Alasan: %(reason)s"
        ) % {
            "old": old_qty,
            "new": new_qty,
            "diff": new_qty - old_qty,
            "user": self.env.user.display_name,
            "reason": self.reason.strip(),
        })

        return {"type": "ir.actions.act_window_close"}
