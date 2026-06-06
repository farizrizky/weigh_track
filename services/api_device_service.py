from odoo import _, fields, models


class ApiDeviceService(models.AbstractModel):
    _name = "wt.api.device.service"
    _description = "API Device Service"

    def _response(self):
        return self.env["wt.api.response.service"].sudo()

    def activate_device(self, payload):
        response = self._response()
        token = payload.get("token")
        device_id = payload.get("device_id")
        device_type = payload.get("device_type")
        app_version = payload.get("app_version")

        if not token:
            return response.error("missing_token", _("Token is required."), 400)
        if not device_id:
            return response.error("missing_device_id", _("Device ID is required."), 400)
        if not device_type:
            return response.error("missing_device_type", _("Device type is required."), 400)
        if not app_version:
            return response.error("missing_app_version", _("App version is required."), 400)
        if device_type not in {"mobile", "desktop"}:
            return response.error(
                "invalid_device_type",
                _("Device type must be mobile or desktop."),
                400,
            )

        device = self.env["wt.device"].sudo().search([("token", "=", token)], limit=1)
        if not device:
            return response.error("invalid_token", _("Invalid device token."), 401)
        if device.status != "inactive":
            return response.error(
                "device_not_inactive",
                _("Device token is not available for activation."),
                409,
                device=device,
            )

        duplicate = self.env["wt.device"].sudo().search(
            [
                ("id", "!=", device.id),
                ("device_id", "=", device_id),
            ],
            limit=1,
        )
        if duplicate:
            return response.error(
                "device_id_already_used",
                _("Device ID is already used by another device."),
                409,
                device=device,
            )

        bot_user_result = self.env["wt.api.security.service"].sudo().get_bot_user(
            device.company_id,
            device=device,
        )
        if not bot_user_result["ok"]:
            return bot_user_result

        now = fields.Datetime.now()
        values = {
            "status": "active",
            "device_id": device_id,
            "actived_at": device.actived_at or now,
            "last_seen": now,
            "device_type": device_type,
            "app_version": app_version,
        }
        bot_device = device.with_user(bot_user_result["bot_user"]).sudo().with_context(
            allow_device_state_update=True
        )
        bot_device.write(values)
        device = bot_device

        return response.success(
            {
                "device": self._device_payload(device),
                "company": self._company_payload(device.company_id),
                "employee": self._employee_payload(device.employee_id),
                "role": device.role,
            },
            device=device,
        )

    def _device_payload(self, device):
        return {
            "id": device.id,
            "device_id": device.device_id,
            "name": device.name,
            "status": device.status,
            "device_type": device.device_type,
            "app_version": device.app_version,
            "last_seen": fields.Datetime.to_string(device.last_seen)
            if device.last_seen
            else False,
        }

    def _company_payload(self, company):
        return {
            "id": company.id,
            "name": company.name,
        }

    def _employee_payload(self, employee):
        return {
            "id": employee.id,
            "barcode": employee.barcode if "barcode" in employee._fields else False,
            "name": employee.name,
            "job_position": employee.job_id.name if employee.job_id else False,
        }
