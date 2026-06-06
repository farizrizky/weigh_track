from odoo import _, models


class ApiSecurityService(models.AbstractModel):
    _name = "wt.api.security.service"
    _description = "API Security Service"

    def _response(self):
        return self.env["wt.api.response.service"].sudo()

    def get_bot_user(self, company, device=False):
        response = self._response()
        config = self.env["wt.api.config"].sudo().search(
            [("company_id", "=", company.id)],
            limit=1,
        )
        if not config:
            return response.error(
                "api_config_missing",
                _("Device API bot user has not been configured for this company."),
                500,
                device=device,
            )
        if not config.bot_user_id.active or config.bot_user_id.share:
            return response.error(
                "api_config_invalid",
                _("Device API bot user must be an active internal user."),
                500,
                device=device,
            )
        return {"ok": True, "bot_user": config.bot_user_id}
