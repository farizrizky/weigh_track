# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DeliveryDoWizard(models.TransientModel):
    _name = "wt.delivery.do.wizard"
    _description = "Wizard Buat Delivery Order"

    delivery_id = fields.Many2one(
        "wt.delivery",
        string="Tugas Pengiriman",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        related="delivery_id.company_id",
        store=True,
        readonly=True,
    )
    picking_type_id = fields.Many2one(
        "stock.picking.type",
        string="Tipe Operasi",
        required=True,
        domain="[('code', '=', 'outgoing'), ('company_id', '=', company_id)]",
        options="{'no_create': True, 'no_open': True}",
    )
    operator_id = fields.Many2one(
        "hr.employee",
        string="Operator",
        required=True,
        help="Operator yang bertanggung jawab atas Delivery Order ini.",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Lokasi Sumber",
        domain="[('usage', '=', 'internal')]",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Alamat Tujuan",
        help="Alamat tujuan pengiriman. Akan otomatis terisi di form Delivery Order.",
    )
    scheduled_date = fields.Datetime(
        string="Tanggal Terjadwal",
        default=fields.Datetime.now,
    )

    @api.onchange("picking_type_id")
    def _onchange_picking_type_id(self):
        """Auto-isi lokasi sumber dari tipe operasi yang dipilih."""
        if self.picking_type_id:
            self.location_id = self.picking_type_id.default_location_src_id

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        delivery_id = self.env.context.get("default_delivery_id")
        if delivery_id:
            delivery = self.env["wt.delivery"].browse(delivery_id)
            res["scheduled_date"] = delivery._get_planned_movement_datetime()
            picking_type = self.env["stock.picking.type"].search(
                [
                    ("code", "=", "outgoing"),
                    ("company_id", "=", delivery.company_id.id),
                ],
                limit=1,
            )
            if picking_type:
                res["picking_type_id"] = picking_type.id
                res["location_id"] = picking_type.default_location_src_id.id or False
        return res

    def action_create_do(self):
        """Buat stock.picking baru, lalu tutup wizard (kembali ke delivery form)."""
        self.ensure_one()
        delivery = self.delivery_id
        if delivery.state not in ("draft", "confirmed"):
            raise ValidationError(
                _("DO baru hanya bisa ditambahkan saat status Draft atau Confirmed.")
            )

        self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_id.id,
                "location_id": self.location_id.id
                if self.location_id
                else self.picking_type_id.default_location_src_id.id,
                "location_dest_id": self.picking_type_id.default_location_dest_id.id,
                "partner_id": self.partner_id.id if self.partner_id else False,
                "scheduled_date": self.scheduled_date,
                "wt_delivery_id": delivery.id,
                "wt_operator_id": self.operator_id.id,
                "origin": delivery.name,
                "company_id": delivery.company_id.id,
            }
        )

        # Tutup wizard — kembali ke form delivery tanpa navigasi halaman baru
        return {"type": "ir.actions.act_window_close"}
