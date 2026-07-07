# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DeliveryRoute(models.Model):
    _name = "wt.delivery.route"
    _description = "Konfigurasi Rute Transit Pengiriman"
    _order = "name"

    name = fields.Char(
        string="Nama Rute",
        required=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        required=True,
        default=lambda self: self.env.company,
    )
    source_location_id = fields.Many2one(
        "stock.location",
        string="Lokasi Asal",
        required=True,
        domain="[('usage', '=', 'internal')]",
        help="Lokasi stok asal pengambilan barang (misal: G1/Lokasi-A).",
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
        domain="[('usage', 'in', ['internal', 'transit', 'customer'])]",
        help="Lokasi transit tujuan di gudang berikutnya atau customer (misal: G2/stock/transit atau Partner Locations/Customers).",
    )
    active = fields.Boolean(
        string="Aktif",
        default=True,
    )
    is_transit = fields.Boolean(
        string="Lokasi Tujuan adalah Transit",
        default=False,
        help=(
            "Centang jika lokasi tujuan rute ini adalah lokasi transit/holding internal "
            "(bukan customer langsung). Digunakan oleh aplikasi timbangan untuk menentukan "
            "mode penimbangan: Transit → timbangan RAM (manual), Stok/Divisi → timbangan digital (otomatis)."
        ),
    )

    @api.constrains("source_location_id", "transit_location_id")
    def _check_locations_different(self):
        for rec in self:
            if rec.source_location_id == rec.transit_location_id:
                raise ValidationError(_(
                    "Lokasi asal dan lokasi transit tidak boleh sama pada rute '%s'."
                ) % rec.name)



