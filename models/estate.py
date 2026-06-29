from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Estate(models.Model):
    _name = "wt.estate"
    _description = "Estate"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "code, name"

    active = fields.Boolean(default=True, tracking=True)
    code = fields.Char(string="Code", required=True, index=True, tracking=True)
    name = fields.Char(string="Name", required=True, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )
    def init(self):
        self.env.cr.execute(
            """
            ALTER TABLE wt_estate
            DROP CONSTRAINT IF EXISTS wt_estate_code_company_uniq
            """
        )
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS wt_estate_code_company_active_uniq
            ON wt_estate (code, company_id)
            WHERE active
            """
        )

    @api.constrains("code", "company_id")
    def _check_unique_code_company(self):
        for estate in self:
            duplicate = self.search_count(
                [
                    ("id", "!=", estate.id),
                    ("code", "=", estate.code),
                    ("company_id", "=", estate.company_id.id),
                    ("active", "=", True),
                ]
            )
            if estate.active and duplicate:
                raise ValidationError(_("Estate code must be unique per company."))
