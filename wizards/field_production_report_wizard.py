# -*- coding: utf-8 -*-

import base64
from datetime import timedelta
import io
import re

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class FieldProductionReport(models.TransientModel):
    _name = "wt.field.production.report"
    _description = "Laporan Produksi Field"

    name = fields.Char(
        string="Laporan",
        default="Laporan Produksi Field",
        readonly=True,
    )
    is_filtered = fields.Boolean(default=False, readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    date_start = fields.Date(readonly=True)
    date_end = fields.Date(readonly=True)
    division_id = fields.Many2one("wt.division", readonly=True)

    total_weight = fields.Float(
        string="Total Produksi (kg)", digits=(16, 2), readonly=True
    )
    preview_html = fields.Html(
        string="Preview", readonly=True, sanitize=False
    )
    date_column_ids = fields.One2many(
        "wt.field.production.report.date", "report_id",
        string="Kolom Tanggal", readonly=True,
    )
    line_ids = fields.One2many(
        "wt.field.production.report.line", "report_id",
        string="Baris", readonly=True,
    )

    def action_open_filter(self):
        self.ensure_one()
        return {
            "name": _("Filter Laporan Produksi Field"),
            "type": "ir.actions.act_window",
            "res_model": "wt.field.production.report.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_report_id": self.id,
                "default_company_id": self.company_id.id or self.env.company.id,
                "default_date_start": self.date_start
                    or fields.Date.start_of(fields.Date.context_today(self), "month"),
                "default_date_end": self.date_end or fields.Date.context_today(self),
                "default_division_id": self.division_id.id,
            },
        }

    def action_print_pdf(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Terapkan filter terlebih dahulu sebelum mencetak."))
        return self.env.ref(
            "weightrack.action_report_field_production_report_pdf"
        ).report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Terapkan filter terlebih dahulu sebelum export."))
        if xlsxwriter is None:
            raise ValidationError(_("Package xlsxwriter belum terinstall."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Laporan Produksi Field")

        title_fmt = workbook.add_format(
            {"bold": True, "font_size": 13, "align": "center"}
        )
        label_fmt = workbook.add_format({"bold": True})
        header_fmt = workbook.add_format({
            "bold": True, "align": "center", "valign": "vcenter",
            "border": 1, "text_wrap": True, "bg_color": "#E2E8F0",
        })
        text_fmt  = workbook.add_format({"border": 1, "valign": "vcenter"})
        center_fmt = workbook.add_format(
            {"border": 1, "align": "center", "valign": "vcenter"}
        )
        number_fmt = workbook.add_format(
            {"border": 1, "num_format": "#,##0.00", "valign": "vcenter"}
        )
        total_lbl_fmt = workbook.add_format({
            "bold": True, "border": 1, "align": "right",
            "valign": "vcenter", "bg_color": "#F8FAFC",
        })
        total_num_fmt = workbook.add_format({
            "bold": True, "border": 1, "num_format": "#,##0.00",
            "valign": "vcenter", "bg_color": "#F8FAFC",
        })

        date_cols = self.date_column_ids.sorted("sequence")
        # Cols: 0:No, 1:Divisi, 2:Field, 3:Clone, 4:HA, 5+:dates, last:Total
        first_date_col = 5
        last_date_col  = first_date_col + len(date_cols) - 1
        total_col      = last_date_col + 1
        last_col       = total_col

        sheet.merge_range(0, 0, 0, last_col, self.company_id.name or "", title_fmt)
        sheet.merge_range(1, 0, 1, last_col, _("LAPORAN PRODUKSI FIELD"), title_fmt)

        sheet.write(3, 0, _("Rentang Tanggal"), label_fmt)
        sheet.write(3, 1, "%s - %s" % (
            self.date_start.strftime("%d/%m/%Y"),
            self.date_end.strftime("%d/%m/%Y"),
        ))
        sheet.write(4, 0, _("Filter Divisi"), label_fmt)
        sheet.write(4, 1, self.division_id.display_name or _("Semua"))

        sheet.set_column(0, 0, 6)   # No.
        sheet.set_column(1, 1, 14)  # Divisi
        sheet.set_column(2, 2, 14)  # Field
        sheet.set_column(3, 3, 14)  # Clone
        sheet.set_column(4, 4, 10)  # HA
        sheet.set_column(first_date_col, last_date_col, 14)
        sheet.set_column(total_col, total_col, 18)

        header_row = 6
        for col, h in enumerate([_("No."), _("Divisi"), _("Field"), _("Clone"), _("HA")]):
            sheet.merge_range(header_row, col, header_row + 1, col, h, header_fmt)

        if len(date_cols) == 1:
            sheet.write(header_row, first_date_col, _("Produksi (kg)"), header_fmt)
        else:
            sheet.merge_range(
                header_row, first_date_col,
                header_row, last_date_col,
                _("Produksi (kg)"), header_fmt,
            )
        for offset, dc in enumerate(date_cols):
            sheet.write(
                header_row + 1, first_date_col + offset,
                dc.production_date.strftime("%d/%m/%Y"), header_fmt,
            )
        sheet.merge_range(
            header_row, total_col, header_row + 1, total_col,
            _("Total (kg)"), header_fmt,
        )
        sheet.freeze_panes(header_row + 2, first_date_col)

        data_row = header_row + 2
        for line in self.line_ids.sorted("sequence"):
            sheet.write(data_row, 0, line.sequence, center_fmt)
            sheet.write(data_row, 1, line.division_name or "", text_fmt)
            sheet.write(data_row, 2, line.field_name or "", text_fmt)
            sheet.write(data_row, 3, line.clone or "", text_fmt)
            sheet.write(data_row, 4, line.ha or 0.0, number_fmt)
            for offset, dc in enumerate(date_cols):
                sheet.write(
                    data_row, first_date_col + offset,
                    line.get_daily_weight(dc.production_date), number_fmt,
                )
            sheet.write(data_row, total_col, line.total_weight, number_fmt)
            data_row += 1

        sheet.merge_range(data_row, 0, data_row, 4, _("Total"), total_lbl_fmt)
        for offset, dc in enumerate(date_cols):
            sheet.write(
                data_row, first_date_col + offset,
                dc.total_weight, total_num_fmt,
            )
        sheet.write(data_row, total_col, self.total_weight, total_num_fmt)

        workbook.close()
        output.seek(0)
        filename = "Laporan Produksi Field - %s - %s.xlsx" % (
            self.date_start, self.date_end
        )
        attachment = self.env["ir.attachment"].create({
            "name": filename,
            "type": "binary",
            "datas": base64.b64encode(output.read()),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    def _open_current_report_action(self):
        self.ensure_one()
        return {
            "name": _("Laporan Produksi Field"),
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    def get_date_chunks(self, chunk_size=10):
        self.ensure_one()
        dates = self.date_column_ids.sorted("sequence")
        return [dates[i: i + chunk_size] for i in range(0, len(dates), chunk_size)]

    def _build_preview_html(self):
        self.ensure_one()
        date_cols = self.date_column_ids.sorted("sequence")
        lines = self.line_ids.sorted("sequence")

        th_base = (
            'style="background:#e2e8f0;border:1px solid #94a3b8;'
            'padding:7px;text-align:center;vertical-align:middle;white-space:nowrap;"'
        )
        td_left  = 'style="border:1px solid #cbd5e1;padding:6px 8px;white-space:nowrap;"'
        td_right = 'style="border:1px solid #cbd5e1;padding:6px 8px;text-align:right;white-space:nowrap;"'
        td_center = 'style="border:1px solid #cbd5e1;padding:6px 8px;text-align:center;white-space:nowrap;"'
        th_sub   = 'style="background:#f1f5f9;border:1px solid #94a3b8;padding:6px;text-align:center;white-space:nowrap;"'

        parts = [
            '<div style="overflow-x:auto;width:100%;">',
            '<table style="border-collapse:collapse;width:100%;">',
            "<thead><tr>",
        ]
        for h in [_("No."), _("Divisi"), _("Field"), _("Clone"), _("HA")]:
            parts.append('<th rowspan="2" %s>%s</th>' % (th_base, escape(h)))
        parts.append(
            '<th colspan="%d" %s>%s</th>' % (len(date_cols), th_base, escape(_("Produksi (kg)")))
        )
        parts.append('<th rowspan="2" %s>%s</th>' % (th_base, escape(_("Total (kg)"))))
        parts.append("</tr><tr>")
        for dc in date_cols:
            parts.append(
                "<th %s>%s</th>" % (th_sub, dc.production_date.strftime("%d/%m/%Y"))
            )
        parts.append("</tr></thead><tbody>")

        if not lines:
            parts.append(
                '<tr><td colspan="%d" style="border:1px solid #cbd5e1;'
                'padding:12px;text-align:center;">%s</td></tr>'
                % (len(date_cols) + 6, escape(_("Tidak ada data.")))
            )

        for line in lines:
            parts.append("<tr>")
            parts.append('<td %s>%s</td>' % (td_center, escape(str(line.sequence))))
            parts.append('<td %s>%s</td>' % (td_left, escape(line.division_name or "")))
            parts.append('<td %s>%s</td>' % (td_left, escape(line.field_name or "")))
            parts.append('<td %s>%s</td>' % (td_left, escape(line.clone or "")))
            parts.append('<td %s>%s</td>' % (td_right, self._fmt(line.ha)))
            for dc in date_cols:
                parts.append(
                    '<td %s>%s</td>'
                    % (td_right, self._fmt(line.get_daily_weight(dc.production_date)))
                )
            parts.append('<td style="border:1px solid #cbd5e1;padding:6px 8px;'
                         'text-align:right;font-weight:700;white-space:nowrap;">%s</td>'
                         % self._fmt(line.total_weight))
            parts.append("</tr>")

        # Total row
        total_style = 'style="background:#f8fafc;border:1px solid #94a3b8;font-weight:700;padding:6px 8px;"'
        total_right = 'style="background:#f8fafc;border:1px solid #94a3b8;font-weight:700;padding:6px 8px;text-align:right;white-space:nowrap;"'
        parts.append("<tr>")
        parts.append('<td colspan="5" %s>%s</td>' % (total_style, escape(_("Total"))))
        for dc in date_cols:
            parts.append('<td %s>%s</td>' % (total_right, self._fmt(dc.total_weight)))
        parts.append('<td %s>%s</td>' % (total_right, self._fmt(self.total_weight)))
        parts.append("</tr>")

        parts.extend(["</tbody></table></div>"])
        return Markup("".join(parts))

    @staticmethod
    def _fmt(value):
        return "{:,.2f}".format(value or 0.0)


class FieldProductionReportDate(models.TransientModel):
    _name = "wt.field.production.report.date"
    _description = "Laporan Produksi Field - Kolom Tanggal"
    _order = "sequence, production_date"

    report_id = fields.Many2one(
        "wt.field.production.report", required=True, ondelete="cascade"
    )
    sequence = fields.Integer(readonly=True)
    production_date = fields.Date(readonly=True)
    total_weight = fields.Float(digits=(16, 2), readonly=True)


class FieldProductionReportLine(models.TransientModel):
    _name = "wt.field.production.report.line"
    _description = "Laporan Produksi Field - Baris"
    _order = "sequence, id"

    report_id = fields.Many2one(
        "wt.field.production.report", required=True, ondelete="cascade"
    )
    sequence    = fields.Integer(readonly=True)
    field_name  = fields.Char(readonly=True)
    clone       = fields.Char(readonly=True)
    ha          = fields.Float(digits=(16, 2), readonly=True)
    division_name = fields.Char(readonly=True)
    daily_weight  = fields.Json(readonly=True)
    total_weight  = fields.Float(digits=(16, 2), readonly=True)

    def get_daily_weight(self, production_date):
        self.ensure_one()
        key = fields.Date.to_date(production_date).isoformat()
        return (self.daily_weight or {}).get(key, 0.0)


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------

class FieldProductionReportWizard(models.TransientModel):
    _name = "wt.field.production.report.wizard"
    _description = "Wizard Laporan Produksi Field"

    report_id = fields.Many2one(
        "wt.field.production.report", required=True, ondelete="cascade"
    )
    company_id = fields.Many2one(
        "res.company", string="Perusahaan", required=True,
        default=lambda self: self.env.company,
    )
    date_start = fields.Date(
        string="Dari Tanggal", required=True,
        default=lambda self: fields.Date.start_of(
            fields.Date.context_today(self), "month"
        ),
    )
    date_end = fields.Date(
        string="Sampai Tanggal", required=True,
        default=fields.Date.context_today,
    )
    division_id = fields.Many2one(
        "wt.division", string="Divisi",
        domain="[('company_id', '=', company_id)]",
    )

    @api.onchange("company_id")
    def _onchange_company_id(self):
        self.division_id = False

    def _prepare_report_data(self):
        self.ensure_one()
        if self.date_start > self.date_end:
            raise ValidationError(_("Tanggal mulai tidak boleh lebih dari tanggal selesai."))

        # 1. Kumpulkan semua tanggal dalam rentang secara berurutan
        all_dates = []
        curr = self.date_start
        while curr <= self.date_end:
            all_dates.append(curr)
            curr += timedelta(days=1)

        date_totals = {d.isoformat(): 0.0 for d in all_dates}
        grouped = {}

        # 2. Pre-populate field master dari divisi yang dipilih (atau semua divisi)
        if self.division_id:
            divisions = self.division_id
        else:
            divisions = self.env["wt.division"].search([
                ("company_id", "=", self.company_id.id),
                ("active", "=", True),
            ])

        for div in divisions:
            fields_in_div = self.env["wt.field"].search([
                ("active", "=", True),
                ("division_ids", "in", div.id),
            ])
            for f in fields_in_div:
                group_key = (f.id, div.id)
                grouped[group_key] = {
                    "field_name": f.display_name or "",
                    "clone": f.clone or "",
                    "ha": f.ha or 0.0,
                    "division_name": div.display_name or "",
                    "daily_weight": {d.isoformat(): 0.0 for d in all_dates},
                    "total_weight": 0.0,
                }

        # 3. Ambil semua dokumen Produksi Field yang selesai dalam rentang tanggal
        domain = [
            ("company_id", "=", self.company_id.id),
            ("production_date", ">=", self.date_start),
            ("production_date", "<=", self.date_end),
            ("state", "=", "selesai"),
        ]
        if self.division_id:
            domain.append(("division_id", "=", self.division_id.id))

        productions = self.env["wt.field.production"].search(domain)

        for prod in productions:
            date_key = prod.production_date.isoformat()
            div_id   = prod.division_id.id
            for line in prod.field_line_ids:
                field_id = line.field_id.id
                w = line.today_production_weight or 0.0
                group_key = (field_id, div_id)
                if group_key not in grouped:
                    grouped[group_key] = {
                        "field_name": line.field_id.display_name or "",
                        "clone": line.clone or "",
                        "ha": line.ha or 0.0,
                        "division_name": prod.division_id.display_name or "",
                        "daily_weight": {d.isoformat(): 0.0 for d in all_dates},
                        "total_weight": 0.0,
                    }
                grouped[group_key]["daily_weight"][date_key] += w
                grouped[group_key]["total_weight"] += w
                date_totals[date_key] += w

        # Sort: Divisi (natural) → Field (natural)
        rows = sorted(
            grouped.values(),
            key=lambda r: (
                self._natural_sort_key(r["division_name"]),
                self._natural_sort_key(r["field_name"]),
            ),
        )
        for seq, row in enumerate(rows, start=1):
            row["sequence"] = seq

        return {
            "dates": all_dates,
            "date_totals": date_totals,
            "rows": rows,
            "total_weight": sum(date_totals.values()),
        }

    @staticmethod
    def _natural_sort_key(value):
        return tuple(
            int(p) if p.isdigit() else p.casefold()
            for p in re.split(r"(\d+)", value or "")
        )

    def action_apply_filter(self):
        self.ensure_one()
        data = self._prepare_report_data()
        report = self.report_id
        report.date_column_ids.unlink()
        report.line_ids.unlink()
        report.write({
            "is_filtered": True,
            "company_id": self.company_id.id,
            "date_start": self.date_start,
            "date_end": self.date_end,
            "division_id": self.division_id.id,
            "total_weight": data["total_weight"],
            "preview_html": False,
        })
        self.env["wt.field.production.report.date"].create([
            {
                "report_id": report.id,
                "sequence": seq,
                "production_date": d,
                "total_weight": data["date_totals"][d.isoformat()],
            }
            for seq, d in enumerate(data["dates"], start=1)
        ])
        if data["rows"]:
            self.env["wt.field.production.report.line"].create([
                {
                    "report_id": report.id,
                    "sequence": row["sequence"],
                    "field_name": row["field_name"],
                    "clone": row["clone"],
                    "ha": row["ha"],
                    "division_name": row["division_name"],
                    "daily_weight": row["daily_weight"],
                    "total_weight": row["total_weight"],
                }
                for row in data["rows"]
            ])
        report.preview_html = report._build_preview_html()
        return report._open_current_report_action()


# ---------------------------------------------------------------------------
# Report PDF renderer
# ---------------------------------------------------------------------------

class ReportFieldProductionReport(models.AbstractModel):
    _name = "report.weightrack.report_field_production_report_document"
    _description = "Laporan Produksi Field PDF"

    def _get_report_values(self, docids, data=None):
        docs = self.env["wt.field.production.report"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "wt.field.production.report",
            "docs": docs,
        }
