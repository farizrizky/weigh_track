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

        delivery_model = self.env["wt.delivery"].sudo()
        active_delivery_domain = [
            ("company_id", "=", device.company_id.id),
            ("state", "in", ["confirmed", "in_progress", "completed"]),
        ]

        # Alur baru: tugas operator dibagi sampai level lot line.
        lot_lines = self.env["wt.delivery.do.line.lot"].sudo().search([
            ("delivery_id.company_id", "=", device.company_id.id),
            ("delivery_id.state", "in", ["confirmed", "in_progress", "completed"]),
            ("operator_id", "=", device.employee_id.id),
        ])
        deliveries = lot_lines.mapped("delivery_id")

        # Fallback kompatibilitas untuk data lama yang operatornya masih di baris DO/picking.
        deliveries |= delivery_model.search(
            active_delivery_domain
            + [
                "|",
                ("picking_ids.wt_operator_id", "=", device.employee_id.id),
                ("do_line_ids.operator_id", "=", device.employee_id.id),
            ]
        )

        # Kumpulkan transit_location_id dari semua rute yang ditandai is_transit=True.
        # Field ini diset manual oleh admin di Konfigurasi → Rute Transit Pengiriman,
        # sehingga deteksi transit sepenuhnya dikontrol user — tidak bergantung pada
        # tipe/usage lokasi secara otomatis.
        transit_loc_ids = set(
            self.env["wt.delivery.route"].sudo().search([
                ("is_transit", "=", True),
                ("transit_location_id", "!=", False),
                ("company_id", "=", device.company_id.id),
            ]).mapped("transit_location_id.id")
        )

        deliveries_data = []
        for delivery in deliveries:
            # Auto-start saat di-pull
            if delivery.state == "confirmed":
                delivery.write({"state": "in_progress"})

            lines_data = []
            pulled_line_ids = []

            if delivery.do_line_ids:
                # Alur baru: tarik dari wt.delivery.do.line.lot
                for ml in delivery.do_lot_line_ids.filtered(
                    lambda l: l.qty > 0
                    and (l.operator_id == device.employee_id or (not l.operator_id and l.do_line_id.operator_id == device.employee_id))
                    and not l.wt_skip_line
                    and l.wt_physical_qty == 0.0
                ):
                    # Lokasi fisik lot saat ini (dari stock.quant via computed field)
                    loc = ml.location_id
                    lines_data.append({
                        "move_line_id": ml.id,
                        "picking_id": ml.do_line_id.id,
                        "picking_name": ml.do_line_id.picking_type_id.name or "Rencana DO",
                        "product_id": ml.product_id.id,
                        "product_name": ml.product_id.display_name,
                        "lot_id": ml.lot_id.id or False,
                        "lot_name": ml.lot_id.name or "",
                        "uom_id": ml.product_id.uom_id.id,
                        "uom_name": ml.product_id.uom_id.name,
                        "demand_qty": ml.qty,
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
                        # ── Info lokasi lot ────────────────────────────────
                        "location_id": loc.id if loc else False,
                        "location_name": loc.complete_name if loc else "",
                        "is_transit": (loc.id in transit_loc_ids) if loc else False,
                        "weighing_location_id": ml.weighing_location_id.id or False,
                        "weighing_location_name": ml.weighing_location_id.display_name or "",
                        "operator_employee_id": ml.operator_id.id or ml.do_line_id.operator_id.id or False,
                        "operator_name": ml.operator_id.name or ml.do_line_id.operator_id.name or "",
                    })
                    pulled_line_ids.append(ml.id)

                if pulled_line_ids:
                    self.env["wt.delivery.do.line.lot"].sudo().browse(pulled_line_ids).write({
                        "wt_is_pulled": True,
                    })
            else:
                # Alur lama (move_line_ids dari stock.picking)
                for ml in delivery.move_line_ids.filtered(
                    lambda l: l.quantity > 0
                    and l.picking_id.wt_operator_id == device.employee_id
                    and not l.wt_skip_line
                    and l.wt_physical_qty == 0.0
                ):
                    loc = ml.location_id
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
                        # ── Info lokasi lot ────────────────────────────────
                        "location_id": loc.id if loc else False,
                        "location_name": loc.complete_name if loc else "",
                        "is_transit": (loc.id in transit_loc_ids) if loc else False,
                    })
                    pulled_line_ids.append(ml.id)

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
                ] if not delivery.do_line_ids else [
                    {"picking_id": dl.id, "picking_name": dl.picking_type_id.name or "Rencana DO"}
                    for dl in delivery.do_line_ids
                ],
                "lines": lines_data,
            })

        return response.success({"deliveries": deliveries_data}, device=device)

    # ─────────────────────────────────────────────────── PUSH ───

    def push_delivery(self, payload):
        """Terima hasil timbang dari aplikasi, update wt_physical_qty, lalu tandai completed jika semua baris terisi."""
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
            ("state", "in", ["confirmed", "in_progress", "completed"]),
        ], limit=1)

        if not delivery or not (
            delivery.picking_ids.filtered(lambda picking: picking.wt_operator_id == device.employee_id)
            or delivery.do_line_ids.filtered(lambda line: line.operator_id == device.employee_id)
            or delivery.do_lot_line_ids.filtered(lambda line: line.operator_id == device.employee_id)
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
            move_line_id = item.get("move_line_id")
            physical_qty = item.get("physical_qty")
            reason_code = item.get("reason_code")
            note = item.get("note", "")
            skip_line = item.get("skip_line", False)

            if move_line_id is None:
                continue

            # Verifikasi & cari record
            if delivery.do_line_ids:
                ml = self.env["wt.delivery.do.line.lot"].sudo().search([
                    ("id", "=", move_line_id),
                    ("delivery_id", "=", delivery.id),
                ], limit=1)
            else:
                ml = self.env["stock.move.line"].sudo().search([
                    ("id", "=", move_line_id),
                    ("wt_delivery_id", "=", delivery.id),
                ], limit=1)

            if not ml:
                errors.append(_("Line ID %s tidak ditemukan.") % move_line_id)
                continue

            if delivery.do_line_ids and not (
                ml.operator_id == device.employee_id
                or (not ml.operator_id and ml.do_line_id.operator_id == device.employee_id)
            ):
                errors.append(_("Line ID %s bukan milik operator ini.") % move_line_id)
                continue
            if not delivery.do_line_ids and ml.picking_id.wt_operator_id != device.employee_id:
                errors.append(_("Line ID %s bukan milik operator ini.") % move_line_id)
                continue

            write_vals = {"wt_skip_line": bool(skip_line)}

            if physical_qty is not None:
                try:
                    qty = float(physical_qty)
                except (ValueError, TypeError):
                    errors.append(_("Nilai physical_qty tidak valid pada line %s.") % move_line_id)
                    continue
                write_vals["wt_physical_qty"] = qty

            if note:
                write_vals["wt_note"] = note

            ml.write(write_vals)
            updated += 1

        result_data = {
            "delivery_id": delivery.id,
            "state": delivery.state,
            "updated_lines": updated,
        }
        if errors:
            result_data["warnings"] = errors

        return response.success(result_data, device=device)
