import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Field(models.Model):
    _name = "wt.field"
    _description = "Field"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    active = fields.Boolean(default=True, tracking=True)
    name = fields.Char(
        string="Field",
        required=True,
        index=True,
        tracking=True,
    )
    clone = fields.Char(
        string="Clone",
        tracking=True,
    )
    ha = fields.Float(
        string="HA",
        digits=(16, 2),
        tracking=True,
    )
    planting_year = fields.Char(
        string="Tahun Tanam",
        size=4,
        tracking=True,
    )
    division_ids = fields.Many2many(
        "wt.division",
        "wt_field_division_rel",
        "field_id",
        "division_id",
        string="Divisi",
        tracking=True,
    )

    def init(self):
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS wt_field_name_active_uniq
            ON wt_field (name)
            WHERE active
            """
        )

    @api.constrains("name", "active")
    def _check_unique_name(self):
        for record in self:
            if not (record.active and record.name):
                continue
            duplicate = self.search(
                [
                    ("id", "!=", record.id),
                    ("name", "=", record.name),
                    ("active", "=", True),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _("Field name must be unique. '%s' is already used.") % record.name
                )

    @api.constrains("planting_year")
    def _check_planting_year(self):
        for record in self:
            if not record.planting_year:
                continue
            if not re.fullmatch(r"\d{4}", record.planting_year):
                raise ValidationError(
                    _("Tahun Tanam harus berupa 4 digit angka tahun (contoh: 2010).")
                )

    @api.onchange("planting_year")
    def _onchange_planting_year(self):
        if self.planting_year:
            digits_only = re.sub(r"\D", "", self.planting_year)
            self.planting_year = digits_only[:4]

