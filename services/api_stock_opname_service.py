# -*- coding: utf-8 -*-

from odoo import fields, models, _
from ..constants.roles import Role


class ApiStockOpnameService(models.AbstractModel):
    _name = "wt.api.stock.opname.service"
    _description = "API Stock Opname Service"

    def _response(self):
        return self.env["wt.api.response.service"].sudo()

    def pull_stock_opname(self, payload):
        response = self._response()
        auth = self.env["wt.api.security.service"].sudo().authenticate_device(
            payload,
            allowed_roles=[Role.OPERATOR],
        )
        if not auth["ok"]:
            return auth

        device = auth["device"]
        security = self.env["wt.api.security.service"].sudo()
        pull_result = security.check_pull_enabled(
            device.company_id,
            device=device,
        )
        if not pull_result["ok"]:
            return pull_result

        # Find active stock opnames assigned to this operator
        opnames = self.env["wt.stock.opname"].sudo().search([
            ("company_id", "=", device.company_id.id),
            ("operator_employee_id", "=", device.employee_id.id),
            ("state", "in", ["assigned", "in_progress"]),
        ])

        opnames_data = []
        for op in opnames:
            if op.state == "assigned":
                op.write({"state": "in_progress"})

            lines_data = []
            for line in op.line_ids:
                lines_data.append({
                    "line_id": line.id,
                    "product_id": line.product_id.id,
                    "product_name": line.product_id.display_name,
                    "lot_id": line.lot_id.id,
                    "lot_name": line.lot_id.name,
                    "lot_production_date": str(line.lot_id.production_date) if line.lot_id.production_date else None,
                    "uom_id": line.uom_id.id,
                    "uom_name": line.uom_id.name,
                    "theoretical_qty": line.theoretical_qty,
                    "physical_qty": line.physical_qty,
                    "count_status": line.count_status,
                })

            opnames_data.append({
                "opname_id": op.id,
                "name": op.name,
                "warehouse_id": op.warehouse_id.id,
                "warehouse_name": op.warehouse_id.name,
                "location_id": op.location_id.id,
                "location_name": op.location_id.name,
                "date": str(op.date),
                "lines": lines_data,
            })

        return response.success(
            {
                "opnames": opnames_data,
            },
            device=device,
        )

    def push_stock_opname(self, payload):
        response = self._response()
        auth = self.env["wt.api.security.service"].sudo().authenticate_device(
            payload,
            allowed_roles=[Role.OPERATOR],
        )
        if not auth["ok"]:
            return auth

        device = auth["device"]
        security = self.env["wt.api.security.service"].sudo()
        push_result = security.check_push_enabled(
            device.company_id,
            device=device,
        )
        if not push_result["ok"]:
            return push_result

        opname_id = payload.get("opname_id")
        if not opname_id:
            return response.error(
                "missing_opname_id",
                _("Opname ID is required."),
                400,
                device=device,
            )

        opname = self.env["wt.stock.opname"].sudo().search([
            ("id", "=", opname_id),
            ("company_id", "=", device.company_id.id),
            ("operator_employee_id", "=", device.employee_id.id),
            ("state", "in", ["assigned", "in_progress", "completed"]),
        ], limit=1)

        if not opname:
            return response.error(
                "opname_not_found",
                _("Active stock opname task not found for this operator."),
                404,
                device=device,
            )

        # Write physical quantities
        lines_payload = payload.get("lines") or []
        if not isinstance(lines_payload, list):
            return response.error(
                "invalid_lines",
                _("Lines must be a list."),
                400,
                device=device,
            )

        for line_val in lines_payload:
            line_id = line_val.get("line_id")
            physical_qty = line_val.get("physical_qty")

            if line_id is None or physical_qty is None:
                continue

            op_line = self.env["wt.stock.opname.line"].sudo().search([
                ("id", "=", line_id),
                ("opname_id", "=", opname.id),
            ], limit=1)

            if op_line:
                op_line.write({
                    "physical_qty": float(physical_qty),
                    "count_status": "weighed",
                })

        if opname._all_lines_weighed():
            opname.write({"state": "completed"})
        elif opname.state != "completed":
            opname.write({"state": "in_progress"})

        return response.success(
            {
                "opname_id": opname.id,
                "state": opname.state,
            },
            device=device,
        )
