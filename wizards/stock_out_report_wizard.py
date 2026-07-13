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


class StockOutReport(models.TransientModel):
    _name = "wt.stock.out.report"
    _description = "Stock Out Report"

    name = fields.Char(
        string="Report",
        default="Laporan Stock Keluar",
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
    movement_type = fields.Selection(
        [
            ("all", "Semua"),
            ("inter_warehouse", "Transfer Antar Gudang"),
            ("final_customer", "Final ke Customer"),
        ],
        string="Jenis Pergerakan",
        default="all",
        readonly=True,
    )
    movement_type_label = fields.Char(
        string="Jenis Pergerakan",
        default="Semua",
        readonly=True,
    )
    total_delivery_count = fields.Integer(
        string="Total Pengiriman",
        readonly=True,
    )
    total_picking_count = fields.Integer(
        string="Total Dokumen Inventory",
        readonly=True,
    )
    total_lot_count = fields.Integer(
        string="Total Lot",
        readonly=True,
    )
    total_transfer_qty = fields.Float(
        string="Transfer Antar Gudang",
        readonly=True,
    )
    total_customer_qty = fields.Float(
        string="Final ke Customer",
        readonly=True,
    )
    total_quantity = fields.Float(
        string="Total Stock Keluar",
        readonly=True,
    )
    summary_line_ids = fields.One2many(
        "wt.stock.out.report.summary.line",
        "report_id",
        string="Ringkasan",
        readonly=True,
    )
    detail_line_ids = fields.One2many(
        "wt.stock.out.report.detail.line",
        "report_id",
        string="Detail",
        readonly=True,
    )

    def action_open_filter(self):
        self.ensure_one()
        return {
            "name": _("Filter Laporan Stock Keluar"),
            "type": "ir.actions.act_window",
            "res_model": "wt.stock.out.report.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_report_id": self.id,
                "default_company_id": self.company_id.id or self.env.company.id,
                "default_start_date": self.start_date or fields.Date.context_today(self),
                "default_end_date": self.end_date or fields.Date.context_today(self),
                "default_warehouse_id": self.warehouse_id.id,
                "default_division_id": self.division_id.id,
                "default_movement_type": self.movement_type or "all",
            },
        }

    def action_print_pdf(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Please apply a filter before printing the report."))
        return self.env.ref("weightrack.action_report_stock_out_pdf").report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Please apply a filter before exporting the report."))
        if xlsxwriter is None:
            raise ValidationError(_("The xlsxwriter Python package is not installed."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Stock Keluar")

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

        sheet.merge_range("A1:N1", self.company_id.name or "", title_format)
        sheet.merge_range("A2:N2", "LAPORAN STOCK KELUAR", title_format)
        sheet.write("A4", "Rentang Tanggal", label_format)
        sheet.write("B4", "%s s/d %s" % (self.start_date or "", self.end_date or ""))
        sheet.write("A5", "Gudang", label_format)
        sheet.write("B5", self.warehouse_id.display_name if self.warehouse_id else "Semua Gudang")
        sheet.write("A6", "Divisi", label_format)
        sheet.write("B6", self.division_id.display_name if self.division_id else "Semua Divisi")
        sheet.write("A7", "Jenis Pergerakan", label_format)
        sheet.write("B7", self.movement_type_label or "Semua")

        summary_headers = [
            "No",
            "Gudang",
            "Divisi",
            "Pengiriman",
            "Dokumen Inventory",
            "Lot",
            "Transfer Antar Gudang",
            "Final ke Customer",
            "Total Keluar",
        ]
        summary_widths = [6, 24, 24, 14, 18, 12, 18, 18, 16]
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
            sheet.write(row_index, 3, line.delivery_count, text_format)
            sheet.write(row_index, 4, line.picking_count, text_format)
            sheet.write(row_index, 5, line.lot_count, text_format)
            sheet.write(row_index, 6, line.transfer_qty, number_format)
            sheet.write(row_index, 7, line.customer_qty, number_format)
            sheet.write(row_index, 8, line.quantity, number_format)
            row_index += 1
        sheet.merge_range(row_index, 0, row_index, 2, "Total", total_label_format)
        sheet.write(row_index, 3, self.total_delivery_count, text_format)
        sheet.write(row_index, 4, self.total_picking_count, text_format)
        sheet.write(row_index, 5, self.total_lot_count, text_format)
        sheet.write(row_index, 6, self.total_transfer_qty, total_number_format)
        sheet.write(row_index, 7, self.total_customer_qty, total_number_format)
        sheet.write(row_index, 8, self.total_quantity, total_number_format)

        row_index += 3
        detail_headers = [
            "No",
            "Tanggal",
            "No Pengiriman",
            "No Inventory",
            "Jenis Pergerakan",
            "Customer",
            "Gudang",
            "Gudang Tujuan",
            "Divisi",
            "Lokasi Sumber",
            "Lokasi Tujuan",
            "Lot",
            "Lot Transit",
            "Produk",
            "Qty Keluar",
        ]
        detail_widths = [6, 12, 20, 20, 22, 24, 22, 22, 22, 30, 30, 24, 24, 24, 14]
        for column, width in enumerate(detail_widths):
            sheet.set_column(column, column, width)
        sheet.write(row_index, 0, "DETAIL STOCK KELUAR GUDANG", label_format)
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
            sheet.write(row_index, 2, line.delivery_name or "", text_format)
            sheet.write(row_index, 3, line.picking_name or "", text_format)
            sheet.write(row_index, 4, line.movement_type_label or "", text_format)
            sheet.write(row_index, 5, line.customer_name or "", text_format)
            sheet.write(row_index, 6, line.warehouse_name or "", text_format)
            sheet.write(row_index, 7, line.destination_warehouse_name or "", text_format)
            sheet.write(row_index, 8, line.division_name or "", text_format)
            sheet.write(row_index, 9, line.source_location_name or "", text_format)
            sheet.write(row_index, 10, line.destination_location_name or "", text_format)
            sheet.write(row_index, 11, line.lot_name or "", text_format)
            sheet.write(row_index, 12, line.transit_lot_name or "", text_format)
            sheet.write(row_index, 13, line.product_name or "", text_format)
            sheet.write(row_index, 14, line.quantity, number_format)
            row_index += 1
        sheet.merge_range(row_index, 0, row_index, 13, "Total", total_label_format)
        sheet.write(row_index, 14, self.total_quantity, total_number_format)

        workbook.close()
        output.seek(0)
        filename = "Laporan Stock Keluar - %s sd %s.xlsx" % (
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
            "name": _("Laporan Stock Keluar"),
            "type": "ir.actions.act_window",
            "res_model": "wt.stock.out.report",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }


class StockOutReportSummaryLine(models.TransientModel):
    _name = "wt.stock.out.report.summary.line"
    _description = "Stock Out Report Summary Line"
    _order = "sequence, id"

    report_id = fields.Many2one(
        "wt.stock.out.report",
        string="Report",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="No", readonly=True)
    warehouse_id = fields.Many2one("stock.warehouse", string="Gudang", readonly=True)
    warehouse_name = fields.Char(string="Gudang", readonly=True)
    division_id = fields.Many2one("wt.division", string="Divisi", readonly=True)
    division_name = fields.Char(string="Divisi", readonly=True)
    delivery_count = fields.Integer(string="Pengiriman", readonly=True)
    picking_count = fields.Integer(string="Dokumen Inventory", readonly=True)
    lot_count = fields.Integer(string="Lot", readonly=True)
    transfer_qty = fields.Float(string="Transfer Antar Gudang", readonly=True)
    customer_qty = fields.Float(string="Final ke Customer", readonly=True)
    quantity = fields.Float(string="Qty Keluar", readonly=True)


class StockOutReportDetailLine(models.TransientModel):
    _name = "wt.stock.out.report.detail.line"
    _description = "Stock Out Report Detail Line"
    _order = "sequence, id"

    report_id = fields.Many2one(
        "wt.stock.out.report",
        string="Report",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="No", readonly=True)
    movement_date = fields.Datetime(string="Tanggal", readonly=True)
    delivery_id = fields.Many2one("wt.delivery", string="Pengiriman", readonly=True)
    delivery_name = fields.Char(string="No Pengiriman", readonly=True)
    picking_id = fields.Many2one("stock.picking", string="Dokumen Inventory", readonly=True)
    picking_name = fields.Char(string="No Inventory", readonly=True)
    movement_type = fields.Selection(
        [
            ("inter_warehouse", "Transfer Antar Gudang"),
            ("final_customer", "Final ke Customer"),
        ],
        string="Jenis Pergerakan",
        readonly=True,
    )
    movement_type_label = fields.Char(string="Jenis Pergerakan", readonly=True)
    customer_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    customer_name = fields.Char(string="Customer", readonly=True)
    warehouse_id = fields.Many2one("stock.warehouse", string="Gudang", readonly=True)
    warehouse_name = fields.Char(string="Gudang", readonly=True)
    destination_warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Gudang Tujuan",
        readonly=True,
    )
    destination_warehouse_name = fields.Char(string="Gudang Tujuan", readonly=True)
    division_id = fields.Many2one("wt.division", string="Divisi", readonly=True)
    division_name = fields.Char(string="Divisi", readonly=True)
    source_location_id = fields.Many2one("stock.location", string="Lokasi Sumber", readonly=True)
    source_location_name = fields.Char(string="Lokasi Sumber", readonly=True)
    destination_location_id = fields.Many2one("stock.location", string="Lokasi Tujuan", readonly=True)
    destination_location_name = fields.Char(string="Lokasi Tujuan", readonly=True)
    lot_id = fields.Many2one("stock.lot", string="Lot", readonly=True)
    lot_name = fields.Char(string="Lot", readonly=True)
    transit_lot_id = fields.Many2one("stock.lot", string="Lot Transit", readonly=True)
    transit_lot_name = fields.Char(string="Lot Transit", readonly=True)
    product_id = fields.Many2one("product.product", string="Produk", readonly=True)
    product_name = fields.Char(string="Produk", readonly=True)
    quantity = fields.Float(string="Qty Keluar", readonly=True)
    uom_name = fields.Char(string="Satuan", readonly=True)


class StockOutReportWizard(models.TransientModel):
    _name = "wt.stock.out.report.wizard"
    _description = "Stock Out Report Wizard"

    report_id = fields.Many2one(
        "wt.stock.out.report",
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
    movement_type = fields.Selection(
        [
            ("all", "Semua"),
            ("inter_warehouse", "Transfer Antar Gudang"),
            ("final_customer", "Final ke Customer"),
        ],
        string="Jenis Pergerakan",
        default="all",
        required=True,
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
                "movement_type": self.movement_type,
                "movement_type_label": self._get_filter_movement_type_label(),
                "total_delivery_count": data["total_delivery_count"],
                "total_picking_count": data["total_picking_count"],
                "total_lot_count": data["total_lot_count"],
                "total_transfer_qty": data["total_transfer_qty"],
                "total_customer_qty": data["total_customer_qty"],
                "total_quantity": data["total_quantity"],
            }
        )
        if data["summary_vals"]:
            self.env["wt.stock.out.report.summary.line"].create(data["summary_vals"])
        if data["detail_vals"]:
            self.env["wt.stock.out.report.detail.line"].create(data["detail_vals"])
        return report._open_current_report_action()

    def _prepare_report_data(self):
        move_lines = self._get_move_lines()
        warehouses = self.env["stock.warehouse"].search([("company_id", "=", self.company_id.id)])

        summary_map = {}
        detail_vals = []
        delivery_ids = set()
        picking_ids = set()
        lot_ids = set()
        total_transfer_qty = 0.0
        total_customer_qty = 0.0
        total_quantity = 0.0

        for line in move_lines:
            warehouse = self._resolve_warehouse(line.location_id, warehouses)
            effective_dest_location = self._get_effective_destination_location(line)
            destination_warehouse = self._resolve_warehouse(effective_dest_location, warehouses)
            movement_type = self._get_movement_type(line, warehouse, destination_warehouse)
            if not movement_type:
                continue
            if self.movement_type != "all" and movement_type != self.movement_type:
                continue
            division = line.lot_id.division_id
            if self.warehouse_id and warehouse != self.warehouse_id:
                continue
            if self.division_id and division != self.division_id:
                continue

            quantity = line.quantity or 0.0
            picking = line.picking_id
            delivery = picking.wt_delivery_id
            customer = picking.partner_id or delivery.partner_id
            transit_lot = self._get_transit_lot(line)

            key = (warehouse.id or 0, division.id or 0)
            if key not in summary_map:
                summary_map[key] = {
                    "warehouse": warehouse,
                    "division": division,
                    "delivery_ids": set(),
                    "picking_ids": set(),
                    "lot_ids": set(),
                    "transfer_qty": 0.0,
                    "customer_qty": 0.0,
                    "quantity": 0.0,
                }
            summary_map[key]["delivery_ids"].add(delivery.id)
            summary_map[key]["picking_ids"].add(picking.id)
            summary_map[key]["lot_ids"].add(line.lot_id.id)
            if movement_type == "inter_warehouse":
                summary_map[key]["transfer_qty"] += quantity
                total_transfer_qty += quantity
            elif movement_type == "final_customer":
                summary_map[key]["customer_qty"] += quantity
                total_customer_qty += quantity
            summary_map[key]["quantity"] += quantity

            delivery_ids.add(delivery.id)
            picking_ids.add(picking.id)
            lot_ids.add(line.lot_id.id)
            total_quantity += quantity

            detail_vals.append(
                {
                    "report_id": self.report_id.id,
                    "sequence": len(detail_vals) + 1,
                    "movement_date": line.move_id.date,
                    "delivery_id": delivery.id,
                    "delivery_name": delivery.name or "",
                    "picking_id": picking.id,
                    "picking_name": picking.name or "",
                    "movement_type": movement_type,
                    "movement_type_label": self._get_movement_type_label(movement_type),
                    "customer_id": customer.id or False,
                    "customer_name": (customer.display_name or "-") if movement_type == "final_customer" else "-",
                    "warehouse_id": warehouse.id or False,
                    "warehouse_name": warehouse.display_name or "-",
                    "destination_warehouse_id": destination_warehouse.id or False,
                    "destination_warehouse_name": (
                        destination_warehouse.display_name
                        if movement_type == "inter_warehouse" and destination_warehouse
                        else ((customer.display_name or "-") if movement_type == "final_customer" else "-")
                    ),
                    "division_id": division.id or False,
                    "division_name": division.display_name or "-",
                    "source_location_id": line.location_id.id,
                    "source_location_name": line.location_id.complete_name or line.location_id.display_name,
                    "destination_location_id": effective_dest_location.id,
                    "destination_location_name": (
                        effective_dest_location.complete_name or effective_dest_location.display_name
                    ),
                    "lot_id": line.lot_id.id,
                    "lot_name": line.lot_id.name or "",
                    "transit_lot_id": transit_lot.id or False,
                    "transit_lot_name": transit_lot.name or "-",
                    "product_id": line.product_id.id,
                    "product_name": line.product_id.display_name or "",
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
                    "delivery_count": len(value["delivery_ids"]),
                    "picking_count": len(value["picking_ids"]),
                    "lot_count": len(value["lot_ids"]),
                    "transfer_qty": value["transfer_qty"],
                    "customer_qty": value["customer_qty"],
                    "quantity": value["quantity"],
                }
            )

        return {
            "summary_vals": summary_vals,
            "detail_vals": detail_vals,
            "total_delivery_count": len(delivery_ids),
            "total_picking_count": len(picking_ids),
            "total_lot_count": len(lot_ids),
            "total_transfer_qty": total_transfer_qty,
            "total_customer_qty": total_customer_qty,
            "total_quantity": total_quantity,
        }

    def _get_move_lines(self):
        self.ensure_one()
        start_dt = datetime.combine(self.start_date, time.min)
        end_dt = datetime.combine(self.end_date, time.max)
        domain = [
            ("company_id", "=", self.company_id.id),
            ("move_id.state", "=", "done"),
            ("picking_id.wt_delivery_id", "!=", False),
            ("move_id.date", ">=", fields.Datetime.to_string(start_dt)),
            ("move_id.date", "<=", fields.Datetime.to_string(end_dt)),
            ("quantity", ">", 0),
            ("lot_id", "!=", False),
        ]
        return self.env["stock.move.line"].search(domain, order="id")

    def _get_movement_type(self, line, source_warehouse, destination_warehouse):
        if self._is_transit_merge_consume(line):
            if source_warehouse and destination_warehouse and source_warehouse != destination_warehouse:
                return "inter_warehouse"
            return False
        if line.location_dest_id.usage == "customer":
            return "final_customer"
        if (
            source_warehouse
            and destination_warehouse
            and source_warehouse != destination_warehouse
        ):
            return "inter_warehouse"
        return False

    def _get_movement_type_label(self, movement_type):
        return dict(self.env["wt.stock.out.report.detail.line"]._fields["movement_type"].selection).get(
            movement_type,
            "",
        )

    def _is_transit_merge_consume(self, line):
        description = line.move_id.description_picking or ""
        return (
            description.startswith("Consume old lots for transit merge")
            and line.location_dest_id.usage == "inventory"
            and bool(line.picking_id.location_dest_id)
        )

    def _is_transit_merge_produce(self, line):
        description = line.move_id.description_picking or ""
        return (
            description.startswith("Produce new merged lot for transit")
            and line.location_id.usage == "inventory"
        )

    def _get_effective_destination_location(self, line):
        if self._is_transit_merge_consume(line):
            return line.picking_id.location_dest_id
        return line.location_dest_id

    def _get_transit_lot(self, line):
        if not self._is_transit_merge_consume(line):
            return self.env["stock.lot"]
        produce_line = line.picking_id.move_line_ids.filtered(
            lambda move_line: self._is_transit_merge_produce(move_line)
        )[:1]
        return produce_line.lot_id

    def _get_filter_movement_type_label(self):
        return dict(self._fields["movement_type"].selection).get(self.movement_type, "Semua")

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


class ReportStockOut(models.AbstractModel):
    _name = "report.weightrack.report_stock_out_document"
    _description = "Stock Out Report"

    def _get_report_values(self, docids, data=None):
        docs = self.env["wt.stock.out.report"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "wt.stock.out.report",
            "docs": docs,
        }
