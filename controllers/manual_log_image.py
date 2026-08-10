# -*- coding: utf-8 -*-
import mimetypes
import os

import odoo.tools.config as odoo_config
from odoo import http
from odoo.http import request, Response


class ManualLogImageController(http.Controller):
    """Serve gambar manual log yang tersimpan di filesystem."""

    @http.route(
        "/weightrack/manual_log_image/<int:record_id>",
        type="http",
        auth="user",
        methods=["GET"],
    )
    def serve_manual_log_image(self, record_id, **kwargs):
        record = (
            request.env["wt.weighing.manual.log"]
            .sudo()
            .browse(record_id)
        )
        if not record.exists() or not record.image_path:
            return request.not_found()

        file_path = record.image_path
        if not os.path.isabs(file_path):
            data_dir = request.env["ir.config_parameter"].sudo().get_param(
                "wt.manual_log_image_dir",
                os.path.join(odoo_config.get("data_dir", "/var/lib/odoo"), "weightrack", "manual_log_images"),
            )
            file_path = os.path.join(data_dir, file_path)

        if not os.path.isfile(file_path):
            return request.not_found()

        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "image/jpeg"

        with open(file_path, "rb") as f:
            image_data = f.read()

        return Response(
            image_data,
            content_type=mime_type,
            headers={
                "Cache-Control": "private, max-age=86400",
                "Content-Length": str(len(image_data)),
            },
        )
