# -*- coding: utf-8 -*-
import os

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class WeighingManualLog(models.Model):
    _name = "wt.weighing.manual.log"
    _description = "Weighing Manual Log"
    _order = "date desc, id desc"
    _rec_name = "local_id"
    _sql_constraints = [
        ("local_id_unique", "UNIQUE(local_id)", "Local ID harus unik."),
    ]

    local_id = fields.Char(
        string="Local ID",
        required=True,
        index=True,
        readonly=True,
    )
    date = fields.Datetime(
        string="Date",
        readonly=True,
    )
    manual_reason = fields.Text(
        string="Manual Reason",
        readonly=True,
    )
    # Path relatif file gambar di filesystem (base64 dari device disimpan sebagai file)
    image_path = fields.Char(
        string="Path Gambar",
        readonly=True,
        index=False,
    )

    # Computed HTML untuk menampilkan gambar di form view
    image_html = fields.Html(
        string="Foto",
        compute="_compute_image_html",
        sanitize=False,
        readonly=True,
    )

    @api.depends("image_path")
    def _compute_image_html(self):
        for rec in self:
            if rec.image_path:
                rec.image_html = (
                    f'<div style="text-align:center;">'
                    f'<img src="/weightrack/manual_log_image/{rec.id}"'
                    f' style="max-width:400px; max-height:400px; border-radius:8px;"'
                    f' alt="Foto Timbang Manual"/>'
                    f'</div>'
                )
            else:
                rec.image_html = False
    # Relasi ke wt.weighing yang memakai log ini
    weighing_ids = fields.One2many(
        "wt.weighing",
        "manual_log_id",
        string="Penimbangan",
        readonly=True,
    )
    device_id = fields.Char(
        string="Device ID",
        index=True,
        readonly=True,
    )
    device_record_id = fields.Many2one(
        "wt.device",
        string="Device",
        ondelete="set null",
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        readonly=True,
    )
    received_at = fields.Datetime(
        string="Diterima Pada",
        readonly=True,
    )

    def unlink(self):
        for rec in self:
            if rec.weighing_ids:
                raise UserError(
                    _("Timbang Manual Log '%s' tidak dapat dihapus karena masih memiliki penimbangan terkait.")
                    % rec.local_id
                )
        return super().unlink()
