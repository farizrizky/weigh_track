from odoo import http

from ..api_handler import ApiHandler


class PushApiController(http.Controller):
    @http.route(
        "/weightrack/api/v1/push/weighing",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def push_weighing(self, **kwargs):
        return ApiHandler().handle(
            "push.weighing",
            "wt.api.push.weighing.service",
            "push_weighing",
        )

    @http.route(
        "/weightrack/api/v1/push/stock-opname",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def push_stock_opname(self, **kwargs):
        return ApiHandler().handle(
            "push.stock_opname",
            "wt.api.stock.opname.service",
            "push_stock_opname",
        )
