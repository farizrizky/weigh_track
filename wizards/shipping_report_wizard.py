# -*- coding: utf-8 -*-

import base64
import io
import re
from datetime import datetime, time

from pytz import UTC, timezone

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class ShippingReport(models.TransientModel):
    _name = "wt.shipping.report"
    _description = "Shipping Report"

    name = fields.Char(
        string="Report",
        default="Laporan Pengiriman",
        readonly=True,
    )
    is_filtered = fields.Boolean(
        string="Filtered",
        default=False,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        readonly=True,
    )
    start_date = fields.Date(
        string="Tanggal Dari",
        readonly=True,
    )
    end_date = fields.Date(
        string="Tanggal Sampai",
        readonly=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Gudang",
        readonly=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Divisi",
        readonly=True,
    )
    total_quantity = fields.Float(
        string="Total Terkirim",
        readonly=True,
    )
    total_opening_qty = fields.Float(string="Total Stok Awal", readonly=True)
    total_stock_in_qty = fields.Float(string="Total Stok Masuk", readonly=True)
    total_stock_qty = fields.Float(string="Total Stok Tersedia", readonly=True)
    total_balance_qty = fields.Float(string="Total Saldo Akhir", readonly=True)
    total_initial_qty = fields.Float(
        string="Total Stok Tersedia",
        readonly=True,
    )
    total_shipped_percentage = fields.Char(
        string="% Terkirim",
        readonly=True,
    )
    summary_line_ids = fields.One2many(
        "wt.shipping.report.summary.line",
        "report_id",
        string="Ringkasan",
        readonly=True,
    )
    detail_line_ids = fields.One2many(
        "wt.shipping.report.detail.line",
        "report_id",
        string="Detail",
        readonly=True,
    )

    def action_open_filter(self):
        self.ensure_one()
        return {
            "name": _("Filter Laporan Pengiriman"),
            "type": "ir.actions.act_window",
            "res_model": "wt.shipping.report.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_report_id": self.id,
                "default_company_id": self.company_id.id or self.env.company.id,
                "default_start_date": self.start_date or fields.Date.context_today(self),
                "default_end_date": self.end_date or fields.Date.context_today(self),
                "default_warehouse_id": self.warehouse_id.id,
                "default_division_id": self.division_id.id,
            },
        }

    def action_print_pdf(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Please apply a filter before printing the report."))
        return self.env.ref("weightrack.action_report_shipping_pdf").report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Please apply a filter before exporting the report."))
        if xlsxwriter is None:
            raise ValidationError(_("The xlsxwriter Python package is not installed."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Pengiriman")

        title_format = workbook.add_format(
            {"bold": True, "font_size": 14, "align": "center"}
        )
        label_format = workbook.add_format({"bold": True})
        header_format = workbook.add_format(
            {
                "bold": True,
                "align": "center",
                "valign": "vcenter",
                "border": 1,
                "text_wrap": True,
            }
        )
        text_format = workbook.add_format({"border": 1})
        number_format = workbook.add_format(
            {"border": 1, "num_format": "#,##0.00"}
        )
        date_format = workbook.add_format(
            {"border": 1, "num_format": "dd/mm/yyyy"}
        )
        total_label_format = workbook.add_format(
            {"bold": True, "align": "right", "border": 1}
        )
        total_number_format = workbook.add_format(
            {"bold": True, "border": 1, "num_format": "#,##0.00"}
        )

        sheet.merge_range("A1:L1", self.company_id.name or "", title_format)
        sheet.merge_range("A2:L2", "LAPORAN PENGIRIMAN", title_format)
        sheet.write("A4", "Rentang Tanggal", label_format)
        sheet.write("B4", "%s s/d %s" % (self.start_date or "", self.end_date or ""))
        sheet.write("A5", "Gudang", label_format)
        sheet.write(
            "B5",
            self.warehouse_id.display_name if self.warehouse_id else "Semua Gudang",
        )
        sheet.write("A6", "Divisi", label_format)
        sheet.write(
            "B6",
            self.division_id.display_name if self.division_id else "Semua Divisi",
        )
        sheet.write("A7", "Status DO", label_format)
        sheet.write("B7", "Selesai / Retur")

        summary_headers = [
            "No", "Gudang", "Divisi", "Stok Awal", "Stok Masuk",
            "Stok Tersedia", "Total Terkirim", "Saldo Akhir", "% Terkirim",
        ]
        summary_widths = [6, 24, 20, 14, 14, 14, 16, 14, 12]
        for column, width in enumerate(summary_widths):
            sheet.set_column(column, column, width)
        sheet.write(8, 0, "RINGKASAN PER DIVISI", label_format)
        for column, header in enumerate(summary_headers):
            sheet.write(9, column, header, header_format)

        row_index = 10
        for line in self.summary_line_ids:
            sheet.write(row_index, 0, line.sequence, text_format)
            sheet.write(row_index, 1, line.warehouse_name or "", text_format)
            sheet.write(row_index, 2, line.division_name or "", text_format)
            sheet.write(row_index, 3, line.opening_qty, number_format)
            sheet.write(row_index, 4, line.stock_in_qty, number_format)
            sheet.write(row_index, 5, line.stock_qty, number_format)
            sheet.write(row_index, 6, line.quantity, number_format)
            sheet.write(row_index, 7, line.balance_qty, number_format)
            sheet.write(row_index, 8, line.shipped_percentage or "0.00%", text_format)
            row_index += 1
        sheet.merge_range(row_index, 0, row_index, 2, "Total", total_label_format)
        sheet.write(row_index, 3, self.total_opening_qty, total_number_format)
        sheet.write(row_index, 4, self.total_stock_in_qty, total_number_format)
        sheet.write(row_index, 5, self.total_stock_qty, total_number_format)
        sheet.write(row_index, 6, self.total_quantity, total_number_format)
        sheet.write(row_index, 7, self.total_balance_qty, total_number_format)
        sheet.write(row_index, 8, self.total_shipped_percentage or "0.00%", total_label_format)

        row_index += 3
        detail_headers = [
            "No",
            "Tanggal Produksi",
            "Gudang",
            "Divisi",
            "Lot Produksi",
            "Produk",
            "Stok",
            "Qty Terkirim",
            "Saldo Akhir",
            "% Terkirim",
            "Satuan",
        ]
        detail_widths = [6, 15, 24, 20, 28, 24, 14, 14, 14, 12, 12]
        for column, width in enumerate(detail_widths):
            sheet.set_column(column, column, width)
        sheet.write(row_index, 0, "DETAIL PENGIRIMAN", label_format)
        row_index += 1
        for column, header in enumerate(detail_headers):
            sheet.write(row_index, column, header, header_format)
        row_index += 1

        for line in self.detail_line_ids:
            sheet.write(row_index, 0, line.sequence, text_format)
            if line.production_date:
                sheet.write_datetime(
                    row_index,
                    1,
                    datetime.combine(line.production_date, time.min),
                    date_format,
                )
            else:
                sheet.write(row_index, 1, "", text_format)
            sheet.write(row_index, 2, line.warehouse_name or "", text_format)
            sheet.write(row_index, 3, line.division_name or "", text_format)
            sheet.write(row_index, 4, line.lot_name or "", text_format)
            sheet.write(row_index, 5, line.product_name or "", text_format)
            sheet.write(row_index, 6, line.stock_qty, number_format)
            sheet.write(row_index, 7, line.quantity, number_format)
            sheet.write(row_index, 8, line.balance_qty, number_format)
            sheet.write(row_index, 9, line.shipped_percentage or "0.00%", text_format)
            sheet.write(row_index, 10, line.uom_name or "", text_format)
            row_index += 1
        sheet.merge_range(row_index, 0, row_index, 5, "Total", total_label_format)
        sheet.write(row_index, 6, self.total_stock_qty, total_number_format)
        sheet.write(row_index, 7, self.total_quantity, total_number_format)
        sheet.write(row_index, 8, self.total_balance_qty, total_number_format)
        sheet.write(row_index, 9, self.total_shipped_percentage or "0.00%", total_label_format)
        sheet.write(row_index, 10, "", text_format)

        workbook.close()
        output.seek(0)
        filename = "Laporan Pengiriman - %s sd %s.xlsx" % (
            self.start_date or "",
            self.end_date or "",
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
            "name": _("Laporan Pengiriman"),
            "type": "ir.actions.act_window",
            "res_model": "wt.shipping.report",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }


class ShippingReportSummaryLine(models.TransientModel):
    _name = "wt.shipping.report.summary.line"
    _description = "Shipping Report Summary Line"
    _order = "sequence, id"

    report_id = fields.Many2one(
        "wt.shipping.report",
        string="Report",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="No", readonly=True)
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Gudang",
        readonly=True,
    )
    warehouse_name = fields.Char(string="Gudang", readonly=True)
    division_id = fields.Many2one(
        "wt.division",
        string="Divisi",
        readonly=True,
    )
    division_name = fields.Char(string="Divisi", readonly=True)
    opening_qty = fields.Float(string="Stok Awal", readonly=True)
    stock_in_qty = fields.Float(string="Stok Masuk", readonly=True)
    stock_qty = fields.Float(string="Stok Tersedia", readonly=True)
    quantity = fields.Float(string="Total Terkirim", readonly=True)
    balance_qty = fields.Float(string="Saldo Akhir", readonly=True)
    shipped_percentage = fields.Char(string="% Terkirim", readonly=True)


class ShippingReportDetailLine(models.TransientModel):
    _name = "wt.shipping.report.detail.line"
    _description = "Shipping Report Detail Line"
    _order = "sequence, id"

    report_id = fields.Many2one(
        "wt.shipping.report",
        string="Report",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="No", readonly=True)
    production_date = fields.Date(string="Tanggal Produksi", readonly=True)
    movement_date = fields.Datetime(string="Tanggal", readonly=True)
    delivery_id = fields.Many2one(
        "wt.delivery",
        string="Pengiriman",
        readonly=True,
    )
    delivery_name = fields.Char(string="Nomor DO", readonly=True)
    customer_id = fields.Many2one(
        "res.partner",
        string="Customer Penerima",
        readonly=True,
    )
    customer_name = fields.Char(string="Customer Penerima", readonly=True)
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Gudang",
        readonly=True,
    )
    warehouse_name = fields.Char(string="Gudang", readonly=True)
    division_id = fields.Many2one(
        "wt.division",
        string="Divisi",
        readonly=True,
    )
    division_name = fields.Char(string="Divisi", readonly=True)
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot Produksi",
        readonly=True,
    )
    lot_name = fields.Char(string="Lot Produksi", readonly=True)
    product_id = fields.Many2one(
        "product.product",
        string="Produk",
        readonly=True,
    )
    product_name = fields.Char(string="Produk", readonly=True)
    quantity = fields.Float(string="Qty Terkirim", readonly=True)
    stock_qty = fields.Float(string="Stok", readonly=True)
    balance_qty = fields.Float(string="Saldo Akhir", readonly=True)
    movement_count = fields.Integer(string="Jumlah Pergerakan", readonly=True)
    initial_qty = fields.Float(string="Stok", readonly=True)
    shipped_percentage = fields.Char(string="% Terkirim", readonly=True)
    uom_name = fields.Char(string="Satuan", readonly=True)


