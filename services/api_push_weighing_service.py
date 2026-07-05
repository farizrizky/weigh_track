# -*- coding: utf-8 -*-

from odoo import _, fields, models

from ..constants.roles import Role


class ApiPushWeighingService(models.AbstractModel):
    _name = "wt.api.push.weighing.service"
    _description = "API Push Weighing Service"

    PUSH_ROLES = {Role.OPERATOR}
    def _response(self):
        return self.env["wt.api.response.service"].sudo()

    def push_weighing(self, payload):
        response = self._response()
        auth = self.env["wt.api.security.service"].sudo().authenticate_device(
            payload,
            allowed_roles=self.PUSH_ROLES,
        )
        if not auth["ok"]:
            return auth

        device = auth["device"]
        security = self.env["wt.api.security.service"].sudo()
        push_result = security.check_push_enabled(device.company_id, device=device)
        if not push_result["ok"]:
            return push_result

        bot_user_result = security.get_bot_user(device.company_id, device=device)
        if not bot_user_result["ok"]:
            return bot_user_result
        bot_user = bot_user_result["bot_user"]

        validation = self._validate_root_payload(payload)
        if not validation["ok"]:
            return validation

        items = payload["items"]
        handler = self._handler().with_user(bot_user).with_context(
            lang=bot_user.lang or self.env.lang
        )
        item_validation = handler.validate_items(items)
        if not item_validation["ok"]:
            return item_validation

        now = fields.Datetime.now()
        master_synced_at = self._to_datetime(payload.get("master_synced_at"))
        sent_at = self._to_datetime(payload.get("sent_at"))

        item_results = handler.process_items(
            items,
            payload,
            device,
            bot_user,
            master_synced_at,
            sent_at,
            now,
        )

        device.with_user(bot_user).sudo().with_context(
            allow_device_state_update=True
        ).write(
            {
                "last_seen": now,
                "last_push": now,
                **(
                    {"app_version": payload.get("app_version")}
                    if payload.get("app_version")
                    else {}
                ),
            }
        )

        return response.success(
            {
                "summary": self._summary(item_results),
                "items": item_results,
            },
            device=device,
        )

    def _validate_root_payload(self, payload):
        response = self._response()
        items = payload.get("items")
        if not isinstance(items, list):
            return response.error(
                "missing_items",
                _("Weighing items are required."),
                400,
            )
        if not items:
            return response.error(
                "empty_items",
                _("Weighing items are empty."),
                400,
            )
        if payload.get("master_synced_at") and not self._is_valid_datetime(
            payload.get("master_synced_at")
        ):
            return response.error(
                "invalid_master_synced_at",
                _("Master synced at is invalid."),
                400,
            )
        if payload.get("sent_at") and not self._is_valid_datetime(payload.get("sent_at")):
            return response.error(
                "invalid_sent_at",
                _("Sent at is invalid."),
                400,
            )
        return {"ok": True}

    def _handler(self):
        return self.env["wt.weighing.service"].sudo()

    def _summary(self, items):
        return {
            "received": len(items),
            "created": sum(1 for item in items if item.get("status") == "created"),
            "duplicates": sum(
                1 for item in items if item.get("status") == "duplicate"
            ),
            "with_data_problem": sum(
                1 for item in items if item.get("has_data_problem")
            ),
            "weighing_ids": sorted(
                {
                    item["weighing_id"]
                    for item in items
                    if item.get("weighing_id")
                }
            ),
        }

    def _to_datetime(self, value):
        return fields.Datetime.to_datetime(value) if value else False

    def _is_valid_datetime(self, value):
        try:
            return bool(fields.Datetime.to_datetime(value))
        except (TypeError, ValueError):
            return False
