# -*- coding: utf-8 -*-

from odoo import _, models

from ..constants.roles import Role


class ApiDeliveryService(models.AbstractModel):
    _name = "wt.api.delivery.service"
    _description = "API Delivery Weighing Service"

    def _response(self):
        return self.env["wt.api.response.service"].sudo()

    def _bot_model(self, model_name, bot_user):
        return self.env[model_name].with_user(bot_user).sudo().with_context(
            lang=bot_user.lang or self.env.lang,
            tz=bot_user.tz or "UTC",
        )

    def pull_delivery(self, payload):
        """Kirimkan daftar tugas pengiriman aktif untuk operator device."""
        response = self._response()
        auth = self.env["wt.api.security.service"].sudo().authenticate_device(
            payload,
            allowed_roles=[Role.OPERATOR],
        )
        if not auth["ok"]:
            return auth

        device = auth["device"]
        pull_result = self.env["wt.api.security.service"].sudo().check_pull_enabled(
            device.company_id,
            device=device,
        )
        if not pull_result["ok"]:
            return pull_result
        bot_user_result = self.env["wt.api.security.service"].sudo().get_bot_user(
            device.company_id,
            device=device,
        )
        if not bot_user_result["ok"]:
            return bot_user_result
        bot_user = bot_user_result["bot_user"]
        lot_line_model = self._bot_model("wt.delivery.do.line.lot", bot_user)
        route_line_model = self._bot_model("wt.delivery.route.line", bot_user)

        lot_lines = lot_line_model.search([
            ("delivery_id.company_id", "=", device.company_id.id),
            ("delivery_id.state", "in", ["confirmed", "in_progress"]),
            ("operator_id", "=", device.employee_id.id),
        ])
        deliveries = lot_lines.mapped("delivery_id")

        transit_loc_ids = set(
            route_line_model.search([
                ("route_type", "=", "transit"),
                ("location_dest_id", "!=", False),
                ("company_id", "=", device.company_id.id),
            ]).mapped("location_dest_id.id")
        )

        deliveries_data = []
        for delivery in deliveries:
            if delivery.state == "confirmed":
                delivery.write({"state": "in_progress"})

            lines_data = []
            pulled_line_ids = []

            for line in delivery.do_lot_line_ids.filtered(
                lambda lot_line: lot_line.qty > 0
                and (
                    lot_line.operator_id == device.employee_id
                    or (
                        not lot_line.operator_id
                        and lot_line.do_line_id.operator_id == device.employee_id
                    )
                )
                and lot_line.wt_physical_qty == 0.0
            ):
                location = line.location_id
                lines_data.append({
                    "delivery_lot_line_id": line.id,
                    "picking_id": line.do_line_id.id,
                    "picking_name": line.do_line_id.picking_type_id.name or "Rencana DO",
                    "product_id": line.product_id.id,
                    "product_name": line.product_id.display_name,
                    "lot_id": line.lot_id.id or False,
                    "lot_name": line.lot_id.name or "",
                    "lot_production_date": str(line.lot_id.production_date) if line.lot_id.production_date else None,
                    "uom_id": line.product_id.uom_id.id,
                    "uom_name": line.product_id.uom_id.name,
                    "demand_qty": line.qty,
                    "location_id": location.id if location else False,
                    "location_name": location.complete_name if location else "",
                    "is_transit": (location.id in transit_loc_ids) if location else False,
                    "weighing_location_id": line.weighing_location_id.id or False,
                    "weighing_location_name": line.weighing_location_id.display_name or "",
                    "operator_employee_id": line.operator_id.id or line.do_line_id.operator_id.id or False,
                    "operator_name": line.operator_id.name or line.do_line_id.operator_id.name or "",
                })
                pulled_line_ids.append(line.id)

            if pulled_line_ids:
                lot_line_model.browse(pulled_line_ids).write({
                    "wt_is_pulled": True,
                })

            deliveries_data.append({
                "delivery_id": delivery.id,
                "name": delivery.name,
                "date": str(delivery.date),
                "state": delivery.state,
                "total_demand_qty": delivery.total_demand_qty,
                "pickings": [
                    {"picking_id": line.id, "picking_name": line.picking_type_id.name or "Rencana DO"}
                    for line in delivery.do_line_ids
                ],
                "lines": lines_data,
            })

        return response.success({"deliveries": deliveries_data}, device=device)

    def push_delivery(self, payload):
        """Terima hasil timbang dari aplikasi dan update berat fisik lot rencana DO."""
        response = self._response()
        auth = self.env["wt.api.security.service"].sudo().authenticate_device(
            payload,
            allowed_roles=[Role.OPERATOR],
        )
        if not auth["ok"]:
            return auth

        device = auth["device"]
        push_result = self.env["wt.api.security.service"].sudo().check_push_enabled(
            device.company_id,
            device=device,
        )
        if not push_result["ok"]:
            return push_result
        bot_user_result = self.env["wt.api.security.service"].sudo().get_bot_user(
            device.company_id,
            device=device,
        )
        if not bot_user_result["ok"]:
            return bot_user_result
        bot_user = bot_user_result["bot_user"]
        datetime_service = self._bot_model("wt.weighing.service", bot_user)
        delivery_model = self._bot_model("wt.delivery", bot_user)
        lot_line_model = self._bot_model("wt.delivery.do.line.lot", bot_user)

        delivery_id = payload.get("delivery_id")
        if not delivery_id:
            return response.error(
                "missing_delivery_id",
                _("delivery_id wajib diisi."),
                400,
                device=device,
            )

        delivery = delivery_model.search([
            ("id", "=", delivery_id),
            ("company_id", "=", device.company_id.id),
            ("state", "in", ["confirmed", "in_progress"]),
        ], limit=1)

        if not delivery or not delivery.do_lot_line_ids.filtered(
            lambda line: line.operator_id == device.employee_id
            or (not line.operator_id and line.do_line_id.operator_id == device.employee_id)
        ):
            return response.error(
                "delivery_not_found",
                _("Tugas pengiriman aktif tidak ditemukan untuk operator ini."),
                404,
                device=device,
            )

        lines_payload = payload.get("lines") or []
        if not isinstance(lines_payload, list):
            return response.error("invalid_lines", _("lines harus berupa list."), 400, device=device)

        updated = 0
        errors = []
        for item in lines_payload:
            delivery_lot_line_id = item.get("delivery_lot_line_id")
            physical_qty = item.get("physical_qty")
            weighed_at = item.get("weighed_at")
            lot_id = item.get("lot_id")
            lot_name = item.get("lot_name")
            note = item.get("note", "")

            if delivery_lot_line_id is None:
                errors.append(_("delivery_lot_line_id wajib diisi."))
                continue

            line = lot_line_model.search([
                ("id", "=", delivery_lot_line_id),
                ("delivery_id", "=", delivery.id),
            ], limit=1)
            if not line:
                errors.append(_("Line ID %s tidak ditemukan.") % delivery_lot_line_id)
                continue

            if not (
                line.operator_id == device.employee_id
                or (not line.operator_id and line.do_line_id.operator_id == device.employee_id)
            ):
                errors.append(_("Line ID %s bukan milik operator ini.") % delivery_lot_line_id)
                continue

            if lot_id:
                try:
                    payload_lot_id = int(lot_id)
                except (ValueError, TypeError):
                    errors.append(_("lot_id pada line %s tidak valid.") % delivery_lot_line_id)
                    continue
                if payload_lot_id != line.lot_id.id:
                    errors.append(_("lot_id pada line %s tidak cocok dengan Lot Odoo.") % delivery_lot_line_id)
                    continue
            if lot_name and lot_name != (line.lot_id.name or ""):
                errors.append(_("lot_name pada line %s tidak cocok dengan Lot Odoo.") % delivery_lot_line_id)
                continue

            if physical_qty is None:
                errors.append(_("physical_qty wajib diisi pada line %s.") % delivery_lot_line_id)
                continue
            try:
                qty = float(physical_qty)
            except (ValueError, TypeError):
                errors.append(_("Nilai physical_qty tidak valid pada line %s.") % delivery_lot_line_id)
                continue
            if qty <= 0.0:
                errors.append(_("Nilai physical_qty harus lebih dari 0 pada line %s.") % delivery_lot_line_id)
                continue

            if not weighed_at:
                errors.append(_("weighed_at wajib diisi pada line %s.") % delivery_lot_line_id)
                continue
            try:
                weighed_dt = datetime_service._to_datetime(weighed_at, bot_user)
            except (ValueError, TypeError):
                errors.append(_("Nilai weighed_at tidak valid pada line %s.") % delivery_lot_line_id)
                continue
            if not weighed_dt:
                errors.append(_("Nilai weighed_at tidak valid pada line %s.") % delivery_lot_line_id)
                continue

            write_vals = {
                "wt_physical_qty": qty,
                "wt_weighed_at": weighed_dt,
            }
            if note:
                write_vals["wt_note"] = note

            line.write(write_vals)
            updated += 1

        result_data = {
            "delivery_id": delivery.id,
            "state": delivery.state,
            "updated_lines": updated,
        }
        if errors:
            result_data["warnings"] = errors

        return response.success(result_data, device=device)
