from odoo import http

from ..api_handler import ApiHandler


class DeviceApiController(http.Controller):
    @http.route(
        "/weightrack/api/v1/device/activate",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def activate(self, **kwargs):
        return ApiHandler().handle(
            "device.activate",
            "wt.api.device.service",
            "activate_device",
        )
