from odoo import fields, models


class Estate(models.Model):
    _name = "wt.estate"
    _description = "Estate"
    _order = "code, name"

    code = fields.Char(string="Code", required=True, index=True)
    name = fields.Char(string="Name", required=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "code_company_uniq",
            "unique(code, company_id)",
            "Estate code must be unique per company.",
        ),
    ]
