from odoo import _, models


class ApiSecurityService(models.AbstractModel):
    _name = "wt.api.security.service"
    _description = "API Security Service"

    def _response(self):
        return self.env["wt.api.response.service"].sudo()

    def get_api(self, company, device=False):
        response = self._response()
        config = self.env["wt.api"].sudo().search(
            [("company_id", "=", company.id)],
            limit=1,
        )
        if not config:
            return response.error(
                "api_missing",
                _("Device API bot user has not been configured for this company."),
                500,
                device=device,
            )
        return {"ok": True, "config": config}

    def authenticate_device(self, payload, allowed_roles=False):
        response = self._response()
        token = payload.get("token")
        device_id = payload.get("device_id")

        if not token:
            return response.error("missing_token", _("Token is required."), 400)
        if not device_id:
            return response.error("missing_device_id", _("Device ID is required."), 400)

        device = self.env["wt.device"].sudo().search(
            [
                ("token", "=", token),
                ("device_id", "=", device_id),
            ],
            limit=1,
        )
        if not device:
            return response.error(
                "invalid_device_credentials",
                _("Invalid device credentials."),
                401,
            )
        if device.status != "active":
            return response.error(
                "device_not_active",
                _("Device must be active."),
                403,
                device=device,
            )
        if allowed_roles and device.role not in set(allowed_roles):
            return response.error(
                "role_not_allowed",
                _("Device role is not allowed for this endpoint."),
                403,
                device=device,
            )

        return {"ok": True, "device": device}

    def check_pull_enabled(self, company, device=False):
        config_result = self.get_api(company, device=device)
        if not config_result["ok"]:
            return config_result

        config = config_result["config"]
        if not config.pull_enabled:
            return self._response().error(
                "pull_closed",
                _("Pull data is closed for this company."),
                403,
                device=device,
            )
        return {"ok": True, "config": config}

    def check_push_enabled(self, company, device=False):
        config_result = self.get_api(company, device=device)
        if not config_result["ok"]:
            return config_result

        config = config_result["config"]
        if not config.push_enabled:
            return self._response().error(
                "push_closed",
                _("Push data is closed for this company."),
                403,
                device=device,
            )
        return {"ok": True, "config": config}

    def get_bot_user(self, company, device=False):
        config_result = self.get_api(company, device=device)
        if not config_result["ok"]:
            return config_result

        response = self._response()
        config = config_result["config"]
        if not config.bot_user_id.active or config.bot_user_id.share:
            return response.error(
                "api_invalid",
                _("Device API bot user must be an active internal user."),
                500,
                device=device,
            )
        return {"ok": True, "bot_user": config.bot_user_id}
