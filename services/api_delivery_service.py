# -*- coding: utf-8 -*-

from odoo import _, models
from ..constants.roles import Role


class ApiDeliveryService(models.AbstractModel):
    _name = "wt.api.delivery.service"
    _description = "API Delivery Weighing Service"

    def _response(self):
        return self.env["wt.api.response.service"].sudo()

    # ─────────────────────────────────────────────────── PULL ───

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

        deliveries = self.env["wt.delivery"].sudo().search([
            ("company_id", "=", device.company_id.id),
            ("line_ids.operator_employee_id", "=", device.employee_id.id),
            ("state", "in", ["assigned", "in_progress"]),
        ])

        deliveries_data = []
        for delivery in deliveries:
            # Auto-start saat di-pull
            if delivery.state == "assigned":
                delivery.write({"state": "in_progress"})

            lines_data = []
            for line in delivery.line_ids:
                lines_data.append({
                    "line_id": line.id,
                    "picking_id": line.picking_id.id,
                    "picking_name": line.picking_name,
                    "operator_employee_id": line.operator_employee_id.id or False,
                    "operator_employee_name": line.operator_employee_id.name or "",
                    "product_id": line.product_id.id,
                    "product_name": line.product_id.display_name,
                    "lot_id": line.lot_id.id,
                    "lot_name": line.lot_id.name,
                    "uom_id": line.uom_id.id,
                    "uom_name": line.uom_id.name,
                    "demand_qty": line.demand_qty,
                    "physical_qty": line.physical_qty,
                    "difference_qty": line.difference_qty,
                    "note": line.note or "",
                    "skip_line": line.skip_line,
                })

            deliveries_data.append({
                "delivery_id": delivery.id,
                "name": delivery.name,
                "date": str(delivery.date),
                "state": delivery.state,
                "total_demand_qty": delivery.total_demand_qty,
                "pickings": [
                    {"picking_id": p.id, "picking_name": p.name}
                    for p in delivery.picking_ids
                ],
                "lines": lines_data,
            })

        return response.success({"deliveries": deliveries_data}, device=device)

    # ─────────────────────────────────────────────────── PUSH ───

    def push_delivery(self, payload):
        """Terima hasil timbang dari aplikasi, update physical_qty & reason,
        lalu tandai completed jika semua baris terisi."""
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

        delivery_id = payload.get("delivery_id")
        if not delivery_id:
            return response.error(
                "missing_delivery_id",
                _("delivery_id wajib diisi."),
                400,
                device=device,
            )

        delivery = self.env["wt.delivery"].sudo().search([
            ("id", "=", delivery_id),
            ("company_id", "=", device.company_id.id),
            ("operator_employee_id", "=", device.employee_id.id),
            ("state", "in", ["assigned", "in_progress", "completed"]),
        ], limit=1)

        if not delivery:
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
            line_id = item.get("line_id")
            physical_qty = item.get("physical_qty")
            reason_code = item.get("reason_code")
            note = item.get("note", "")
            skip_line = item.get("skip_line", False)

            if line_id is None:
                continue

            line = self.env["wt.delivery.line"].sudo().search([
                ("id", "=", line_id),
                ("delivery_id", "=", delivery.id),
            ], limit=1)

            if not line:
                errors.append(_("Line ID %s tidak ditemukan.") % line_id)
                continue

            write_vals = {"skip_line": bool(skip_line)}

            if physical_qty is not None:
                try:
                    write_vals["physical_qty"] = float(physical_qty)
                except (ValueError, TypeError):
                    errors.append(_("Nilai physical_qty tidak valid pada line %s.") % line_id)
                    continue

            if reason_code:
                reason = self.env["wt.stock.opname.difference.reason"].sudo().search([
                    ("code", "=", reason_code),
                    "|",
                    ("company_id", "=", device.company_id.id),
                    ("company_id", "=", False),
                ], limit=1)
                if reason:
                    write_vals["reason_id"] = reason.id
                else:
                    errors.append(_("Kode alasan '%s' tidak ditemukan pada line %s.") % (reason_code, line_id))

            if note:
                write_vals["note"] = note

            line.write(write_vals)
            updated += 1

        # Tandai completed jika semua baris sudah punya physical_qty atau skip_line
        all_done = all(
            l.skip_line or l.physical_qty > 0.0
            for l in delivery.line_ids
        )
        if all_done and delivery.state in ["assigned", "in_progress"]:
            delivery.write({"state": "completed"})

        result_data = {
            "delivery_id": delivery.id,
            "state": delivery.state,
            "updated_lines": updated,
        }
        if errors:
            result_data["warnings"] = errors

        return response.success(result_data, device=device)
