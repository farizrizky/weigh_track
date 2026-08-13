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


# Regex untuk menghapus karakter Unicode tak terlihat (format/control characters)
# yang sering muncul dari copy-paste, contoh: U+2060 WORD JOINER, U+200B ZERO WIDTH SPACE, dll.
_INVISIBLE_CHARS_RE = re.compile(
    r"[\u00ad\u200b-\u200f\u2028\u2029\u202a-\u202e\u2060-\u206f\ufeff]"
)


def _clean_name(name):
    """Hapus karakter Unicode tersembunyi dari nama agar aman dirender di PDF."""
    if not name:
        return "-"
    return _INVISIBLE_CHARS_RE.sub("", name).strip() or "-"


class DeliveryShrinkageReport(models.TransientModel):
    _name = "wt.delivery.shrinkage.report"
    _description = "Delivery Shrinkage Report"

    name = fields.Char(
        string="Report",
        default="Laporan Susut Pengiriman",
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
    customer_id = fields.Many2one(
        "res.partner",
        string="Customer",
        readonly=True,
    )
    total_shipped_qty = fields.Float(
        string="Total Terkirim (kg)",
        readonly=True,
        digits="Product Unit of Measure",
    )
    total_received_qty = fields.Float(
        string="Total Diterima (kg)",
        readonly=True,
        digits="Product Unit of Measure",
    )
    total_shrinkage_qty = fields.Float(
        string="Total Susut (kg)",
        readonly=True,
        digits="Product Unit of Measure",
    )
    total_shrinkage_percentage = fields.Char(
        string="% Susut",
        readonly=True,
    )
    summary_line_ids = fields.One2many(
        "wt.delivery.shrinkage.report.summary.line",
        "report_id",
        string="Ringkasan",
        readonly=True,
    )
    detail_line_ids = fields.One2many(
        "wt.delivery.shrinkage.report.detail.line",
        "report_id",
        string="Detail",
        readonly=True,
    )

    def action_open_filter(self):
        self.ensure_one()
        return {
            "name": _("Filter Laporan Susut Pengiriman"),
            "type": "ir.actions.act_window",
            "res_model": "wt.delivery.shrinkage.report.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_report_id": self.id,
                "default_company_id": self.company_id.id or self.env.company.id,
                "default_start_date": self.start_date or fields.Date.context_today(self),
                "default_end_date": self.end_date or fields.Date.context_today(self),
                "default_customer_id": self.customer_id.id,
            },
        }

    def action_print_pdf(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Silakan terapkan filter terlebih dahulu sebelum mencetak laporan."))
        return self.env.ref("weightrack.action_report_delivery_shrinkage_pdf").report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Silakan terapkan filter terlebih dahulu sebelum mengekspor laporan."))
        if xlsxwriter is None:
            raise ValidationError(_("Paket Python xlsxwriter tidak terinstal."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Susut Pengiriman")

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
                "bg_color": "#f3f4f6",
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

        col_count = 11
        sheet.merge_range(
            0, 0, 0, col_count - 1,
            self.company_id.name or "",
            title_format,
        )
        sheet.merge_range(
            1, 0, 1, col_count - 1,
            "LAPORAN SUSUT PENGIRIMAN",
            title_format,
        )
        sheet.write("A4", "Rentang Tanggal", label_format)
        sheet.write("B4", "%s s/d %s" % (self.start_date or "", self.end_date or ""))
        sheet.write("A5", "Customer", label_format)
        sheet.write(
            "B5",
            self.customer_id.display_name if self.customer_id else "Semua Customer",
        )
        sheet.write("A6", "Status DO", label_format)
        sheet.write("B6", "Selesai (ada data berat diterima)")

        # Ringkasan per customer
        summary_headers = ["No", "Customer", "Total Terkirim (kg)", "Total Diterima (kg)", "Susut (kg)", "% Susut"]
        summary_widths = [6, 32, 20, 20, 16, 12]
        for column, width in enumerate(summary_widths):
            sheet.set_column(column, column, width)
        sheet.write(9, 0, "RINGKASAN PER CUSTOMER", label_format)
        for column, header in enumerate(summary_headers):
            sheet.write(10, column, header, header_format)

        row_index = 11
        for line in self.summary_line_ids:
            sheet.write(row_index, 0, line.sequence, text_format)
            sheet.write(row_index, 1, line.customer_name or "", text_format)
            sheet.write(row_index, 2, line.shipped_qty, number_format)
            sheet.write(row_index, 3, line.received_qty, number_format)
            sheet.write(row_index, 4, line.shrinkage_qty, number_format)
            sheet.write(row_index, 5, line.shrinkage_percentage or "0.00%", text_format)
            row_index += 1
        sheet.merge_range(row_index, 0, row_index, 1, "Total", total_label_format)
        sheet.write(row_index, 2, self.total_shipped_qty, total_number_format)
        sheet.write(row_index, 3, self.total_received_qty, total_number_format)
        sheet.write(row_index, 4, self.total_shrinkage_qty, total_number_format)
        sheet.write(row_index, 5, self.total_shrinkage_percentage or "0.00%", total_label_format)

        # Detail per DO
        row_index += 3
        detail_headers = [
            "No",
            "Tanggal",
            "Nomor DO",
            "Customer",
            "Gudang",
            "Divisi",
            "Berat Terkirim (kg)",
            "Berat Diterima (kg)",
            "Susut (kg)",
            "% Susut",
            "Satuan",
        ]
        detail_widths = [6, 13, 22, 28, 28, 22, 20, 20, 16, 12, 10]
        for column, width in enumerate(detail_widths):
            sheet.set_column(column, column, width)
        sheet.write(row_index, 0, "DETAIL SUSUT PENGIRIMAN", label_format)
        row_index += 1
        for column, header in enumerate(detail_headers):
            sheet.write(row_index, column, header, header_format)
        row_index += 1

        for line in self.detail_line_ids:
            sheet.write(row_index, 0, line.sequence, text_format)
            if line.delivery_date:
                local_date = fields.Datetime.context_timestamp(
                    self,
                    fields.Datetime.to_datetime(line.delivery_date),
                ).replace(tzinfo=None)
                sheet.write_datetime(row_index, 1, local_date, date_format)
            else:
                sheet.write(row_index, 1, "", text_format)
            sheet.write(row_index, 2, line.delivery_name or "", text_format)
            sheet.write(row_index, 3, line.customer_name or "", text_format)
            sheet.write(row_index, 4, line.warehouse_name or "", text_format)
            sheet.write(row_index, 5, line.division_name or "", text_format)
            sheet.write(row_index, 6, line.shipped_qty, number_format)
            sheet.write(row_index, 7, line.received_qty, number_format)
            sheet.write(row_index, 8, line.shrinkage_qty, number_format)
            sheet.write(row_index, 9, line.shrinkage_percentage or "0.00%", text_format)
            sheet.write(row_index, 10, line.uom_name or "kg", text_format)
            row_index += 1
        sheet.merge_range(row_index, 0, row_index, 5, "Total", total_label_format)
        sheet.write(row_index, 6, self.total_shipped_qty, total_number_format)
        sheet.write(row_index, 7, self.total_received_qty, total_number_format)
        sheet.write(row_index, 8, self.total_shrinkage_qty, total_number_format)
        sheet.write(row_index, 9, self.total_shrinkage_percentage or "0.00%", total_label_format)
        sheet.write(row_index, 10, "", text_format)

        workbook.close()
        output.seek(0)
        filename = "Laporan Susut Pengiriman - %s sd %s.xlsx" % (
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
            "name": _("Laporan Susut Pengiriman"),
            "type": "ir.actions.act_window",
            "res_model": "wt.delivery.shrinkage.report",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }


class DeliveryShrinkageReportSummaryLine(models.TransientModel):
    _name = "wt.delivery.shrinkage.report.summary.line"
    _description = "Delivery Shrinkage Report Summary Line"
    _order = "sequence, id"

    report_id = fields.Many2one(
        "wt.delivery.shrinkage.report",
        string="Report",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="No", readonly=True)
    customer_id = fields.Many2one(
        "res.partner",
        string="Customer",
        readonly=True,
    )
    customer_name = fields.Char(string="Customer", readonly=True)
    shipped_qty = fields.Float(string="Terkirim (kg)", readonly=True, digits="Product Unit of Measure")
    received_qty = fields.Float(string="Diterima (kg)", readonly=True, digits="Product Unit of Measure")
    shrinkage_qty = fields.Float(string="Susut (kg)", readonly=True, digits="Product Unit of Measure")
    shrinkage_percentage = fields.Char(string="% Susut", readonly=True)


class DeliveryShrinkageReportDetailLine(models.TransientModel):
    _name = "wt.delivery.shrinkage.report.detail.line"
    _description = "Delivery Shrinkage Report Detail Line"
    _order = "sequence, id"

    report_id = fields.Many2one(
        "wt.delivery.shrinkage.report",
        string="Report",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="No", readonly=True)
    delivery_date = fields.Datetime(string="Tanggal", readonly=True)
    delivery_id = fields.Many2one(
        "wt.delivery",
        string="Pengiriman",
        readonly=True,
    )
    delivery_name = fields.Char(string="Nomor DO", readonly=True)
    customer_id = fields.Many2one(
        "res.partner",
        string="Customer",
        readonly=True,
    )
    customer_name = fields.Char(string="Customer", readonly=True)
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
    shipped_qty = fields.Float(string="Berat Terkirim (kg)", readonly=True, digits="Product Unit of Measure")
    received_qty = fields.Float(string="Berat Diterima (kg)", readonly=True, digits="Product Unit of Measure")
    shrinkage_qty = fields.Float(string="Susut (kg)", readonly=True, digits="Product Unit of Measure")
    shrinkage_percentage = fields.Char(string="% Susut", readonly=True)
    uom_name = fields.Char(string="Satuan", readonly=True)


class DeliveryShrinkageReportWizard(models.TransientModel):
    _name = "wt.delivery.shrinkage.report.wizard"
    _description = "Delivery Shrinkage Report Wizard"

    report_id = fields.Many2one(
        "wt.delivery.shrinkage.report",
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
    customer_id = fields.Many2one(
        "res.partner",
        string="Customer",
    )

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
                "customer_id": self.customer_id.id or False,
                "total_shipped_qty": data["total_shipped_qty"],
                "total_received_qty": data["total_received_qty"],
                "total_shrinkage_qty": data["total_shrinkage_qty"],
                "total_shrinkage_percentage": data["total_shrinkage_percentage"],
            }
        )
        if data["summary_vals"]:
            self.env["wt.delivery.shrinkage.report.summary.line"].create(
                data["summary_vals"]
            )
        if data["detail_vals"]:
            self.env["wt.delivery.shrinkage.report.detail.line"].create(
                data["detail_vals"]
            )
        return report._open_current_report_action()

    def _prepare_report_data(self):
        user_tz = timezone(self.env.user.tz or "UTC")
        start_local = user_tz.localize(
            datetime.combine(self.start_date, time.min)
        )
        end_local = user_tz.localize(
            datetime.combine(self.end_date, time.max)
        )
        start_dt = start_local.astimezone(UTC).replace(tzinfo=None)
        end_dt = end_local.astimezone(UTC).replace(tzinfo=None)

        # Cari delivery yang sudah selesai dan punya received_qty dalam rentang tanggal
        domain = [
            ("company_id", "=", self.company_id.id),
            ("state", "=", "done"),
            ("received_qty", ">", 0),
            ("validated_at", ">=", fields.Datetime.to_string(start_dt)),
            ("validated_at", "<=", fields.Datetime.to_string(end_dt)),
        ]
        if self.customer_id:
            domain.append(("partner_id", "=", self.customer_id.id))

        deliveries = self.env["wt.delivery"].search(domain, order="validated_at, name")



        summary_map = {}
        detail_vals = []
        total_shipped_qty = 0.0
        total_received_qty = 0.0

        for delivery in deliveries:

            shipped_qty = delivery.total_physical_qty or 0.0
            received_qty = delivery.received_qty or 0.0
            shrinkage_qty = shipped_qty - received_qty
            shrinkage_pct = (
                "%.2f%%" % (shrinkage_qty / shipped_qty * 100.0)
                if shipped_qty
                else "0.00%"
            )

            customer = delivery.partner_id
            customer_key = customer.id or 0
            if customer_key not in summary_map:
                summary_map[customer_key] = {
                    "customer": customer,
                    "shipped_qty": 0.0,
                    "received_qty": 0.0,
                }
            summary_map[customer_key]["shipped_qty"] += shipped_qty
            summary_map[customer_key]["received_qty"] += received_qty

            total_shipped_qty += shipped_qty
            total_received_qty += received_qty

            uom_name = "kg"
            product = delivery.product_id
            if product and product.uom_id:
                uom_name = product.uom_id.name

            detail_vals.append(
                {
                    "report_id": self.report_id.id,
                    "delivery_date": delivery.validated_at,
                    "delivery_id": delivery.id,
                    "delivery_name": delivery.name or "",
                    "customer_id": customer.id or False,
                    "customer_name": _clean_name(customer.name),
                    "shipped_qty": shipped_qty,
                    "received_qty": received_qty,
                    "shrinkage_qty": shrinkage_qty,
                    "shrinkage_percentage": shrinkage_pct,
                    "uom_name": uom_name,
                }
            )

        # Tambah sequence setelah filter
        for i, val in enumerate(detail_vals, start=1):
            val["sequence"] = i

        # Hitung ringkasan per customer
        summary_vals = []
        sorted_summaries = sorted(
            summary_map.values(),
            key=lambda v: _clean_name(v["customer"].name),
        )
        for seq, value in enumerate(sorted_summaries, start=1):
            s_qty = value["shipped_qty"]
            r_qty = value["received_qty"]
            sh_qty = s_qty - r_qty
            sh_pct = (
                "%.2f%%" % (sh_qty / s_qty * 100.0) if s_qty else "0.00%"
            )
            summary_vals.append(
                {
                    "report_id": self.report_id.id,
                    "sequence": seq,
                    "customer_id": value["customer"].id or False,
                    "customer_name": _clean_name(value["customer"].name),
                    "shipped_qty": s_qty,
                    "received_qty": r_qty,
                    "shrinkage_qty": sh_qty,
                    "shrinkage_percentage": sh_pct,
                }
            )

        total_shrinkage_qty = total_shipped_qty - total_received_qty
        total_shrinkage_pct = (
            "%.2f%%" % (total_shrinkage_qty / total_shipped_qty * 100.0)
            if total_shipped_qty
            else "0.00%"
        )

        return {
            "summary_vals": summary_vals,
            "detail_vals": detail_vals,
            "total_shipped_qty": total_shipped_qty,
            "total_received_qty": total_received_qty,
            "total_shrinkage_qty": total_shrinkage_qty,
            "total_shrinkage_percentage": total_shrinkage_pct,
        }



class ReportDeliveryShrinkage(models.AbstractModel):
    _name = "report.weightrack.report_delivery_shrinkage_document"
    _description = "Delivery Shrinkage Report"

    def _get_report_values(self, docids, data=None):
        docs = self.env["wt.delivery.shrinkage.report"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "wt.delivery.shrinkage.report",
            "docs": docs,
        }
