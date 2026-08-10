# -*- coding: utf-8 -*-

import base64
import json
import logging
import os

import odoo.tools.config as odoo_config
import pytz
from psycopg2 import IntegrityError

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


def _detect_image_ext(image_bytes):
    """Deteksi ekstensi gambar dari magic bytes tanpa library imghdr (removed di Python 3.13)."""
    if image_bytes[:2] == b'\xff\xd8':
        return 'jpeg'
    if image_bytes[:4] == b'\x89PNG':
        return 'png'
    if image_bytes[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    if image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        return 'webp'
    return 'jpeg'  # default fallback


class WeighingService(models.AbstractModel):
    _name = "wt.weighing.service"
    _description = "Weighing Service"

    WEIGHT_EPSILON = 0.0001
    DATA_PROBLEM_LABEL_IDN = {
        "Estate": "Estate",
        "Weighing location": "Lokasi timbang",
        "Initial weighing location": "Lokasi timbang awal",
        "Division": "Divisi",
        "Product": "Produk",
        "Receipt rule": "Aturan penerimaan",
        "Product mapping": "Mapping produk",
        "Foreman": "Mandor",
        "Tapper": "Tapper",
    }
    INACTIVE_MASTER_MESSAGE_EN = "%s is archived in master data."
    INACTIVE_MASTER_MESSAGE_IDN = "%s sudah diarsipkan di master data."
    DATA_PROBLEM_NOTE_IDN = {
        "Payload company does not match weighing company.": (
            "Perusahaan pada record penimbangan tidak sesuai dengan data master perusahaan."
        ),
        "Payload operator does not match device operator.": (
            "Operator pada record penimbangan tidak sesuai dengan operator device."
        ),
        "Initial weighing device is required.": (
            "Device penimbangan lapangan wajib diisi."
        ),
        "Initial weighing device was not found in Odoo.": (
            "Device penimbangan lapangan tidak ditemukan di master data."
        ),
        "Initial weighing location is required.": (
            "Lokasi timbang awal wajib diisi."
        ),
        "Initial weighing location was not found in Odoo.": (
            "Lokasi timbang awal tidak ditemukan di master data."
        ),
        "Initial weighing location must use Field type.": (
            "Lokasi timbang awal harus bertipe Lapangan."
        ),
        "Initial weighing location does not belong to the weighing company.": (
            "Lokasi timbang awal tidak sesuai dengan perusahaan penimbangan."
        ),
        "Estate does not belong to weighing company.": (
            "Estate pada record penimbangan tidak sesuai dengan estate perusahaan."
        ),
        "Payload estate does not match weighing location estate.": (
            "Estate pada record penimbangan tidak sesuai dengan estate lokasi timbang."
        ),
        "Weighing location does not belong to the weighing company.": (
            "Lokasi timbang pada record penimbangan tidak sesuai dengan lokasi timbang perusahaan."
        ),
        "Weighing location operator does not match device operator.": (
            "Operator lokasi timbang pada record penimbangan tidak sesuai dengan operator device."
        ),
        "Division does not belong to weighing company.": (
            "Divisi pada record penimbangan tidak sesuai dengan dengan divisi perusahaan."
        ),
        "Division is not allowed in the weighing location.": (
            "Divisi tidak diizinkan pada lokasi timbang."
        ),
        "Receipt rule company does not match.": (
            "Perusahaan pada aturan penerimaan tidak sesuai."
        ),
        "Receipt rule weighing location does not match.": (
            "Lokasi timbang pada aturan penerimaan tidak sesuai."
        ),
        "Receipt rule division does not match.": (
            "Divisi pada aturan penerimaan tidak sesuai."
        ),
        "Weighing product is not configured for the weighing company.": (
            "Produk penimbangan belum dikonfigurasi untuk perusahaan penimbangan."
        ),
        "Payload product does not match configured weighing product.": (
            "Produk pada payload tidak sesuai dengan produk penimbangan yang dikonfigurasi."
        ),
        "Payload clerk does not match division clerk.": (
            "Kerani pada record penimbangan tidak sesuai dengan kerani divisi."
        ),
        "Foreman employee is not assigned as foreman in the division.": (
            "Karyawan mandor pada record penimbangan tidak ditugaskan sebagai mandor pada divisi tersebut."
        ),
        "Foreman does not belong to the division.": (
            "Mandor pada record penimbangan tidak berada pada divisi tersebut."
        ),
        "Foreman employee does not match.": "Karyawan mandor tidak sesuai.",
        "Tapper employee is not assigned as tapper.": (
            "Karyawan tapper pada record penimbangan tidak ditugaskan sebagai tapper."
        ),
        "Tapper does not belong to the division.": (
            "Tapper pada record penimbangan tidak berada pada divisi tersebut."
        ),
        "Tapper does not belong to the foreman.": (
            "Tapper pada record penimbangan tidak berada di bawah mandor tersebut."
        ),
        "Tapper employee does not match.": (
            "Karyawan tapper pada record penimbangan tidak sesuai."
        ),
        "Tapper foreman employee does not match weighing foreman.": (
            "Mandor dari tapper pada record penimbangan tidak sesuai dengan mandor penimbangan."
        ),
        "Production weight must equal slab weight + reject weight + net weight.": (
            "Berat produksi harus sama dengan berat slab + berat reject + berat net."
        ),
        "Shrinkage tolerance weight must equal initial weight * shrinkage percentage.": (
            "Berat toleransi penyusutan harus sama dengan berat penimbangan lapangan * persentase penyusutan."
        ),
        "Production weight must equal initial weight minus shrinkage tolerance weight for cross-day weighing.": (
            "Berat produksi harus sama dengan berat penimbangan lapangan dikurangi berat toleransi penyusutan untuk penimbangan lintas hari."
        ),
        "Production date must match initial weighing date.": (
            "Tanggal produksi harus sama dengan tanggal penimbangan lapangan."
        ),
        INACTIVE_MASTER_MESSAGE_EN: INACTIVE_MASTER_MESSAGE_IDN,
    }

    def _response(self):
        return self.env["wt.api.response.service"].sudo()

    def validate_items(self, items):
        response = self._response()
        for item in items:
            if not isinstance(item, dict):
                return response.error(
                    "invalid_inbound_item",
                    _("Each weighing item must be an object."),
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
            location_id = self._nested_id(item, "weighing_location")
            location = self._browse("wt.weighing.location", location_id)
            if location and location.location_type != "warehouse":
                return response.error(
                    "invalid_weighing_location_type",
                    _("Only Warehouse weighing locations can push final weighing."),
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
        # Proses manual_logs terlebih dahulu (upsert by local_id)
        manual_log_map = self._process_manual_logs(
            payload.get("manual_logs") or [],
            device,
            bot_user,
            received_at,
        )
        return [
            self._process_weighing_item(
                item,
                payload,
                device,
                bot_user,
                master_synced_at,
                sent_at,
                received_at,
                manual_log_map,
            )
            for item in items
        ]

    def _process_manual_logs(self, manual_logs, device, bot_user, received_at):
        """Upsert manual log entries by local_id. Return dict {local_id: record_id}."""
        if not manual_logs or not isinstance(manual_logs, list):
            return {}
        log_model = (
            self.env["wt.weighing.manual.log"]
            .with_user(bot_user)
            .sudo()
        )
        log_map = {}
        for log_data in manual_logs:
            if not isinstance(log_data, dict):
                continue
            local_id = log_data.get("local_id")
            if not local_id:
                continue
            log_record = self._upsert_manual_log(
                log_model, log_data, local_id, device, bot_user, received_at
            )
            if log_record:
                log_map[local_id] = log_record.id
        return log_map

    def _upsert_manual_log(self, log_model, log_data, local_id, device, bot_user, received_at):
        """Buat manual log jika local_id belum ada, atau kembalikan yang sudah ada."""
        _logger.info("[ManualLog] Memproses local_id=%s", local_id)

        existing = log_model.search([("local_id", "=", local_id)], limit=1)
        if existing:
            _logger.info("[ManualLog] local_id=%s sudah ada, skip.", local_id)
            return existing

        date_val = self._to_datetime(log_data.get("date"), bot_user)

        # Decode base64 gambar dan simpan ke filesystem
        image_base64 = log_data.get("image_base64")
        if not image_base64:
            raise ValueError(f"Manual log '{local_id}': image_base64 wajib diisi.")

        _logger.info("[ManualLog] Memulai decode base64 untuk local_id=%s (len=%d)", local_id, len(image_base64))

        # Bersihkan header data URI jika ada (misal: data:image/jpeg;base64,...)
        if "," in image_base64:
            image_base64 = image_base64.split(",", 1)[1]

        image_bytes = base64.b64decode(image_base64)
        _logger.info("[ManualLog] Decode berhasil, ukuran=%d bytes", len(image_bytes))

        img_type = _detect_image_ext(image_bytes)
        ext = img_type

        data_dir = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("wt.manual_log_image_dir", "")
            or os.path.join(
                odoo_config.get("data_dir", "/var/lib/odoo"),
                "weightrack",
                "manual_log_images",
            )
        )
        _logger.info("[ManualLog] Direktori target: %s", data_dir)

        os.makedirs(data_dir, exist_ok=True)

        safe_local_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in local_id)
        file_path = os.path.join(data_dir, f"{safe_local_id}.{ext}")
        _logger.info("[ManualLog] Menyimpan file ke: %s", file_path)

        with open(file_path, "wb") as f:
            f.write(image_bytes)

        _logger.info("[ManualLog] File berhasil disimpan, membuat record DB...")

        vals = {
            "local_id": local_id,
            "date": date_val,
            "manual_reason": log_data.get("manual_reason"),
            "image_path": file_path,
            "device_id": device.device_id,
            "device_record_id": device.id,
            "company_id": device.company_id.id,
            "received_at": received_at,
        }
        try:
            record = log_model.create(vals)
            _logger.info("[ManualLog] Record DB berhasil dibuat, id=%s", record.id)
            return record
        except Exception as e:
            _logger.error("[ManualLog] Gagal buat record DB: %s", e, exc_info=True)
            return log_model.search([("local_id", "=", local_id)], limit=1)

    def _process_weighing_item(
        self,
        item,
        payload,
        device,
        bot_user,
        master_synced_at,
        sent_at,
        received_at,
        manual_log_map=None,
    ):
        existing = self._existing_weighing(device, item.get("local_id"))
        if existing:
            return self._duplicate_item_response(item, existing)

        production_date = self._to_date(item.get("production_date"))
        weighing_date = self._to_datetime(item.get("weighing_date"), bot_user)
        records = self._records_from_weighing_item(item, device.company_id)
        problem = self._evaluate_weighing_data_problem(
            item,
            records,
            device,
            master_synced_at,
            production_date,
            bot_user,
        )
        try:
            with self.env.cr.savepoint():
                vals = self._weighing_values(
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
                    bot_user,
                )
                # Link ke manual log jika ada
                manual_log_local_id = item.get("manual_log_local_id")
                if manual_log_local_id and manual_log_map and manual_log_local_id in manual_log_map:
                    vals["manual_log_id"] = manual_log_map[manual_log_local_id]
                detail = (
                    self.env["wt.weighing"]
                    .with_user(bot_user)
                    .sudo()
                    .with_context(tz=bot_user.tz or "UTC")
                    .create(vals)
                )
        except IntegrityError:
            existing = self._existing_weighing(device, item.get("local_id"))
            if existing:
                return self._duplicate_item_response(item, existing)
            raise
        return {
            "local_id": item.get("local_id"),
            "status": "created",
            "has_data_problem": detail.has_data_problem,
            "data_problem_code": detail.data_problem_code,
            "weighing_id": detail.id,
        }

    def _existing_weighing(self, device, local_id):
        return self.env["wt.weighing"].sudo().search(
            [
                ("data_source", "=", "api"),
                ("device_id", "=", device.device_id),
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
            "weighing_id": detail.id,
        }

    def _weighing_values(
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
        bot_user=False,
    ):
        initial = item.get("initial_weighing") or {}
        operator = item.get("operator") or {}
        clerk = item.get("clerk") or {}
        foreman = item.get("foreman") or {}
        tapper = item.get("tapper") or {}
        product = item.get("product") or {}
        uom = product.get("uom") or {}
        initial_device = records["initial_device"]
        initial_location = records["initial_weighing_location"]
        weighing_product = records["product"]
        uom_id = (
            weighing_product.uom_id.id
            if weighing_product
            else self._browse("uom.uom", self._payload_id(uom)).id
        )
        return {
            "local_id": item.get("local_id"),
            "device_id": device.device_id,
            "device_record_id": device.id,
            "company_id": device.company_id.id,
            "data_source": "api",
            "production_date": production_date,
            "weighing_date": weighing_date,
            "master_synced_at": master_synced_at,
            "sent_at": sent_at,
            "received_at": received_at,
            "batch_local_id": payload.get("batch_local_id"),
            "has_data_problem": problem["has_data_problem"],
            "data_problem_code": problem["data_problem_code"],
            "data_problem_note_en": problem["data_problem_note_en"],
            "data_problem_note_idn": problem["data_problem_note_idn"],
            "device_snapshot_json": json.dumps(item, ensure_ascii=False),
            "odoo_snapshot_json": problem["odoo_snapshot_json"],
            "estate_id": records["estate"].id or False,
            "weighing_location_id": records["weighing_location"].id or False,
            "division_id": records["division"].id or False,
            "product_id": records["product"].id or False,
            "receipt_rule_id": records["receipt_rule"].id or False,
            "uom_id": uom_id or False,
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
            "initial_weighing_date": self._to_datetime(
                initial.get("weighing_date"),
                bot_user,
            ),
            "initial_weighing_location_id": initial_location.id or False,
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
                "weighing_location_id": detail.initial_weighing_location_id.id,
                "weight": detail.initial_weight,
                "device_id": detail.initial_device_id.device_id,
            },
        }
        records = self._records_from_weighing_item(item, detail.company_id)
        return self._evaluate_weighing_data_problem(
            item,
            records,
            detail.device_record_id,
            detail.master_synced_at,
            detail.production_date,
        )

    def _records_from_weighing_item(self, item, company):
        location = self._browse(
            "wt.weighing.location",
            self._nested_id(item, "weighing_location"),
        )
        initial = item.get("initial_weighing") or {}
        initial = initial if isinstance(initial, dict) else {}
        initial_device = self._initial_device(initial, company)
        division = self._browse("wt.division", self._nested_id(item, "division"))
        initial_location = self._initial_weighing_location_from_device(
            initial_device,
            company,
            division,
            location,
        )
        foreman = self._foreman_from_employee_division(
            self._nested_employee_id(item, "foreman"),
            division,
        )
        tapper = self._tapper_from_employee(self._nested_employee_id(item, "tapper"))
        if not foreman:
            foreman = self._browse("wt.foreman", self._nested_id(item, "foreman"))
        if not tapper:
            tapper = self._browse("wt.tapper", self._nested_id(item, "tapper"))
        payload_receipt_rule = self._browse(
            "wt.receipt.rule",
            self._nested_id(item, "receipt_rule"),
        )
        fallback_receipt_rule = self._active_receipt_rule(company, location, division)
        receipt_rule = payload_receipt_rule
        if (
            fallback_receipt_rule
            and (
                not receipt_rule
                or self._is_archived(receipt_rule)
                or not self._receipt_rule_matches_scope(
                    receipt_rule,
                    company,
                    location,
                    division,
                )
            )
        ):
            receipt_rule = fallback_receipt_rule
        product_mapping = self._configured_product_mapping(company)
        return {
            "company": company,
            "estate": self._browse("wt.estate", self._nested_id(item, "estate")),
            "weighing_location": location,
            "initial_device": initial_device,
            "initial_weighing_location": initial_location,
            "division": division,
            "product": product_mapping.product_id,
            "payload_product": self._browse(
                "product.product",
                self._nested_id(item, "product"),
            ),
            "product_mapping": product_mapping,
            "receipt_rule": receipt_rule,
            "payload_receipt_rule": payload_receipt_rule,
            "foreman": foreman,
            "tapper": tapper,
        }

    def _evaluate_weighing_data_problem(
        self,
        item,
        records,
        device,
        master_synced_at,
        production_date,
        bot_user=False,
    ):
        issues = []
        notes_en = []
        notes_idn = []
        company = device.company_id or records["company"]
        has_device = bool(device)

        def add(code, note_en, note_idn=None):
            issues.append(code)
            notes_en.append(note_en)
            notes_idn.append(note_idn or self._data_problem_note_idn(note_en))

        payload_company_id = self._nested_id(item, "company")
        if payload_company_id and company and payload_company_id != company.id:
            add(
                "company_mismatch",
                "Payload company does not match weighing company.",
            )

        operator_employee_id = self._nested_employee_id(item, "operator")
        if has_device and operator_employee_id and operator_employee_id != device.employee_id.id:
            add(
                "operator_mismatch",
                "Payload operator does not match device operator.",
            )

        for key, label in (
            ("estate", "Estate"),
            ("weighing_location", "Weighing location"),
            ("division", "Division"),
            ("foreman", "Foreman"),
            ("tapper", "Tapper"),
        ):
            if self._nested_id(item, key) and not records[key]:
                add(
                    "missing_master",
                    "%s was not found in Odoo." % label,
                    "%s tidak ditemukan di master data."
                    % self.DATA_PROBLEM_LABEL_IDN.get(label, label),
                )
            elif self._is_archived(records[key]):
                add(
                    "inactive_master",
                    self.INACTIVE_MASTER_MESSAGE_EN % label,
                    self.INACTIVE_MASTER_MESSAGE_IDN
                    % self.DATA_PROBLEM_LABEL_IDN.get(label, label),
                )

        payload_receipt_rule_id = self._nested_id(item, "receipt_rule")
        payload_receipt_rule = records["payload_receipt_rule"]
        if payload_receipt_rule_id and not payload_receipt_rule:
            add(
                "missing_master",
                "Receipt rule was not found in Odoo.",
                "%s tidak ditemukan di master data."
                % self.DATA_PROBLEM_LABEL_IDN["Receipt rule"],
            )
        elif self._is_archived(payload_receipt_rule):
            add(
                "inactive_master",
                self.INACTIVE_MASTER_MESSAGE_EN % "Receipt rule",
                self.INACTIVE_MASTER_MESSAGE_IDN
                % self.DATA_PROBLEM_LABEL_IDN["Receipt rule"],
            )

        initial = item.get("initial_weighing") or {}
        initial = initial if isinstance(initial, dict) else {}
        initial_device_id = initial.get("device_id")
        initial_device = records["initial_device"]
        initial_location = records["initial_weighing_location"]
        if initial.get("weighing_date") and not initial_device_id:
            add("missing_master", "Initial weighing device is required.")
        if initial_device_id and not initial_device:
            add(
                "missing_master",
                "Initial weighing device was not found in Odoo.",
            )
        if initial.get("weighing_date") and initial_device and not initial_location:
            add(
                "missing_master",
                "Initial weighing location was not found in Odoo.",
            )
        elif self._is_archived(initial_location):
            add(
                "inactive_master",
                self.INACTIVE_MASTER_MESSAGE_EN % "Initial weighing location",
                self.INACTIVE_MASTER_MESSAGE_IDN
                % self.DATA_PROBLEM_LABEL_IDN["Initial weighing location"],
            )
        elif initial_location:
            if company and initial_location.company_id != company:
                add(
                    "weighing_location_mismatch",
                    "Initial weighing location does not belong to the weighing company.",
                )
            if initial_location.location_type != "field":
                add(
                    "weighing_location_mismatch",
                    "Initial weighing location must use Field type.",
                )

        estate = records["estate"]
        location = records["weighing_location"]
        division = records["division"]
        product = records["product"]
        payload_product = records["payload_product"]
        product_mapping = records["product_mapping"]
        receipt_rule = records["receipt_rule"]
        payload_receipt_rule = records["payload_receipt_rule"]
        foreman = records["foreman"]
        tapper = records["tapper"]

        if estate:
            if company and estate.company_id != company:
                add(
                    "estate_mismatch",
                    "Estate does not belong to weighing company.",
                )
            if location and location.estate_id != estate:
                add(
                    "estate_mismatch",
                    "Payload estate does not match weighing location estate.",
                )

        if location:
            if company and location.company_id != company:
                add(
                    "weighing_location_mismatch",
                    "Weighing location does not belong to the weighing company.",
                )
            if (
                has_device
                and location.operator_id
                and location.operator_id != device.employee_id
            ):
                add(
                    "operator_mismatch",
                    "Weighing location operator does not match device operator.",
                )

        if division:
            if company and division.company_id != company:
                add(
                    "company_mismatch",
                    "Division does not belong to weighing company.",
                )
            if location and division not in location.allowed_division_ids:
                add(
                    "division_not_allowed",
                    "Division is not allowed in the weighing location.",
                )

        if receipt_rule:
            if company and receipt_rule.company_id != company:
                add(
                    "receipt_rule_mismatch",
                    "Receipt rule company does not match.",
                )
            if location and receipt_rule.weighing_location_id != location:
                add(
                    "receipt_rule_mismatch",
                    "Receipt rule weighing location does not match.",
                )
            if division and receipt_rule.division_id != division:
                add(
                    "receipt_rule_mismatch",
                    "Receipt rule division does not match.",
                )

        if payload_receipt_rule and payload_receipt_rule != receipt_rule:
            if company and payload_receipt_rule.company_id != company:
                add(
                    "receipt_rule_mismatch",
                    "Receipt rule company does not match.",
                )
            if location and payload_receipt_rule.weighing_location_id != location:
                add(
                    "receipt_rule_mismatch",
                    "Receipt rule weighing location does not match.",
                )
            if division and payload_receipt_rule.division_id != division:
                add(
                    "receipt_rule_mismatch",
                    "Receipt rule division does not match.",
                )

        payload_product_id = self._nested_id(item, "product")
        if payload_product_id and not payload_product:
            add(
                "missing_master",
                "Product was not found in Odoo.",
                "Produk tidak ditemukan di master data.",
            )
        elif self._is_archived(payload_product):
            add(
                "inactive_master",
                self.INACTIVE_MASTER_MESSAGE_EN % "Product",
                self.INACTIVE_MASTER_MESSAGE_IDN % self.DATA_PROBLEM_LABEL_IDN["Product"],
            )

        if not product_mapping:
            add(
                "product_mapping_mismatch",
                "Weighing product is not configured for the weighing company.",
            )
        elif self._is_archived(product_mapping):
            add(
                "inactive_master",
                self.INACTIVE_MASTER_MESSAGE_EN % "Product mapping",
                self.INACTIVE_MASTER_MESSAGE_IDN
                % self.DATA_PROBLEM_LABEL_IDN["Product mapping"],
            )
        elif self._is_archived(product):
            add(
                "inactive_master",
                self.INACTIVE_MASTER_MESSAGE_EN % "Product",
                self.INACTIVE_MASTER_MESSAGE_IDN % self.DATA_PROBLEM_LABEL_IDN["Product"],
            )
        elif payload_product and payload_product != product:
            add(
                "product_mapping_mismatch",
                "Payload product does not match configured weighing product.",
            )

        clerk_employee_id = self._nested_employee_id(item, "clerk")
        if division and clerk_employee_id and division.clerk_id.id != clerk_employee_id:
            add(
                "clerk_mismatch",
                "Payload clerk does not match division clerk.",
            )

        foreman_employee_id = self._nested_employee_id(item, "foreman")
        foreman_from_employee = self._foreman_from_employee_division(
            foreman_employee_id,
            division,
        )
        effective_foreman = foreman_from_employee or foreman
        if foreman_employee_id and not foreman_from_employee:
            add(
                "foreman_mismatch",
                "Foreman employee is not assigned as foreman in the division.",
            )
        if foreman:
            if division and foreman.division_id != division:
                add(
                    "foreman_mismatch",
                    "Foreman does not belong to the division.",
                )
            if foreman_employee_id and foreman.employee_id.id != foreman_employee_id:
                add(
                    "foreman_mismatch",
                    "Foreman employee does not match.",
                )

        tapper_employee_id = self._nested_employee_id(item, "tapper")
        tapper_from_employee = self._tapper_from_employee(tapper_employee_id)
        if tapper_employee_id and not tapper_from_employee:
            add(
                "tapper_mismatch",
                "Tapper employee is not assigned as tapper.",
            )
        if tapper:
            if division and tapper.division_id != division:
                add(
                    "tapper_mismatch",
                    "Tapper does not belong to the division.",
                )
            if effective_foreman and tapper.foreman_id != effective_foreman:
                add(
                    "tapper_mismatch",
                    "Tapper does not belong to the foreman.",
                )
            if tapper_employee_id and tapper.employee_id.id != tapper_employee_id:
                add(
                    "tapper_mismatch",
                    "Tapper employee does not match.",
                )
        if tapper_from_employee and tapper_from_employee != tapper:
            if division and tapper_from_employee.division_id != division:
                add(
                    "tapper_mismatch",
                    "Tapper does not belong to the division.",
                )
            if (
                effective_foreman
                and tapper_from_employee.foreman_id != effective_foreman
            ):
                add(
                    "tapper_mismatch",
                    "Tapper does not belong to the foreman.",
                )
        if (
            tapper_from_employee
            and not effective_foreman
            and foreman_employee_id
            and tapper_from_employee.foreman_id
            and tapper_from_employee.foreman_id.employee_id.id != foreman_employee_id
        ):
            add(
                "tapper_mismatch",
                "Tapper foreman employee does not match weighing foreman.",
            )

        self._evaluate_initial_weighing_date_rule(
            item,
            production_date,
            add,
            bot_user,
        )
        self._evaluate_weighing_weight_rules(item, production_date, add, bot_user)

        unique_issues = list(dict.fromkeys(issues))
        return {
            "has_data_problem": bool(unique_issues),
            "data_problem_code": self._data_problem_code(unique_issues),
            "data_problem_note_en": "\n".join(notes_en),
            "data_problem_note_idn": "\n".join(notes_idn),
            "odoo_snapshot_json": json.dumps(
                self._odoo_snapshot(records, device),
                ensure_ascii=False,
            ),
        }

    def _evaluate_weighing_weight_rules(
        self,
        item,
        production_date,
        add,
        bot_user=False,
    ):
        initial = item.get("initial_weighing") or {}
        weighing_date = self._to_datetime(item.get("weighing_date"), bot_user)
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
                "Production weight must equal slab weight + reject weight + net weight.",
            )

        if not self._has_initial_weighing(initial):
            return

        expected_shrinkage_weight = initial_weight * shrinkage_percentage / 100.0
        if self._float_mismatch(shrinkage_weight, expected_shrinkage_weight):
            add(
                "shrinkage_tolerance_mismatch",
                "Shrinkage tolerance weight must equal initial weight * shrinkage percentage.",
            )

        if not self._is_after_production_date(production_date, weighing_date, bot_user):
            return

        expected_production_weight = initial_weight - expected_shrinkage_weight
        if self._float_mismatch(production_weight, expected_production_weight):
            add(
                "initial_weight_mismatch",
                "Production weight must equal initial weight minus shrinkage tolerance weight for cross-day weighing.",
            )

    def _evaluate_initial_weighing_date_rule(
        self,
        item,
        production_date,
        add,
        bot_user=False,
    ):
        initial = item.get("initial_weighing") or {}
        if not initial.get("weighing_date"):
            return
        production_date_value = self._date_part(production_date)
        initial_weighing_date_value = self._date_part(
            initial.get("weighing_date"),
            bot_user,
        )
        if (
            production_date_value
            and initial_weighing_date_value
            and production_date_value != initial_weighing_date_value
        ):
            add(
                "initial_weighing_date_mismatch",
                "Production date must match initial weighing date.",
            )

    def _data_problem_note_idn(self, note_en):
        return self.DATA_PROBLEM_NOTE_IDN.get(note_en, note_en)

    def _has_initial_weighing(self, initial):
        if not isinstance(initial, dict):
            return False
        return any(
            initial.get(field_name) not in (None, False, "")
            for field_name in (
                "weighing_date",
                "weight",
                "device_id",
            )
        )

    def _is_after_production_date(self, production_date, weighing_date, bot_user=False):
        if not production_date or not weighing_date:
            return False
        return self._date_part(weighing_date, bot_user) > fields.Date.to_date(production_date)

    def _date_part(self, value, bot_user=False):
        if not value:
            return False
        if hasattr(value, "hour"):
            return self._user_datetime_date(value, bot_user)
        if isinstance(value, str) and ":" in value:
            datetime_value = self._to_datetime(value, bot_user)
            if datetime_value:
                return self._user_datetime_date(datetime_value, bot_user)
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
        estate = records["estate"]
        location = records["weighing_location"]
        division = records["division"]
        product = records["product"]
        product_mapping = records.get("product_mapping")
        receipt_rule = records["receipt_rule"]
        payload_receipt_rule = records.get("payload_receipt_rule")
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
            "estate": self._record_snapshot(
                estate,
                ["code", "name", "active", "company_id"],
            ),
            "weighing_location": self._record_snapshot(
                location,
                ["code", "name", "active", "company_id", "operator_id", "location_type"],
            ),
            "initial_weighing_location": self._record_snapshot(
                records.get("initial_weighing_location"),
                [
                    "code",
                    "name",
                    "active",
                    "company_id",
                    "operator_id",
                    "location_type",
                    "warehouse_weighing_location_id",
                ],
            ),
            "division": self._record_snapshot(
                division,
                ["code", "name", "active", "company_id", "estate_id", "clerk_id"],
            ),
            "product": self._record_snapshot(product, ["display_name", "active"]),
            "product_mapping": self._record_snapshot(
                product_mapping,
                ["active", "company_id", "product_id"],
            ),
            "receipt_rule": self._record_snapshot(
                receipt_rule,
                [
                    "active",
                    "company_id",
                    "weighing_location_id",
                    "division_id",
                ],
            ),
            "payload_receipt_rule": self._record_snapshot(
                payload_receipt_rule,
                [
                    "active",
                    "company_id",
                    "weighing_location_id",
                    "division_id",
                ],
            ),
            "foreman": self._record_snapshot(
                foreman,
                ["active", "employee_id", "division_id", "company_id"],
            ),
            "tapper": self._record_snapshot(
                tapper,
                ["active", "employee_id", "division_id", "foreman_id", "company_id"],
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

    def _is_archived(self, record):
        return bool(record and "active" in record._fields and not record.active)

    def _configured_product_mapping(self, company):
        if not company:
            return self.env["wt.product"].browse()
        product_mapping = self.env["wt.product"].sudo().search(
            [("company_id", "=", company.id), ("active", "=", True)],
            limit=1,
        )
        if product_mapping:
            return product_mapping
        return self.env["wt.product"].sudo().with_context(active_test=False).search(
            [("company_id", "=", company.id)],
            limit=1,
        )

    def _active_receipt_rule(self, company, location, division):
        if not (company and location and division):
            return self.env["wt.receipt.rule"].browse()
        return self.env["wt.receipt.rule"].sudo().search(
            [
                ("company_id", "=", company.id),
                ("weighing_location_id", "=", location.id),
                ("division_id", "=", division.id),
                ("active", "=", True),
            ],
            limit=1,
        )

    def _receipt_rule_matches_scope(self, receipt_rule, company, location, division):
        if not receipt_rule:
            return False
        return (
            (not company or receipt_rule.company_id == company)
            and (not location or receipt_rule.weighing_location_id == location)
            and (not division or receipt_rule.division_id == division)
        )

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
        return self.env[model].sudo().with_context(active_test=False).browse(
            record_id
        ).exists()

    def _initial_device(self, initial, company):
        if not isinstance(initial, dict) or not initial.get("device_id"):
            return self.env["wt.device"].browse()
        domain = [("device_id", "=", initial.get("device_id"))]
        if company:
            domain.append(("company_id", "=", company.id))
        return self.env["wt.device"].sudo().search(domain, limit=1)

    def _initial_weighing_location_from_device(
        self,
        initial_device,
        company,
        division=False,
        final_location=False,
    ):
        if not initial_device or not initial_device.employee_id:
            return self.env["wt.weighing.location"].browse()

        base_domain = [
            ("location_type", "=", "field"),
            ("operator_id", "=", initial_device.employee_id.id),
        ]
        if company:
            base_domain.append(("company_id", "=", company.id))

        prioritized_domains = []
        if final_location and division:
            prioritized_domains.append(
                base_domain
                + [
                    ("warehouse_weighing_location_id", "=", final_location.id),
                    ("allowed_division_ids", "in", division.id),
                ]
            )
        if final_location:
            prioritized_domains.append(
                base_domain
                + [("warehouse_weighing_location_id", "=", final_location.id)]
            )
        if division:
            prioritized_domains.append(
                base_domain + [("allowed_division_ids", "in", division.id)]
            )
        prioritized_domains.append(base_domain)

        location_model = self.env["wt.weighing.location"].sudo().with_context(
            active_test=False
        )
        for domain in prioritized_domains:
            location = location_model.search(domain, limit=1, order="active desc, id")
            if location:
                return location
        return location_model.browse()

    def _to_date(self, value):
        return fields.Date.to_date(value) if value else False

    def _to_datetime(self, value, bot_user=False):
        datetime_value = fields.Datetime.to_datetime(value) if value else False
        if not datetime_value:
            return False
        if datetime_value.tzinfo:
            return datetime_value.astimezone(pytz.UTC).replace(tzinfo=None)

        tz_name = bot_user.tz if bot_user and bot_user.tz else "UTC"
        try:
            user_tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            user_tz = pytz.UTC
        try:
            localized = user_tz.localize(datetime_value, is_dst=None)
        except (pytz.AmbiguousTimeError, pytz.NonExistentTimeError):
            localized = user_tz.localize(datetime_value, is_dst=False)
        return localized.astimezone(pytz.UTC).replace(tzinfo=None)

    def _user_datetime_date(self, value, bot_user=False):
        if not value:
            return False
        if value.tzinfo:
            utc_value = value.astimezone(pytz.UTC)
        else:
            utc_value = pytz.UTC.localize(value)

        tz_name = bot_user.tz if bot_user and bot_user.tz else "UTC"
        try:
            user_tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            user_tz = pytz.UTC
        return utc_value.astimezone(user_tz).date()

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