class ShippingReportWizard(models.TransientModel):
    _name = "wt.shipping.report.wizard"
    _inherit = [
        "wt.shipping.provenance.mixin",
        "wt.stock.period.basis.mixin",
    ]
    _description = "Shipping Report Wizard"

    report_id = fields.Many2one(
        "wt.shipping.report",
        string="Report",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        required=True,
        default=lambda self: self.env.company,
    )
    start_date = fields.Date(
        string="Tanggal Dari",
        required=True,
        default=fields.Date.context_today,
    )
    end_date = fields.Date(
        string="Tanggal Sampai",
        required=True,
        default=fields.Date.context_today,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Gudang",
        domain="[('company_id', '=', company_id)]",
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Divisi",
        domain="[('company_id', '=', company_id)]",
    )

    @api.onchange("company_id")
    def _onchange_company_id(self):
        self.warehouse_id = False
        self.division_id = False

    def action_apply_filter(self):
        self.ensure_one()
        if self.start_date > self.end_date:
            raise ValidationError(
                _("Tanggal Dari tidak boleh lebih besar dari Tanggal Sampai.")
            )

        data = self._prepare_report_data()
        report = self.report_id
        report.summary_line_ids.unlink()
        report.detail_line_ids.unlink()
        report.write(
            {
                "is_filtered": True,
                "company_id": self.company_id.id,
                "start_date": self.start_date,
                "end_date": self.end_date,
                "warehouse_id": self.warehouse_id.id or False,
                "division_id": self.division_id.id or False,
                "total_quantity": data["total_quantity"],
                "total_opening_qty": data["total_opening_qty"],
                "total_stock_in_qty": data["total_stock_in_qty"],
                "total_stock_qty": data["total_stock_qty"],
                "total_balance_qty": data["total_balance_qty"],
                "total_initial_qty": data["total_initial_qty"],
                "total_shipped_percentage": data["total_shipped_percentage"],
            }
        )
        if data["summary_vals"]:
            self.env["wt.shipping.report.summary.line"].create(
                data["summary_vals"]
            )
        if data["detail_vals"]:
            self.env["wt.shipping.report.detail.line"].create(
                data["detail_vals"]
            )
        return report._open_current_report_action()

    def _prepare_report_data(self):
        warehouses = self.env["stock.warehouse"].search(
            [("company_id", "=", self.company_id.id)]
        )
        division_warehouses = self._basis_division_warehouse_map()
        events = []
        start_dt, end_dt = self._get_utc_date_range()
        for source_event in self._iter_delivery_shipping_source_events(
            fields.Datetime.to_string(start_dt),
            fields.Datetime.to_string(end_dt),
            warehouses,
            end_operator="<=",
            transit_quantity_basis="source",
        ):
            self._append_event(events, **source_event)
        rows = self._build_period_stock_basis(start_dt, end_dt, warehouses)
        if self.division_id:
            rows = {
                key: value
                for key, value in rows.items()
                if value["division"] == self.division_id
            }
        for row in rows.values():
            row.update(quantity=0.0, movement_count=0, movement_date=False)

        for event in events:
            key = self._stock_basis_key(event["division"], event["lot"])
            row = rows.setdefault(
                key,
                {
                    "warehouse": (
                        self.warehouse_id
                        or event["warehouse"]
                        or division_warehouses.get(event["division"].id)
                        or self.env["stock.warehouse"]
                    ),
                    "division": event["division"],
                    "lot": event["lot"],
                    "product": event["product"],
                    "uom": event["uom"],
                    "opening_qty": 0.0,
                    "stock_in_qty": 0.0,
                    "closing_qty": 0.0,
                    "quantity": 0.0,
                    "movement_count": 0,
                    "movement_date": False,
                },
            )
            row["quantity"] += event["quantity"]
            row["movement_count"] += 1
            if not row["movement_date"] or event["movement_date"] > row["movement_date"]:
                row["movement_date"] = event["movement_date"]

        transit_proportions = self._get_transit_shrinkage_proportion_map(warehouses)
        for key, proportion_qty in transit_proportions.items():
            row = rows.get(key)
            if row:
                row["quantity"] = max(0.0, row["quantity"] - proportion_qty)

        summary_map = {}
        detail_vals = []
        sorted_rows = sorted(
            rows.values(),
            key=lambda row: (
                self._natural_sort_key(row["division"].code or ""),
                row["lot"].production_date or fields.Date.today(),
                row["lot"].name or "",
            ),
        )
        for sequence, row in enumerate(sorted_rows, start=1):
            stock_qty = row["opening_qty"] + row["stock_in_qty"]
            percentage = (
                "%.2f%%" % (row["quantity"] / stock_qty * 100.0)
                if stock_qty
                else "0.00%"
            )
            division = row["division"]
            warehouse = (
                row["warehouse"]
                or division_warehouses.get(division.id)
                or self.env["stock.warehouse"]
            )
            summary = summary_map.setdefault(
                division.id or 0,
                {
                    "division": division,
                    "warehouse": warehouse,
                    "opening_qty": 0.0,
                    "stock_in_qty": 0.0,
                    "stock_qty": 0.0,
                    "quantity": 0.0,
                    "balance_qty": 0.0,
                },
            )
            summary["opening_qty"] += row["opening_qty"]
            summary["stock_in_qty"] += row["stock_in_qty"]
            summary["stock_qty"] += stock_qty
            summary["quantity"] += row["quantity"]
            summary["balance_qty"] += row["closing_qty"]
            detail_vals.append(
                {
                    "report_id": self.report_id.id,
                    "sequence": sequence,
                    "production_date": row["lot"].production_date,
                    "movement_date": row["movement_date"],
                    "warehouse_id": warehouse.id or False,
                    "warehouse_name": warehouse.display_name or "-",
                    "division_id": division.id or False,
                    "division_name": division.display_name or "-",
                    "lot_id": row["lot"].id,
                    "lot_name": row["lot"].name or "",
                    "product_id": row["product"].id,
                    "product_name": row["product"].display_name or "",
                    "quantity": row["quantity"],
                    "stock_qty": stock_qty,
                    "initial_qty": stock_qty,
                    "balance_qty": row["closing_qty"],
                    "movement_count": row["movement_count"],
                    "shipped_percentage": percentage,
                    "uom_name": row["uom"].name or "",
                }
            )

        summary_vals = []
        for sequence, value in enumerate(
            sorted(
                summary_map.values(),
                key=lambda value: self._natural_sort_key(value["division"].code or ""),
            ),
            start=1,
        ):
            percentage = (
                "%.2f%%" % (value["quantity"] / value["stock_qty"] * 100.0)
                if value["stock_qty"]
                else "0.00%"
            )
            summary_vals.append(
                {
                    "report_id": self.report_id.id,
                    "sequence": sequence,
                    "warehouse_id": value["warehouse"].id or False,
                    "warehouse_name": value["warehouse"].display_name or "-",
                    "division_id": value["division"].id or False,
                    "division_name": value["division"].display_name or "-",
                    "opening_qty": value["opening_qty"],
                    "stock_in_qty": value["stock_in_qty"],
                    "stock_qty": value["stock_qty"],
                    "quantity": value["quantity"],
                    "balance_qty": value["balance_qty"],
                    "shipped_percentage": percentage,
                }
            )

        total_opening_qty = sum(row["opening_qty"] for row in rows.values())
        total_stock_in_qty = sum(row["stock_in_qty"] for row in rows.values())
        total_stock_qty = total_opening_qty + total_stock_in_qty
        total_quantity = sum(row["quantity"] for row in rows.values())
        total_balance_qty = sum(row["closing_qty"] for row in rows.values())
        total_pct = (
            "%.2f%%" % (total_quantity / total_stock_qty * 100.0)
            if total_stock_qty
            else "0.00%"
        )
        return {
            "summary_vals": summary_vals,
            "detail_vals": detail_vals,
            "total_quantity": total_quantity,
            "total_opening_qty": total_opening_qty,
            "total_stock_in_qty": total_stock_in_qty,
            "total_stock_qty": total_stock_qty,
            "total_balance_qty": total_balance_qty,
            "total_initial_qty": total_stock_qty,
            "total_shipped_percentage": total_pct,
        }

    def _get_lot_initial_qty_map(self, lot_ids):
        """Kembalikan dict {lot_id: total_qty_masuk} untuk lot-lot yang diberikan.

        Total stok awal dihitung dari semua stock.move.line yang sudah done
        dengan lot bersangkutan masuk ke lokasi internal dari sumber non-internal.
        """
        if not lot_ids:
            return {}
        incoming_lines = self.env["stock.move.line"].search(
            [
                ("lot_id", "in", lot_ids),
                ("move_id.state", "=", "done"),
                ("location_dest_id.usage", "=", "internal"),
                ("location_id.usage", "!=", "internal"),
                ("quantity", ">", 0),
            ]
        )
        result = {}
        for line in incoming_lines:
            lid = line.lot_id.id
            result[lid] = result.get(lid, 0.0) + (line.quantity or 0.0)
        return result

    @staticmethod
    def _natural_sort_key(value):
        return tuple(
            int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", value or "")
        )

    def _append_event(
        self,
        events,
        *,
        movement_date,
        delivery,
        warehouse,
        division,
        lot,
        product,
        quantity,
        uom,
    ):
        if quantity <= 0.0:
            return
        if self.warehouse_id and warehouse != self.warehouse_id:
            return
        if self.division_id and division != self.division_id:
            return
        events.append(
            {
                "movement_date": movement_date,
                "delivery": delivery,
                "warehouse": warehouse,
                "division": division,
                "lot": lot,
                "product": product,
                "quantity": quantity,
                "uom": uom,
            }
        )

    def _get_shipping_move_lines(self):
        start_dt, end_dt = self._get_utc_date_range()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("move_id.state", "=", "done"),
            ("picking_id.wt_delivery_id", "!=", False),
            ("picking_id.wt_delivery_id.state", "in", ("done", "returned")),
            ("move_id.date", ">=", fields.Datetime.to_string(start_dt)),
            ("move_id.date", "<=", fields.Datetime.to_string(end_dt)),
            ("location_dest_id.usage", "=", "customer"),
            ("quantity", ">", 0),
            ("lot_id", "!=", False),
        ]
        return self.env["stock.move.line"].search(domain, order="id")

    def _get_transit_shrinkage_proportion_map(self, warehouses):
        self.ensure_one()
        values = {}
        deliveries = self.env["wt.delivery"].search([
            ("company_id", "=", self.company_id.id),
            ("state", "in", ["delivered", "done"]),
            ("transit_shrinkage_proportion_saved", "=", True),
        ])
        matched_deliveries = deliveries.filtered(
            lambda delivery: self.start_date
            <= (
                delivery.backdate_effective_at.date()
                if delivery.backdate_effective_at
                else delivery.date
            )
            <= self.end_date
        )
        if not matched_deliveries:
            return values
        proportions = self.env["wt.delivery.transit.shrinkage.proportion"].search([
            ("delivery_id", "in", matched_deliveries.ids),
            ("proportion_qty", ">", 0),
        ])
        division_warehouses = self._basis_division_warehouse_map()
        for prop in proportions:
            lot = prop.lot_id
            if not lot:
                continue
            division = lot.division_id
            warehouse = (
                self._resolve_warehouse(prop.do_line_id.location_id, warehouses)
                or division_warehouses.get(division.id)
                or self.env["stock.warehouse"]
            )
            if self.warehouse_id and warehouse != self.warehouse_id:
                continue
            if self.division_id and division != self.division_id:
                continue
            key = self._stock_basis_key(division, lot)
            values[key] = values.get(key, 0.0) + (prop.proportion_qty or 0.0)
        return values

    def _get_utc_date_range(self):
        user_tz = timezone(self.env.user.tz or "UTC")
        start_local = user_tz.localize(datetime.combine(self.start_date, time.min))
        end_local = user_tz.localize(datetime.combine(self.end_date, time.max))
        return (
            start_local.astimezone(UTC).replace(tzinfo=None),
            end_local.astimezone(UTC).replace(tzinfo=None),
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


class ReportShipping(models.AbstractModel):
    _name = "report.weightrack.report_shipping_document"
    _description = "Shipping Report"

    def _get_report_values(self, docids, data=None):
        docs = self.env["wt.shipping.report"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "wt.shipping.report",
            "docs": docs,
        }
