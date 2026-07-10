# -*- coding: utf-8 -*-

import base64
import io

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class WeighingRejectSlabReport(models.TransientModel):
    _name = "wt.weighing.reject.slab.report"
    _description = "Weighing Reject and Slab Report"

    name = fields.Char(
        string="Report",
        default="Laporan Reject dan Slab",
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

    total_reject_weight = fields.Float(
        string="Total Reject",
        readonly=True,
    )
    total_slab_weight = fields.Float(
        string="Total Slab",
        readonly=True,
    )
    line_ids = fields.One2many(
        "wt.weighing.reject.slab.report.line",
        "report_id",
        string="Lines",
        readonly=True,
    )

    def action_open_filter(self):
        self.ensure_one()
        return {
            "name": _("Filter Laporan Reject dan Slab"),
            "type": "ir.actions.act_window",
            "res_model": "wt.weighing.reject.slab.report.wizard",
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
            "weightrack.action_report_weighing_reject_slab_pdf"
        ).report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Please apply a filter before exporting the report."))
        if xlsxwriter is None:
            raise ValidationError(_("The xlsxwriter Python package is not installed."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Laporan Reject dan Slab")

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
        integer_format = workbook.add_format({"border": 1, "num_format": "#,##0"})
        number_format = workbook.add_format({"border": 1, "num_format": "#,##0.00"})
        total_label_format = workbook.add_format(
            {"bold": True, "align": "center", "border": 1}
        )
        total_number_format = workbook.add_format(
            {"bold": True, "border": 1, "num_format": "#,##0.00"}
        )

        sheet.merge_range("A1:G1", self.company_id.name or "", title_format)
        sheet.merge_range("A2:G2", "LAPORAN REJECT DAN SLAB", title_format)

        sheet.write("A4", "Rentang Tanggal", label_format)
        sheet.write("B4", f"{self.start_date or ''} s/d {self.end_date or ''}")
        sheet.write("A5", "Estate", label_format)
        sheet.write("B5", self.estate_id.display_name if self.estate_id else "-")
        sheet.write("A6", "Divisi", label_format)
        sheet.write("B6", self.division_id.display_name if self.division_id else "Semua Divisi")
        sheet.write("A7", "Mandor", label_format)
        sheet.write("B7", self.foreman_id.display_name if self.foreman_id else "Semua Mandor")
        sheet.write("A8", "Tapper", label_format)
        sheet.write("B8", self.tapper_id.display_name if self.tapper_id else "Semua Tapper")

        headers = [
            "No",
            "Estate",
            "Divisi",
            "Mandor",
            "Tapper",
            "Total Reject",
            "Total Slab",
        ]
        widths = [6, 20, 20, 25, 25, 18, 18]
        for column, width in enumerate(widths):
            sheet.set_column(column, column, width)

        header_row = 10
        for column, header in enumerate(headers):
            sheet.write(header_row, column, header, header_format)

        row_index = header_row + 1
        for line in self.line_ids:
            sheet.write(row_index, 0, line.sequence, integer_format)
            sheet.write(row_index, 1, line.estate_name or "", text_format)
            sheet.write(row_index, 2, line.division_name or "", text_format)
            sheet.write(row_index, 3, line.foreman_name or "", text_format)
            sheet.write(row_index, 4, line.tapper_name or "", text_format)
            sheet.write(row_index, 5, line.total_reject, number_format)
            sheet.write(row_index, 6, line.total_slab, number_format)
            row_index += 1

        sheet.merge_range(row_index, 0, row_index, 4, "Total", total_label_format)
        sheet.write(row_index, 5, self.total_reject_weight, total_number_format)
        sheet.write(row_index, 6, self.total_slab_weight, total_number_format)

        workbook.close()
        output.seek(0)
        filename = f"Laporan Reject dan Slab - {self.start_date} sd {self.end_date}.xlsx"
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
            "name": _("Laporan Reject dan Slab"),
            "type": "ir.actions.act_window",
            "res_model": "wt.weighing.reject.slab.report",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }


class WeighingRejectSlabReportLine(models.TransientModel):
    _name = "wt.weighing.reject.slab.report.line"
    _description = "Weighing Reject and Slab Report Line"
    _order = "sequence, id"

    report_id = fields.Many2one(
        "wt.weighing.reject.slab.report",
        string="Report",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(
        string="No",
        readonly=True,
    )
    estate_name = fields.Char(
        string="Estate",
        readonly=True,
    )
    division_name = fields.Char(
        string="Divisi",
        readonly=True,
    )
    foreman_name = fields.Char(
        string="Mandor",
        readonly=True,
    )
    tapper_name = fields.Char(
        string="Tapper",
        readonly=True,
    )
    total_reject = fields.Float(
        string="Total Reject",
        readonly=True,
    )
    total_slab = fields.Float(
        string="Total Slab",
        readonly=True,
    )


class WeighingRejectSlabReportWizard(models.TransientModel):
    _name = "wt.weighing.reject.slab.report.wizard"
    _description = "Weighing Reject and Slab Report Wizard"

    report_id = fields.Many2one(
        "wt.weighing.reject.slab.report",
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
        required=True,
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
        if not self.estate_id:
            raise ValidationError(_("Estate wajib diisi."))
        domain = [
            ("company_id", "=", self.company_id.id),
            ("production_date", ">=", self.start_date),
            ("production_date", "<=", self.end_date),
            ("estate_id", "=", self.estate_id.id),
            ("state", "=", "receipt_validated"),
        ]
        if self.division_id:
            domain.append(("division_id", "=", self.division_id.id))
        if self.foreman_id:
            domain.append(("foreman_id", "=", self.foreman_id.id))
        if self.tapper_id:
            domain.append(("tapper_id", "=", self.tapper_id.id))
        return domain

    def _prepare_report_data(self):
        self.ensure_one()
        records = self.env["wt.weighing"].search(self._get_domain())
        groups = {}
        total_reject = 0.0
        total_slab = 0.0

        for record in records:
            est_name = record.estate_id.name or "-"
            div_name = record.division_id.name or "-"
            foreman_name = record.foreman_name or (record.foreman_id.name if record.foreman_id else "") or "-"
            tapper_name = record.tapper_name or (record.tapper_id.name if record.tapper_id else "") or "-"
            key = (est_name, div_name, foreman_name, tapper_name)
            if key not in groups:
                groups[key] = {"reject": 0.0, "slab": 0.0}
            groups[key]["reject"] += record.reject_weight or 0.0
            groups[key]["slab"] += record.slab_weight or 0.0

        sorted_keys = sorted(groups.keys(), key=lambda k: (k[0], k[1], k[2], k[3]))
        rows = []
        for number, key in enumerate(sorted_keys, start=1):
            rej_w = groups[key]["reject"]
            slab_w = groups[key]["slab"]
            rows.append(
                {
                    "number": number,
                    "estate_name": key[0],
                    "division_name": key[1],
                    "foreman_name": key[2],
                    "tapper_name": key[3],
                    "total_reject": rej_w,
                    "total_slab": slab_w,
                }
            )
            total_reject += rej_w
            total_slab += slab_w

        return {
            "rows": rows,
            "total_reject_weight": total_reject,
            "total_slab_weight": total_slab,
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
                "total_reject_weight": data["total_reject_weight"],
                "total_slab_weight": data["total_slab_weight"],
            }
        )
        line_vals = [
            {
                "report_id": report.id,
                "sequence": row["number"],
                "estate_name": row["estate_name"],
                "division_name": row["division_name"],
                "foreman_name": row["foreman_name"],
                "tapper_name": row["tapper_name"],
                "total_reject": row["total_reject"],
                "total_slab": row["total_slab"],
            }
            for row in data["rows"]
        ]
        if line_vals:
            self.env["wt.weighing.reject.slab.report.line"].create(line_vals)
        return report._open_current_report_action()


class ReportWeighingRejectSlab(models.AbstractModel):
    _name = "report.weightrack.report_weighing_reject_slab_doc"
    _description = "Weighing Reject and Slab Report Document"

    def _get_report_values(self, docids, data=None):
        docs = self.env["wt.weighing.reject.slab.report"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "wt.weighing.reject.slab.report",
            "docs": docs,
        }
