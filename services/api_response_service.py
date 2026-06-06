from odoo import _, models


class ApiResponseService(models.AbstractModel):
    _name = "wt.api.response.service"
    _description = "API Response Service"

    def success(self, data, http_status=200, device=False):
        return {
            "ok": True,
            "http_status": http_status,
            "data": data,
            "device": device,
        }

    def error(self, code, message, http_status, device=False):
        return {
            "ok": False,
            "http_status": http_status,
            "error": {
                "code": code,
                "message": str(message),
            },
            "device": device,
        }

    def body(self, request_id, result):
        response_body = {
            "ok": bool(result.get("ok")),
            "request_id": request_id,
        }
        if result.get("ok"):
            response_body["data"] = result.get("data") or {}
        else:
            response_body["error"] = result.get("error") or {
                "code": "unknown_error",
                "message": _("Unknown API error."),
            }
        return response_body
