# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Drc(models.Model):
    _name = "wt.drc"
    _description = "DRC (Dry Rubber Content)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "state asc, valid_from desc, id desc"

    name = fields.Char(
        string="Nomor",
        default="/",
        readonly=True,
        copy=False,
        index=True,
        tracking=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Divisi",
        required=True,
        tracking=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="division_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    estate_id = fields.Many2one(
        "wt.estate",
        string="Estate",
        related="division_id.estate_id",
        store=True,
        readonly=True,
        index=True,
    )
    percentage = fields.Float(
        string="Persentase DRC (%)",
        required=True,
        digits=(5, 1),
        tracking=True,
    )
    valid_from = fields.Date(
        string="Berlaku Dari",
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    valid_until = fields.Date(
        string="Berlaku Sampai",
        required=True,
        tracking=True,
    )
    notes = fields.Text(
        string="Catatan",
    )
    is_active_drc = fields.Boolean(
        string="Aktif",
        compute="_compute_is_active_drc",
        store=True,
        index=True,
    )
    state = fields.Selection(
        selection=[
            ("active", "Aktif"),
            ("expired", "Kadaluarsa"),
        ],
        string="Status",
        compute="_compute_is_active_drc",
        store=True,
    )

    # -------------------------------------------------------------------------
    # Compute
    # -------------------------------------------------------------------------

    @api.depends("valid_until")
    def _compute_is_active_drc(self):
        today = fields.Date.today()
        for rec in self:
            active = bool(rec.valid_until and rec.valid_until >= today)
            rec.is_active_drc = active
            rec.state = "active" if active else "expired"

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains("percentage")
    def _check_percentage(self):
        for rec in self:
            if rec.percentage <= 0 or rec.percentage > 100:
                raise ValidationError(
                    _("Persentase DRC harus berada di antara 0 dan 100.")
                )

    @api.constrains("valid_from", "valid_until")
    def _check_valid_dates(self):
        for rec in self:
            if rec.valid_from and rec.valid_until and rec.valid_from > rec.valid_until:
                raise ValidationError(
                    _("Tanggal 'Berlaku Dari' tidak boleh lebih besar dari 'Berlaku Sampai'.")
                )

    @api.constrains("division_id", "valid_from", "valid_until")
    def _check_no_active_drc(self):
        """
        Validasi: tidak boleh ada lebih dari satu DRC aktif untuk divisi yang sama.
        DRC dianggap aktif jika valid_until >= hari ini.
        """
        today = fields.Date.today()
        for rec in self:
            if not rec.division_id or not rec.valid_until:
                continue
            # Cek apakah DRC ini sendiri aktif; kalau tidak, skip validasi
            if rec.valid_until < today:
                continue
            conflict = self.search(
                [
                    ("id", "!=", rec.id),
                    ("division_id", "=", rec.division_id.id),
                    ("valid_until", ">=", today),
                ],
                limit=1,
            )
            if conflict:
                raise ValidationError(
                    _(
                        "Divisi '%(division)s' masih memiliki DRC aktif "
                        "(%(name)s, berlaku sampai %(until)s). "
                        "Data DRC baru tidak dapat ditambahkan sebelum DRC tersebut berakhir.",
                        division=rec.division_id.display_name,
                        name=conflict.name,
                        until=conflict.valid_until,
                    )
                )

    # -------------------------------------------------------------------------
    # ORM Override
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("wt.drc") or "/"
        return super().create(vals_list)
