# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockOpnameDifferenceReason(models.Model):
    _name = "wt.stock.opname.difference.reason"
    _description = "Alasan Selisih Stock Opname"
    _order = "sequence, name"

    name = fields.Char(
        string="Nama Alasan",
        required=True,
        translate=True,
    )
    code = fields.Char(
        string="Kode",
        required=True,
        help="Kode singkat unik untuk alasan ini (contoh: SUSUT, HILANG, RUSAK).",
    )
    sequence = fields.Integer(
        string="Urutan",
        default=10,
    )
    location_dest_id = fields.Many2one(
        "stock.location",
        string="Lokasi Tujuan Default",
        required=True,
        domain="[('usage', 'not in', ['view'])]",
        help="Lokasi tujuan untuk selisih/susut. "
             "Pilih lokasi virtual loss Anda (tipe: Virtual Locations). "
             "Jika belum ada, buat dulu di Inventori > Konfigurasi > Lokasi "
             "dengan tipe 'Virtual Locations'.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        default=lambda self: self.env.company,
        index=True,
    )
    active = fields.Boolean(
        string="Aktif",
        default=True,
    )
    description = fields.Text(
        string="Keterangan",
    )

    _sql_constraints = [
        (
            "code_company_uniq",
            "unique(code, company_id)",
            "Kode alasan harus unik per perusahaan.",
        )
    ]
