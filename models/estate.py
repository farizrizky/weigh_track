from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Estate(models.Model):
    _name = "wt.estate"
    _description = "Estate"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "code, name"

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
    _sql_constraints = [
        (
            "code_company_uniq",
            "unique(code, company_id)",
            "Estate code must be unique per company.",
        ),
    ]

    @api.constrains("code", "company_id")
    def _check_unique_code_company(self):
        for estate in self:
            duplicate = self.search_count(
                [
                    ("id", "!=", estate.id),
                    ("code", "=", estate.code),
                    ("company_id", "=", estate.company_id.id),
                ]
            )
            if duplicate:
                raise ValidationError(_("Estate code must be unique per company."))
