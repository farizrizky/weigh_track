# -*- coding: utf-8 -*-

import json

from psycopg2 import IntegrityError

from odoo import _, fields, models

from ..constants.product_types import ProductType


class CupLumpService(models.AbstractModel):
    _name = "wt.cup.lump.service"
    _description = "Cup Lump Service"

    WEIGHT_EPSILON = 0.0001

    def _response(self):
        return self.env["wt.api.response.service"].sudo()

    def validate_items(self, items):
        response = self._response()
        for item in items:
            if not isinstance(item, dict):
                return response.error(
                    "invalid_inbound_item",
                    _("Each inbound cup lump item must be an object."),
                    400,
                )
            for field_name in ("local_id", "production_date", "weighing_date"):
                if not item.get(field_name):
                    return response.error(
                        "missing_%s" % field_name,
                        _("%s is required.") % field_name,
                        400,
                    )
            if not self._is_valid_date(item.get("production_date")):
                return response.error(
                    "invalid_production_date",
                    _("Production date is invalid."),
                    400,
                )
            if not self._is_valid_datetime(item.get("weighing_date")):
                return response.error(
                    "invalid_weighing_date",
                    _("Weighing date is invalid."),
                    400,
                )
        return {"ok": True}

    def process_items(
        self,
        items,
        payload,
        device,
        bot_user,
        master_synced_at,
        sent_at,
        received_at,
    ):
        return [
            self._process_cup_lump_item(
                item,
                payload,
                device,
                bot_user,
                master_synced_at,
                sent_at,
                received_at,
            )
            for item in items
        ]

    def _process_cup_lump_item(
        self,
        item,
        payload,
        device,
        bot_user,
        master_synced_at,
        sent_at,
        received_at,
    ):
        existing = self._existing_cup_lump(device, item.get("local_id"))
        if existing:
            return self._duplicate_item_response(item, existing)

        production_date = self._to_date(item.get("production_date"))
        weighing_date = self._to_datetime(item.get("weighing_date"))
        records = self._records_from_cup_lump_item(item, device.company_id)
        problem = self._evaluate_cup_lump_data_problem(
            item,
            records,
            device,
            master_synced_at,
            production_date,
        )
        try:
            with self.env.cr.savepoint():
                detail = (
                    self.env["wt.weighing.cup.lump"]
                    .with_user(bot_user)
                    .sudo()
                    .create(
                        self._cup_lump_values(
                            item,
                            payload,
                            records,
                            device,
                            production_date,
                            weighing_date,
                            master_synced_at,
                            sent_at,
                            received_at,
                            problem,
                        )
                    )
                )
        except IntegrityError:
            existing = self._existing_cup_lump(device, item.get("local_id"))
            if existing:
                return self._duplicate_item_response(item, existing)
            raise
        return {
            "local_id": item.get("local_id"),
            "status": "created",
            "has_data_problem": detail.has_data_problem,
            "data_problem_code": detail.data_problem_code,
            "weighing_cup_lump_id": detail.id,
        }

    def _existing_cup_lump(self, device, local_id):
        return self.env["wt.weighing.cup.lump"].sudo().search(
            [
                ("data_source", "=", "api"),
                ("device_id", "=", device.device_id),
                ("product_type", "=", ProductType.CUP_LUMP),
                ("local_id", "=", local_id),
            ],
            limit=1,
        )

    def _duplicate_item_response(self, item, detail):
        return {
            "local_id": item.get("local_id"),
            "status": "duplicate",
            "has_data_problem": detail.has_data_problem,
            "data_problem_code": detail.data_problem_code,
            "weighing_cup_lump_id": detail.id,
        }

    def _cup_lump_values(
        self,
        item,
        payload,
        records,
        device,
        production_date,
        weighing_date,
        master_synced_at,
        sent_at,
        received_at,
        problem,
    ):
        initial = item.get("initial_weighing") or {}
        operator = item.get("operator") or {}
        clerk = item.get("clerk") or {}
        foreman = item.get("foreman") or {}
        tapper = item.get("tapper") or {}
        product = item.get("product") or {}
        uom = product.get("uom") or {}
        initial_device = self._initial_device(initial, device.company_id)
        return {
            "local_id": item.get("local_id"),
            "device_id": device.device_id,
            "device_record_id": device.id,
            "company_id": device.company_id.id,
            "product_type": ProductType.CUP_LUMP,
            "data_source": "api",
            "production_date": production_date,
            "weighing_date": weighing_date,
            "master_synced_at": master_synced_at,
            "sent_at": sent_at,
            "received_at": received_at,
            "batch_local_id": payload.get("batch_local_id"),
            "has_data_problem": problem["has_data_problem"],
            "data_problem_code": problem["data_problem_code"],
            "data_problem_note": problem["data_problem_note"],
            "device_snapshot_json": json.dumps(item, ensure_ascii=False),
            "odoo_snapshot_json": problem["odoo_snapshot_json"],
            "estate_id": records["estate"].id or False,
            "weighing_location_id": records["weighing_location"].id or False,
            "division_id": records["division"].id or False,
            "product_id": records["product"].id or False,
            "receipt_rule_id": records["receipt_rule"].id or False,
            "uom_id": self._browse("uom.uom", self._payload_id(uom)).id or False,
            "operator_employee_id": self._browse(
                "hr.employee",
                operator.get("employee_id"),
            ).id or device.employee_id.id,
            "clerk_employee_id": self._browse(
                "hr.employee",
                clerk.get("employee_id"),
            ).id or False,
            "foreman_id": records["foreman"].id or False,
            "foreman_employee_id": self._browse(
                "hr.employee",
                foreman.get("employee_id"),
            ).id or False,
            "tapper_id": records["tapper"].id or False,
            "tapper_employee_id": self._browse(
                "hr.employee",
                tapper.get("employee_id"),
            ).id or False,
            "total_bag": item.get("total_bag") or 0,
            "production_weight": item.get("production_weight") or 0.0,
            "reject_weight": item.get("reject_weight") or 0.0,
            "slab_weight": item.get("slab_weight") or 0.0,
            "net_weight": item.get("net_weight") or 0.0,
            "shrinkage_tolerance_percentage": item.get(
                "shrinkage_tolerance_percentage"
            ) or 0.0,
            "shrinkage_tolerance_weight": item.get("shrinkage_tolerance_weight") or 0.0,
            "is_manual_weighing": bool(item.get("is_manual_weighing")),
            "manual_weighing_reason": item.get("manual_weighing_reason"),
            "note": item.get("note"),
            "initial_weighing_date": self._to_datetime(initial.get("weighing_date")),
            "initial_device_id": initial_device.id or False,
            "initial_weight": initial.get("weight") or 0.0,
            "initial_is_manual_weighing": bool(initial.get("is_manual_weighing")),
            "initial_manual_weighing_reason": initial.get("manual_weighing_reason"),
            "initial_note": initial.get("note"),
        }

    def evaluate_data_problem_from_record(self, detail):
        item = {
            "company": {"id": detail.company_id.id},
            "estate": {"id": detail.estate_id.id},
            "weighing_location": {"id": detail.weighing_location_id.id},
            "division": {"id": detail.division_id.id},
            "operator": {"employee_id": detail.operator_employee_id.id},
            "clerk": {"employee_id": detail.clerk_employee_id.id},
            "foreman": {
                "id": detail.foreman_id.id,
                "employee_id": detail.foreman_employee_id.id,
            },
            "tapper": {
                "id": detail.tapper_id.id,
                "employee_id": detail.tapper_employee_id.id,
            },
            "product": {"id": detail.product_id.id},
            "receipt_rule": {"id": detail.receipt_rule_id.id},
            "production_date": detail.production_date,
            "weighing_date": detail.weighing_date,
            "production_weight": detail.production_weight,
            "reject_weight": detail.reject_weight,
            "slab_weight": detail.slab_weight,
            "net_weight": detail.net_weight,
            "shrinkage_tolerance_percentage": detail.shrinkage_tolerance_percentage,
            "shrinkage_tolerance_weight": detail.shrinkage_tolerance_weight,
            "initial_weighing": {
                "weighing_date": detail.initial_weighing_date,
                "weight": detail.initial_weight,
                "device_id": detail.initial_device_id.device_id,
            },
        }
        records = self._records_from_cup_lump_item(item, detail.company_id)
        return self._evaluate_cup_lump_data_problem(
            item,
            records,
            detail.device_record_id,
            detail.master_synced_at,
            detail.production_date,
        )

    def _records_from_cup_lump_item(self, item, company):
        division = self._browse("wt.division", self._nested_id(item, "division"))
        foreman = self._browse("wt.foreman", self._nested_id(item, "foreman"))
        tapper = self._browse("wt.tapper", self._nested_id(item, "tapper"))
        if not foreman:
            foreman = self._foreman_from_employee_division(
                self._nested_employee_id(item, "foreman"),
                division,
            )
        if not tapper:
            tapper = self._tapper_from_employee(self._nested_employee_id(item, "tapper"))
        return {
            "company": company,
            "estate": self._browse("wt.estate", self._nested_id(item, "estate")),
            "weighing_location": self._browse(
                "wt.weighing.location",
                self._nested_id(item, "weighing_location"),
            ),
            "division": division,
            "product": self._browse("product.product", self._nested_id(item, "product")),
            "receipt_rule": self._browse(
                "wt.receipt.rule",
                self._nested_id(item, "receipt_rule"),
            ),
            "foreman": foreman,
            "tapper": tapper,
        }

    def _evaluate_cup_lump_data_problem(
        self,
        item,
        records,
        device,
        master_synced_at,
        production_date,
    ):
        issues = []
        notes = []
        company = device.company_id or records["company"]
        has_device = bool(device)

        def add(code, note):
            issues.append(code)
            notes.append(note)

        payload_company_id = self._nested_id(item, "company")
        if payload_company_id and company and payload_company_id != company.id:
            add("company_mismatch", _("Payload company does not match weighing company."))

        operator_employee_id = self._nested_employee_id(item, "operator")
        if has_device and operator_employee_id and operator_employee_id != device.employee_id.id:
            add("operator_mismatch", _("Payload operator does not match device operator."))

        for key, label in (
            ("estate", _("Estate")),
            ("weighing_location", _("Weighing location")),
            ("division", _("Division")),
            ("product", _("Product")),
            ("receipt_rule", _("Receipt rule")),
            ("foreman", _("Foreman")),
            ("tapper", _("Tapper")),
        ):
            if self._nested_id(item, key) and not records[key]:
                add("missing_master", _("%s was not found in Odoo.") % label)

        initial = item.get("initial_weighing") or {}
        initial = initial if isinstance(initial, dict) else {}
        initial_device_id = initial.get("device_id")
        if initial.get("weighing_date") and not initial_device_id:
            add("missing_master", _("Initial weighing device is required."))
        if initial_device_id and not self._initial_device(initial, company):
            add("missing_master", _("Initial weighing device was not found in Odoo."))

        estate = records["estate"]
        location = records["weighing_location"]
        division = records["division"]
        product = records["product"]
        receipt_rule = records["receipt_rule"]
        foreman = records["foreman"]
        tapper = records["tapper"]

        if estate:
            if company and estate.company_id != company:
                add("estate_mismatch", _("Estate does not belong to weighing company."))
            if location and location.estate_id != estate:
                add(
                    "estate_mismatch",
                    _("Payload estate does not match weighing location estate."),
                )

        if location:
            if company and location.company_id != company:
                add(
                    "weighing_location_mismatch",
                    _("Weighing location does not belong to the weighing company."),
                )
            if (
                has_device
                and location.operator_id
                and location.operator_id != device.employee_id
            ):
                add(
                    "operator_mismatch",
                    _("Weighing location operator does not match device operator."),
                )

        if division:
            if company and division.company_id != company:
                add("company_mismatch", _("Division does not belong to weighing company."))
            if location and division not in location.allowed_division_ids:
                add(
                    "division_not_allowed",
                    _("Division is not allowed in the weighing location."),
                )

        if receipt_rule:
            if company and receipt_rule.company_id != company:
                add("receipt_rule_mismatch", _("Receipt rule company does not match."))
            if location and receipt_rule.weighing_location_id != location:
                add(
                    "receipt_rule_mismatch",
                    _("Receipt rule weighing location does not match."),
                )
            if division and receipt_rule.division_id != division:
                add("receipt_rule_mismatch", _("Receipt rule division does not match."))
            if product and receipt_rule.product_id != product:
                add("receipt_rule_mismatch", _("Receipt rule product does not match."))

        if product:
            mapping = self.env["wt.product"].sudo().search(
                [
                    ("company_id", "=", company.id if company else False),
                    ("product_type", "=", ProductType.CUP_LUMP),
                    ("product_id", "=", product.id),
                ],
                limit=1,
            )
            if not mapping:
                add(
                    "product_mapping_mismatch",
                    _("Product is not configured as Cup Lump for the weighing company."),
                )

        clerk_employee_id = self._nested_employee_id(item, "clerk")
        if division and clerk_employee_id and division.clerk_id.id != clerk_employee_id:
            add("clerk_mismatch", _("Payload clerk does not match division clerk."))

        foreman_employee_id = self._nested_employee_id(item, "foreman")
        foreman_from_employee = self._foreman_from_employee_division(
            foreman_employee_id,
            division,
        )
        effective_foreman = foreman_from_employee or foreman
        if foreman_employee_id and not foreman_from_employee:
            add(
                "foreman_mismatch",
                _("Foreman employee is not assigned as foreman in the division."),
            )
        if foreman:
            if division and foreman.division_id != division:
                add("foreman_mismatch", _("Foreman does not belong to the division."))
            if foreman_employee_id and foreman.employee_id.id != foreman_employee_id:
                add("foreman_mismatch", _("Foreman employee does not match."))

        tapper_employee_id = self._nested_employee_id(item, "tapper")
        tapper_from_employee = self._tapper_from_employee(tapper_employee_id)
        if tapper_employee_id and not tapper_from_employee:
            add("tapper_mismatch", _("Tapper employee is not assigned as tapper."))
        if tapper:
            if division and tapper.division_id != division:
                add("tapper_mismatch", _("Tapper does not belong to the division."))
            if effective_foreman and tapper.foreman_id != effective_foreman:
                add("tapper_mismatch", _("Tapper does not belong to the foreman."))
            if tapper_employee_id and tapper.employee_id.id != tapper_employee_id:
                add("tapper_mismatch", _("Tapper employee does not match."))
        if tapper_from_employee and tapper_from_employee != tapper:
            if division and tapper_from_employee.division_id != division:
                add("tapper_mismatch", _("Tapper does not belong to the division."))
            if (
                effective_foreman
                and tapper_from_employee.foreman_id != effective_foreman
            ):
                add("tapper_mismatch", _("Tapper does not belong to the foreman."))
        if (
            tapper_from_employee
            and not effective_foreman
            and foreman_employee_id
            and tapper_from_employee.foreman_id
            and tapper_from_employee.foreman_id.employee_id.id != foreman_employee_id
        ):
            add(
                "tapper_mismatch",
                _("Tapper foreman employee does not match weighing foreman."),
            )

        self._evaluate_initial_weighing_date_rule(item, production_date, add)
        self._evaluate_cup_lump_weight_rules(item, production_date, add)

        unique_issues = list(dict.fromkeys(issues))
        return {
            "has_data_problem": bool(unique_issues),
            "data_problem_code": self._data_problem_code(unique_issues),
            "data_problem_note": "\n".join(notes),
            "odoo_snapshot_json": json.dumps(
                self._odoo_snapshot(records, device),
                ensure_ascii=False,
            ),
        }

    def _evaluate_cup_lump_weight_rules(self, item, production_date, add):
        initial = item.get("initial_weighing") or {}
        weighing_date = self._to_datetime(item.get("weighing_date"))
        production_weight = self._to_float(item.get("production_weight"))
        slab_weight = self._to_float(item.get("slab_weight"))
        reject_weight = self._to_float(item.get("reject_weight"))
        net_weight = self._to_float(item.get("net_weight"))
        shrinkage_percentage = self._to_float(
            item.get("shrinkage_tolerance_percentage")
        )
        shrinkage_weight = self._to_float(item.get("shrinkage_tolerance_weight"))
        initial_weight = self._to_float(initial.get("weight"))

        component_weight = slab_weight + reject_weight + net_weight
        if self._float_mismatch(production_weight, component_weight):
            add(
                "weight_formula_mismatch",
                _(
                    "Production weight must equal slab weight + reject weight + net weight."
                ),
            )

        if not self._has_initial_weighing(initial):
            return

        expected_shrinkage_weight = initial_weight * shrinkage_percentage / 100.0
        if self._float_mismatch(shrinkage_weight, expected_shrinkage_weight):
            add(
                "shrinkage_tolerance_mismatch",
                _("Shrinkage tolerance weight must equal initial weight * shrinkage percentage."),
            )

        if not self._is_after_production_date(production_date, weighing_date):
            return

        expected_production_weight = initial_weight - expected_shrinkage_weight
        if self._float_mismatch(production_weight, expected_production_weight):
            add(
                "initial_weight_mismatch",
                _(
                    "Production weight must equal initial weight minus shrinkage tolerance weight for cross-day weighing."
                ),
            )

    def _evaluate_initial_weighing_date_rule(self, item, production_date, add):
        initial = item.get("initial_weighing") or {}
        if not initial.get("weighing_date"):
            return
        production_date_value = self._date_part(production_date)
        initial_weighing_date_value = self._date_part(initial.get("weighing_date"))
        if (
            production_date_value
            and initial_weighing_date_value
            and production_date_value != initial_weighing_date_value
        ):
            add(
                "initial_weighing_date_mismatch",
                _("Production date must match initial weighing date."),
            )

    def _has_initial_weighing(self, initial):
        if not isinstance(initial, dict):
            return False
        return any(
            initial.get(field_name) not in (None, False, "")
            for field_name in ("weighing_date", "weight", "device_id")
        )

    def _is_after_production_date(self, production_date, weighing_date):
        if not production_date or not weighing_date:
            return False
        return self._date_part(weighing_date) > fields.Date.to_date(production_date)

    def _date_part(self, value):
        if not value:
            return False
        if hasattr(value, "hour"):
            return fields.Datetime.context_timestamp(self, value).date()
        if isinstance(value, str) and ":" in value:
            datetime_value = self._to_datetime(value)
            if datetime_value:
                return fields.Datetime.context_timestamp(self, datetime_value).date()
        return fields.Date.to_date(value)

    def _to_float(self, value):
        if value in (None, False, ""):
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _float_mismatch(self, left, right):
        return abs(left - right) > self.WEIGHT_EPSILON

    def _data_problem_code(self, issues):
        if not issues:
            return "none"
        if len(issues) == 1:
            return issues[0]
        return "multiple_problem"

    def _odoo_snapshot(self, records, device):
        location = records["weighing_location"]
        division = records["division"]
        product = records["product"]
        receipt_rule = records["receipt_rule"]
        foreman = records["foreman"]
        tapper = records["tapper"]
        return {
            "device": (
                {
                    "id": device.id,
                    "device_id": device.device_id,
                    "name": device.name,
                    "employee_id": device.employee_id.id,
                    "employee_name": device.employee_id.name,
                }
                if device
                else False
            ),
            "company": self._record_snapshot(records["company"], ["name"]),
            "weighing_location": self._record_snapshot(
                location,
                ["code", "name", "company_id", "operator_id"],
            ),
            "division": self._record_snapshot(
                division,
                ["code", "name", "company_id", "estate_id", "clerk_id"],
            ),
            "product": self._record_snapshot(product, ["display_name"]),
            "receipt_rule": self._record_snapshot(
                receipt_rule,
                ["company_id", "weighing_location_id", "division_id", "product_id"],
            ),
            "foreman": self._record_snapshot(
                foreman,
                ["employee_id", "division_id", "company_id"],
            ),
            "tapper": self._record_snapshot(
                tapper,
                ["employee_id", "division_id", "foreman_id", "company_id"],
            ),
        }

    def _record_snapshot(self, record, field_names):
        if not record:
            return False
        snapshot = {"id": record.id}
        for field_name in field_names:
            value = record[field_name]
            if hasattr(value, "id"):
                snapshot[field_name] = value.id
                if "name" in value._fields:
                    snapshot["%s_name" % field_name] = value.name
            else:
                snapshot[field_name] = value
        return snapshot

    def _nested_id(self, item, key):
        value = item.get(key) or {}
        return self._payload_id(value)

    def _nested_employee_id(self, item, key):
        value = item.get(key) or {}
        return value.get("employee_id") if isinstance(value, dict) else False

    def _foreman_from_employee_division(self, employee_id, division):
        if not employee_id or not division:
            return self.env["wt.foreman"].browse()
        return self.env["wt.foreman"].sudo().search(
            [
                ("employee_id", "=", employee_id),
                ("division_id", "=", division.id),
            ],
            limit=1,
        )

    def _tapper_from_employee(self, employee_id):
        if not employee_id:
            return self.env["wt.tapper"].browse()
        return self.env["wt.tapper"].sudo().search(
            [("employee_id", "=", employee_id)],
            limit=1,
        )

    def _payload_id(self, value):
        if isinstance(value, dict):
            return value.get("id")
        return False

    def _browse(self, model, record_id):
        if not record_id:
            return self.env[model].browse()
        return self.env[model].sudo().browse(record_id).exists()

    def _initial_device(self, initial, company):
        if not isinstance(initial, dict) or not initial.get("device_id"):
            return self.env["wt.device"].browse()
        domain = [("device_id", "=", initial.get("device_id"))]
        if company:
            domain.append(("company_id", "=", company.id))
        return self.env["wt.device"].sudo().search(domain, limit=1)

    def _to_date(self, value):
        return fields.Date.to_date(value) if value else False

    def _to_datetime(self, value):
        return fields.Datetime.to_datetime(value) if value else False

    def _is_valid_date(self, value):
        try:
            return bool(fields.Date.to_date(value))
        except (TypeError, ValueError):
            return False

    def _is_valid_datetime(self, value):
        try:
            return bool(fields.Datetime.to_datetime(value))
        except (TypeError, ValueError):
            return False
