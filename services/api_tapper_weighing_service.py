# -*- coding: utf-8 -*-

from datetime import date
from dateutil.relativedelta import relativedelta

from odoo import _, fields, models


class ApiTapperWeighingService(models.AbstractModel):
    _name = "wt.api.tapper.weighing.service"
    _description = "API Tapper Weighing Service"

    def _response(self):
        return self.env["wt.api.response.service"].sudo()

    def pull_tapper_weighing(self, payload):
        """
        Mengembalikan data penimbangan 3 bulan terakhir untuk tapper tertentu.

        Request payload:
            badge_id (str): Badge ID (barcode) dari karyawan tapper.

        Response data:
            tapper    : info tapper (nama, badge_id, foreman, estate)
            weighings : list penimbangan receipt_validated 3 bulan terakhir
        """
        response = self._response()

        # --- Validasi payload ---
        badge_id = payload.get("badge_id")
        if not badge_id:
            return response.error(
                "missing_badge_id",
                _("Badge ID is required."),
                400,
            )

        # --- Cari karyawan berdasarkan badge / barcode ---
        employee = self.env["hr.employee"].sudo().search(
            [("barcode", "=", badge_id)],
            limit=1,
        )
        if not employee:
            return response.error(
                "tapper_not_found",
                _("Data Tidak Ditemukan."),
                404,
            )

        # --- Cari record tapper aktif untuk karyawan tersebut ---
        tapper = self.env["wt.tapper"].sudo().search(
            [
                ("employee_id", "=", employee.id),
                ("active", "=", True),
            ],
            limit=1,
        )
        if not tapper:
            return response.error(
                "tapper_record_not_found",
                _("Data Tidak Ditemukan."),
                404,
            )

        # --- Rentang tanggal: 3 bulan ke belakang dari hari ini ---
        today = date.today()
        date_from = today - relativedelta(months=3)

        # --- Query penimbangan ---
        weighings = self.env["wt.weighing"].sudo().search(
            [
                ("tapper_id", "=", tapper.id),
                ("state", "=", "receipt_validated"),
                ("production_date", ">=", fields.Date.to_string(date_from)),
                ("production_date", "<=", fields.Date.to_string(today)),
            ],
            order="production_date desc, id desc",
        )

        return response.success(
            {
                "tapper": self._tapper_payload(tapper),
                "weighings": [
                    self._weighing_payload(w) for w in weighings
                ],
                "count": len(weighings),
                "date_from": fields.Date.to_string(date_from),
                "date_to": fields.Date.to_string(today),
            }
        )

    # ------------------------------------------------------------------
    # Payload builders
    # ------------------------------------------------------------------

    def _tapper_payload(self, tapper):
        employee = tapper.employee_id
        foreman = tapper.foreman_id
        division = tapper.division_id
        estate = division.estate_id if division else self.env["wt.estate"].browse()

        return {
            "id": tapper.id,
            "name": employee.name,
            "badge_id": employee.barcode or False,
            "company_id": tapper.company_id.id,
            "company_name": tapper.company_id.name,
            "division_id": division.id if division else False,
            "division_name": division.name if division else False,
            "estate_id": estate.id if estate else False,
            "estate_name": estate.name if estate else False,
            "foreman_id": foreman.id if foreman else False,
            "foreman_name": foreman.employee_id.name if foreman else False,
            "foreman_badge_id": foreman.employee_id.barcode if foreman else False,
        }

    def _weighing_payload(self, weighing):
        weighing_location = weighing.weighing_location_id
        estate = weighing.estate_id

        return {
            "id": weighing.id,
            "name": weighing.name,
            "production_date": fields.Date.to_string(weighing.production_date),
            # Berat
            "production_weight": weighing.production_weight,
            "slab_weight": weighing.slab_weight,
            "reject_weight": weighing.reject_weight,
            "net_weight": weighing.net_weight,
            # Lokasi timbang
            "weighing_location_id": weighing_location.id if weighing_location else False,
            "weighing_location_name": weighing_location.name if weighing_location else False,
            "estate_id": estate.id if estate else False,
            "estate_name": estate.name if estate else False,
            # Mandor
            "foreman_id": weighing.foreman_id.id if weighing.foreman_id else False,
            "foreman_name": weighing.foreman_name or False,
            "foreman_badge_id": weighing.foreman_barcode or False,
            # Status
            "state": weighing.state,
        }
