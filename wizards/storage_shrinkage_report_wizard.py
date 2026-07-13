# -*- coding: utf-8 -*-

import base64
import io
from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class StorageShrinkageReport(models.TransientModel):
    _name = "wt.storage.shrinkage.report"
    _description = "Storage Shrinkage Report"

    name = fields.Char(
        string="Report",
        default="Laporan Susut Penyimpanan",
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
    total_stock_opname_qty = fields.Float(
        string="Total Stock Opname",
        readonly=True,
    )
    total_delivery_qty = fields.Float(
        string="Total Pengiriman",
        readonly=True,
    )
    total_shrinkage_qty = fields.Float(
        string="Total Susut",
        readonly=True,
    )
    summary_line_ids = fields.One2many(
        "wt.storage.shrinkage.report.summary.line",
        "report_id",
        string="Ringkasan",
        readonly=True,
    )
    detail_line_ids = fields.One2many(
        "wt.storage.shrinkage.report.detail.line",
        "report_id",
        string="Detail",
        readonly=True,
    )

    def action_open_filter(self):
        self.ensure_one()
        return {
            "name": _("Filter Laporan Susut Penyimpanan"),
            "type": "ir.actions.act_window",
            "res_model": "wt.storage.shrinkage.report.wizard",
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
        return self.env.ref("weightrack.action_report_storage_shrinkage_pdf").report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Please apply a filter before exporting the report."))
        if xlsxwriter is None:
            raise ValidationError(_("The xlsxwriter Python package is not installed."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Susut Penyimpanan")

        title_format = workbook.add_format({"bold": True, "font_size": 14, "align": "center"})
        label_format = workbook.add_format({"bold": True})
        header_format = workbook.add_format(
            {"bold": True, "align": "center", "valign": "vcenter", "border": 1, "text_wrap": True}
        )
        text_format = workbook.add_format({"border": 1})
        number_format = workbook.add_format({"border": 1, "num_format": "#,##0.00"})
        date_format = workbook.add_format({"border": 1, "num_format": "dd/mm/yyyy"})
        total_label_format = workbook.add_format({"bold": True, "align": "right", "border": 1})
        total_number_format = workbook.add_format({"bold": True, "border": 1, "num_format": "#,##0.00"})

        sheet.merge_range("A1:I1", self.company_id.name or "", title_format)
        sheet.merge_range("A2:I2", "LAPORAN SUSUT PENYIMPANAN", title_format)
        sheet.write("A4", "Rentang Tanggal", label_format)
        sheet.write("B4", "%s s/d %s" % (self.start_date or "", self.end_date or ""))
        sheet.write("A5", "Gudang", label_format)
        sheet.write("B5", self.warehouse_id.display_name if self.warehouse_id else "Semua Gudang")
        sheet.write("A6", "Divisi", label_format)
        sheet.write("B6", self.division_id.display_name if self.division_id else "Semua Divisi")

        summary_headers = ["No", "Gudang", "Divisi", "Total Susut"]
        summary_widths = [6, 22, 22, 16]
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
            sheet.write(row_index, 3, line.total_qty, number_format)
            row_index += 1
        sheet.merge_range(row_index, 0, row_index, 2, "Total", total_label_format)
        sheet.write(row_index, 3, self.total_shrinkage_qty, total_number_format)

        row_index += 3
        detail_headers = [
            "No",
            "Tanggal",
            "Sumber",
            "No Dokumen",
            "Gudang",
            "Divisi",
            "Lokasi Asal",
            "Lot",
            "Qty Susut",
        ]
        detail_widths = [6, 12, 16, 20, 22, 22, 30, 24, 14]
        for column, width in enumerate(detail_widths):
            sheet.set_column(column, column, width)
        sheet.write(row_index, 0, "DETAIL PERGERAKAN SUSUT", label_format)
        row_index += 1
        for column, header in enumerate(detail_headers):
            sheet.write(row_index, column, header, header_format)
        row_index += 1
        for line in self.detail_line_ids:
            sheet.write(row_index, 0, line.sequence, text_format)
            if line.movement_date:
                sheet.write_datetime(
                    row_index,
                    1,
                    fields.Datetime.to_datetime(line.movement_date),
                    date_format,
                )
            else:
                sheet.write(row_index, 1, "", text_format)
            sheet.write(row_index, 2, line.source_type, text_format)
            sheet.write(row_index, 3, line.source_document or "", text_format)
            sheet.write(row_index, 4, line.warehouse_name or "", text_format)
            sheet.write(row_index, 5, line.division_name or "", text_format)
            sheet.write(row_index, 6, line.source_location_name or "", text_format)
            sheet.write(row_index, 7, line.lot_name or "", text_format)
            sheet.write(row_index, 8, line.quantity, number_format)
            row_index += 1
        sheet.merge_range(row_index, 0, row_index, 7, "Total", total_label_format)
        sheet.write(row_index, 8, self.total_shrinkage_qty, total_number_format)

        workbook.close()
        output.seek(0)
        filename = "Laporan Susut Penyimpanan - %s sd %s.xlsx" % (
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
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
            "name": _("Laporan Susut Penyimpanan"),
            "type": "ir.actions.act_window",
            "res_model": "wt.storage.shrinkage.report",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }


class StorageShrinkageReportSummaryLine(models.TransientModel):
    _name = "wt.storage.shrinkage.report.summary.line"
    _description = "Storage Shrinkage Report Summary Line"
    _order = "sequence, id"

    report_id = fields.Many2one(
        "wt.storage.shrinkage.report",
        string="Report",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="No", readonly=True)
    warehouse_id = fields.Many2one("stock.warehouse", string="Gudang", readonly=True)
    warehouse_name = fields.Char(string="Gudang", readonly=True)
    division_id = fields.Many2one("wt.division", string="Divisi", readonly=True)
    division_name = fields.Char(string="Divisi", readonly=True)
    stock_opname_qty = fields.Float(string="Stock Opname", readonly=True)
    delivery_qty = fields.Float(string="Pengiriman", readonly=True)
    total_qty = fields.Float(string="Total Susut", readonly=True)


class StorageShrinkageReportDetailLine(models.TransientModel):
    _name = "wt.storage.shrinkage.report.detail.line"
    _description = "Storage Shrinkage Report Detail Line"
    _order = "sequence, id"

    report_id = fields.Many2one(
        "wt.storage.shrinkage.report",
        string="Report",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="No", readonly=True)
    movement_date = fields.Datetime(string="Tanggal", readonly=True)
    source_type = fields.Char(string="Sumber", readonly=True)
    source_document = fields.Char(string="No Dokumen", readonly=True)
    warehouse_id = fields.Many2one("stock.warehouse", string="Gudang", readonly=True)
    warehouse_name = fields.Char(string="Gudang", readonly=True)
    division_id = fields.Many2one("wt.division", string="Divisi", readonly=True)
    division_name = fields.Char(string="Divisi", readonly=True)
    source_location_id = fields.Many2one("stock.location", string="Lokasi Asal", readonly=True)
    source_location_name = fields.Char(string="Lokasi Asal", readonly=True)
    lot_id = fields.Many2one("stock.lot", string="Lot", readonly=True)
    lot_name = fields.Char(string="Lot", readonly=True)
    product_id = fields.Many2one("product.product", string="Produk", readonly=True)
    quantity = fields.Float(string="Qty Susut", readonly=True)
    uom_name = fields.Char(string="Satuan", readonly=True)


class StorageShrinkageReportWizard(models.TransientModel):
    _name = "wt.storage.shrinkage.report.wizard"
    _description = "Storage Shrinkage Report Wizard"

    report_id = fields.Many2one(
        "wt.storage.shrinkage.report",
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
            raise ValidationError(_("Tanggal Dari tidak boleh lebih besar dari Tanggal Sampai."))

        report = self.report_id
        data = self._prepare_report_data()
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
                "total_stock_opname_qty": data["total_stock_opname_qty"],
                "total_delivery_qty": data["total_delivery_qty"],
                "total_shrinkage_qty": data["total_shrinkage_qty"],
            }
        )
        if data["summary_vals"]:
            self.env["wt.storage.shrinkage.report.summary.line"].create(data["summary_vals"])
        if data["detail_vals"]:
            self.env["wt.storage.shrinkage.report.detail.line"].create(data["detail_vals"])
        return report._open_current_report_action()

    def _prepare_report_data(self):
        move_lines = self._get_move_lines()
        warehouses = self.env["stock.warehouse"].search([("company_id", "=", self.company_id.id)])

        summary_map = {}
        detail_vals = []
        total_stock_opname_qty = 0.0

        for line in move_lines:
            move = line.move_id
            source_type = move.inventory_name or ""
            warehouse = self._resolve_warehouse(line.location_id, warehouses)
            division = line.lot_id.division_id
            if self.warehouse_id and warehouse != self.warehouse_id:
                continue
            if self.division_id and division != self.division_id:
                continue

            quantity = line.quantity or 0.0
            key = (warehouse.id or 0, division.id or 0)
            if key not in summary_map:
                summary_map[key] = {
                    "warehouse": warehouse,
                    "division": division,
                    "stock_opname_qty": 0.0,
                    "delivery_qty": 0.0,
                }
            summary_map[key]["stock_opname_qty"] += quantity
            total_stock_opname_qty += quantity

            detail_vals.append(
                {
                    "report_id": self.report_id.id,
                    "sequence": len(detail_vals) + 1,
                    "movement_date": move.date,
                    "source_type": source_type,
                    "source_document": move.origin or "",
                    "warehouse_id": warehouse.id or False,
                    "warehouse_name": warehouse.display_name or "-",
                    "division_id": division.id or False,
                    "division_name": division.display_name or "-",
                    "source_location_id": line.location_id.id,
                    "source_location_name": line.location_id.complete_name or line.location_id.display_name,
                    "lot_id": line.lot_id.id,
                    "lot_name": line.lot_id.name or "",
                    "product_id": line.product_id.id,
                    "quantity": quantity,
                    "uom_name": line.product_uom_id.name or line.product_id.uom_id.name or "",
                }
            )

        summary_vals = []
        for number, value in enumerate(
            sorted(
                summary_map.values(),
                key=lambda row: (
                    row["warehouse"].display_name or "",
                    row["division"].display_name or "",
                ),
            ),
            start=1,
        ):
            summary_vals.append(
                {
                    "report_id": self.report_id.id,
                    "sequence": number,
                    "warehouse_id": value["warehouse"].id or False,
                    "warehouse_name": value["warehouse"].display_name or "-",
                    "division_id": value["division"].id or False,
                    "division_name": value["division"].display_name or "-",
                    "stock_opname_qty": value["stock_opname_qty"],
                    "delivery_qty": value["delivery_qty"],
                    "total_qty": value["stock_opname_qty"],
                }
            )

        return {
            "summary_vals": summary_vals,
            "detail_vals": detail_vals,
            "total_stock_opname_qty": total_stock_opname_qty,
            "total_delivery_qty": 0.0,
            "total_shrinkage_qty": total_stock_opname_qty,
        }

    def _get_move_lines(self):
        self.ensure_one()
        shrinkage_location = self.env.ref(
            "weightrack.stock_location_wt_inventory_loss_susut",
            raise_if_not_found=False,
        )
        if not shrinkage_location:
            shrinkage_location = self.env["stock.location"].search(
                [
                    ("name", "=", "Susut"),
                    ("usage", "=", "inventory"),
                    ("location_id.name", "=", "Inventory Loss"),
                ],
                limit=1,
            )
        if not shrinkage_location:
            return self.env["stock.move.line"]

        start_dt = datetime.combine(self.start_date, time.min)
        end_dt = datetime.combine(self.end_date, time.max)
        domain = [
            ("company_id", "=", self.company_id.id),
            ("move_id.state", "=", "done"),
            ("move_id.inventory_name", "=", "Stock Opname"),
            ("move_id.date", ">=", fields.Datetime.to_string(start_dt)),
            ("move_id.date", "<=", fields.Datetime.to_string(end_dt)),
            ("location_dest_id", "child_of", shrinkage_location.id),
            ("quantity", ">", 0),
            ("lot_id", "!=", False),
        ]
        move_lines = self.env["stock.move.line"].search(domain, order="id")
        return move_lines.filtered(lambda line: not self._is_transit_merge_move_line(line))

    def _is_transit_merge_move_line(self, line):
        description = line.move_id.description_picking or ""
        return (
            description.startswith("Consume old lots for transit merge")
            or description.startswith("Produce new merged lot for transit")
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


class ReportStorageShrinkage(models.AbstractModel):
    _name = "report.weightrack.report_storage_shrinkage_document"
    _description = "Storage Shrinkage Report"

    def _get_report_values(self, docids, data=None):
        docs = self.env["wt.storage.shrinkage.report"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "wt.storage.shrinkage.report",
            "docs": docs,
        }
