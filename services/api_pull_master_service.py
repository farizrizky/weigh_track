from odoo import fields, models


class ApiPullMasterService(models.AbstractModel):
    _name = "wt.api.pull.master.service"
    _description = "API Pull Master Service"

    PULL_ROLES = {"operator", "clerk", "foreman"}

    def _response(self):
        return self.env["wt.api.response.service"].sudo()

    def pull_master(self, payload):
        response = self._response()
        auth = self.env["wt.api.security.service"].sudo().authenticate_device(
            payload,
            allowed_roles=self.PULL_ROLES,
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

        bot_user_result = security.get_bot_user(device.company_id, device=device)
        if not bot_user_result["ok"]:
            return bot_user_result

        scope = self._scope_for_device(device)
        now = fields.Datetime.now()
        values = {
            "last_seen": now,
            "last_pull": now,
        }
        if payload.get("app_version"):
            values["app_version"] = payload.get("app_version")
        device.with_user(bot_user_result["bot_user"]).sudo().with_context(
            allow_device_state_update=True
        ).write(values)

        return response.success(
            {
                "meta": {
                    "server_time": fields.Datetime.to_string(now),
                    "role": device.role,
                    "company_id": device.company_id.id,
                    "employee_id": device.employee_id.id,
                    "device": self._device_payload(device),
                },
                "scope": self._scope_payload(device, scope),
                "masters": self._masters_payload(scope, device),
            },
            device=device,
        )

    def _scope_for_device(self, device):
        if device.role == "foreman":
            return self._foreman_scope(device)
        if device.role == "clerk":
            return self._clerk_scope(device)
        if device.role == "operator":
            return self._operator_scope(device)
        return {
            "estates": self.env["wt.estate"].browse(),
            "divisions": self.env["wt.division"].browse(),
            "weighing_locations": self.env["wt.weighing.location"].browse(),
            "clerks": self.env["hr.employee"].browse(),
            "foremen": self.env["wt.foreman"].browse(),
            "operators": self.env["hr.employee"].browse(),
            "tappers": self.env["wt.tapper"].browse(),
        }

    def _foreman_scope(self, device):
        foremen = self.env["wt.foreman"].sudo().search(
            [
                ("company_id", "=", device.company_id.id),
                ("employee_id", "=", device.employee_id.id),
            ]
        )
        divisions = foremen.mapped("division_id")
        tappers = self.env["wt.tapper"].sudo().search(
            [
                ("company_id", "=", device.company_id.id),
                ("foreman_id", "in", foremen.ids),
            ]
        )
        locations = self._locations_for_divisions(device.company_id, divisions)
        return self._build_scope(
            device,
            divisions=divisions,
            foremen=foremen,
            tappers=tappers,
            locations=locations,
        )

    def _clerk_scope(self, device):
        divisions = self.env["wt.division"].sudo().search(
            [
                ("company_id", "=", device.company_id.id),
                ("clerk_id", "=", device.employee_id.id),
            ]
        )
        foremen = self.env["wt.foreman"].sudo().search(
            [
                ("company_id", "=", device.company_id.id),
                ("division_id", "in", divisions.ids),
            ]
        )
        tappers = self.env["wt.tapper"].sudo().search(
            [
                ("company_id", "=", device.company_id.id),
                ("division_id", "in", divisions.ids),
            ]
        )
        locations = self._locations_for_divisions(device.company_id, divisions)
        return self._build_scope(
            device,
            divisions=divisions,
            foremen=foremen,
            tappers=tappers,
            locations=locations,
        )

    def _operator_scope(self, device):
        locations = self.env["wt.weighing.location"].sudo().search(
            [
                ("company_id", "=", device.company_id.id),
                ("operator_id", "=", device.employee_id.id),
            ]
        )
        divisions = locations.mapped("allowed_division_ids")
        foremen = self.env["wt.foreman"].sudo().search(
            [
                ("company_id", "=", device.company_id.id),
                ("division_id", "in", divisions.ids),
            ]
        )
        tappers = self.env["wt.tapper"].sudo().search(
            [
                ("company_id", "=", device.company_id.id),
                ("division_id", "in", divisions.ids),
            ]
        )
        return self._build_scope(
            device,
            divisions=divisions,
            foremen=foremen,
            tappers=tappers,
            locations=locations,
        )

    def _locations_for_divisions(self, company, divisions):
        if not divisions:
            return self.env["wt.weighing.location"].browse()
        return self.env["wt.weighing.location"].sudo().search(
            [
                ("company_id", "=", company.id),
                ("allowed_division_ids", "in", divisions.ids),
            ]
        )

    def _build_scope(self, device, divisions, foremen, tappers, locations):
        estates = divisions.mapped("estate_id") | locations.mapped("estate_id")
        clerks = divisions.mapped("clerk_id")
        operators = locations.mapped("operator_id")
        if device.role == "operator":
            operators |= device.employee_id
        return {
            "estates": estates,
            "divisions": divisions,
            "weighing_locations": locations,
            "clerks": clerks,
            "foremen": foremen,
            "operators": operators,
            "tappers": tappers,
        }

    def _scope_payload(self, device, scope):
        return {
            "role": device.role,
            "company_id": device.company_id.id,
            "employee_id": device.employee_id.id,
            "estate_ids": scope["estates"].ids,
            "division_ids": scope["divisions"].ids,
            "weighing_location_ids": scope["weighing_locations"].ids,
            "clerk_employee_ids": scope["clerks"].ids,
            "foreman_ids": scope["foremen"].ids,
            "operator_employee_ids": scope["operators"].ids,
            "tapper_ids": scope["tappers"].ids,
        }

    def _masters_payload(self, scope, device):
        return {
            "company": self._company_payload(device.company_id),
            "employee": self._employee_payload(device.employee_id),
            "estates": [self._estate_payload(estate) for estate in scope["estates"]],
            "divisions": [
                self._division_payload(division) for division in scope["divisions"]
            ],
            "weighing_locations": [
                self._weighing_location_payload(location)
                for location in scope["weighing_locations"]
            ],
            "clerks": [self._employee_payload(employee) for employee in scope["clerks"]],
            "foremen": [self._foreman_payload(foreman) for foreman in scope["foremen"]],
            "operators": [
                self._employee_payload(employee) for employee in scope["operators"]
            ],
            "tappers": [self._tapper_payload(tapper) for tapper in scope["tappers"]],
        }

    def _device_payload(self, device):
        return {
            "id": device.id,
            "device_id": device.device_id,
            "name": device.name,
            "status": device.status,
            "role": device.role,
            "device_type": device.device_type,
            "app_version": device.app_version,
            "last_pull": fields.Datetime.to_string(device.last_pull)
            if device.last_pull
            else False,
            "last_seen": fields.Datetime.to_string(device.last_seen)
            if device.last_seen
            else False,
        }

    def _company_payload(self, company):
        return {
            "id": company.id,
            "name": company.name,
        }

    def _estate_payload(self, estate):
        return {
            "id": estate.id,
            "code": estate.code,
            "name": estate.name,
            "company_id": estate.company_id.id,
        }

    def _division_payload(self, division):
        return {
            "id": division.id,
            "code": division.code,
            "name": division.name,
            "company_id": division.company_id.id,
            "estate_id": division.estate_id.id,
            "clerk_employee_id": division.clerk_id.id or False,
        }

    def _weighing_location_payload(self, location):
        return {
            "id": location.id,
            "code": location.code,
            "name": location.name,
            "company_id": location.company_id.id,
            "estate_id": location.estate_id.id,
            "warehouse": self._warehouse_payload(location.warehouse_id),
            "operator_employee_id": location.operator_id.id or False,
            "allowed_division_ids": location.allowed_division_ids.ids,
        }

    def _warehouse_payload(self, warehouse):
        if not warehouse:
            return False
        return {
            "id": warehouse.id,
            "code": warehouse.code if "code" in warehouse._fields else False,
            "name": warehouse.name,
        }

    def _foreman_payload(self, foreman):
        return {
            "id": foreman.id,
            "name": foreman.name,
            "employee_id": foreman.employee_id.id,
            "employee_name": foreman.employee_id.name,
            "employee_barcode": self._employee_barcode(foreman.employee_id),
            "company_id": foreman.company_id.id,
            "division_id": foreman.division_id.id,
        }

    def _tapper_payload(self, tapper):
        return {
            "id": tapper.id,
            "name": tapper.name,
            "employee_id": tapper.employee_id.id,
            "employee_name": tapper.employee_id.name,
            "employee_barcode": self._employee_barcode(tapper.employee_id),
            "company_id": tapper.company_id.id,
            "division_id": tapper.division_id.id,
            "foreman_id": tapper.foreman_id.id or False,
        }

    def _employee_payload(self, employee):
        return {
            "id": employee.id,
            "name": employee.name,
            "barcode": self._employee_barcode(employee),
            "job_position": employee.job_id.name if employee.job_id else False,
            "company_id": employee.company_id.id if employee.company_id else False,
        }

    def _employee_barcode(self, employee):
        return employee.barcode if employee and "barcode" in employee._fields else False
