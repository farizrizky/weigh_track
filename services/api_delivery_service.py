# -*- coding: utf-8 -*-

from odoo import _, fields, models
from ..constants.roles import Role


class ApiDeliveryService(models.AbstractModel):
    _name = "wt.api.delivery.service"
    _description = "API Delivery Weighing Service"

    def _response(self):
        return self.env["wt.api.response.service"].sudo()

    # ─────────────────────────────────────────────────── PULL ───

    def pull_delivery(self, payload):
        """Kirimkan daftar tugas pengiriman aktif untuk operator device.

        Move lines dibaca langsung dari stock.move.line via wt_delivery_id,
        tidak lagi melalui wt.delivery.line yang terpisah.
        """
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

        # Cari delivery yang operatornya adalah employee device ini
        # (via picking.wt_operator_id)
        deliveries = self.env["wt.delivery"].sudo().search([
            ("company_id", "=", device.company_id.id),
            ("picking_ids.wt_operator_id", "=", device.employee_id.id),
            ("state", "in", ["confirmed", "in_progress"]),
        ])

        deliveries_data = []
        for delivery in deliveries:
            # Auto-start saat di-pull
            if delivery.state == "confirmed":
                delivery.write({"state": "in_progress"})

            # Move lines milik operator ini (filter per picking.wt_operator_id)
            lines_data = []
            pulled_line_ids = []
            for ml in delivery.move_line_ids.filtered(
                lambda l: l.quantity > 0
                and l.picking_id.wt_operator_id == device.employee_id
            ):
                lines_data.append({
                    "move_line_id": ml.id,
                    "picking_id": ml.picking_id.id,
                    "picking_name": ml.picking_id.name,
                    "product_id": ml.product_id.id,
                    "product_name": ml.product_id.display_name,
                    "lot_id": ml.lot_id.id or False,
                    "lot_name": ml.lot_id.name or "",
                    "uom_id": ml.product_uom_id.id,
                    "uom_name": ml.product_uom_id.name,
                    "demand_qty": ml.quantity,
                    "physical_qty": ml.wt_physical_qty,
                    "difference_qty": ml.wt_difference_qty,
                    "allocated_qty": ml.wt_allocated_qty,
                    "unallocated_qty": ml.wt_unallocated_qty,
                    "is_fully_allocated": ml.wt_is_fully_allocated,
                    "allocations": [
                        {
                            "reason": a.reason_id.name,
                            "qty": a.qty,
                            "location": a.location_dest_id.complete_name,
                        }
                        for a in ml.wt_allocation_ids
                    ],
                    "note": ml.wt_note or "",
                    "skip_line": ml.wt_skip_line,
                })
                pulled_line_ids.append(ml.id)

            # Tandai semua baris yang dikirim ke operator sebagai sudah di-pull.
            # Hanya baris dengan wt_is_pulled=True yang tampil di Detail Timbang
            # sehingga admin bebas mengubah perincian DO sebelum operator pull ulang.
            if pulled_line_ids:
                self.env["stock.move.line"].sudo().browse(pulled_line_ids).write({
                    "wt_is_pulled": True,
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
        """Terima hasil timbang dari aplikasi, update wt_physical_qty pada
        stock.move.line, lalu tandai completed jika semua baris terisi."""
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
            ("picking_ids.wt_operator_id", "=", device.employee_id.id),
            ("state", "in", ["confirmed", "in_progress", "completed"]),
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
            move_line_id = item.get("move_line_id")
            physical_qty = item.get("physical_qty")
            reason_code = item.get("reason_code")
            note = item.get("note", "")
            skip_line = item.get("skip_line", False)

            if move_line_id is None:
                continue

            # Verifikasi move line milik delivery ini
            ml = self.env["stock.move.line"].sudo().search([
                ("id", "=", move_line_id),
                ("wt_delivery_id", "=", delivery.id),
            ], limit=1)

            if not ml:
                errors.append(_("Move Line ID %s tidak ditemukan.") % move_line_id)
                continue

            write_vals = {"wt_skip_line": bool(skip_line)}

            if physical_qty is not None:
                try:
                    qty = float(physical_qty)
                except (ValueError, TypeError):
                    errors.append(_("Nilai physical_qty tidak valid pada move line %s.") % move_line_id)
                    continue
                write_vals["wt_physical_qty"] = qty

            if note:
                write_vals["wt_note"] = note

            ml.write(write_vals)
            updated += 1

        # Tandai picking milik operator ini sebagai done jika semua move line-nya terisi
        now = fields.Datetime.now()
        operator_pickings = delivery.picking_ids.filtered(
            lambda p: p.wt_operator_id == device.employee_id
        )
        for picking in operator_pickings:
            picking_lines = picking.move_line_ids.filtered(lambda l: l.quantity > 0)
            picking_done = all(
                l.wt_skip_line or l.wt_physical_qty > 0.0
                for l in picking_lines
            )
            if picking_done and not picking.wt_push_done:
                picking.sudo().write({
                    "wt_push_done": True,
                    "wt_push_done_at": now,
                })

        # Catatan: state delivery TIDAK otomatis berubah ke 'completed'.
        # Admin harus secara manual mengubah state via tombol di form delivery.
        # Ini memungkinkan lot tambahan untuk ditambahkan dan ditimbang
        # setelah Apply Adjustment dilakukan.

        result_data = {
            "delivery_id": delivery.id,
            "state": delivery.state,
            "updated_lines": updated,
        }
        if errors:
            result_data["warnings"] = errors

        return response.success(result_data, device=device)

