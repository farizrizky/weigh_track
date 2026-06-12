from odoo import fields, models

from ..constants.product_types import ProductType
from ..constants.roles import Role


class ApiPullMasterService(models.AbstractModel):
    _name = "wt.api.pull.master.service"
    _description = "API Pull Master Service"

    PULL_ROLES = set(Role.DEVICE_VALUES)

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
        bot_user = bot_user_result["bot_user"]

        scope = self._scope_for_device(device)
        now = fields.Datetime.now()
        values = {
            "last_seen": now,
            "last_pull": now,
        }
        if payload.get("app_version"):
            values["app_version"] = payload.get("app_version")
        device.with_user(bot_user).sudo().with_context(
            allow_device_state_update=True
        ).write(values)

        return response.success(
            {
                "meta": {
                    "server_time": self._datetime_local_payload(now, bot_user),
                    "timezone": self._timezone_payload(bot_user),
                    "role": device.role,
                    "company_id": device.company_id.id,
                    "employee_id": device.employee_id.id,
                    "device": self._device_payload(device, bot_user),
                },
                "scope": self._scope_payload(device, scope),
                "masters": self._masters_payload(scope, device),
            },
            device=device,
        )

    def _scope_for_device(self, device):
        if device.role == Role.FOREMAN:
            return self._foreman_scope(device)
        if device.role == Role.CLERK:
            return self._clerk_scope(device)
        if device.role == Role.OPERATOR:
            return self._operator_scope(device)
        return {
            "estates": self.env["wt.estate"].browse(),
            "divisions": self.env["wt.division"].browse(),
            "weighing_locations": self.env["wt.weighing.location"].browse(),
            "receipt_rules": self.env["wt.receipt.rule"].browse(),
            "products": self.env["product.product"].browse(),
            "uoms": self.env["uom.uom"].browse(),
            "employees": self.env["hr.employee"].browse(),
            "product_type_by_product_id": {},
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
        receipt_rules = self.env["wt.receipt.rule"].sudo().search(
            [
                ("company_id", "=", device.company_id.id),
                ("weighing_location_id", "in", locations.ids),
                ("division_id", "in", divisions.ids),
            ]
        )
        if device.role == Role.OPERATOR:
            operators |= device.employee_id
        products = receipt_rules.mapped("product_id")
        uoms = products.mapped("uom_id")
        product_type_by_product_id = self._product_type_by_product_id(
            device.company_id,
            products,
        )
        employees = (
            clerks
            | operators
            | foremen.mapped("employee_id")
            | tappers.mapped("employee_id")
            | device.employee_id
        )
        return {
            "estates": estates,
            "divisions": divisions,
            "weighing_locations": locations,
            "receipt_rules": receipt_rules,
            "products": products,
            "uoms": uoms,
            "employees": employees,
            "product_type_by_product_id": product_type_by_product_id,
            "clerks": clerks,
            "foremen": foremen,
            "operators": operators,
            "tappers": tappers,
        }

    def _scope_payload(self, device, scope):
        return {
            "role": device.role,
            "company_id": device.company_id.id,
            "estate_ids": scope["estates"].ids,
            "division_ids": scope["divisions"].ids,
            "weighing_location_ids": scope["weighing_locations"].ids,
            "receipt_rule_ids": scope["receipt_rules"].ids,
            "product_ids": scope["products"].ids,
            "product_type_codes": sorted(
                product_type
                for product_type in set(scope["product_type_by_product_id"].values())
                if product_type
            ),
            "uom_ids": scope["uoms"].ids,
            "employee_ids": scope["employees"].ids,
            "foreman_ids": scope["foremen"].ids,
            "tapper_ids": scope["tappers"].ids,
        }

    def _masters_payload(self, scope, device):
        receipt_rules = scope["receipt_rules"]
        product_type_by_product_id = scope["product_type_by_product_id"]
        product_type_codes = set(product_type_by_product_id.values())
        return {
            "company": self._company_payload(device.company_id),
            "roles": self._selection_payload(Role.DEVICE_SELECTION, {device.role}),
            "employees": [
                self._employee_payload(employee) for employee in scope["employees"]
            ],
            "estates": [self._estate_payload(estate) for estate in scope["estates"]],
            "divisions": [
                self._division_payload(division) for division in scope["divisions"]
            ],
            "weighing_locations": [
                self._weighing_location_payload(location)
                for location in scope["weighing_locations"]
            ],
            "receipt_rules": [
                self._receipt_rule_payload(rule) for rule in receipt_rules
            ],
            "products": [
                self._product_payload(
                    product,
                    product_type_by_product_id.get(product.id),
                )
                for product in scope["products"]
            ],
            "uoms": [self._uom_payload(uom) for uom in scope["uoms"]],
            "product_types": self._selection_payload(
                ProductType.SELECTION,
                product_type_codes,
            ),
            "foremen": [self._foreman_payload(foreman) for foreman in scope["foremen"]],
            "tappers": [self._tapper_payload(tapper) for tapper in scope["tappers"]],
        }

    def _device_payload(self, device, user):
        return {
            "id": device.id,
            "device_id": device.device_id,
            "name": device.name,
            "status": device.status,
            "role": device.role,
            "device_type": device.device_type,
            "app_version": device.app_version,
            "last_pull": self._datetime_local_payload(device.last_pull, user),
            "last_seen": self._datetime_local_payload(device.last_seen, user),
        }

    def _timezone_payload(self, user):
        return user.tz or "UTC"

    def _datetime_local_payload(self, value, user):
        if not value:
            return False
        datetime_value = fields.Datetime.to_datetime(value)
        timezone = self._timezone_payload(user)
        localized = fields.Datetime.context_timestamp(
            user.with_context(tz=timezone),
            datetime_value,
        )
        return localized.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")

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
            "operator_employee_id": location.operator_id.id or False,
            "allowed_division_ids": location.allowed_division_ids.ids,
        }

    def _receipt_rule_payload(self, rule):
        return {
            "id": rule.id,
            "name": rule.name,
            "company_id": rule.company_id.id,
            "weighing_location_id": rule.weighing_location_id.id,
            "division_id": rule.division_id.id,
            "product_id": rule.product_id.id,
        }

    def _product_payload(self, product, product_type=False):
        return {
            "id": product.id,
            "name": product.display_name,
            "company_id": product.product_tmpl_id.company_id.id or False,
            "uom_id": product.uom_id.id,
            "product_type": product_type or False,
        }

    def _product_type_by_product_id(self, company, products):
        mapping = {}
        if not products:
            return mapping

        product_config_model = self.env["wt.product"].sudo()
        product_configs = product_config_model.search(
            [
                ("company_id", "=", company.id),
                ("product_id", "in", products.ids),
            ]
        )
        for product_config in product_configs:
            if product_config.product_id and product_config.product_type:
                mapping[product_config.product_id.id] = product_config.product_type

        return mapping

    def _uom_payload(self, uom):
        return {
            "id": uom.id,
            "name": uom.name,
        }

    def _selection_payload(self, selection, allowed_values=None):
        if allowed_values is not None:
            selection = [
                (value, label)
                for value, label in selection
                if value in allowed_values
            ]
        return [{"code": value, "name": label} for value, label in selection]

    def _foreman_payload(self, foreman):
        return {
            "id": foreman.id,
            "employee_id": foreman.employee_id.id,
            "company_id": foreman.company_id.id,
            "division_id": foreman.division_id.id,
        }

    def _tapper_payload(self, tapper):
        return {
            "id": tapper.id,
            "employee_id": tapper.employee_id.id,
            "company_id": tapper.company_id.id,
            "division_id": tapper.division_id.id,
            "foreman_id": tapper.foreman_id.id or False,
        }

    def _employee_payload(self, employee):
        return {
            "id": employee.id,
            "name": employee.name,
            "barcode": self._employee_barcode(employee),
            "company_id": employee.company_id.id if employee.company_id else False,
        }

    def _employee_barcode(self, employee):
        return employee.barcode if employee and "barcode" in employee._fields else False
