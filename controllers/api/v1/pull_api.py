from odoo import http

from ..api_handler import ApiHandler


class PullApiController(http.Controller):
    @http.route(
        "/weightrack/api/v1/pull/master",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def pull_master(self, **kwargs):
        return ApiHandler().handle(
            "pull.master",
            "wt.api.pull.master.service",
            "pull_master",
        )

    @http.route(
        "/weightrack/api/v1/pull/stock-opname",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def pull_stock_opname(self, **kwargs):
        return ApiHandler().handle(
            "pull.stock_opname",
            "wt.api.stock.opname.service",
            "pull_stock_opname",
        )

