# -*- coding: utf-8 -*-

import base64
import io
import re
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


REPORT_LEVELS = [
    ("division", "Division"),
    ("foreman", "Foreman"),
]


class ProductionSummaryReport(models.TransientModel):
    _name = "wt.production.summary.report"
    _description = "Production Total Summary Report"

    name = fields.Char(string="Report", readonly=True)
    report_level = fields.Selection(
        REPORT_LEVELS,
        string="Report Level",
        required=True,
        readonly=True,
    )
    is_filtered = fields.Boolean(string="Filtered", default=False, readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    date_start = fields.Date(string="Start Date", readonly=True)
    date_end = fields.Date(string="End Date", readonly=True)
    estate_id = fields.Many2one("wt.estate", string="Estate", readonly=True)
    division_id = fields.Many2one("wt.division", string="Division", readonly=True)
    foreman_id = fields.Many2one("wt.foreman", string="Foreman", readonly=True)
    total_production = fields.Float(string="Total Production", readonly=True)
    preview_html = fields.Html(
        string="Preview",
        readonly=True,
        sanitize=False,
    )
    date_column_ids = fields.One2many(
        "wt.production.summary.report.date",
        "report_id",
        string="Production Dates",
        readonly=True,
    )
    line_ids = fields.One2many(
        "wt.production.summary.report.line",
        "report_id",
        string="Lines",
        readonly=True,
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        level = values.get("report_level") or self.env.context.get(
            "default_report_level", "division"
        )
        values["report_level"] = level
        values.setdefault("name", self._get_level_title(level))
        return values

    @api.model
    def _get_level_title(self, level):
        if level == "foreman":
            return _("Foreman Production Total Report")
        return _("Division Production Total Report")

    def action_open_filter(self):
        self.ensure_one()
        return {
            "name": _("Filter %s") % self._get_level_title(self.report_level),
            "type": "ir.actions.act_window",
            "res_model": "wt.production.summary.report.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_report_id": self.id,
                "default_report_level": self.report_level,
                "default_company_id": self.company_id.id or self.env.company.id,
                "default_date_start": self.date_start
                or fields.Date.start_of(fields.Date.context_today(self), "month"),
                "default_date_end": self.date_end
                or fields.Date.context_today(self),
                "default_estate_id": self.estate_id.id,
                "default_division_id": self.division_id.id,
                "default_foreman_id": self.foreman_id.id,
            },
        }

    def action_print_pdf(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Please apply a filter before printing the report."))
        return self.env.ref(
            "weightrack.action_report_production_summary_pdf"
        ).report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Please apply a filter before exporting the report."))
        if xlsxwriter is None:
            raise ValidationError(_("The xlsxwriter Python package is not installed."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet(
            "Produksi Divisi" if self.report_level == "division" else "Produksi Mandor"
        )
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
                "bg_color": "#E2E8F0",
            }
        )
        text_format = workbook.add_format({"border": 1, "valign": "vcenter"})
        center_format = workbook.add_format(
            {"border": 1, "align": "center", "valign": "vcenter"}
        )
        number_format = workbook.add_format(
            {"border": 1, "num_format": "#,##0.00", "valign": "vcenter"}
        )
        total_label_format = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "align": "right",
                "valign": "vcenter",
                "bg_color": "#F8FAFC",
            }
        )
        total_number_format = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "num_format": "#,##0.00",
                "valign": "vcenter",
                "bg_color": "#F8FAFC",
            }
        )

        date_columns = self.date_column_ids.sorted("sequence")
        static_headers = self._get_static_headers()
        first_date_column = len(static_headers)
        last_date_column = first_date_column + len(date_columns) - 1
        total_column = last_date_column + 1

        sheet.merge_range(
            0, 0, 0, total_column, self.company_id.name or "", title_format
        )
        sheet.merge_range(
            1,
            0,
            1,
            total_column,
            self._get_level_title(self.report_level).upper(),
            title_format,
        )
        sheet.write(3, 0, _("Date Range"), label_format)
        sheet.write(
            3,
            1,
            "%s - %s"
            % (
                self.date_start.strftime("%d/%m/%Y"),
                self.date_end.strftime("%d/%m/%Y"),
            ),
        )
        sheet.write(4, 0, _("Estate"), label_format)
        sheet.write(4, 1, self.estate_id.display_name or _("All"))
        sheet.write(4, 3, _("Division"), label_format)
        sheet.write(4, 4, self.division_id.display_name or _("All"))
        if self.report_level == "foreman":
            sheet.write(5, 0, _("Foreman"), label_format)
            sheet.write(5, 1, self.foreman_id.display_name or _("All"))

        header_row = 7
        for column, header in enumerate(static_headers):
            sheet.merge_range(
                header_row,
                column,
                header_row + 1,
                column,
                header,
                header_format,
            )
        if len(date_columns) == 1:
            sheet.write(header_row, first_date_column, _("Production"), header_format)
        else:
            sheet.merge_range(
                header_row,
                first_date_column,
                header_row,
                last_date_column,
                _("Production"),
                header_format,
            )
        for offset, date_column in enumerate(date_columns):
            sheet.write(
                header_row + 1,
                first_date_column + offset,
                date_column.production_date.strftime("%d/%m/%Y"),
                header_format,
            )
        sheet.merge_range(
            header_row,
            total_column,
            header_row + 1,
            total_column,
            _("Total Production"),
            header_format,
        )

        sheet.set_column(0, 0, 6)
        if self.report_level == "division":
            sheet.set_column(1, 2, 22)
        else:
            sheet.set_column(1, 1, 16)
            sheet.set_column(2, 2, 24)
            sheet.set_column(3, 3, 18)
        sheet.set_column(first_date_column, last_date_column, 13)
        sheet.set_column(total_column, total_column, 16)
        sheet.freeze_panes(header_row + 2, first_date_column)

        row_index = header_row + 2
        for line in self.line_ids.sorted("sequence"):
            values = line.get_static_values(self.report_level)
            for column, value in enumerate(values):
                cell_format = center_format if column == 0 else text_format
                sheet.write(row_index, column, value, cell_format)
            for offset, date_column in enumerate(date_columns):
                sheet.write(
                    row_index,
                    first_date_column + offset,
                    line.get_daily_production(date_column.production_date),
                    number_format,
                )
            sheet.write(
                row_index,
                total_column,
                line.total_production,
                number_format,
            )
            row_index += 1

        sheet.merge_range(
            row_index,
            0,
            row_index,
            first_date_column - 1,
            _("Total Production"),
            total_label_format,
        )
        for offset, date_column in enumerate(date_columns):
            sheet.write(
                row_index,
                first_date_column + offset,
                date_column.total_production,
                total_number_format,
            )
        sheet.write(
            row_index,
            total_column,
            self.total_production,
            total_number_format,
        )
        workbook.close()
        output.seek(0)

        filename = "%s - %s - %s.xlsx" % (
            self._get_level_title(self.report_level),
            self.date_start,
            self.date_end,
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

    def _get_static_headers(self):
        self.ensure_one()
        if self.report_level == "foreman":
            return [_("No."), _("Badge Number"), _("Foreman"), _("Division")]
        return [_("No."), _("Estate"), _("Division")]

    def _open_current_report_action(self):
        self.ensure_one()
        xmlid = (
            "weightrack.action_wt_foreman_production_total_report"
            if self.report_level == "foreman"
            else "weightrack.action_wt_division_production_total_report"
        )
        action = self.env["ir.actions.actions"]._for_xml_id(xmlid)
        action["res_id"] = self.id
        return action

    def get_date_chunks(self, chunk_size=7):
        self.ensure_one()
        dates = self.date_column_ids.sorted("sequence")
        return [
            dates[index : index + chunk_size]
            for index in range(0, len(dates), chunk_size)
        ]

    def _build_preview_html(self):
        self.ensure_one()
        date_columns = self.date_column_ids.sorted("sequence")
        lines = self.line_ids.sorted("sequence")
        static_headers = self._get_static_headers()
        parts = [
            '<div style="overflow-x:auto;width:100%;">',
            '<table style="border-collapse:collapse;min-width:900px;width:100%;">',
            "<thead><tr>",
        ]
        for header in static_headers:
            parts.append(
                '<th rowspan="2" style="background:#e2e8f0;border:1px solid #94a3b8;'
                'padding:7px;text-align:center;vertical-align:middle;white-space:nowrap;">%s</th>'
                % escape(header)
            )
        parts.append(
            '<th colspan="%s" style="background:#e2e8f0;border:1px solid #94a3b8;'
            'padding:7px;text-align:center;">%s</th>'
            % (len(date_columns), escape(_("Production")))
        )
        parts.append(
            '<th rowspan="2" style="background:#e2e8f0;border:1px solid #94a3b8;'
            'padding:7px;text-align:center;vertical-align:middle;white-space:nowrap;">%s</th>'
            % escape(_("Total Production"))
        )
        parts.extend(["</tr><tr>"])
        for date_column in date_columns:
            parts.append(
                '<th style="background:#f1f5f9;border:1px solid #94a3b8;'
                'padding:7px;text-align:center;white-space:nowrap;">%s</th>'
                % date_column.production_date.strftime("%d/%m/%Y")
            )
        parts.extend(["</tr></thead><tbody>"])
        if not lines:
            parts.append(
                '<tr><td colspan="%s" style="border:1px solid #cbd5e1;'
                'padding:12px;text-align:center;">%s</td></tr>'
                % (len(date_columns) + len(static_headers) + 1,
                   escape(_("No weighing data found.")))
            )
        for line in lines:
            parts.append("<tr>")
            for index, value in enumerate(line.get_static_values(self.report_level)):
                parts.append(
                    '<td style="border:1px solid #cbd5e1;padding:7px;'
                    'text-align:%s;white-space:nowrap;">%s</td>'
                    % ("center" if index == 0 else "left", escape(value))
                )
            for date_column in date_columns:
                parts.append(
                    '<td style="border:1px solid #cbd5e1;padding:7px;'
                    'text-align:right;white-space:nowrap;">%s</td>'
                    % self._format_weight(
                        line.get_daily_production(date_column.production_date)
                    )
                )
            parts.append(
                '<td style="border:1px solid #cbd5e1;padding:7px;'
                'font-weight:700;text-align:right;white-space:nowrap;">%s</td>'
                % self._format_weight(line.total_production)
            )
            parts.append("</tr>")
        parts.append("<tr>")
        parts.append(
            '<td colspan="%s" style="background:#f8fafc;border:1px solid #94a3b8;'
            'font-weight:700;padding:7px;text-align:right;">%s</td>'
            % (len(static_headers), escape(_("Total Production")))
        )
        for date_column in date_columns:
            parts.append(
                '<td style="background:#f8fafc;border:1px solid #94a3b8;'
                'font-weight:700;padding:7px;text-align:right;white-space:nowrap;">%s</td>'
                % self._format_weight(date_column.total_production)
            )
        parts.append(
            '<td style="background:#f8fafc;border:1px solid #94a3b8;'
            'font-weight:700;padding:7px;text-align:right;white-space:nowrap;">%s</td>'
            % self._format_weight(self.total_production)
        )
        parts.extend(["</tr></tbody></table></div>"])
        return Markup("".join(parts))

    @staticmethod
    def _format_weight(value):
        return "{:,.2f}".format(value or 0.0)


class ProductionSummaryReportDate(models.TransientModel):
    _name = "wt.production.summary.report.date"
    _description = "Production Total Summary Report Date"
    _order = "sequence, production_date"

    report_id = fields.Many2one(
        "wt.production.summary.report",
        string="Report",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="Sequence", readonly=True)
    production_date = fields.Date(string="Production Date", readonly=True)
    total_production = fields.Float(string="Total Production", readonly=True)


class ProductionSummaryReportLine(models.TransientModel):
    _name = "wt.production.summary.report.line"
    _description = "Production Total Summary Report Line"
    _order = "sequence, id"

    report_id = fields.Many2one(
        "wt.production.summary.report",
        string="Report",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="No.", readonly=True)
    badge_number = fields.Char(string="Badge Number", readonly=True)
    estate_name = fields.Char(string="Estate", readonly=True)
    estate_code = fields.Char(string="Estate Code", readonly=True)
    division_name = fields.Char(string="Division", readonly=True)
    division_code = fields.Char(string="Division Code", readonly=True)
    foreman_name = fields.Char(string="Foreman", readonly=True)
    daily_production = fields.Json(string="Daily Production", readonly=True)
    total_production = fields.Float(string="Total Production", readonly=True)

    def get_static_values(self, report_level):
        self.ensure_one()
        if report_level == "foreman":
            return [
                self.sequence,
                self.badge_number or "",
                self.foreman_name or "",
                self.division_name or "",
            ]
        return [
            self.sequence,
            self.estate_name or "",
            self.division_name or "",
        ]

    def get_daily_production(self, production_date):
        self.ensure_one()
        date_value = fields.Date.to_date(production_date)
        return (self.daily_production or {}).get(date_value.isoformat(), 0.0)


class ProductionSummaryReportWizard(models.TransientModel):
    _name = "wt.production.summary.report.wizard"
    _description = "Production Total Summary Report Wizard"

    report_id = fields.Many2one(
        "wt.production.summary.report",
        string="Report",
        required=True,
        ondelete="cascade",
    )
    report_level = fields.Selection(
        REPORT_LEVELS,
        string="Report Level",
        required=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    date_start = fields.Date(
        string="Start Date",
        required=True,
        default=lambda self: fields.Date.start_of(
            fields.Date.context_today(self), "month"
        ),
    )
    date_end = fields.Date(
        string="End Date",
        required=True,
        default=fields.Date.context_today,
    )
    estate_id = fields.Many2one(
        "wt.estate",
        string="Estate",
        domain="[('company_id', '=', company_id)]",
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Division",
        domain="[('company_id', '=', company_id), ('estate_id', '=?', estate_id)]",
    )
    foreman_id = fields.Many2one(
        "wt.foreman",
        string="Foreman",
        domain=(
            "[('company_id', '=', company_id), "
            "('division_id', '=?', division_id), "
            "('division_id.estate_id', '=?', estate_id)]"
        ),
    )

    @api.onchange("company_id")
    def _onchange_company_id(self):
        self.estate_id = False
        self.division_id = False
        self.foreman_id = False

    @api.onchange("estate_id")
    def _onchange_estate_id(self):
        if self.division_id and self.division_id.estate_id != self.estate_id:
            self.division_id = False
        if self.foreman_id and self.foreman_id.division_id.estate_id != self.estate_id:
            self.foreman_id = False

    @api.onchange("division_id")
    def _onchange_division_id(self):
        if self.foreman_id and self.foreman_id.division_id != self.division_id:
            self.foreman_id = False

    @api.onchange("foreman_id")
    def _onchange_foreman_id(self):
        if self.foreman_id:
            self.estate_id = self.foreman_id.division_id.estate_id
            self.division_id = self.foreman_id.division_id

    def _get_domain(self):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("production_date", ">=", self.date_start),
            ("production_date", "<=", self.date_end),
        ]
        if self.estate_id:
            domain.append(("estate_id", "=", self.estate_id.id))
        if self.division_id:
            domain.append(("division_id", "=", self.division_id.id))
        if self.report_level == "foreman" and self.foreman_id:
            domain.append(
                ("foreman_employee_id", "=", self.foreman_id.employee_id.id)
            )
        return domain

    def _prepare_report_data(self):
        self.ensure_one()
        if self.date_start > self.date_end:
            raise ValidationError(_("Start Date cannot be later than End Date."))
        date_values = []
        current_date = self.date_start
        while current_date <= self.date_end:
            date_values.append(current_date)
            current_date += timedelta(days=1)

        grouped = {}
        date_totals = {date_value.isoformat(): 0.0 for date_value in date_values}
        records = self.env["wt.weighing"].search(self._get_domain())
        for record in records:
            production_date = record.production_date.isoformat()
            production_weight = record.production_weight or 0.0
            if self.report_level == "foreman":
                group_key = (
                    record.division_id.id or 0,
                    record.foreman_employee_id.id or 0,
                )
            else:
                group_key = (record.estate_id.id or 0, record.division_id.id or 0)
            row = grouped.setdefault(
                group_key,
                {
                    "badge_number": (
                        record.foreman_barcode or ""
                        if self.report_level == "foreman"
                        else ""
                    ),
                    "estate_name": record.estate_id.name or "",
                    "estate_code": record.estate_id.code or "",
                    "division_name": record.division_id.name or "",
                    "division_code": record.division_id.code or "",
                    "foreman_name": (
                        record.foreman_employee_id.name or ""
                        if self.report_level == "foreman"
                        else ""
                    ),
                    "daily_production": {
                        date_value.isoformat(): 0.0 for date_value in date_values
                    },
                    "total_production": 0.0,
                },
            )
            row["daily_production"][production_date] += production_weight
            row["total_production"] += production_weight
            date_totals[production_date] += production_weight

        rows = sorted(
            grouped.values(),
            key=lambda row: (
                self._natural_sort_key(row["division_code"]),
                self._natural_sort_key(row["estate_code"]),
                (row["foreman_name"] or "").casefold(),
            ),
        )
        for number, row in enumerate(rows, start=1):
            row["sequence"] = number
        return {
            "dates": date_values,
            "date_totals": date_totals,
            "rows": rows,
            "total_production": sum(date_totals.values()),
        }

    @staticmethod
    def _natural_sort_key(value):
        return tuple(
            int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", value or "")
        )

    def action_apply_filter(self):
        self.ensure_one()
        data = self._prepare_report_data()
        report = self.report_id
        report.date_column_ids.unlink()
        report.line_ids.unlink()
        report.write(
            {
                "name": report._get_level_title(self.report_level),
                "report_level": self.report_level,
                "is_filtered": True,
                "company_id": self.company_id.id,
                "date_start": self.date_start,
                "date_end": self.date_end,
                "estate_id": self.estate_id.id,
                "division_id": self.division_id.id,
                "foreman_id": (
                    self.foreman_id.id if self.report_level == "foreman" else False
                ),
                "total_production": data["total_production"],
                "preview_html": False,
            }
        )
        self.env["wt.production.summary.report.date"].create(
            [
                {
                    "report_id": report.id,
                    "sequence": sequence,
                    "production_date": production_date,
                    "total_production": data["date_totals"][
                        production_date.isoformat()
                    ],
                }
                for sequence, production_date in enumerate(data["dates"], start=1)
            ]
        )
        if data["rows"]:
            self.env["wt.production.summary.report.line"].create(
                [
                    {
                        "report_id": report.id,
                        "sequence": row["sequence"],
                        "badge_number": row["badge_number"],
                        "estate_name": row["estate_name"],
                        "estate_code": row["estate_code"],
                        "division_name": row["division_name"],
                        "division_code": row["division_code"],
                        "foreman_name": row["foreman_name"],
                        "daily_production": row["daily_production"],
                        "total_production": row["total_production"],
                    }
                    for row in data["rows"]
                ]
            )
        report.preview_html = report._build_preview_html()
        return report._open_current_report_action()


class ReportProductionSummary(models.AbstractModel):
    _name = "report.weightrack.report_production_summary_document"
    _description = "Production Total Summary Report"

    def _get_report_values(self, docids, data=None):
        docs = self.env["wt.production.summary.report"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "wt.production.summary.report",
            "docs": docs,
        }
