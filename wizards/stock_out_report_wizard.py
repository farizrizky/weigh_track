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
    total_shipping_qty = fields.Float(
        string="Pengiriman",
        readonly=True,
    )
    total_storage_shrinkage_qty = fields.Float(
        string="Susut Penyimpanan",
        readonly=True,
    )
    total_transfer_shrinkage_qty = fields.Float(
        string="Susut Transfer",
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

        sheet.merge_range("A1:H1", self.company_id.name or "", title_format)
        sheet.merge_range("A2:H2", "LAPORAN STOCK KELUAR", title_format)
        sheet.write("A4", "Rentang Tanggal", label_format)
        sheet.write("B4", "%s s/d %s" % (self.start_date or "", self.end_date or ""))
        sheet.write("A5", "Gudang", label_format)
        sheet.write("B5", self.warehouse_id.display_name if self.warehouse_id else "Semua Gudang")
        sheet.write("A6", "Divisi", label_format)
        sheet.write("B6", self.division_id.display_name if self.division_id else "Semua Divisi")
        sheet.write("A7", "Status DO", label_format)
        sheet.write("B7", "Selesai")

        summary_headers = [
            "No",
            "Gudang",
            "Divisi",
            "Qty Keluar",
            "Susut Penyimpanan",
            "Susut Transfer",
            "Pengiriman",
        ]
        summary_widths = [6, 26, 22, 16, 18, 16, 16]
        for column, width in enumerate(summary_widths):
            sheet.set_column(column, column, width)
        sheet.write(8, 0, "STOCK KELUAR PER GUDANG DAN DIVISI", label_format)
        for column, header in enumerate(summary_headers):
            sheet.write(9, column, header, header_format)
        row_index = 10
        for line in self.summary_line_ids:
            sheet.write(row_index, 0, line.sequence, text_format)
            sheet.write(row_index, 1, line.warehouse_name or "", text_format)
            sheet.write(row_index, 2, line.division_name or "", text_format)
            sheet.write(row_index, 3, line.quantity, number_format)
            sheet.write(row_index, 4, line.storage_shrinkage_qty, number_format)
            sheet.write(row_index, 5, line.transfer_shrinkage_qty, number_format)
            sheet.write(row_index, 6, line.shipping_qty, number_format)
            row_index += 1
        sheet.merge_range(row_index, 0, row_index, 2, "Total", total_label_format)
        sheet.write(row_index, 3, self.total_quantity, total_number_format)
        sheet.write(row_index, 4, self.total_storage_shrinkage_qty, total_number_format)
        sheet.write(row_index, 5, self.total_transfer_shrinkage_qty, total_number_format)
        sheet.write(row_index, 6, self.total_shipping_qty, total_number_format)

        row_index += 3
        detail_headers = [
            "No",
            "Tanggal",
            "No DO / Referensi",
            "Gudang",
            "Divisi",
            "Lot",
            "Kategori",
            "Qty",
        ]
        detail_widths = [6, 14, 22, 26, 20, 26, 22, 14]
        for column, width in enumerate(detail_widths):
            sheet.set_column(column, column, width)
        sheet.write(row_index, 0, "DETAIL SUMBER PERGERAKAN", label_format)
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
            sheet.write(row_index, 2, line.source_document or "", text_format)
            sheet.write(row_index, 3, line.warehouse_name or "", text_format)
            sheet.write(row_index, 4, line.division_name or "", text_format)
            sheet.write(row_index, 5, line.lot_name or "", text_format)
            sheet.write(row_index, 6, line.category_label or "", text_format)
            sheet.write(row_index, 7, line.quantity, number_format)
            row_index += 1
        sheet.merge_range(row_index, 0, row_index, 6, "Total", total_label_format)
        sheet.write(row_index, 7, self.total_quantity, total_number_format)

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
    shipping_qty = fields.Float(string="Pengiriman", readonly=True)
    storage_shrinkage_qty = fields.Float(string="Susut Penyimpanan", readonly=True)
    transfer_shrinkage_qty = fields.Float(string="Susut Transfer", readonly=True)
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
    category = fields.Selection(
        [
            ("shipping", "Pengiriman"),
            ("storage_shrinkage", "Susut Penyimpanan"),
            ("transfer_shrinkage", "Susut Transfer"),
        ],
        string="Kategori",
        readonly=True,
    )
    category_label = fields.Char(string="Kategori", readonly=True)
    source_document = fields.Char(string="No DO / Referensi", readonly=True)
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
                "movement_type": "all",
                "movement_type_label": _("Semua"),
                "total_delivery_count": data["total_delivery_count"],
                "total_picking_count": data["total_picking_count"],
                "total_lot_count": data["total_lot_count"],
                "total_transfer_qty": data["total_transfer_qty"],
                "total_customer_qty": data["total_customer_qty"],
                "total_quantity": data["total_quantity"],
                "total_shipping_qty": data["total_shipping_qty"],
                "total_storage_shrinkage_qty": data["total_storage_shrinkage_qty"],
                "total_transfer_shrinkage_qty": data["total_transfer_shrinkage_qty"],
            }
        )
        if data["summary_vals"]:
            self.env["wt.stock.out.report.summary.line"].create(data["summary_vals"])
        if data["detail_vals"]:
            self.env["wt.stock.out.report.detail.line"].create(data["detail_vals"])
        return report._open_current_report_action()

    def _prepare_report_data(self):
        warehouses = self.env["stock.warehouse"].search([("company_id", "=", self.company_id.id)])
        completed_deliveries = self.env["wt.delivery"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("state", "=", "done"),
            ]
        )
        completed_delivery_by_name = {
            delivery.name: delivery for delivery in completed_deliveries if delivery.name
        }
        events = []
        provenance_cache = {}

        for line in self._get_shipping_move_lines():
            delivery = line.picking_id.wt_delivery_id
            lot = line.lot_id
            quantity = line.quantity or 0.0
            if lot.wt_lot_type == "transit":
                sources = self._get_transit_provenance(
                    lot,
                    warehouses,
                    provenance_cache,
                )
                if sources:
                    source_total = sum(source["quantity"] for source in sources)
                    remaining = quantity
                    for index, source in enumerate(sources):
                        allocated_qty = (
                            remaining
                            if index == len(sources) - 1
                            else quantity * source["quantity"] / source_total
                        )
                        remaining -= allocated_qty
                        self._append_report_event(
                            events,
                            line=line,
                            category="shipping",
                            quantity=allocated_qty,
                            warehouse=source["warehouse"],
                            division=source["division"],
                            lot=source["lot"],
                            source_location=source["source_location"],
                            source_document=delivery.name,
                            delivery=delivery,
                            picking=line.picking_id,
                            customer=line.picking_id.partner_id or delivery.partner_id,
                        )
                    continue

            warehouse = self._resolve_warehouse(line.location_id, warehouses)
            self._append_report_event(
                events,
                line=line,
                category="shipping",
                quantity=quantity,
                warehouse=warehouse,
                division=lot.division_id,
                lot=lot,
                source_location=line.location_id,
                source_document=delivery.name,
                delivery=delivery,
                picking=line.picking_id,
                customer=line.picking_id.partner_id or delivery.partner_id,
            )

        for line in self._get_storage_shrinkage_move_lines():
            warehouse = self._resolve_warehouse(line.location_id, warehouses)
            self._append_report_event(
                events,
                line=line,
                category="storage_shrinkage",
                quantity=line.quantity or 0.0,
                warehouse=warehouse,
                division=line.lot_id.division_id,
                lot=line.lot_id,
                source_location=line.location_id,
                source_document=line.move_id.origin or "",
            )

        for line in self._get_transfer_shrinkage_move_lines():
            delivery = completed_delivery_by_name.get(line.move_id.origin)
            warehouse = self._resolve_warehouse(line.location_id, warehouses)
            self._append_report_event(
                events,
                line=line,
                category="transfer_shrinkage",
                quantity=line.quantity or 0.0,
                warehouse=warehouse,
                division=self.env["wt.division"],
                lot=line.lot_id,
                source_location=line.location_id,
                source_document=line.move_id.origin or "",
                delivery=delivery,
                is_transit=True,
            )

        events.sort(
            key=lambda event: (
                event["movement_date"] or datetime.min,
                event["source_document"] or "",
                event["lot"].name or "",
                event["category"],
            )
        )
        summary_map = {}
        detail_vals = []
        delivery_ids = set()
        picking_ids = set()
        lot_ids = set()
        totals = {
            "shipping": 0.0,
            "storage_shrinkage": 0.0,
            "transfer_shrinkage": 0.0,
        }

        for sequence, event in enumerate(events, start=1):
            warehouse = event["warehouse"]
            division = event["division"]
            is_transit = event["is_transit"]
            quantity = event["quantity"]
            category = event["category"]
            delivery = event["delivery"]
            picking = event["picking"]
            lot = event["lot"]

            key = (warehouse.id or 0, division.id or 0, is_transit)
            if key not in summary_map:
                summary_map[key] = {
                    "warehouse": warehouse,
                    "division": division,
                    "division_code": "" if is_transit else (division.code or ""),
                    "division_name": _("Transit") if is_transit else (division.display_name or "-"),
                    "shipping_qty": 0.0,
                    "storage_shrinkage_qty": 0.0,
                    "transfer_shrinkage_qty": 0.0,
                    "quantity": 0.0,
                }
            summary_map[key]["%s_qty" % category] += quantity
            summary_map[key]["quantity"] += quantity
            totals[category] += quantity

            if delivery:
                delivery_ids.add(delivery.id)
            if picking:
                picking_ids.add(picking.id)
            if lot:
                lot_ids.add(lot.id)

            detail_vals.append(
                {
                    "report_id": self.report_id.id,
                    "sequence": sequence,
                    "movement_date": event["movement_date"],
                    "delivery_id": delivery.id if delivery else False,
                    "delivery_name": delivery.name if delivery else "",
                    "picking_id": picking.id if picking else False,
                    "picking_name": picking.name if picking else "",
                    "movement_type": "final_customer" if category == "shipping" else False,
                    "movement_type_label": event["category_label"],
                    "category": category,
                    "category_label": event["category_label"],
                    "source_document": event["source_document"],
                    "customer_id": event["customer"].id if event["customer"] else False,
                    "customer_name": event["customer"].display_name if event["customer"] else "-",
                    "warehouse_id": warehouse.id or False,
                    "warehouse_name": warehouse.display_name or "-",
                    "destination_warehouse_id": False,
                    "destination_warehouse_name": "-",
                    "division_id": division.id or False,
                    "division_name": _("Transit") if is_transit else (division.display_name or "-"),
                    "source_location_id": event["source_location"].id,
                    "source_location_name": (
                        event["source_location"].complete_name
                        or event["source_location"].display_name
                    ),
                    "destination_location_id": event["destination_location"].id,
                    "destination_location_name": (
                        event["destination_location"].complete_name
                        or event["destination_location"].display_name
                    ),
                    "lot_id": lot.id,
                    "lot_name": lot.name or "",
                    "transit_lot_id": lot.id if is_transit else False,
                    "transit_lot_name": lot.name if is_transit else "-",
                    "product_id": event["product"].id,
                    "product_name": event["product"].display_name or "",
                    "quantity": quantity,
                    "uom_name": event["uom"].name or "",
                }
            )

        summary_vals = []
        for number, value in enumerate(
            sorted(
                summary_map.values(),
                key=lambda row: (
                    self._natural_sort_key(row["division_code"]),
                    row["warehouse"].display_name or "",
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
                    "division_name": value["division_name"],
                    "delivery_count": 0,
                    "picking_count": 0,
                    "lot_count": 0,
                    "transfer_qty": value["transfer_shrinkage_qty"],
                    "customer_qty": value["shipping_qty"],
                    "shipping_qty": value["shipping_qty"],
                    "storage_shrinkage_qty": value["storage_shrinkage_qty"],
                    "transfer_shrinkage_qty": value["transfer_shrinkage_qty"],
                    "quantity": value["quantity"],
                }
            )

        total_quantity = sum(totals.values())
        return {
            "summary_vals": summary_vals,
            "detail_vals": detail_vals,
            "total_delivery_count": len(delivery_ids),
            "total_picking_count": len(picking_ids),
            "total_lot_count": len(lot_ids),
            "total_transfer_qty": totals["transfer_shrinkage"],
            "total_customer_qty": totals["shipping"],
            "total_quantity": total_quantity,
            "total_shipping_qty": totals["shipping"],
            "total_storage_shrinkage_qty": totals["storage_shrinkage"],
            "total_transfer_shrinkage_qty": totals["transfer_shrinkage"],
        }

    @staticmethod
    def _natural_sort_key(value):
        return tuple(
            int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", value or "")
        )

    def _append_report_event(
        self,
        events,
        *,
        line,
        category,
        quantity,
        warehouse,
        division,
        lot,
        source_location,
        source_document,
        delivery=None,
        picking=None,
        customer=None,
        is_transit=False,
    ):
        if quantity <= 0.0 or not source_location:
            return
        if self.warehouse_id and warehouse != self.warehouse_id:
            return
        if self.division_id and (is_transit or division != self.division_id):
            return

        category_labels = {
            "shipping": _("Pengiriman"),
            "storage_shrinkage": _("Susut Penyimpanan"),
            "transfer_shrinkage": _("Susut Transfer"),
        }
        events.append(
            {
                "movement_date": line.move_id.date,
                "source_document": source_document,
                "category": category,
                "category_label": category_labels[category],
                "quantity": quantity,
                "warehouse": warehouse,
                "division": division,
                "is_transit": is_transit,
                "lot": lot,
                "source_location": source_location,
                "destination_location": line.location_dest_id,
                "delivery": delivery or self.env["wt.delivery"],
                "picking": picking or self.env["stock.picking"],
                "customer": customer or self.env["res.partner"],
                "product": line.product_id,
                "uom": line.product_uom_id or line.product_id.uom_id,
            }
        )

    def _get_shipping_move_lines(self):
        self.ensure_one()
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

    def _get_storage_shrinkage_move_lines(self):
        self.ensure_one()
        return self._get_shrinkage_move_lines(
            [
                ("lot_id.wt_lot_type", "=", "production"),
            ]
        )

    def _get_transfer_shrinkage_move_lines(self):
        self.ensure_one()
        move_lines = self._get_shrinkage_move_lines(
            [
                ("lot_id.wt_lot_type", "=", "transit"),
            ]
        )
        return move_lines.filtered(lambda line: not self._is_transit_merge_move_line(line))

    def _get_shrinkage_move_lines(self, extra_domain):
        shrinkage_location = self._get_shrinkage_location()
        if not shrinkage_location:
            return self.env["stock.move.line"]
        start_dt, end_dt = self._get_utc_date_range()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("move_id.state", "=", "done"),
            ("move_id.date", ">=", fields.Datetime.to_string(start_dt)),
            ("move_id.date", "<=", fields.Datetime.to_string(end_dt)),
            ("location_id.usage", "=", "internal"),
            ("location_dest_id", "child_of", shrinkage_location.id),
            ("quantity", ">", 0),
            ("lot_id", "!=", False),
        ]
        return self.env["stock.move.line"].search(domain + extra_domain, order="id")

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

    def _get_utc_date_range(self):
        user_tz = timezone(self.env.user.tz or "UTC")
        start_local = user_tz.localize(datetime.combine(self.start_date, time.min))
        end_local = user_tz.localize(datetime.combine(self.end_date, time.max))
        return (
            start_local.astimezone(UTC).replace(tzinfo=None),
            end_local.astimezone(UTC).replace(tzinfo=None),
        )

    def _get_transit_provenance(self, lot, warehouses, cache, visiting=None):
        if lot.id in cache:
            return cache[lot.id]

        visiting = set(visiting or ())
        if lot.id in visiting:
            return []
        visiting.add(lot.id)

        picking = lot.wt_source_picking_id
        if not picking:
            cache[lot.id] = []
            return []

        consume_lines = picking.move_line_ids.filtered(
            lambda line: line.lot_id
            and line.lot_id != lot
            and self._is_transit_merge_consume(line)
        )
        if not consume_lines:
            consume_lines = picking.move_line_ids.filtered(
                lambda line: line.lot_id
                and line.lot_id != lot
                and line.location_id.usage == "internal"
                and line.location_dest_id.usage == "inventory"
            )

        provenance_map = {}
        for line in consume_lines:
            source_lot = line.lot_id
            source_quantity = line.quantity or 0.0
            if source_quantity <= 0.0:
                continue

            if source_lot.wt_lot_type == "transit":
                nested_sources = self._get_transit_provenance(
                    source_lot,
                    warehouses,
                    cache,
                    visiting,
                )
                nested_total = sum(source["quantity"] for source in nested_sources)
                if nested_total:
                    for source in nested_sources:
                        self._merge_provenance_source(
                            provenance_map,
                            source,
                            source_quantity * source["quantity"] / nested_total,
                        )
                continue

            warehouse = self._resolve_warehouse(line.location_id, warehouses)
            source = {
                "warehouse": warehouse,
                "division": source_lot.division_id,
                "lot": source_lot,
                "source_location": line.location_id,
            }
            self._merge_provenance_source(provenance_map, source, source_quantity)

        result = list(provenance_map.values())
        cache[lot.id] = result
        return result

    def _merge_provenance_source(self, provenance_map, source, quantity):
        key = (
            source["warehouse"].id or 0,
            source["division"].id or 0,
            source["lot"].id,
            source["source_location"].id,
        )
        if key not in provenance_map:
            provenance_map[key] = dict(source, quantity=0.0)
        provenance_map[key]["quantity"] += quantity

    def _is_transit_merge_consume(self, line):
        description = line.move_id.description_picking or ""
        return (
            description.startswith("Consume old lots for transit merge")
            and line.location_dest_id.usage == "inventory"
        )

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
