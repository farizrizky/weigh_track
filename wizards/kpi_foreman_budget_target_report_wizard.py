# -*- coding: utf-8 -*-

import base64
import io
import re
from collections import OrderedDict
from datetime import date

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


MONTH_FIELDS = (
    ("january", "Januari"),
    ("february", "Februari"),
    ("march", "Maret"),
    ("april", "April"),
    ("may", "Mei"),
    ("june", "Juni"),
    ("july", "Juli"),
    ("august", "Agustus"),
    ("september", "September"),
    ("october", "Oktober"),
    ("november", "November"),
    ("december", "Desember"),
)


class KpiForemanBudgetTargetReport(models.TransientModel):
    _name = "wt.kpi.foreman.budget.target.report"
    _description = "Laporan Budget Target Mandor"

    name = fields.Char(
        string="Laporan",
        default="Laporan Budget Target Mandor",
        readonly=True,
    )
    is_filtered = fields.Boolean(
        string="Sudah Difilter",
        default=False,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        readonly=True,
    )
    year = fields.Integer(string="Tahun", readonly=True)
    year_display = fields.Char(string="Tahun", readonly=True)
    estate_id = fields.Many2one(
        "wt.estate",
        string="Estate",
        readonly=True,
    )
    budget_mandor_id = fields.Many2one(
        "wt.kpi.foreman.budget.target",
        string="Budget Target Mandor",
        readonly=True,
    )
    preview_html = fields.Html(
        string="Preview",
        readonly=True,
        sanitize=False,
    )

    def action_open_filter(self):
        self.ensure_one()
        return {
            "name": _("Filter Laporan Budget Target Mandor"),
            "type": "ir.actions.act_window",
            "res_model": "wt.kpi.foreman.budget.target.report.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_report_id": self.id,
                "default_company_id": self.company_id.id or self.env.company.id,
                "default_year": str(
                    self.year or fields.Date.context_today(self).year
                ),
                "default_year_number": (
                    self.year or fields.Date.context_today(self).year
                ),
                "default_estate_id": self.estate_id.id,
                "default_budget_mandor_id": self.budget_mandor_id.id,
            },
        }

    @staticmethod
    def _line_values(line):
        return [line[field_name] or 0.0 for field_name, _label in MONTH_FIELDS]

    @staticmethod
    def _sum_values(value_rows):
        return [sum(values[index] for values in value_rows) for index in range(12)]

    @staticmethod
    def _variance_values(budget_values, actual_values):
        return [
            actual - budget
            for budget, actual in zip(budget_values, actual_values)
        ]

    def _get_actual_values(self, lines):
        keys = {
            (line.division_id.id, line.employee_id.id)
            for line in lines
        }
        values = {key: [0.0] * 12 for key in keys}
        if not keys:
            return values

        records = self.env["wt.weighing"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("production_date", ">=", date(self.year, 1, 1)),
                ("production_date", "<", date(self.year + 1, 1, 1)),
                ("division_id", "in", list({key[0] for key in keys})),
                (
                    "foreman_employee_id",
                    "in",
                    list({key[1] for key in keys}),
                ),
            ]
        )
        for record in records:
            key = (record.division_id.id, record.foreman_employee_id.id)
            if key in values and record.production_date:
                values[key][record.production_date.month - 1] += (
                    record.production_weight or 0.0
                )
        return values

    @staticmethod
    def _estate_sort_key(estate):
        identity = "%s %s" % (estate.code or "", estate.name or "")
        normalized_identity = identity.casefold()
        if "sebayur" in normalized_identity:
            priority = 0
        elif "gembung" in normalized_identity:
            priority = 1
        else:
            priority = 2
        return (
            priority,
            (estate.code or "").casefold(),
            (estate.name or "").casefold(),
            estate.id,
        )

    def _get_report_rows(self):
        self.ensure_one()
        if not self.budget_mandor_id:
            return []

        lines = self.budget_mandor_id.foreman_line_ids
        if self.estate_id:
            lines = lines.filtered(
                lambda line: line.division_id.estate_id == self.estate_id
            )
        lines = lines.sorted(
            key=lambda line: (
                self._estate_sort_key(line.division_id.estate_id),
                line.division_id.code or "",
                line.division_id.name or "",
                (line.foreman_name or "").casefold(),
                line.id,
            )
        )
        actual_values_by_foreman = self._get_actual_values(lines)
        grouped_estates = OrderedDict()
        for line in lines:
            estate = line.division_id.estate_id
            grouped_estates.setdefault(
                estate.id,
                {
                    "estate": estate,
                    "lines": self.env[line._name],
                },
            )
            grouped_estates[estate.id]["lines"] |= line

        rows = []
        for estate_data in grouped_estates.values():
            estate = estate_data["estate"]
            rows.append(
                {
                    "kind": "estate_header",
                    "label": estate.display_name,
                }
            )
            grouped_divisions = OrderedDict()
            for line in estate_data["lines"]:
                grouped_divisions.setdefault(
                    line.division_id.id,
                    {
                        "division": line.division_id,
                        "lines": self.env[line._name],
                    },
                )
                grouped_divisions[line.division_id.id]["lines"] |= line

            estate_values = []
            estate_actual_values = []
            for division_data in grouped_divisions.values():
                division = division_data["division"]
                division_values = []
                division_actual_values = []
                for sequence, line in enumerate(division_data["lines"], start=1):
                    values = self._line_values(line)
                    actual_values = actual_values_by_foreman.get(
                        (line.division_id.id, line.employee_id.id),
                        [0.0] * 12,
                    )
                    variance_values = self._variance_values(
                        values, actual_values
                    )
                    division_values.append(values)
                    division_actual_values.append(actual_values)
                    estate_values.append(values)
                    estate_actual_values.append(actual_values)
                    rows.append(
                        {
                            "kind": "foreman",
                            "division": division.code or division.name,
                            "sequence": sequence,
                            "foreman": line.foreman_name,
                            "unit": line.uom_name,
                            "values": values,
                            "actual_values": actual_values,
                            "variance_values": variance_values,
                            "total": sum(values),
                            "actual_total": sum(actual_values),
                            "variance_total": sum(actual_values) - sum(values),
                        }
                    )
                subtotal_values = self._sum_values(division_values)
                subtotal_actual_values = self._sum_values(
                    division_actual_values
                )
                subtotal_variance_values = self._variance_values(
                    subtotal_values, subtotal_actual_values
                )
                rows.append(
                    {
                        "kind": "division_total",
                        "label": _("Total Divisi %s")
                        % (division.code or division.name),
                        "unit": "Kg Basah",
                        "values": subtotal_values,
                        "actual_values": subtotal_actual_values,
                        "variance_values": subtotal_variance_values,
                        "total": sum(subtotal_values),
                        "actual_total": sum(subtotal_actual_values),
                        "variance_total": sum(subtotal_actual_values)
                        - sum(subtotal_values),
                    }
                )

            total_values = self._sum_values(estate_values)
            total_actual_values = self._sum_values(estate_actual_values)
            total_variance_values = self._variance_values(
                total_values, total_actual_values
            )
            if estate_values:
                rows.append(
                    {
                        "kind": "estate_total",
                        "label": _("Total Estate %s") % estate.display_name,
                        "unit": "Kg Basah",
                        "values": total_values,
                        "actual_values": total_actual_values,
                        "variance_values": total_variance_values,
                        "total": sum(total_values),
                        "actual_total": sum(total_actual_values),
                        "variance_total": sum(total_actual_values)
                        - sum(total_values),
                    }
                )
        return rows

    @staticmethod
    def _format_number(value):
        return "{:,.2f}".format(value or 0.0)

    @staticmethod
    def _variance_style(value):
        if value > 0:
            return "color:#15803d;"
        if value < 0:
            return "color:#dc2626;"
        return ""

    def _build_preview_html(self):
        self.ensure_one()
        rows = self._get_report_rows()
        parts = [
            '<div style="overflow-x:auto;width:100%;">',
            '<table style="border-collapse:collapse;min-width:4300px;width:100%;">',
            "<thead><tr>",
        ]
        for header in (_("Divisi"), _("No"), _("Mandor"), _("Satuan")):
            parts.append(
                '<th rowspan="2" style="border:1px solid #475569;padding:6px;'
                'text-align:center;vertical-align:middle;white-space:nowrap;">%s</th>'
                % escape(header)
            )
        for _field_name, month_label in MONTH_FIELDS:
            parts.append(
                '<th colspan="3" style="border:1px solid #475569;padding:6px;'
                'text-align:center;white-space:nowrap;">%s</th>'
                % escape(month_label.upper())
            )
        parts.append(
            '<th colspan="3" style="border:1px solid #475569;padding:6px;'
            'text-align:center;white-space:nowrap;">%s</th>'
            % escape(_("TOTAL"))
        )
        parts.append("</tr><tr>")
        for _index in range(13):
            for header in (_("Budget"), _("Realisasi"), _("Selisih")):
                parts.append(
                    '<th style="background:#f3f4f6;border:1px solid #475569;'
                    'padding:5px;text-align:center;white-space:nowrap;">%s</th>'
                    % escape(header)
                )
        parts.append("</tr></thead><tbody>")

        for row in rows:
            kind = row["kind"]
            if kind == "estate_header":
                parts.append(
                    '<tr><td colspan="43" style="background:#d9ead3;'
                    'border:1px solid #94a3b8;padding:5px;font-weight:700;">'
                    '%s</td></tr>' % escape(row["label"])
                )
                continue
            is_total = kind in {"division_total", "estate_total"}
            style = "background:#d9d9d9;font-weight:700;" if is_total else ""
            parts.append("<tr>")
            if is_total:
                parts.append(
                    '<td colspan="3" style="border:1px solid #94a3b8;'
                    'padding:5px;%s">%s</td>' % (style, escape(row["label"]))
                )
            else:
                parts.append(
                    '<td style="border:1px solid #94a3b8;padding:5px;'
                    'text-align:center;white-space:nowrap;">%s</td>'
                    % escape(row["division"])
                )
                parts.append(
                    '<td style="border:1px solid #94a3b8;padding:5px;'
                    'text-align:center;">%s</td>' % row["sequence"]
                )
                parts.append(
                    '<td style="border:1px solid #94a3b8;padding:5px;'
                    'white-space:nowrap;">%s</td>' % escape(row["foreman"])
                )
            parts.append(
                '<td style="border:1px solid #94a3b8;padding:5px;'
                'white-space:nowrap;%s">%s</td>'
                % (style, escape(row["unit"]))
            )
            for budget_value, actual_value, variance_value in zip(
                row["values"],
                row["actual_values"],
                row["variance_values"],
            ):
                for value, variance_style in (
                    (budget_value, ""),
                    (actual_value, ""),
                    (variance_value, self._variance_style(variance_value)),
                ):
                    parts.append(
                        '<td style="border:1px solid #94a3b8;padding:5px;'
                        'text-align:right;white-space:nowrap;%s%s">%s</td>'
                        % (
                            style,
                            variance_style,
                            self._format_number(value),
                        )
                    )
            for value, variance_style in (
                (row["total"], ""),
                (row["actual_total"], ""),
                (row["variance_total"], self._variance_style(row["variance_total"])),
            ):
                parts.append(
                    '<td style="border:1px solid #94a3b8;padding:5px;'
                    'text-align:right;white-space:nowrap;%s%s">%s</td>'
                    % (
                        style,
                        variance_style,
                        self._format_number(value),
                    )
                )
            parts.append("</tr>")
        parts.append("</tbody></table></div>")
        return Markup("".join(parts))

    def action_export_excel(self):
        self.ensure_one()
        if not self.is_filtered or not self.budget_mandor_id:
            raise ValidationError(_("Silakan terapkan filter sebelum mengekspor laporan."))
        if xlsxwriter is None:
            raise ValidationError(_("Package xlsxwriter belum terinstall."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Target Mandor %s" % self.year)
        sheet.hide_gridlines(2)
        sheet.set_landscape()
        sheet.fit_to_pages(1, 0)
        sheet.set_margins(0.25, 0.25, 0.35, 0.35)
        sheet.repeat_rows(0, 5)
        sheet.freeze_panes(6, 4)

        base_font = {"font_name": "Tahoma", "font_size": 10}
        title_format = workbook.add_format(
            {**base_font, "bold": True, "font_size": 11, "align": "left"}
        )
        header_format = workbook.add_format(
            {
                **base_font,
                "bold": True,
                "align": "center",
                "valign": "vcenter",
                "border": 1,
                "text_wrap": True,
            }
        )
        subheader_format = workbook.add_format(
            {
                **base_font,
                "bold": True,
                "align": "center",
                "valign": "vcenter",
                "border": 1,
                "bg_color": "#F3F4F6",
            }
        )
        text_format = workbook.add_format({**base_font, "border": 1})
        center_format = workbook.add_format(
            {**base_font, "border": 1, "align": "center"}
        )
        number_format = workbook.add_format(
            {**base_font, "border": 1, "num_format": "#,##0.00"}
        )
        total_text_format = workbook.add_format(
            {**base_font, "bold": True, "border": 1, "bg_color": "#D9D9D9"}
        )
        total_number_format = workbook.add_format(
            {
                **base_font,
                "bold": True,
                "border": 1,
                "bg_color": "#D9D9D9",
                "num_format": "#,##0.00",
            }
        )
        estate_format = workbook.add_format(
            {**base_font, "bold": True, "border": 1, "bg_color": "#D9EAD3"}
        )
        positive_variance_format = workbook.add_format(
            {"font_color": "#15803D"}
        )
        negative_variance_format = workbook.add_format(
            {"font_color": "#DC2626"}
        )

        sheet.set_column("A:A", 12)
        sheet.set_column("B:B", 6)
        sheet.set_column("C:C", 26)
        sheet.set_column("D:D", 12)
        sheet.set_column(4, 42, 13)

        last_column = 42
        sheet.merge_range(
            0, 0, 0, last_column, self.company_id.name or "", title_format
        )
        scope_title = (
            _("TARGET MANDOR ESTATE %s") % self.estate_id.display_name.upper()
            if self.estate_id
            else _("TARGET MANDOR SEMUA ESTATE")
        )
        sheet.merge_range(1, 0, 1, last_column, scope_title, title_format)
        sheet.merge_range(
            2, 0, 2, last_column, _("TAHUN %s") % self.year, title_format
        )
        headers = (_("DIVISI"), _("NO"), _("MANDOR"), _("SATUAN"))
        for column, header in enumerate(headers):
            sheet.merge_range(4, column, 5, column, header, header_format)
        for month_index, (_field_name, month_label) in enumerate(MONTH_FIELDS):
            start_column = 4 + (month_index * 3)
            sheet.merge_range(
                4,
                start_column,
                4,
                start_column + 2,
                month_label.upper(),
                header_format,
            )
            for offset, header in enumerate(
                (_("BUDGET"), _("REALISASI"), _("SELISIH"))
            ):
                sheet.write(5, start_column + offset, header, subheader_format)
        total_start_column = 40
        sheet.merge_range(
            4,
            total_start_column,
            4,
            last_column,
            _("TOTAL"),
            header_format,
        )
        for offset, header in enumerate(
            (_("BUDGET"), _("REALISASI"), _("SELISIH"))
        ):
            sheet.write(5, total_start_column + offset, header, subheader_format)

        row_index = 6
        for row in self._get_report_rows():
            if row["kind"] == "estate_header":
                sheet.merge_range(
                    row_index,
                    0,
                    row_index,
                    last_column,
                    row["label"],
                    estate_format,
                )
                row_index += 1
                continue
            if row["kind"] in {"division_total", "estate_total"}:
                sheet.merge_range(
                    row_index,
                    0,
                    row_index,
                    2,
                    row["label"],
                    total_text_format,
                )
                text_cell_format = total_text_format
                value_cell_format = total_number_format
            else:
                sheet.write(row_index, 0, row["division"], center_format)
                sheet.write_number(row_index, 1, row["sequence"], center_format)
                sheet.write(row_index, 2, row["foreman"], text_format)
                text_cell_format = text_format
                value_cell_format = number_format
            sheet.write(row_index, 3, row["unit"], text_cell_format)
            current_column = 4
            for budget_value, actual_value, variance_value in zip(
                row["values"],
                row["actual_values"],
                row["variance_values"],
            ):
                for value in (budget_value, actual_value, variance_value):
                    sheet.write_number(
                        row_index, current_column, value, value_cell_format
                    )
                    current_column += 1
            for value in (
                row["total"],
                row["actual_total"],
                row["variance_total"],
            ):
                sheet.write_number(
                    row_index, current_column, value, value_cell_format
                )
                current_column += 1
            row_index += 1

        variance_columns = [4 + (month_index * 3) + 2 for month_index in range(12)]
        variance_columns.append(last_column)
        for column in variance_columns:
            sheet.conditional_format(
                6,
                column,
                row_index - 1,
                column,
                {
                    "type": "cell",
                    "criteria": ">",
                    "value": 0,
                    "format": positive_variance_format,
                },
            )
            sheet.conditional_format(
                6,
                column,
                row_index - 1,
                column,
                {
                    "type": "cell",
                    "criteria": "<",
                    "value": 0,
                    "format": negative_variance_format,
                },
            )

        sheet.print_area(0, 0, row_index - 1, last_column)
        workbook.close()
        output.seek(0)

        estate_name = re.sub(
            r'[\\/:*?"<>|]+',
            "-",
            self.estate_id.display_name if self.estate_id else _("Semua Estate"),
        )
        filename = "Laporan Budget Target Mandor - %s - %s.xlsx" % (
            estate_name,
            self.year,
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
        action = self.env["ir.actions.actions"]._for_xml_id(
            "weightrack.action_wt_kpi_foreman_budget_target_report"
        )
        action["res_id"] = self.id
        return action


class KpiForemanBudgetTargetReportWizard(models.TransientModel):
    _name = "wt.kpi.foreman.budget.target.report.wizard"
    _description = "Filter Laporan Budget Target Mandor"

    report_id = fields.Many2one(
        "wt.kpi.foreman.budget.target.report",
        string="Laporan",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        required=True,
        default=lambda self: self.env.company,
    )
    year = fields.Char(
        string="Tahun",
        required=True,
        default=lambda self: str(date.today().year),
    )
    year_number = fields.Integer(
        string="Tahun Angka",
        required=True,
        default=lambda self: date.today().year,
    )
    budget_mandor_id = fields.Many2one(
        "wt.kpi.foreman.budget.target",
        string="Budget Target Mandor",
        required=True,
        domain=(
            "[('company_id', '=', company_id), ('year', '=', year_number), "
            "('state', '=', 'valid')]"
        ),
    )
    estate_id = fields.Many2one(
        "wt.estate",
        string="Estate",
        domain="[('company_id', '=', company_id)]",
        help="Kosongkan untuk menampilkan semua estate.",
    )

    @api.constrains("year")
    def _check_year(self):
        for wizard in self:
            if not re.fullmatch(r"\d{4}", wizard.year or ""):
                raise ValidationError(_("Tahun harus berupa 4 digit."))

    def _year_number(self):
        self.ensure_one()
        if not re.fullmatch(r"\d{4}", self.year or ""):
            raise ValidationError(_("Tahun harus berupa 4 digit."))
        return int(self.year)

    @api.onchange("company_id", "year")
    def _onchange_company_year(self):
        for wizard in self:
            year_number = (
                int(wizard.year)
                if re.fullmatch(r"\d{4}", wizard.year or "")
                else False
            )
            wizard.year_number = year_number or 0
            if wizard.budget_mandor_id and (
                wizard.budget_mandor_id.company_id != wizard.company_id
                or wizard.budget_mandor_id.year != year_number
                or wizard.budget_mandor_id.state != "valid"
            ):
                wizard.budget_mandor_id = False
            if (
                wizard.estate_id
                and wizard.estate_id.company_id != wizard.company_id
            ):
                wizard.estate_id = False
            if not wizard.company_id or not year_number:
                continue
            budgets = self.env["wt.kpi.foreman.budget.target"].search(
                [
                    ("company_id", "=", wizard.company_id.id),
                    ("year", "=", year_number),
                    ("state", "=", "valid"),
                ],
                limit=2,
            )
            if not wizard.budget_mandor_id and len(budgets) == 1:
                wizard.budget_mandor_id = budgets

    def action_apply_filter(self):
        self.ensure_one()
        year_number = self._year_number()
        budget = self.budget_mandor_id
        if (
            budget.company_id != self.company_id
            or budget.year != year_number
            or budget.state != "valid"
        ):
            raise ValidationError(
                _("Budget Target Mandor harus Valid dan sesuai Tahun serta Perusahaan.")
            )
        selected_lines = budget.foreman_line_ids
        if self.estate_id:
            selected_lines = selected_lines.filtered(
                lambda line: line.division_id.estate_id == self.estate_id
            )
        if not selected_lines:
            message = _(
                "Budget Target Mandor %(budget)s tidak memiliki data Mandor.",
                budget=budget.display_name,
            )
            if self.estate_id:
                message = _(
                    "Budget Target Mandor %(budget)s tidak memiliki data untuk "
                    "Estate %(estate)s.",
                    budget=budget.display_name,
                    estate=self.estate_id.display_name,
                )
            raise ValidationError(message)

        report = self.report_id
        report.write(
            {
                "name": _("Laporan Budget Target Mandor"),
                "is_filtered": True,
                "company_id": self.company_id.id,
                "year": year_number,
                "year_display": self.year,
                "estate_id": self.estate_id.id or False,
                "budget_mandor_id": budget.id,
                "preview_html": False,
            }
        )
        report.preview_html = report._build_preview_html()
        return report._open_current_report_action()
