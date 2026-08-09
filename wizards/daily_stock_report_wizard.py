# -*- coding: utf-8 -*-

import base64
import html
import io
import json
from collections import defaultdict
from datetime import datetime, time, timedelta

from pytz import UTC, timezone

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


LOT_TYPE_LABELS = {
    "production": "Lot Produksi",
    "transit": "Lot Transit",
    "warehouse_stock": "Stock Gudang",
}


class DailyStockReport(models.TransientModel):
    _name = "wt.daily.stock.report"
    _description = "Daily Stock Report"

    name = fields.Char(
        string="Laporan",
        default="Laporan Stock Harian",
        readonly=True,
    )
    is_filtered = fields.Boolean(
        string="Sudah Difilter",
        default=False,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        readonly=True,
    )
    report_date = fields.Date(
        string="Tanggal Laporan",
        readonly=True,
    )
    month_start_date = fields.Date(
        string="Awal Bulan",
        readonly=True,
    )
    opening_stock = fields.Float(
        string="Stock Awal",
        readonly=True,
    )
    total_weighing = fields.Float(
        string="Total Penimbangan",
        readonly=True,
    )
    total_sales = fields.Float(
        string="Total Penjualan",
        readonly=True,
    )
    total_shrinkage = fields.Float(
        string="Total Susut",
        readonly=True,
    )
    closing_stock = fields.Float(
        string="Saldo Akhir",
        readonly=True,
    )
    balance_difference = fields.Float(
        string="Selisih Rekonsiliasi",
        readonly=True,
    )
    is_balanced = fields.Boolean(
        string="Rekonsiliasi Balance",
        default=True,
        readonly=True,
    )
    balance_warning = fields.Char(
        string="Catatan Rekonsiliasi",
        readonly=True,
    )
    matrix_data_json = fields.Text(
        string="Data Matriks",
        readonly=True,
    )
    preview_html = fields.Html(
        string="Preview",
        sanitize=False,
        readonly=True,
    )

    def action_open_filter(self):
        self.ensure_one()
        return {
            "name": _("Filter Laporan Stock Harian"),
            "type": "ir.actions.act_window",
            "res_model": "wt.daily.stock.report.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_report_id": self.id,
                "default_company_id": self.company_id.id or self.env.company.id,
                "default_report_date": (
                    self.report_date or fields.Date.context_today(self)
                ),
            },
        }

    def action_print_pdf(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Terapkan filter sebelum mencetak laporan."))
        return self.env.ref(
            "weightrack.action_report_daily_stock_pdf"
        ).report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Terapkan filter sebelum mengekspor laporan."))
        if xlsxwriter is None:
            raise ValidationError(_("Paket Python xlsxwriter belum terpasang."))

        data = self.get_matrix_data()
        columns = data.get("columns", [])
        rows = data.get("rows", [])
        spacer_column = 3 + len(columns)
        total_column = spacer_column + 1

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Stock Harian")

        base_format = {
            "font_name": "Arial",
            "font_size": 8,
            "border": 1,
            "border_color": "#111111",
            "valign": "vcenter",
        }
        title_format = workbook.add_format(
            {
                "font_name": "Arial",
                "font_size": 15,
                "bold": True,
                "align": "right",
                "valign": "vcenter",
            }
        )
        brand_format = workbook.add_format(
            {
                "font_name": "Arial",
                "font_size": 16,
                "bold": True,
                "font_color": "#247a3b",
                "valign": "vcenter",
            }
        )
        meta_format = workbook.add_format(
            {
                "font_name": "Arial",
                "font_size": 8,
                "font_color": "#4b5563",
                "align": "right",
            }
        )
        header_format = workbook.add_format(
            dict(
                base_format,
                bold=True,
                align="center",
                text_wrap=True,
                bg_color="#c7dca5",
            )
        )
        text_format = workbook.add_format(
            dict(base_format, text_wrap=True, indent=3)
        )
        number_format = workbook.add_format(
            dict(base_format, align="right", num_format="#,##0.##")
        )
        unit_format = workbook.add_format(dict(base_format, align="center"))
        percentage_text_format = workbook.add_format(
            dict(base_format, text_wrap=True, indent=3, font_color="#d60000")
        )
        percentage_format = workbook.add_format(
            dict(
                base_format,
                align="right",
                num_format="0.0\\%",
                font_color="#d60000",
            )
        )
        percentage_unit_format = workbook.add_format(
            dict(base_format, align="center", font_color="#d60000")
        )
        section_format = workbook.add_format(
            dict(base_format, bold=True, indent=1)
        )
        subsection_format = workbook.add_format(
            dict(base_format, bold=True, indent=2)
        )
        total_text_format = workbook.add_format(
            dict(
                base_format,
                bold=True,
                bg_color="#dcebc9",
                text_wrap=True,
                indent=3,
            )
        )
        total_number_format = workbook.add_format(
            dict(
                base_format,
                bold=True,
                bg_color="#dcebc9",
                align="right",
                num_format="#,##0.##",
            )
        )
        total_unit_format = workbook.add_format(
            dict(
                base_format,
                bold=True,
                bg_color="#dcebc9",
                align="center",
            )
        )

        sheet.merge_range(0, 0, 1, 2, "JULANG\nPLANTATIONS", brand_format)
        sheet.merge_range(
            0,
            max(3, total_column - 4),
            0,
            total_column,
            "LAPORAN STOCK HARIAN",
            title_format,
        )
        sheet.merge_range(
            1,
            max(3, total_column - 4),
            1,
            total_column,
            "Tanggal: %s   |   Perusahaan: %s"
            % (self.report_date or "", self.company_id.name or ""),
            meta_format,
        )

        header_row = 3
        sheet.merge_range(header_row, 0, header_row + 1, 0, "No", header_format)
        sheet.merge_range(header_row, 1, header_row + 1, 1, "Uraian", header_format)
        sheet.merge_range(header_row, 2, header_row + 1, 2, "Satuan", header_format)

        division_columns = [column for column in columns if column["kind"] == "division"]
        estate_columns = [column for column in columns if column["kind"] == "estate"]
        column_index = 3
        if division_columns:
            if len(division_columns) == 1:
                sheet.write(header_row, column_index, "Sub Divisi", header_format)
            else:
                sheet.merge_range(
                    header_row,
                    column_index,
                    header_row,
                    column_index + len(division_columns) - 1,
                    "Sub Divisi",
                    header_format,
                )
            for column in division_columns:
                sheet.write(header_row + 1, column_index, column["label"], header_format)
                column_index += 1
        if estate_columns:
            if len(estate_columns) == 1:
                sheet.write(header_row, column_index, "Divisi", header_format)
            else:
                sheet.merge_range(
                    header_row,
                    column_index,
                    header_row,
                    column_index + len(estate_columns) - 1,
                    "Divisi",
                    header_format,
                )
            for column in estate_columns:
                sheet.write(header_row + 1, column_index, column["label"], header_format)
                column_index += 1
        sheet.merge_range(
            header_row,
            total_column,
            header_row + 1,
            total_column,
            "Total",
            header_format,
        )

        row_index = header_row + 2
        for row in rows:
            style = row.get("style", "data")
            if style == "section":
                sheet.write(row_index, 0, row.get("number", ""), section_format)
                sheet.write(row_index, 1, row.get("label", ""), section_format)
                for index in range(2, spacer_column):
                    sheet.write(row_index, index, "", section_format)
                sheet.write(row_index, spacer_column, "")
                sheet.write(row_index, total_column, "", section_format)
                sheet.set_row(row_index, 13)
                row_index += 1
                continue

            if style == "subsection":
                for index in range(spacer_column):
                    sheet.write(row_index, index, "", subsection_format)
                sheet.write(row_index, 1, row.get("label", ""), subsection_format)
                sheet.write(row_index, spacer_column, "")
                sheet.write(row_index, total_column, "", subsection_format)
                sheet.set_row(row_index, 13)
                row_index += 1
                continue

            if style == "total":
                row_text_format = total_text_format
                row_number_format = total_number_format
                row_unit_format = total_unit_format
            elif style == "percentage":
                row_text_format = percentage_text_format
                row_number_format = percentage_format
                row_unit_format = percentage_unit_format
            else:
                row_text_format = text_format
                row_number_format = number_format
                row_unit_format = unit_format

            sheet.write(row_index, 0, "", row_text_format)
            sheet.write(row_index, 1, row.get("label", ""), row_text_format)
            sheet.write(row_index, 2, row.get("unit", ""), row_unit_format)
            values = row.get("values", {})
            for offset, column in enumerate(columns, start=3):
                value = values.get(column["key"])
                if value is None:
                    sheet.write(row_index, offset, "-", row_number_format)
                else:
                    sheet.write_number(row_index, offset, value, row_number_format)
            total_value = values.get("total")
            sheet.write(row_index, spacer_column, "")
            if total_value is None:
                sheet.write(row_index, total_column, "-", row_number_format)
            else:
                sheet.write_number(
                    row_index,
                    total_column,
                    total_value,
                    row_number_format,
                )
            sheet.set_row(row_index, 13)
            row_index += 1

        sheet.set_column(0, 0, 5)
        sheet.set_column(1, 1, 43)
        sheet.set_column(2, 2, 12)
        if spacer_column > 3:
            sheet.set_column(3, spacer_column - 1, 12)
        sheet.set_column(spacer_column, spacer_column, 1.5)
        sheet.set_column(total_column, total_column, 15)
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 1)
        sheet.set_margins(0.25, 0.25, 0.3, 0.3)
        sheet.repeat_rows(header_row, header_row + 1)
        sheet.hide_gridlines(2)
        sheet.freeze_panes(header_row + 2, 3)

        workbook.close()
        output.seek(0)
        filename = "Laporan Stock Harian - %s.xlsx" % (
            self.report_date or ""
        )
        attachment = self.env["ir.attachment"].create(
            {
                "name": filename,
                "type": "binary",
                "datas": base64.b64encode(output.read()),
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": (
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    def _open_current_report_action(self):
        self.ensure_one()
        return {
            "name": _("Laporan Stock Harian"),
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    def get_matrix_data(self):
        self.ensure_one()
        if not self.matrix_data_json:
            return {"columns": [], "rows": []}
        return json.loads(self.matrix_data_json)

    @api.model
    def format_matrix_value(self, value, percentage=False):
        if value is None:
            return "-"
        decimals = 1 if percentage else (0 if float(value).is_integer() else 2)
        formatted = ("{:,.%df}" % decimals).format(value)
        formatted = formatted.replace(",", "#").replace(".", ",").replace("#", ".")
        return "%s%s" % (formatted, "%" if percentage else "")


class DailyStockReportWizard(models.TransientModel):
    _name = "wt.daily.stock.report.wizard"
    _inherit = ["wt.shipping.provenance.mixin"]
    _description = "Daily Stock Report Wizard"

    report_id = fields.Many2one(
        "wt.daily.stock.report",
        string="Laporan",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        required=True,
        default=lambda self: self.env.company,
    )
    report_date = fields.Date(
        string="Tanggal Laporan",
        required=True,
        default=fields.Date.context_today,
    )

    def action_apply_filter(self):
        self.ensure_one()
        data = self.env["wt.daily.stock.analysis.service"].calculate(
            self.company_id,
            self.report_date,
        )
        balance_difference = data["balance_difference"]
        if abs(balance_difference) <= 0.01:
            balance_warning = _("Rekonsiliasi balance")
        else:
            balance_warning = _(
                "Ada selisih rekonsiliasi %.2f kg. Periksa pergerakan stok di luar alur WeighTrack."
            ) % balance_difference

        report = self.report_id
        report.write(
            {
                "is_filtered": True,
                "company_id": self.company_id.id,
                "report_date": self.report_date,
                "month_start_date": self.report_date.replace(day=1),
                "opening_stock": data["opening_stock"],
                "total_weighing": data["total_weighing"],
                "total_sales": data["total_sales"],
                "total_shrinkage": data["total_shrinkage"],
                "closing_stock": data["closing_stock"],
                "balance_difference": balance_difference,
                "is_balanced": abs(balance_difference) <= 0.01,
                "balance_warning": balance_warning,
                "matrix_data_json": json.dumps(data["matrix"], ensure_ascii=True),
                "preview_html": self._build_preview_html(data["matrix"]),
            }
        )
        return report._open_current_report_action()

    def _prepare_report_data(self):
        self.ensure_one()
        product = self.env["wt.product"].get_active_product(self.company_id)
        if not product:
            raise ValidationError(
                _("Produk timbang aktif untuk perusahaan ini belum dikonfigurasi.")
            )

        divisions = self.env["wt.division"].with_context(active_test=False).search(
            [("company_id", "=", self.company_id.id)],
            order="code, name",
        )
        estates = self.env["wt.estate"].with_context(active_test=False).search(
            [("company_id", "=", self.company_id.id)],
            order="code, name",
        )
        estates = estates.sorted(key=self._estate_report_sort_key)
        warehouses = self.env["stock.warehouse"].search(
            [("company_id", "=", self.company_id.id)],
            order="name",
        )
        columns = self._prepare_columns(divisions, estates)

        day_start, day_end = self._get_utc_bounds(
            self.report_date,
            self.report_date,
        )
        month_start = self.report_date.replace(day=1)
        mtd_start, mtd_end = self._get_utc_bounds(month_start, self.report_date)

        weighing_day = self._aggregate_weighings(
            self.report_date,
            self.report_date,
        )
        weighing_mtd = self._aggregate_weighings(month_start, self.report_date)

        month_opening = self._build_stock_snapshot(
            product,
            mtd_start,
            warehouses,
        )
        day_opening = (
            month_opening
            if day_start == mtd_start
            else self._build_stock_snapshot(
                product,
                day_start,
                warehouses,
            )
        )
        closing = self._build_stock_snapshot(
            product,
            day_end,
            warehouses,
        )
        stock_day = self._aggregate_stock_events(
            product,
            day_start,
            day_end,
            warehouses,
        )
        stock_mtd = self._aggregate_stock_events(
            product,
            mtd_start,
            mtd_end,
            warehouses,
        )

        opening_total = month_opening["all"].get("total", 0.0)
        closing_total = closing["all"].get("total", 0.0)
        production_in_total = stock_mtd["production_in"].get("total", 0.0)
        shipping_total = stock_mtd["shipping"].get("total", 0.0)
        shrink_total = self._sum_values(
            stock_mtd["storage_shrinkage"],
            stock_mtd["transfer_shrinkage"],
        ).get("total", 0.0)
        balance_difference = (
            opening_total
            + production_in_total
            - shipping_total
            - shrink_total
            - closing_total
        )

        rows = self._prepare_matrix_rows(
            month_opening,
            closing,
            weighing_day,
            weighing_mtd,
            stock_day,
            stock_mtd,
        )
        return {
            "matrix": {
                "columns": columns,
                "rows": rows,
            },
            "product_id": product.id,
            "analysis_values": {
                "opening_stock": day_opening["all"],
                "weighing_qty": stock_day["production_in"],
                "sales_qty": stock_day["shipping"],
                "storage_shrinkage_qty": stock_day["storage_shrinkage"],
                "transfer_shrinkage_qty": stock_day["transfer_shrinkage"],
                "closing_stock": closing["all"],
            },
            "opening_stock": opening_total,
            "total_weighing": production_in_total,
            "total_sales": shipping_total,
            "total_shrinkage": shrink_total,
            "closing_stock": closing_total,
            "balance_difference": balance_difference,
        }

    def _estate_report_sort_key(self, estate):
        name = (estate.name or "").strip().casefold()
        code = (estate.code or "").strip().casefold()
        identity = "%s %s" % (name, code)
        if "sebayur" in identity:
            priority = 0
        elif "gembung" in identity:
            priority = 1
        else:
            priority = 2
        return priority, code, name, estate.id

    def _prepare_columns(self, divisions, estates):
        columns = []
        for division in divisions:
            columns.append(
                {
                    "key": self._division_key(division),
                    "label": division.code or division.name,
                    "kind": "division",
                }
            )
        for estate in estates:
            columns.append(
                {
                    "key": self._estate_key(estate),
                    "label": estate.name or estate.code,
                    "kind": "estate",
                }
            )
        return columns

    def _prepare_matrix_rows(
        self,
        month_opening,
        closing,
        weighing_day,
        weighing_mtd,
        stock_day,
        stock_mtd,
    ):
        field_shrink_percentage_day = self._percentage_values(
            weighing_day["field_shrinkage"],
            weighing_day["field_weight"],
        )
        field_shrink_percentage_mtd = self._percentage_values(
            weighing_mtd["field_shrinkage"],
            weighing_mtd["field_weight"],
        )
        stock_shrink_day = self._sum_values(
            stock_day["storage_shrinkage"],
            stock_day["transfer_shrinkage"],
        )
        stock_shrink_mtd = self._sum_values(
            stock_mtd["storage_shrinkage"],
            stock_mtd["transfer_shrinkage"],
        )
        stock_out_day = self._sum_values(
            stock_day["shipping"],
            stock_day["transfer_shrinkage"],
        )
        shrink_base_day = self._sum_values(stock_day["shipping"], stock_shrink_day)
        shrink_base_mtd = self._sum_values(stock_mtd["shipping"], stock_shrink_mtd)
        stock_shrink_percentage_day = self._percentage_values(
            stock_shrink_day,
            shrink_base_day,
        )
        stock_shrink_percentage_mtd = self._percentage_values(
            stock_shrink_mtd,
            shrink_base_mtd,
        )

        rows = [
            self._section_row("I", _("Penimbangan")),
            self._subsection_row(_("Stock Awal")),
            self._data_row(
                _("Stock Awal"),
                month_opening["all"],
                style="total",
            ),
                self._subsection_row(_("Penimbangan Kebun")),
                self._data_row(_("Hari ini"), weighing_day["field_weight"]),
                self._data_row(
                    _("Sampai dengan hari ini"),
                    weighing_mtd["field_weight"],
                    style="total",
                ),
                self._subsection_row(_("Penimbangan Gudang")),
                self._data_row(_("Gudang Induk"), weighing_day["warehouse_main"]),
                self._data_row(
                    _("Gudang Transit"),
                    weighing_day["warehouse_transit"],
                ),
                self._data_row(
                    _("Jumlah Penerimaan Gudang"),
                    weighing_day["warehouse_total"],
                    style="total",
                ),
                self._data_row(
                    _("Sampai dengan hari ini"),
                    weighing_mtd["warehouse_total"],
                    style="total",
                ),
                self._subsection_row(_("Penjualan Produksi")),
                self._data_row(_("Hari ini"), stock_day["shipping"]),
                self._data_row(
                    _("Susut Transfer Antar Gudang"),
                    stock_day["transfer_shrinkage"],
                ),
                self._data_row(
                    _("Jumlah Pengeluaran Hari ini"),
                    stock_out_day,
                    style="total",
                ),
                self._data_row(
                    _("Sampai dengan hari ini"),
                    stock_mtd["shipping"],
                    style="total",
                ),
                self._section_row("II", _("Susut Produksi")),
                self._subsection_row(_("Susut Timbang dari Kebun ke Gudang")),
                self._data_row(_("Hari ini"), weighing_day["field_shrinkage"]),
                self._data_row(
                    _("Hari ini"),
                    field_shrink_percentage_day,
                    unit="%",
                    style="percentage",
                ),
                self._data_row(
                    _("Sampai dengan hari ini"),
                    weighing_mtd["field_shrinkage"],
                    style="total",
                ),
                self._data_row(
                    _("Sampai dengan hari ini"),
                    field_shrink_percentage_mtd,
                    unit="%",
                    style="percentage",
                ),
                self._subsection_row(_("Susut Timbang dari Gudang ke Pengiriman")),
                self._data_row(
                    _("Susut Penyimpanan Hari ini"),
                    stock_day["storage_shrinkage"],
                ),
                self._data_row(
                    _("Susut Transfer Antar Gudang"),
                    stock_day["transfer_shrinkage"],
                ),
                self._data_row(
                    _("Jumlah Susut Hari ini"),
                    stock_shrink_day,
                    style="total",
                ),
                self._data_row(
                    _("Jumlah Susut Hari ini"),
                    stock_shrink_percentage_day,
                    unit="%",
                    style="percentage",
                ),
                self._data_row(
                    _("Susut Penyimpanan s.d. Hari ini"),
                    stock_mtd["storage_shrinkage"],
                ),
                self._data_row(
                    _("Susut Transfer Antar Gudang s.d. Hari ini"),
                    stock_mtd["transfer_shrinkage"],
                ),
                self._data_row(
                    _("Jumlah Susut s.d. Hari ini"),
                    stock_shrink_mtd,
                    style="total",
                ),
                self._data_row(
                    _("Jumlah Susut s.d. Hari ini"),
                    stock_shrink_percentage_mtd,
                    unit="%",
                    style="percentage",
                ),
                self._section_row("III", _("Stock Produksi")),
                self._data_row(_("Saldo Awal"), month_opening["all"]),
                self._data_row(_("Produksi Masuk"), stock_mtd["production_in"]),
                self._data_row(_("Produksi Keluar"), stock_mtd["shipping"]),
                self._data_row(
                    _("Penyesuaian Susut Produksi"),
                    stock_shrink_mtd,
                ),
                self._data_row(
                    _("Saldo Akhir"),
                    closing["all"],
                    style="total",
                ),
        ]
        return rows

    def _aggregate_weighings(self, start_date, end_date):
        result = {
            "field_weight": defaultdict(float),
            "warehouse_main": defaultdict(float),
            "warehouse_transit": defaultdict(float),
            "warehouse_total": defaultdict(float),
            "field_shrinkage": defaultdict(float),
        }
        records = self.env["wt.weighing"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("production_date", ">=", start_date),
                ("production_date", "<=", end_date),
            ],
            order="production_date, id",
        )
        for record in records:
            initial_weight = record.initial_weight or 0.0
            net_weight = record.net_weight or 0.0
            tolerance_weight = record.shrinkage_tolerance_weight or 0.0
            field_weight = net_weight + tolerance_weight
            warehouse_main = net_weight if initial_weight <= 0.0 else 0.0
            warehouse_transit = net_weight if initial_weight > 0.0 else 0.0
            field_shrinkage = tolerance_weight
            division = record.division_id
            estate = division.estate_id if division else record.estate_id
            self._add_scope_value(result["field_weight"], field_weight, division, estate)
            self._add_scope_value(
                result["warehouse_main"],
                warehouse_main,
                division,
                estate,
            )
            self._add_scope_value(
                result["warehouse_transit"],
                warehouse_transit,
                division,
                estate,
            )
            self._add_scope_value(
                result["warehouse_total"],
                warehouse_main + warehouse_transit,
                division,
                estate,
            )
            self._add_scope_value(
                result["field_shrinkage"],
                field_shrinkage,
                division,
                estate,
            )
        return {key: dict(values) for key, values in result.items()}

    def _build_stock_snapshot(self, product, cutoff, warehouses):
        result = {
            "all": defaultdict(float),
            "production": defaultdict(float),
            "transit": defaultdict(float),
            "warehouse_lot_type": {},
        }
        domain = [
            ("company_id", "=", self.company_id.id),
            ("move_id.state", "=", "done"),
            ("move_id.date", "<", fields.Datetime.to_string(cutoff)),
            ("product_id", "=", product.id),
            ("lot_id", "!=", False),
            ("lot_id.wt_lot_type", "in", list(LOT_TYPE_LABELS)),
        ]
        move_lines = self.env["stock.move.line"].search(domain, order="id")
        for line in move_lines:
            quantity = self._line_quantity_in_product_uom(line)
            if line.location_id.usage == "internal":
                self._apply_snapshot_side(
                    result,
                    line,
                    line.location_id,
                    warehouses,
                    -quantity,
                )
            if line.location_dest_id.usage == "internal":
                self._apply_snapshot_side(
                    result,
                    line,
                    line.location_dest_id,
                    warehouses,
                    quantity,
                )
        result["all"] = self._clean_values(result["all"])
        result["production"] = self._clean_values(result["production"])
        result["transit"] = self._clean_values(result["transit"])
        result["warehouse_lot_type"] = {
            key: self._clean_values(values)
            for key, values in result["warehouse_lot_type"].items()
        }
        return result

    def _apply_snapshot_side(self, result, line, location, warehouses, quantity):
        lot = line.lot_id
        lot_type = lot.wt_lot_type or "production"
        warehouse = self._resolve_warehouse(location, warehouses)
        division = lot.division_id if lot_type == "production" else self.env["wt.division"]
        estate = (
            division.estate_id
            if division
            else (warehouse.estate_id if warehouse else self.env["wt.estate"])
        )
        self._add_scope_value(result["all"], quantity, division, estate)
        if lot_type == "production":
            self._add_scope_value(result["production"], quantity, division, estate)
        elif lot_type == "transit":
            self._add_scope_value(result["transit"], quantity, False, estate)

        warehouse_key = (warehouse.id or 0, lot_type)
        values = result["warehouse_lot_type"].setdefault(
            warehouse_key,
            defaultdict(float),
        )
        self._add_scope_value(values, quantity, division, estate)

    def _aggregate_stock_events(self, product, start_dt, end_dt, warehouses):
        result = {
            "production_in": defaultdict(float),
            "shipping": defaultdict(float),
            "storage_shrinkage": defaultdict(float),
            "transfer_shrinkage": defaultdict(float),
        }
        shrinkage_location = self._get_shrinkage_location()
        shrinkage_location_ids = set()
        if shrinkage_location:
            shrinkage_location_ids = set(
                self.env["stock.location"].search(
                    [("id", "child_of", shrinkage_location.id)]
                ).ids
            )
        domain = [
            ("company_id", "=", self.company_id.id),
            ("move_id.state", "=", "done"),
            ("move_id.date", ">=", fields.Datetime.to_string(start_dt)),
            ("move_id.date", "<", fields.Datetime.to_string(end_dt)),
            ("product_id", "=", product.id),
            ("lot_id", "!=", False),
            ("lot_id.wt_lot_type", "in", list(LOT_TYPE_LABELS)),
        ]
        move_lines = self.env["stock.move.line"].search(domain, order="id")
        for line in move_lines:
            quantity = self._line_quantity_in_product_uom(line)
            if quantity <= 0.0:
                continue
            picking = line.picking_id
            source_usage = line.location_id.usage
            destination_usage = line.location_dest_id.usage

            if picking.production_receipt_id or picking.production_receipt_reverse_id:
                sign = 0.0
                location = line.location_dest_id
                if source_usage != "internal" and destination_usage == "internal":
                    sign = 1.0
                    location = line.location_dest_id
                elif source_usage == "internal" and destination_usage != "internal":
                    sign = -1.0
                    location = line.location_id
                if sign:
                    self._add_event_value(
                        result["production_in"],
                        line,
                        location,
                        warehouses,
                        quantity * sign,
                    )

            delivery = picking.wt_delivery_id
            return_picking = getattr(picking, "return_id", self.env["stock.picking"])
            if not delivery and return_picking:
                delivery = return_picking.wt_delivery_id
            if delivery and delivery.state == "done":
                if source_usage == "customer" and destination_usage == "internal":
                    self._add_event_value(
                        result["shipping"],
                        line,
                        line.location_dest_id,
                        warehouses,
                        -quantity,
                    )

            if self._is_transit_merge_move_line(line):
                continue
            source_is_shrinkage = line.location_id.id in shrinkage_location_ids
            destination_is_shrinkage = line.location_dest_id.id in shrinkage_location_ids
            shrinkage_sign = 0.0
            stock_location = line.location_id
            if source_usage == "internal" and destination_is_shrinkage:
                shrinkage_sign = 1.0
                stock_location = line.location_id
            elif source_is_shrinkage and destination_usage == "internal":
                shrinkage_sign = -1.0
                stock_location = line.location_dest_id
            if shrinkage_sign:
                category = (
                    "transfer_shrinkage"
                    if line.lot_id.wt_lot_type == "transit"
                    else "storage_shrinkage"
                )
                self._add_event_value(
                    result[category],
                    line,
                    stock_location,
                    warehouses,
                    quantity * shrinkage_sign,
                )
        source_lot_sales = self._aggregate_delivery_source_lot_sales(
            product,
            start_dt,
            end_dt,
            warehouses,
        )
        for key, value in source_lot_sales.items():
            result["shipping"][key] += value
        return {
            key: self._clean_values(values)
            for key, values in result.items()
        }

    def _aggregate_delivery_source_lot_sales(
        self,
        product,
        start_dt,
        end_dt,
        warehouses,
    ):
        values = defaultdict(float)
        for source_event in self._iter_delivery_shipping_source_events(
            fields.Datetime.to_string(start_dt),
            fields.Datetime.to_string(end_dt),
            warehouses,
            end_operator="<",
            product=product,
        ):
            division = source_event["division"]
            warehouse = source_event["warehouse"]
            estate = (
                division.estate_id
                if division
                else (
                    warehouse.estate_id
                    if warehouse
                    else self.env["wt.estate"]
                )
            )
            self._add_scope_value(
                values,
                source_event["quantity"],
                division,
                estate,
            )
        return self._clean_values(values)

    def _add_event_value(self, values, line, location, warehouses, quantity):
        lot = line.lot_id
        warehouse = self._resolve_warehouse(location, warehouses)
        division = (
            lot.division_id
            if lot.wt_lot_type == "production"
            else self.env["wt.division"]
        )
        estate = (
            division.estate_id
            if division
            else (warehouse.estate_id if warehouse else self.env["wt.estate"])
        )
        self._add_scope_value(values, quantity, division, estate)

    def _add_scope_value(self, values, quantity, division=False, estate=False):
        if abs(quantity) <= 0.000001:
            return
        if division:
            values[self._division_key(division)] += quantity
            estate = division.estate_id or estate
        if estate:
            values[self._estate_key(estate)] += quantity
        values["total"] += quantity

    def _division_key(self, division):
        return "division:%s" % division.id

    def _estate_key(self, estate):
        return "estate:%s" % estate.id

    def _sum_values(self, *value_sets):
        result = defaultdict(float)
        for values in value_sets:
            for key, value in (values or {}).items():
                result[key] += value or 0.0
        return self._clean_values(result)

    def _percentage_values(self, numerator, denominator):
        result = {}
        keys = set(numerator or {}) | set(denominator or {})
        for key in keys:
            base = (denominator or {}).get(key, 0.0)
            if abs(base) <= 0.000001:
                continue
            result[key] = (numerator or {}).get(key, 0.0) / base * 100.0
        return result

    def _clean_values(self, values):
        return {
            key: value
            for key, value in dict(values or {}).items()
            if abs(value) > 0.000001
        }

    def _has_values(self, values):
        return bool(values) and any(
            abs(value or 0.0) > 0.000001 for value in values.values()
        )

    def _line_quantity_in_product_uom(self, line):
        uom = line.product_uom_id or line.product_id.uom_id
        return uom._compute_quantity(
            line.quantity,
            line.product_id.uom_id,
            round=False,
        )

    def _resolve_warehouse(self, location, warehouses):
        if not location or not location.parent_path:
            return self.env["stock.warehouse"]
        best_warehouse = self.env["stock.warehouse"]
        best_length = 0
        for warehouse in warehouses:
            parent_path = warehouse.view_location_id.parent_path
            if parent_path and location.parent_path.startswith(parent_path):
                path_length = len(parent_path)
                if path_length > best_length:
                    best_warehouse = warehouse
                    best_length = path_length
        return best_warehouse

    def _get_shrinkage_location(self):
        location = self.env.ref(
            "weightrack.stock_location_wt_inventory_loss_susut",
            raise_if_not_found=False,
        )
        if location:
            return location
        return self.env["stock.location"].search(
            [
                ("name", "=", "Susut"),
                ("usage", "=", "inventory"),
                ("location_id.name", "=", "Inventory Loss"),
            ],
            limit=1,
        )

    def _is_transit_merge_move_line(self, line):
        description = line.move_id.description_picking or ""
        return (
            description.startswith("Consume old lots for transit merge")
            or description.startswith("Produce new merged lot for transit")
        )

    def _get_utc_bounds(self, start_date, end_date):
        user_tz = timezone(self.env.user.tz or "UTC")
        start_local = user_tz.localize(datetime.combine(start_date, time.min))
        next_date = end_date + timedelta(days=1)
        end_local = user_tz.localize(datetime.combine(next_date, time.min))
        return (
            start_local.astimezone(UTC).replace(tzinfo=None),
            end_local.astimezone(UTC).replace(tzinfo=None),
        )

    def _section_row(self, number, label):
        return {
            "style": "section",
            "number": number,
            "label": label,
            "values": {},
        }

    def _subsection_row(self, label):
        return {"style": "subsection", "label": label, "values": {}}

    def _data_row(self, label, values, unit="Kg Basah", style="data"):
        return {
            "style": style,
            "label": label,
            "unit": unit,
            "values": dict(values or {}),
        }

    def _build_preview_html(self, matrix):
        columns = matrix.get("columns", [])
        rows = matrix.get("rows", [])
        division_columns = [column for column in columns if column["kind"] == "division"]
        estate_columns = [column for column in columns if column["kind"] == "estate"]
        total_columns = 4 + len(columns)
        parts = [
            '<div class="table-responsive">',
            '<table class="table table-sm table-hover table-bordered align-middle mb-0">',
            '<thead class="table-light"><tr>',
            '<th rowspan="2" class="text-center">No</th>',
            '<th rowspan="2">Uraian</th>',
            '<th rowspan="2" class="text-center">Satuan</th>',
        ]
        if division_columns:
            parts.append(
                '<th colspan="%s" class="text-center">Sub Divisi</th>'
                % len(division_columns)
            )
        if estate_columns:
            parts.append(
                '<th colspan="%s" class="text-center">Divisi</th>'
                % len(estate_columns)
            )
        parts.append(
            '<th rowspan="2" class="text-end">Total</th></tr><tr>'
        )
        for column in columns:
            parts.append(
                '<th class="text-center">%s</th>'
                % html.escape(column["label"] or "-")
            )
        parts.append("</tr></thead><tbody>")

        for row in rows:
            style = row.get("style", "data")
            if style == "section":
                parts.append(
                    '<tr class="table-secondary fw-bold">'
                    '<td class="text-center">%s</td><td colspan="%s">%s</td></tr>'
                    % (
                        html.escape(row.get("number", "")),
                        total_columns - 1,
                        html.escape(row.get("label", "")),
                    )
                )
                continue
            if style == "subsection":
                parts.append(
                    '<tr class="fw-bold"><td></td><td class="ps-3">%s</td><td></td>'
                    '<td colspan="%s"></td></tr>'
                    % (
                        html.escape(row.get("label", "")),
                        len(columns) + 1,
                    )
                )
                continue

            row_class = {
                "total": "table-success fw-bold",
                "percentage": "text-danger",
            }.get(style, "")
            parts.append('<tr class="%s">' % row_class)
            parts.append('<td></td><td class="ps-4">%s</td>'
                         '<td class="text-center">%s</td>' % (
                html.escape(row.get("label", "")),
                html.escape(row.get("unit", "")),
            ))
            values = row.get("values", {})
            is_percentage = style == "percentage"
            for column in columns:
                parts.append(
                    '<td class="text-end text-nowrap">%s</td>'
                    % self._format_html_value(
                        values.get(column["key"]),
                        is_percentage,
                    )
                )
            parts.append(
                '<td class="text-end text-nowrap">%s</td>'
                % self._format_html_value(values.get("total"), is_percentage)
            )
            parts.append("</tr>")
        parts.append("</tbody></table>")
        parts.append("</div>")
        return "".join(parts)

    def _format_html_value(self, value, percentage=False):
        if value is None:
            return "-"
        decimals = 1 if percentage else (0 if float(value).is_integer() else 2)
        formatted = ("{:,.%df}" % decimals).format(value)
        formatted = formatted.replace(",", "#").replace(".", ",").replace("#", ".")
        return "%s%%" % formatted if percentage else formatted


class ReportDailyStock(models.AbstractModel):
    _name = "report.weightrack.report_daily_stock_document"
    _description = "Daily Stock Report"

    def _get_report_values(self, docids, data=None):
        docs = self.env["wt.daily.stock.report"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "wt.daily.stock.report",
            "docs": docs,
        }
