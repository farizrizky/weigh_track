# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockOpnameDifferenceReason(models.Model):
    _name = "wt.stock.opname.difference.reason"
    _description = "Alasan Selisih Stock Opname"
    _order = "sequence, name"

    DIFFERENCE_TYPE_SELECTION = [
        ("susut", "SUSUT"),
        ("hilang", "HILANG"),
        ("salah", "SALAH"),
        ("lainnya", "LAINNYA"),
    ]

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
    difference_type = fields.Selection(
        DIFFERENCE_TYPE_SELECTION,
        string="Tipe Selisih",
        required=True,
        default="lainnya",
        index=True,
    )
    location_dest_id = fields.Many2one(
        "stock.location",
        string="Lokasi Stock",
        required=True,
        domain="[('usage', 'not in', ['view'])]",
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
    is_system_default = fields.Boolean(
        string="Default Sistem",
        default=False,
        readonly=True,
        copy=False,
    )

    _sql_constraints = [
        (
            "code_company_uniq",
            "unique(code, company_id)",
            "Kode alasan harus unik per perusahaan.",
        )
    ]

    def _allow_system_default_write(self):
        return self.env.context.get("install_mode") or self.env.context.get("module")

    def write(self, vals):
        if vals and not self._allow_system_default_write():
            protected = self.filtered("is_system_default")
            if protected:
                raise ValidationError(_(
                    "Alasan selisih default sistem tidak dapat diubah. "
                    "Silahkan tambahkan alasan selisih baru jika membutuhkan variasi lain."
                ))
        return super().write(vals)

    def unlink(self):
        protected = self.filtered("is_system_default")
        if protected:
            raise ValidationError(_(
                "Alasan selisih default sistem tidak dapat dihapus."
            ))
        return super().unlink()
