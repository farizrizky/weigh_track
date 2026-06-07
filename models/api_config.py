from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ApiConfig(models.Model):
    _name = "wt.api.config"
    _description = "API Configuration"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "company_id"

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )
    bot_user_id = fields.Many2one(
        "res.users",
        string="Bot User",
        required=True,
        ondelete="restrict",
        domain="[('share', '=', False), ('active', '=', True)]",
        tracking=True,
        help="Reserved internal user for future WeighTrack device pull and push processing.",
    )
    pull_enabled = fields.Boolean(
        string="Enable Pull Data",
        default=True,
        tracking=True,
        help="Disable this to temporarily close device pull data endpoints for this company.",
    )
    push_enabled = fields.Boolean(
        string="Enable Push Data",
        default=True,
        tracking=True,
        help="Disable this to temporarily close device push data endpoints for this company.",
    )

    _sql_constraints = [
        (
            "company_uniq",
            "unique(company_id)",
            "API configuration must be unique per company.",
        ),
    ]

    @api.depends("company_id", "bot_user_id")
    def _compute_name(self):
        for config in self:
            config.name = "%s - %s" % (
                config.company_id.name or "",
                config.bot_user_id.name or "",
            )

    @api.constrains("bot_user_id")
    def _check_bot_user_internal(self):
        for config in self:
            if config.bot_user_id.share:
                raise ValidationError(_("Bot user must be an internal user."))
            if not config.bot_user_id.active:
                raise ValidationError(_("Bot user must be active."))

    @api.constrains("company_id")
    def _check_unique_company(self):
        for config in self:
            if not config.company_id:
                continue
            duplicate = self.search(
                [
                    ("id", "!=", config.id),
                    ("company_id", "=", config.company_id.id),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _("Only one API configuration is allowed per company.")
                )

    @api.model
    def get_bot_user(self, company):
        config = self.search([("company_id", "=", company.id)], limit=1)
        if not config:
            raise ValidationError(
                _("Device API bot user has not been configured for this company.")
            )
        return config.bot_user_id
