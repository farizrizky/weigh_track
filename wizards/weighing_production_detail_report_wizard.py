# -*- coding: utf-8 -*-

import base64
import io

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class WeighingProductionDetailReport(models.TransientModel):
    _name = "wt.weighing.production.detail.report"
    _description = "Weighing Production Detail Report"

    name = fields.Char(
        string="Report",
        default="Laporan Penimbangan Produksi Detail",
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
        string="Tanggal Produksi Dari",
        readonly=True,
    )
    end_date = fields.Date(
        string="Tanggal Produksi Sampai",
        readonly=True,
    )
    estate_id = fields.Many2one(
        "wt.estate",
        string="Estate",
        readonly=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Divisi",
        readonly=True,
    )
    foreman_id = fields.Many2one(
        "wt.foreman",
        string="Mandor",
        readonly=True,
    )
    tapper_id = fields.Many2one(
        "wt.tapper",
        string="Tapper",
        readonly=True,
    )

    total_bag = fields.Integer(
        string="Total Karung",
        readonly=True,
    )
    total_production_weight = fields.Float(
        string="Total Berat Produksi",
        readonly=True,
    )
    total_reject_weight = fields.Float(
        string="Total Berat Reject",
        readonly=True,
    )
    total_slab_weight = fields.Float(
        string="Total Berat Slab",
        readonly=True,
    )
    total_net_weight = fields.Float(
        string="Total Berat Bersih",
        readonly=True,
    )
    total_initial_weight = fields.Float(
        string="Total Berat Lapangan",
        readonly=True,
    )
    total_shrinkage_tolerance_weight = fields.Float(
        string="Total Berat Toleransi Susut",
        readonly=True,
    )
    line_ids = fields.One2many(
        "wt.weighing.production.detail.report.line",
        "report_id",
        string="Lines",
        readonly=True,
    )

    def action_open_filter(self):
        self.ensure_one()
        return {
            "name": _("Filter Laporan Penimbangan Produksi Detail"),
            "type": "ir.actions.act_window",
            "res_model": "wt.weighing.production.detail.report.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_report_id": self.id,
                "default_company_id": self.company_id.id or self.env.company.id,
                "default_start_date": self.start_date or fields.Date.context_today(self),
                "default_end_date": self.end_date or fields.Date.context_today(self),
                "default_estate_id": self.estate_id.id,
                "default_division_id": self.division_id.id,
                "default_foreman_id": self.foreman_id.id,
                "default_tapper_id": self.tapper_id.id,
            },
        }

    def action_print_pdf(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Please apply a filter before printing the report."))
        return self.env.ref(
            "weightrack.action_report_weighing_production_detail_pdf"
        ).report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Please apply a filter before exporting the report."))
        if xlsxwriter is None:
            raise ValidationError(_("The xlsxwriter Python package is not installed."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Laporan Penimbangan Detail")

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
        text_center_format = workbook.add_format({"border": 1, "align": "center"})
        number_format = workbook.add_format({"border": 1, "num_format": "#,##0.00"})
        integer_format = workbook.add_format({"border": 1, "num_format": "#,##0"})
        total_label_format = workbook.add_format(
            {"bold": True, "align": "center", "border": 1}
        )
        total_number_format = workbook.add_format(
            {"bold": True, "border": 1, "num_format": "#,##0.00"}
        )
        total_integer_format = workbook.add_format(
            {"bold": True, "border": 1, "num_format": "#,##0"}
        )

        sheet.merge_range("A1:AA1", self.company_id.name or "", title_format)
        sheet.merge_range("A2:AA2", "LAPORAN PENIMBANGAN PRODUKSI DETAIL", title_format)
        
        sheet.write("A4", "Rentang Tanggal", label_format)
        sheet.write("B4", f"{self.start_date or ''} s/d {self.end_date or ''}")
        sheet.write("A5", "Estate", label_format)
        sheet.write("B5", self.estate_id.display_name if self.estate_id else "Semua Estate")
        sheet.write("A6", "Divisi", label_format)
        sheet.write("B6", self.division_id.display_name if self.division_id else "Semua Divisi")
        sheet.write("A7", "Mandor", label_format)
        sheet.write("B7", self.foreman_id.display_name if self.foreman_id else "Semua Mandor")
        sheet.write("A8", "Tapper", label_format)
        sheet.write("B8", self.tapper_id.display_name if self.tapper_id else "Semua Tapper")

        headers = [
            "No",
            "Nomor Penimbangan",
            "Tanggal Produksi",
            "Tanggal Timbang",
            "Tanggal Penerimaan",
            "Badge Number",
            "Tapper",
            "Divisi",
            "Lokasi Timbang",
            "Device ID",
            "Operator",
            "Mandor",
            "Krani",
            "Production Receipt Number",
            "Inventory Receipt Number",
            "Lot",
            "Manual Penimbangan (Y/N)",
            "Alasan Penimbangan Manual",
            "Sumber Data",
            "Total Karung",
            "Berat Produksi",
            "Berat Reject",
            "Berat Slab",
            "Berat Bersih",
            "Berat Lapangan",
            "Persentase Toleransi Susut",
            "Berat Toleransi Susut",
        ]
        widths = [
            6, 20, 14, 18, 14, 14, 22, 18, 20, 16, 20, 20, 20,
            24, 24, 24, 14, 25, 14, 12, 16, 16, 16, 16, 16, 16, 18
        ]
        for column, width in enumerate(widths):
            sheet.set_column(column, column, width)
        
        header_row = 10
        for column, header in enumerate(headers):
            sheet.write(header_row, column, header, header_format)

        row_index = header_row + 1
        for line in self.line_ids:
            sheet.write(row_index, 0, line.sequence, integer_format)
            sheet.write(row_index, 1, line.weighing_number or "", text_format)
            sheet.write(row_index, 2, line.production_date or "", text_center_format)
            sheet.write(row_index, 3, line.weighing_date or "", text_center_format)
            sheet.write(row_index, 4, line.receipt_date or "", text_center_format)
            sheet.write(row_index, 5, line.badge_number or "", text_center_format)
            sheet.write(row_index, 6, line.tapper_name or "", text_format)
            sheet.write(row_index, 7, line.division_name or "", text_format)
            sheet.write(row_index, 8, line.weighing_location_name or "", text_format)
            sheet.write(row_index, 9, line.device_id or "", text_center_format)
            sheet.write(row_index, 10, line.operator_name or "", text_format)
            sheet.write(row_index, 11, line.foreman_name or "", text_format)
            sheet.write(row_index, 12, line.clerk_name or "", text_format)
            sheet.write(row_index, 13, line.production_receipt_number or "", text_format)
            sheet.write(row_index, 14, line.inventory_receipt_number or "", text_format)
            sheet.write(row_index, 15, line.lot_name or "", text_format)
            sheet.write(row_index, 16, line.manual_weighing or "", text_center_format)
            sheet.write(row_index, 17, line.manual_weighing_reason or "", text_format)
            sheet.write(row_index, 18, line.data_source or "", text_center_format)
            sheet.write(row_index, 19, line.total_bag, integer_format)
            sheet.write(row_index, 20, line.production_weight, number_format)
            sheet.write(row_index, 21, line.reject_weight, number_format)
            sheet.write(row_index, 22, line.slab_weight, number_format)
            sheet.write(row_index, 23, line.net_weight, number_format)
            sheet.write(row_index, 24, line.initial_weight, number_format)
            sheet.write(row_index, 25, line.shrinkage_tolerance_percentage, number_format)
            sheet.write(row_index, 26, line.shrinkage_tolerance_weight, number_format)
            row_index += 1

        sheet.merge_range(row_index, 0, row_index, 18, "Total", total_label_format)
        sheet.write(row_index, 19, self.total_bag, total_integer_format)
        sheet.write(row_index, 20, self.total_production_weight, total_number_format)
        sheet.write(row_index, 21, self.total_reject_weight, total_number_format)
        sheet.write(row_index, 22, self.total_slab_weight, total_number_format)
        sheet.write(row_index, 23, self.total_net_weight, total_number_format)
        sheet.write(row_index, 24, self.total_initial_weight, total_number_format)
        sheet.write(row_index, 25, "", total_label_format)
        sheet.write(row_index, 26, self.total_shrinkage_tolerance_weight, total_number_format)

        workbook.close()
        output.seek(0)
        filename = f"Laporan Penimbangan Produksi Detail - {self.start_date} sd {self.end_date}.xlsx"
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
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    def _open_current_report_action(self):
        self.ensure_one()
        return {
            "name": _("Laporan Penimbangan Produksi Detail"),
            "type": "ir.actions.act_window",
            "res_model": "wt.weighing.production.detail.report",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }


class WeighingProductionDetailReportLine(models.TransientModel):
    _name = "wt.weighing.production.detail.report.line"
    _description = "Weighing Production Detail Report Line"
    _order = "sequence, id"

    report_id = fields.Many2one(
        "wt.weighing.production.detail.report",
        string="Report",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(
        string="No",
        readonly=True,
    )
    weighing_number = fields.Char(
        string="Nomor Penimbangan",
        readonly=True,
    )
    production_date = fields.Char(
        string="Tanggal Produksi",
        readonly=True,
    )
    weighing_date = fields.Char(
        string="Tanggal Timbang",
        readonly=True,
    )
    receipt_date = fields.Char(
        string="Tanggal Penerimaan",
        readonly=True,
    )
    badge_number = fields.Char(
        string="Badge Number",
        readonly=True,
    )
    tapper_name = fields.Char(
        string="Tapper",
        readonly=True,
    )
    division_name = fields.Char(
        string="Divisi",
        readonly=True,
    )
    weighing_location_name = fields.Char(
        string="Lokasi Timbang",
        readonly=True,
    )
    device_id = fields.Char(
        string="Device ID",
        readonly=True,
    )
    operator_name = fields.Char(
        string="Operator",
        readonly=True,
    )
    foreman_name = fields.Char(
        string="Mandor",
        readonly=True,
    )
    clerk_name = fields.Char(
        string="Krani",
        readonly=True,
    )
    production_receipt_number = fields.Char(
        string="Production Receipt Number",
        readonly=True,
    )
    inventory_receipt_number = fields.Char(
        string="Inventory Receipt Number",
        readonly=True,
    )
    lot_name = fields.Char(
        string="Lot",
        readonly=True,
    )
    manual_weighing = fields.Char(
        string="Manual Penimbangan (Y/N)",
        readonly=True,
    )
    manual_weighing_reason = fields.Char(
        string="Alasan Penimbangan Manual",
        readonly=True,
    )
    data_source = fields.Char(
        string="Sumber Data",
        readonly=True,
    )
    total_bag = fields.Integer(
        string="Total Karung",
        readonly=True,
    )
    production_weight = fields.Float(
        string="Berat Produksi",
        readonly=True,
    )
    reject_weight = fields.Float(
        string="Berat Reject",
        readonly=True,
    )
    slab_weight = fields.Float(
        string="Berat Slab",
        readonly=True,
    )
    net_weight = fields.Float(
        string="Berat Bersih",
        readonly=True,
    )
    initial_weight = fields.Float(
        string="Berat Lapangan",
        readonly=True,
    )
    shrinkage_tolerance_percentage = fields.Float(
        string="Persentase Toleransi Susut",
        readonly=True,
    )
    shrinkage_tolerance_weight = fields.Float(
        string="Berat Toleransi Susut",
        readonly=True,
    )


class WeighingProductionDetailReportWizard(models.TransientModel):
    _name = "wt.weighing.production.detail.report.wizard"
    _description = "Weighing Production Detail Report Wizard"

    report_id = fields.Many2one(
        "wt.weighing.production.detail.report",
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
        string="Tanggal Produksi Dari",
        required=True,
        default=fields.Date.context_today,
    )
    end_date = fields.Date(
        string="Tanggal Produksi Sampai",
        required=True,
        default=fields.Date.context_today,
    )
    estate_id = fields.Many2one(
        "wt.estate",
        string="Estate",
        required=False,
        domain="[('company_id', '=', company_id)]",
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Divisi",
        required=False,
    )
    foreman_id = fields.Many2one(
        "wt.foreman",
        string="Mandor",
        required=False,
    )
    tapper_id = fields.Many2one(
        "wt.tapper",
        string="Tapper",
        required=False,
    )

    @api.constrains("start_date", "end_date")
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.start_date > rec.end_date:
                raise ValidationError(_("Tanggal Produksi Dari tidak boleh lebih besar dari Tanggal Produksi Sampai."))

    @api.onchange("company_id")
    def _onchange_company_id(self):
        self.estate_id = False
        self.division_id = False
        self.foreman_id = False
        self.tapper_id = False

    @api.onchange("estate_id")
    def _onchange_estate_id(self):
        self.division_id = False
        self.foreman_id = False
        self.tapper_id = False
        domain = [("company_id", "=", self.company_id.id)]
        if self.estate_id:
            domain.append(("estate_id", "=", self.estate_id.id))
        return {"domain": {"division_id": domain}}

    @api.onchange("division_id")
    def _onchange_division_id(self):
        self.foreman_id = False
        self.tapper_id = False
        domain_foreman = []
        domain_tapper = []
        if self.division_id:
            domain_foreman.append(("division_id", "=", self.division_id.id))
            domain_tapper.append(("division_id", "=", self.division_id.id))
        elif self.estate_id:
            divisions = self.env["wt.division"].search([("estate_id", "=", self.estate_id.id)])
            domain_foreman.append(("division_id", "in", divisions.ids))
            domain_tapper.append(("division_id", "in", divisions.ids))
        elif self.company_id:
            domain_foreman.append(("company_id", "=", self.company_id.id))
            domain_tapper.append(("company_id", "=", self.company_id.id))
        return {"domain": {"foreman_id": domain_foreman, "tapper_id": domain_tapper}}

    @api.onchange("foreman_id")
    def _onchange_foreman_id(self):
        self.tapper_id = False
        domain = []
        if self.foreman_id:
            domain.append(("foreman_id", "=", self.foreman_id.id))
        elif self.division_id:
            domain.append(("division_id", "=", self.division_id.id))
        return {"domain": {"tapper_id": domain}}

    def _get_domain(self):
        self.ensure_one()
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError(_("Tanggal Produksi Dari tidak boleh lebih besar dari Tanggal Produksi Sampai."))
        domain = [
            ("company_id", "=", self.company_id.id),
            ("production_date", ">=", self.start_date),
            ("production_date", "<=", self.end_date),
            ("state", "=", "receipt_validated"),
        ]
        if self.estate_id:
            domain.append(("estate_id", "=", self.estate_id.id))
        if self.division_id:
            domain.append(("division_id", "=", self.division_id.id))
        if self.foreman_id:
            domain.append(("foreman_id", "=", self.foreman_id.id))
        if self.tapper_id:
            domain.append(("tapper_id", "=", self.tapper_id.id))
        return domain

    def _get_weighing_records(self):
        self.ensure_one()
        records = self.env["wt.weighing"].search(
            self._get_domain(),
            order="production_date, tapper_name, id",
        )
        return sorted(
            records,
            key=lambda r: (r.production_date or fields.Date.today(), r.tapper_name or "", r.id),
        )

    def _prepare_report_data(self):
        self.ensure_one()
        records = self._get_weighing_records()
        rows = []
        total_bag = 0
        total_production_weight = 0.0
        total_reject_weight = 0.0
        total_slab_weight = 0.0
        total_net_weight = 0.0
        total_initial_weight = 0.0
        total_shrinkage_tolerance_weight = 0.0

        for number, record in enumerate(records, start=1):
            bag = record.total_bag or 0
            prod_w = record.production_weight or 0.0
            rej_w = record.reject_weight or 0.0
            slab_w = record.slab_weight or 0.0
            net_w = record.net_weight or 0.0
            init_w = record.initial_weight or 0.0
            shrink_pct = record.shrinkage_tolerance_percentage or 0.0
            shrink_w = record.shrinkage_tolerance_weight or 0.0

            badge_no = record.tapper_barcode or (record.tapper_id.employee_id.barcode if record.tapper_id else "") or "-"
            tapper_nm = record.tapper_name or (record.tapper_id.name if record.tapper_id else "") or "-"
            div_nm = record.division_id.name or "-"
            loc_nm = record.weighing_location_id.name or "-"
            dev_id = record.device_id or (record.device_record_id.device_id if record.device_record_id else "") or "-"
            op_nm = record.operator_name or (record.operator_employee_id.name if record.operator_employee_id else "") or "-"
            foreman_nm = record.foreman_name or (record.foreman_id.name if record.foreman_id else "") or "-"
            clerk_nm = record.clerk_name or (record.clerk_employee_id.name if record.clerk_employee_id else "") or "-"
            pr_number = record.production_receipt_id.name if record.production_receipt_id else "-"
            ir_number = (
                record.production_receipt_id.stock_picking_id.name
                if record.production_receipt_id and record.production_receipt_id.stock_picking_id
                else "-"
            )
            lot_nm = (
                record.production_receipt_id.lot_id.name
                if record.production_receipt_id and record.production_receipt_id.lot_id
                else "-"
            )
            manual_yn = "Y" if record.is_manual_weighing else "N"
            manual_reason = record.manual_weighing_reason or "-"
            rcpt_dt = str(record.production_receipt_id.received_date) if record.production_receipt_id and record.production_receipt_id.received_date else "-"
            weigh_dt = record.weighing_date.strftime("%Y-%m-%d %H:%M:%S") if record.weighing_date else "-"
            prod_dt = str(record.production_date) if record.production_date else "-"
            ds = "API" if record.data_source == "api" else ("Manual" if record.data_source == "manual" else "-")

            rows.append(
                {
                    "number": number,
                    "weighing_number": record.name or "/",
                    "production_date": prod_dt,
                    "weighing_date": weigh_dt,
                    "receipt_date": rcpt_dt,
                    "badge_number": badge_no,
                    "tapper_name": tapper_nm,
                    "division_name": div_nm,
                    "weighing_location_name": loc_nm,
                    "device_id": dev_id,
                    "operator_name": op_nm,
                    "foreman_name": foreman_nm,
                    "clerk_name": clerk_nm,
                    "production_receipt_number": pr_number,
                    "inventory_receipt_number": ir_number,
                    "lot_name": lot_nm,
                    "manual_weighing": manual_yn,
                    "manual_weighing_reason": manual_reason,
                    "data_source": ds,
                    "total_bag": bag,
                    "production_weight": prod_w,
                    "reject_weight": rej_w,
                    "slab_weight": slab_w,
                    "net_weight": net_w,
                    "initial_weight": init_w,
                    "shrinkage_tolerance_percentage": shrink_pct,
                    "shrinkage_tolerance_weight": shrink_w,
                }
            )

            total_bag += bag
            total_production_weight += prod_w
            total_reject_weight += rej_w
            total_slab_weight += slab_w
            total_net_weight += net_w
            total_initial_weight += init_w
            total_shrinkage_tolerance_weight += shrink_w

        return {
            "rows": rows,
            "total_bag": total_bag,
            "total_production_weight": total_production_weight,
            "total_reject_weight": total_reject_weight,
            "total_slab_weight": total_slab_weight,
            "total_net_weight": total_net_weight,
            "total_initial_weight": total_initial_weight,
            "total_shrinkage_tolerance_weight": total_shrinkage_tolerance_weight,
        }

    def action_apply_filter(self):
        self.ensure_one()
        report = self.report_id
        data = self._prepare_report_data()
        report.line_ids.unlink()
        report.write(
            {
                "is_filtered": True,
                "company_id": self.company_id.id,
                "start_date": self.start_date,
                "end_date": self.end_date,
                "estate_id": self.estate_id.id if self.estate_id else False,
                "division_id": self.division_id.id if self.division_id else False,
                "foreman_id": self.foreman_id.id if self.foreman_id else False,
                "tapper_id": self.tapper_id.id if self.tapper_id else False,
                "total_bag": data["total_bag"],
                "total_production_weight": data["total_production_weight"],
                "total_reject_weight": data["total_reject_weight"],
                "total_slab_weight": data["total_slab_weight"],
                "total_net_weight": data["total_net_weight"],
                "total_initial_weight": data["total_initial_weight"],
                "total_shrinkage_tolerance_weight": data["total_shrinkage_tolerance_weight"],
            }
        )
        line_vals = [
            {
                "report_id": report.id,
                "sequence": row["number"],
                "weighing_number": row["weighing_number"],
                "production_date": row["production_date"],
                "weighing_date": row["weighing_date"],
                "receipt_date": row["receipt_date"],
                "badge_number": row["badge_number"],
                "tapper_name": row["tapper_name"],
                "division_name": row["division_name"],
                "weighing_location_name": row["weighing_location_name"],
                "device_id": row["device_id"],
                "operator_name": row["operator_name"],
                "foreman_name": row["foreman_name"],
                "clerk_name": row["clerk_name"],
                "production_receipt_number": row["production_receipt_number"],
                "inventory_receipt_number": row["inventory_receipt_number"],
                "lot_name": row["lot_name"],
                "manual_weighing": row["manual_weighing"],
                "manual_weighing_reason": row["manual_weighing_reason"],
                "data_source": row["data_source"],
                "total_bag": row["total_bag"],
                "production_weight": row["production_weight"],
                "reject_weight": row["reject_weight"],
                "slab_weight": row["slab_weight"],
                "net_weight": row["net_weight"],
                "initial_weight": row["initial_weight"],
                "shrinkage_tolerance_percentage": row["shrinkage_tolerance_percentage"],
                "shrinkage_tolerance_weight": row["shrinkage_tolerance_weight"],
            }
            for row in data["rows"]
        ]
        if line_vals:
            self.env["wt.weighing.production.detail.report.line"].create(line_vals)
        return report._open_current_report_action()


class ReportWeighingProductionDetail(models.AbstractModel):
    _name = "report.weightrack.report_weighing_production_detail_doc"
    _description = "Weighing Production Detail Report Document"

    def _get_report_values(self, docids, data=None):
        docs = self.env["wt.weighing.production.detail.report"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "wt.weighing.production.detail.report",
            "docs": docs,
        }
