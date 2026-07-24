# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError


class DeliveryReturnWizard(models.TransientModel):
    _name = "wt.delivery.return.wizard"
    _description = "Wizard Retur Tugas Pengiriman"

    delivery_id = fields.Many2one(
        "wt.delivery",
        string="Tugas Pengiriman",
        required=True,
        readonly=True,
    )
    reason = fields.Text(
        string="Alasan Retur",
        required=True,
        help="Wajib memasukkan alasan mengapa pengiriman ini diretur.",
    )

    def action_confirm(self):
        self.ensure_one()
        delivery = self.delivery_id
        if delivery.wt_is_returned:
            raise ValidationError(_("Pengiriman ini sudah diretur."))

        # Cari picking yang berasosiasi dengan delivery ini yang statusnya 'done'
        pickings = delivery.picking_ids.filtered(lambda p: p.state == "done")
        if not pickings:
            raise ValidationError(_("Tidak ada DO selesai yang dapat diretur."))

        # Filter rute outgoing jika ada outgoing
        outgoing_pickings = pickings.filtered(lambda p: p.picking_type_id.code == "outgoing")
        pickings_to_return = outgoing_pickings if outgoing_pickings else pickings

        returned_pickings = []
        for picking in pickings_to_return:
            # Panggil wizard return standard Odoo
            wizard = self.env["stock.return.picking"].with_context(
                active_id=picking.id,
                active_ids=[picking.id],
                active_model="stock.picking",
                wt_allow_return=True,
            ).create({})
            
            # Buat return picking dengan kuantitas penuh
            res = wizard.action_create_returns_all()
            return_picking_id = res.get("res_id")
            if return_picking_id:
                return_picking = self.env["stock.picking"].browse(return_picking_id)
                delivery.do_line_ids.filtered(
                    lambda line: line.picking_id == picking
                ).write({
                    "return_picking_id": return_picking.id,
                })
                # Validasi otomatis return picking ke status 'done'
                return_picking.with_context(
                    skip_backorder=True,
                    no_backorder=True,
                    skip_immediate=True,
                    wt_force_validate=True,
                ).button_validate()
                returned_pickings.append(return_picking.name)

        if returned_pickings:
            delivery.write({
                "state": "returned",
                "wt_is_returned": True,
                "wt_return_reason": self.reason,
            })
            delivery.message_post(
                body=_(
                    "<b>Retur Pengiriman Berhasil</b>.<br/>"
                    "Alasan Retur: %s<br/>"
                    "Dokumen retur terbentuk dan divalidasi: %s"
                ) % (self.reason, ", ".join(returned_pickings))
            )
        return {"type": "ir.actions.act_window_close"}


class StockReturnPicking(models.TransientModel):
    _inherit = "stock.return.picking"

    @api.model
    def default_get(self, fields_list):
        res = super(StockReturnPicking, self).default_get(fields_list)
        # Ambil picking_id dari context
        active_id = self.env.context.get("active_id")
        active_model = self.env.context.get("active_model")
        
        if active_model == "stock.picking" and active_id:
            picking = self.env["stock.picking"].browse(active_id)
            if picking.wt_delivery_id and not self.env.context.get("wt_allow_return"):
                raise UserError(_(
                    "DO ini dibuat dari Tugas Pengiriman '%s'.\n\n"
                    "Proses retur hanya dapat dilakukan melalui tombol 'Retur Pengiriman' "
                    "di dokumen Tugas Pengiriman WeighTrack."
                ) % picking.origin)
        return res
