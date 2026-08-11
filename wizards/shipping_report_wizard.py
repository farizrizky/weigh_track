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

        sheet.merge_range("A1:J1", self.company_id.name or "", title_format)
        sheet.merge_range("A2:J2", "LAPORAN PENGIRIMAN", title_format)
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
        sheet.write("B7", "Selesai")

        summary_headers = ["No", "Gudang", "Divisi", "Total Terkirim"]
        summary_widths = [6, 30, 24, 18]
        for column, width in enumerate(summary_widths):
            sheet.set_column(column, column, width)
        sheet.write(8, 0, "RINGKASAN PER GUDANG DAN DIVISI", label_format)
        for column, header in enumerate(summary_headers):
            sheet.write(9, column, header, header_format)

        row_index = 10
        for line in self.summary_line_ids:
            sheet.write(row_index, 0, line.sequence, text_format)
            sheet.write(row_index, 1, line.warehouse_name or "", text_format)
            sheet.write(row_index, 2, line.division_name or "", text_format)
            sheet.write(row_index, 3, line.quantity, number_format)
            row_index += 1
        sheet.merge_range(row_index, 0, row_index, 2, "Total", total_label_format)
        sheet.write(row_index, 3, self.total_quantity, total_number_format)

        row_index += 3
        detail_headers = [
            "No",
            "Tanggal",
            "Nomor DO",
            "Customer Penerima",
            "Gudang",
            "Divisi",
            "Lot Produksi",
            "Produk",
            "Qty",
            "Satuan",
        ]
        detail_widths = [6, 13, 22, 28, 28, 22, 28, 24, 14, 12]
        for column, width in enumerate(detail_widths):
            sheet.set_column(column, column, width)
        sheet.write(row_index, 0, "DETAIL PENGIRIMAN", label_format)
        row_index += 1
        for column, header in enumerate(detail_headers):
            sheet.write(row_index, column, header, header_format)
        row_index += 1

        for line in self.detail_line_ids:
            sheet.write(row_index, 0, line.sequence, text_format)
            if line.movement_date:
                local_movement_date = fields.Datetime.context_timestamp(
                    self,
                    fields.Datetime.to_datetime(line.movement_date),
                ).replace(tzinfo=None)
                sheet.write_datetime(
                    row_index,
                    1,
                    local_movement_date,
                    date_format,
                )
            else:
                sheet.write(row_index, 1, "", text_format)
            sheet.write(row_index, 2, line.delivery_name or "", text_format)
            sheet.write(row_index, 3, line.customer_name or "", text_format)
            sheet.write(row_index, 4, line.warehouse_name or "", text_format)
            sheet.write(row_index, 5, line.division_name or "", text_format)
            sheet.write(row_index, 6, line.lot_name or "", text_format)
            sheet.write(row_index, 7, line.product_name or "", text_format)
            sheet.write(row_index, 8, line.quantity, number_format)
            sheet.write(row_index, 9, line.uom_name or "", text_format)
            row_index += 1
        sheet.merge_range(row_index, 0, row_index, 7, "Total", total_label_format)
        sheet.write(row_index, 8, self.total_quantity, total_number_format)
        sheet.write(row_index, 9, "", text_format)

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
    quantity = fields.Float(string="Total Terkirim", readonly=True)


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
    uom_name = fields.Char(string="Satuan", readonly=True)


class ShippingReportWizard(models.TransientModel):
    _name = "wt.shipping.report.wizard"
    _inherit = ["wt.shipping.provenance.mixin"]
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
        events = []
        start_dt, end_dt = self._get_utc_date_range()
        for source_event in self._iter_delivery_shipping_source_events(
            fields.Datetime.to_string(start_dt),
            fields.Datetime.to_string(end_dt),
            warehouses,
            end_operator="<=",
        ):
            self._append_event(events, **source_event)

        events.sort(
            key=lambda event: (
                event["movement_date"] or datetime.min,
                event["delivery"].name or "",
                event["lot"].name or "",
            )
        )

        summary_map = {}
        detail_vals = []
        total_quantity = 0.0
        for sequence, event in enumerate(events, start=1):
            warehouse = event["warehouse"]
            division = event["division"]
            quantity = event["quantity"]
            key = (warehouse.id or 0, division.id or 0)
            if key not in summary_map:
                summary_map[key] = {
                    "warehouse": warehouse,
                    "division": division,
                    "quantity": 0.0,
                }
            summary_map[key]["quantity"] += quantity
            total_quantity += quantity

            delivery = event["delivery"]
            customer = delivery.partner_id
            lot = event["lot"]
            detail_vals.append(
                {
                    "report_id": self.report_id.id,
                    "sequence": sequence,
                    "movement_date": event["movement_date"],
                    "delivery_id": delivery.id,
                    "delivery_name": delivery.name or "",
                    "customer_id": customer.id or False,
                    "customer_name": customer.display_name or "-",
                    "warehouse_id": warehouse.id or False,
                    "warehouse_name": warehouse.display_name or "-",
                    "division_id": division.id or False,
                    "division_name": division.display_name or "-",
                    "lot_id": lot.id,
                    "lot_name": lot.name or "",
                    "product_id": event["product"].id,
                    "product_name": event["product"].display_name or "",
                    "quantity": quantity,
                    "uom_name": event["uom"].name or "",
                }
            )

        summary_vals = []
        sorted_summaries = sorted(
            summary_map.values(),
            key=lambda value: (
                self._natural_sort_key(value["division"].code if value.get("division") else ""),
                value["warehouse"].display_name or "",
            ),
        )
        for sequence, value in enumerate(sorted_summaries, start=1):
            summary_vals.append(
                {
                    "report_id": self.report_id.id,
                    "sequence": sequence,
                    "warehouse_id": value["warehouse"].id or False,
                    "warehouse_name": value["warehouse"].display_name or "-",
                    "division_id": value["division"].id or False,
                    "division_name": value["division"].display_name or "-",
                    "quantity": value["quantity"],
                }
            )

        return {
            "summary_vals": summary_vals,
            "detail_vals": detail_vals,
            "total_quantity": total_quantity,
        }

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
            ("picking_id.wt_delivery_id.state", "=", "done"),
            ("move_id.date", ">=", fields.Datetime.to_string(start_dt)),
            ("move_id.date", "<=", fields.Datetime.to_string(end_dt)),
            ("location_dest_id.usage", "=", "customer"),
            ("quantity", ">", 0),
            ("lot_id", "!=", False),
        ]
        return self.env["stock.move.line"].search(domain, order="id")

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
