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
