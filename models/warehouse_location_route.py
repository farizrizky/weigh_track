# -*- coding: utf-8 -*-

from odoo import _, fields, models


class WarehouseLocationRoute(models.Model):
    _name = "wt.warehouse.location.route"
    _description = "Rute Lokasi Gudang (Sumber → Transit)"
    _order = "name"

    name = fields.Char(
        string="Label Rute",
        required=True,
    )
    source_location_id = fields.Many2one(
        "stock.location",
        string="Lokasi Sumber",
        required=True,
        domain="[('usage', '=', 'internal')]",
        help="Lokasi asal lot sebelum dipindahkan (mis. G1/Lok-A, G1/Lok-B).",
    )
    picking_type_id = fields.Many2one(
        "stock.picking.type",
        string="Tipe Operasi",
        domain="[('code', 'in', ('outgoing', 'internal'))]",
        help="Tipe operasi default untuk rute ini.",
    )
    transit_location_id = fields.Many2one(
        "stock.location",
        string="Lokasi Transit Tujuan",
        required=True,
        domain="[('usage', 'in', ('internal', 'transit'))]",
        help="Lokasi transit tujuan setelah Internal Transfer (mis. G2/stock/transit).",
    )
    active = fields.Boolean(
        string="Aktif",
        default=True,
    )

    _sql_constraints = [
        (
            "unique_source_location",
            "UNIQUE(source_location_id)",
            "Setiap lokasi sumber hanya boleh memiliki satu rute transit.",
        ),
    ]
