# -*- coding: utf-8 -*-

import base64
import io

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class WeighingProductionReport(models.TransientModel):
    _name = "wt.weighing.production.report"
    _description = "Weighing Production Report"

    name = fields.Char(
        string="Report",
        default="Laporan Penimbangan Produksi",
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
    production_date = fields.Date(
        string="Tanggal Produksi",
        readonly=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Divisi",
        readonly=True,
    )
    weather_display = fields.Char(
        string="Cuaca",
        default="-",
        readonly=True,
    )
    total_field_weight = fields.Float(
        string="Total Timbangan Lapangan",
        readonly=True,
    )
    total_warehouse_weight = fields.Float(
        string="Total Timbangan Gudang",
        readonly=True,
    )
    total_reject_weight = fields.Float(
        string="Total Reject",
        readonly=True,
    )
    total_slab_weight = fields.Float(
        string="Total Slab",
        readonly=True,
    )
    total_net_weight = fields.Float(
        string="Total Cup Lump Bersih",
        readonly=True,
    )
    total_bag = fields.Integer(
        string="Total Karung",
        readonly=True,
    )
    total_shrinkage = fields.Float(
        string="Total Susut",
        readonly=True,
    )
    line_ids = fields.One2many(
        "wt.weighing.production.report.line",
        "report_id",
        string="Lines",
        readonly=True,
    )

    def action_open_filter(self):
        self.ensure_one()
        return {
            "name": _("Filter Laporan Penimbangan Produksi"),
            "type": "ir.actions.act_window",
            "res_model": "wt.weighing.production.report.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_report_id": self.id,
                "default_company_id": self.company_id.id or self.env.company.id,
                "default_production_date": self.production_date
                or fields.Date.context_today(self),
                "default_division_id": self.division_id.id,
            },
        }

    def action_print_pdf(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Please apply a filter before printing the report."))
        return self.env.ref(
            "weightrack.action_report_weighing_production_pdf"
        ).report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Please apply a filter before exporting the report."))
        if xlsxwriter is None:
            raise ValidationError(_("The xlsxwriter Python package is not installed."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Laporan Penimbangan")

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

        sheet.merge_range("A1:L1", self.company_id.name or "", title_format)
        sheet.merge_range("A2:L2", "LAPORAN PENIMBANGAN PRODUKSI", title_format)
        sheet.write("A4", "Divisi", label_format)
        sheet.write("B4", self.division_id.display_name or "")
        sheet.write("A5", "Tanggal Produksi", label_format)
        sheet.write("B5", str(self.production_date or ""))
        sheet.write("A6", "Cuaca", label_format)
        sheet.write("B6", self.weather_display or "-")

        headers = [
            "No",
            "Nama Tapper",
            "Mandor",
            "Timbangan Lapangan",
            "Timbangan Gudang",
            "Reject",
            "Slab",
            "Cup Lump Bersih",
            "Jml. Karung",
            "Susut",
            "Susut %",
            "Keterangan",
        ]
        widths = [6, 22, 20, 16, 16, 12, 12, 16, 12, 12, 10, 24]
        for column, width in enumerate(widths):
            sheet.set_column(column, column, width)
        for column, header in enumerate(headers):
            sheet.write(8, column, header, header_format)

        row_index = 9
        for line in self.line_ids:
            sheet.write(row_index, 0, line.sequence, integer_format)
            sheet.write(row_index, 1, line.tapper_name or "", text_format)
            sheet.write(row_index, 2, line.foreman_name or "", text_format)
            sheet.write(row_index, 3, line.field_weight, number_format)
            sheet.write(row_index, 4, line.warehouse_weight, number_format)
            sheet.write(row_index, 5, line.reject_weight, number_format)
            sheet.write(row_index, 6, line.slab_weight, number_format)
            sheet.write(row_index, 7, line.net_weight, number_format)
            sheet.write(row_index, 8, line.total_bag, integer_format)
            sheet.write(row_index, 9, line.shrinkage_weight, number_format)
            sheet.write(row_index, 10, line.shrinkage_percentage, number_format)
            sheet.write(row_index, 11, line.note or "", text_format)
            row_index += 1

        sheet.merge_range(row_index, 0, row_index, 2, "Total", total_label_format)
        sheet.write(row_index, 3, self.total_field_weight, total_number_format)
        sheet.write(row_index, 4, self.total_warehouse_weight, total_number_format)
        sheet.write(row_index, 5, self.total_reject_weight, total_number_format)
        sheet.write(row_index, 6, self.total_slab_weight, total_number_format)
        sheet.write(row_index, 7, self.total_net_weight, total_number_format)
        sheet.write(row_index, 8, self.total_bag, total_integer_format)
        sheet.write(row_index, 9, self.total_shrinkage, total_number_format)
        sheet.write(row_index, 10, "", total_label_format)
        sheet.write(row_index, 11, "", total_label_format)

        workbook.close()
        output.seek(0)
        filename = "Laporan Penimbangan Produksi - %s.xlsx" % (
            self.production_date or ""
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
            "name": _("Laporan Penimbangan Produksi"),
            "type": "ir.actions.act_window",
            "res_model": "wt.weighing.production.report",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }


class WeighingProductionReportLine(models.TransientModel):
    _name = "wt.weighing.production.report.line"
    _description = "Weighing Production Report Line"
    _order = "sequence, id"

    report_id = fields.Many2one(
        "wt.weighing.production.report",
        string="Report",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(
        string="No",
        readonly=True,
    )
    tapper_name = fields.Char(
        string="Nama Tapper",
        readonly=True,
    )
    foreman_name = fields.Char(
        string="Mandor",
        readonly=True,
    )
    field_weight = fields.Float(
        string="Timbangan Lapangan",
        readonly=True,
    )
    warehouse_weight = fields.Float(
        string="Timbangan Gudang",
        readonly=True,
    )
    reject_weight = fields.Float(
        string="Reject",
        readonly=True,
    )
    slab_weight = fields.Float(
        string="Slab",
        readonly=True,
    )
    net_weight = fields.Float(
        string="Cup Lump Bersih",
        readonly=True,
    )
    total_bag = fields.Integer(
        string="Jml. Karung",
        readonly=True,
    )
    shrinkage_weight = fields.Float(
        string="Susut",
        readonly=True,
    )
    shrinkage_percentage = fields.Float(
        string="Susut %",
        readonly=True,
    )
    note = fields.Char(
        string="Keterangan",
        readonly=True,
    )


class WeighingProductionReportWizard(models.TransientModel):
    _name = "wt.weighing.production.report.wizard"
    _description = "Weighing Production Report Wizard"

    report_id = fields.Many2one(
        "wt.weighing.production.report",
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
    production_date = fields.Date(
        string="Tanggal Produksi",
        required=True,
        default=fields.Date.context_today,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Divisi",
        required=True,
        domain="[('company_id', '=', company_id)]",
    )

    @api.onchange("company_id")
    def _onchange_company_id(self):
        self.division_id = False

    def _get_domain(self):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("production_date", "=", self.production_date),
            ("division_id", "=", self.division_id.id),
        ]
        return domain

    def _get_weighing_records(self):
        self.ensure_one()
        return self.env["wt.weighing"].search(
            self._get_domain(),
            order="foreman_employee_id, tapper_employee_id, id",
        )

    def _get_weather_display(self):
        self.ensure_one()
        estate = self.division_id.estate_id
        if not estate:
            return "-"
        weather_data = self.env["wt.weather.data"].search(
            [
                ("estate_id", "=", estate.id),
                ("weather_date", "=", self.production_date),
            ],
            limit=1,
        )
        return weather_data.weather_id.name or "-"

    def _prepare_report_data(self):
        self.ensure_one()
        records = self._get_weighing_records()
        rows = []
        total_field_weight = 0.0
        total_warehouse_weight = 0.0
        total_reject_weight = 0.0
        total_slab_weight = 0.0
        total_net_weight = 0.0
        total_bag = 0
        total_shrinkage = 0.0
        for number, record in enumerate(records, start=1):
            field_weight = record.initial_weight or 0.0
            warehouse_weight = record.production_weight or 0.0
            reject_weight = record.reject_weight or 0.0
            slab_weight = record.slab_weight or 0.0
            net_weight = record.net_weight or 0.0
            shrinkage_weight = (
                field_weight - warehouse_weight if field_weight else 0.0
            )
            shrinkage_percentage = (
                (shrinkage_weight / field_weight * 100.0) if field_weight else 0.0
            )
            rows.append(
                {
                    "number": number,
                    "tapper": record.tapper_employee_id.name or "",
                    "foreman": record.foreman_employee_id.name or "",
                    "field_weight": field_weight,
                    "warehouse_weight": warehouse_weight,
                    "reject_weight": reject_weight,
                    "slab_weight": slab_weight,
                    "net_weight": net_weight,
                    "total_bag": record.total_bag or 0,
                    "shrinkage_weight": shrinkage_weight,
                    "shrinkage_percentage": shrinkage_percentage,
                    "note": record.note or "",
                }
            )
            total_field_weight += field_weight
            total_warehouse_weight += warehouse_weight
            total_reject_weight += reject_weight
            total_slab_weight += slab_weight
            total_net_weight += net_weight
            total_bag += record.total_bag or 0
            total_shrinkage += shrinkage_weight
        return {
            "records": records,
            "rows": rows,
            "total_field_weight": total_field_weight,
            "total_warehouse_weight": total_warehouse_weight,
            "total_reject_weight": total_reject_weight,
            "total_slab_weight": total_slab_weight,
            "total_net_weight": total_net_weight,
            "total_bag": total_bag,
            "total_shrinkage": total_shrinkage,
            "uom_name": records[:1].uom_id.name if records else "",
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
                "production_date": self.production_date,
                "division_id": self.division_id.id,
                "weather_display": self._get_weather_display(),
                "total_field_weight": data["total_field_weight"],
                "total_warehouse_weight": data["total_warehouse_weight"],
                "total_reject_weight": data["total_reject_weight"],
                "total_slab_weight": data["total_slab_weight"],
                "total_net_weight": data["total_net_weight"],
                "total_bag": data["total_bag"],
                "total_shrinkage": data["total_shrinkage"],
            }
        )
        line_vals = [
            {
                "report_id": report.id,
                "sequence": row["number"],
                "tapper_name": row["tapper"],
                "foreman_name": row["foreman"],
                "field_weight": row["field_weight"],
                "warehouse_weight": row["warehouse_weight"],
                "reject_weight": row["reject_weight"],
                "slab_weight": row["slab_weight"],
                "net_weight": row["net_weight"],
                "total_bag": row["total_bag"],
                "shrinkage_weight": row["shrinkage_weight"],
                "shrinkage_percentage": row["shrinkage_percentage"],
                "note": row["note"],
            }
            for row in data["rows"]
        ]
        if line_vals:
            self.env["wt.weighing.production.report.line"].create(line_vals)
        return report._open_current_report_action()


class ReportWeighingProduction(models.AbstractModel):
    _name = "report.weightrack.report_weighing_production_document"
    _description = "Weighing Production Report"

    def _get_report_values(self, docids, data=None):
        docs = self.env["wt.weighing.production.report"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "wt.weighing.production.report",
            "docs": docs,
        }
