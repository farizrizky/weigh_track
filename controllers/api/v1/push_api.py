from odoo import http

from ..api_handler import ApiHandler


class PushApiController(http.Controller):
    @http.route(
        "/weightrack/api/v1/push/weighing-cup-lump",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def push_weighing_cup_lump(self, **kwargs):
        return ApiHandler().handle(
            "push.weighing_cup_lump",
            "wt.api.push.weighing.cup.lump.service",
            "push_weighing_cup_lump",
        )
