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


class DrcReport(models.TransientModel):
    _name = "wt.drc.report"
    _description = "Laporan DRC"

    name = fields.Char(
        string="Report",
        default="Laporan DRC",
        readonly=True,
    )
    is_filtered = fields.Boolean(default=False, readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    date_start = fields.Date(string="Start Date", readonly=True)
    date_end = fields.Date(string="End Date", readonly=True)
    division_id = fields.Many2one("wt.division", string="Divisi", readonly=True)
    tapper_id = fields.Many2one("wt.tapper", string="Tapper", readonly=True)
    total_hk = fields.Integer(string="Total HK", readonly=True)
    total_lp = fields.Float(string="Total LP", readonly=True)
    avg_drc = fields.Float(string="Rata-rata DRC (%)", readonly=True)
    total_gd = fields.Float(string="Total GD", readonly=True)
    preview_html = fields.Html(string="Preview", readonly=True, sanitize=False)
    date_column_ids = fields.One2many(
        "wt.drc.report.date", "report_id", string="Dates", readonly=True
    )
    line_ids = fields.One2many(
        "wt.drc.report.line", "report_id", string="Lines", readonly=True
    )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_open_filter(self):
        self.ensure_one()
        return {
            "name": _("Filter Laporan DRC"),
            "type": "ir.actions.act_window",
            "res_model": "wt.drc.report.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_report_id": self.id,
                "default_company_id": self.company_id.id or self.env.company.id,
                "default_date_start": self.date_start
                or fields.Date.start_of(fields.Date.context_today(self), "month"),
                "default_date_end": self.date_end or fields.Date.context_today(self),
                "default_division_id": self.division_id.id,
                "default_tapper_id": self.tapper_id.id,
            },
        }

    def action_print_pdf(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Terapkan filter sebelum mencetak laporan."))
        return self.env.ref("weightrack.action_report_drc_pdf").report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Terapkan filter sebelum mengekspor laporan."))
        if xlsxwriter is None:
            raise ValidationError(_("Paket xlsxwriter tidak terinstal."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Laporan DRC")

        # Formats
        title_fmt = workbook.add_format({"bold": True, "font_size": 13, "align": "center"})
        label_fmt = workbook.add_format({"bold": True})
        hdr_fmt = workbook.add_format(
            {"bold": True, "align": "center", "valign": "vcenter",
             "border": 1, "text_wrap": True, "bg_color": "#C6EFCE"}
        )
        txt_fmt = workbook.add_format({"border": 1, "valign": "vcenter"})
        ctr_fmt = workbook.add_format({"border": 1, "align": "center", "valign": "vcenter"})
        num_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.0", "valign": "vcenter"})
        tot_lbl_fmt = workbook.add_format(
            {"bold": True, "border": 1, "align": "right", "valign": "vcenter", "bg_color": "#F8FAFC"}
        )
        tot_num_fmt = workbook.add_format(
            {"bold": True, "border": 1, "num_format": "#,##0.0", "valign": "vcenter", "bg_color": "#F8FAFC"}
        )

        date_columns = self.date_column_ids.sorted("sequence")
        # Static columns: No, ID, NIK, Nama, Mandor, Divisi, Pekerjaan  → 7 cols (0-6)
        STATIC = 7
        first_date_col = STATIC  # each date has LP + DRC + GD = 3 cols
        total_hk_col = first_date_col + len(date_columns) * 3
        total_lp_col = total_hk_col + 1
        avg_drc_col = total_lp_col + 1
        total_gd_col = avg_drc_col + 1
        last_col = total_gd_col

        # Title
        month_label = ""
        if self.date_start:
            month_label = self.date_start.strftime("%B %Y").upper()
        sheet.merge_range(0, 0, 0, last_col, self.company_id.name or "", title_fmt)
        sheet.merge_range(1, 0, 1, last_col, "DAFTAR PEMBAYARAN KARYAWAN TAPPER", title_fmt)
        sheet.merge_range(2, 0, 2, last_col, "BULAN " + month_label, title_fmt)

        sheet.write(4, 0, _("Rentang Tanggal"), label_fmt)
        sheet.write(4, 1, "%s - %s" % (
            self.date_start.strftime("%d/%m/%Y"), self.date_end.strftime("%d/%m/%Y")
        ))
        sheet.write(5, 0, _("Divisi"), label_fmt)
        sheet.write(5, 1, self.division_id.display_name or _("Semua"))
        sheet.write(5, 3, _("Tapper"), label_fmt)
        sheet.write(5, 4, self.tapper_id.display_name or _("Semua"))

        HDR_ROW = 7
        static_headers = ["NO", "ID", "NIK", "NAMA KARYAWAN", "NAMA MANDOR", "DIVISI", "PEKERJAAN"]
        for col, hdr in enumerate(static_headers):
            sheet.merge_range(HDR_ROW, col, HDR_ROW + 1, col, hdr, hdr_fmt)

        for offset, date_col in enumerate(date_columns):
            day_label = date_col.production_date.strftime("%d/%m/%Y")
            col_lp = first_date_col + offset * 3
            col_drc = col_lp + 1
            col_gd = col_lp + 2
            sheet.merge_range(HDR_ROW, col_lp, HDR_ROW, col_gd, day_label, hdr_fmt)
            sheet.write(HDR_ROW + 1, col_lp, "LP", hdr_fmt)
            sheet.write(HDR_ROW + 1, col_drc, "DRC", hdr_fmt)
            sheet.write(HDR_ROW + 1, col_gd, "GD", hdr_fmt)

        sheet.merge_range(HDR_ROW, total_hk_col, HDR_ROW, total_lp_col,
                          "PENERIMAAN KEBUN", hdr_fmt)
        sheet.write(HDR_ROW + 1, total_hk_col, "HK", hdr_fmt)
        sheet.write(HDR_ROW + 1, total_lp_col, "KG", hdr_fmt)
        sheet.merge_range(HDR_ROW, avg_drc_col, HDR_ROW + 1, avg_drc_col,
                          "RATA-RATA\nDRC (%)", hdr_fmt)
        sheet.merge_range(HDR_ROW, total_gd_col, HDR_ROW + 1, total_gd_col,
                          "PENERIMAAN\nGUDANG", hdr_fmt)

        # Column widths
        sheet.set_column(0, 0, 5)
        sheet.set_column(1, 1, 14)
        sheet.set_column(2, 2, 16)
        sheet.set_column(3, 3, 22)
        sheet.set_column(4, 4, 18)
        sheet.set_column(5, 5, 10)
        sheet.set_column(6, 6, 10)
        sheet.set_column(first_date_col, last_col - 1, 8)
        sheet.set_column(total_hk_col, total_gd_col, 12)
        sheet.freeze_panes(HDR_ROW + 2, first_date_col)

        row_idx = HDR_ROW + 2
        for line in self.line_ids.sorted("sequence"):
            sheet.write(row_idx, 0, line.sequence, ctr_fmt)
            sheet.write(row_idx, 1, line.badge_number or "", txt_fmt)
            sheet.write(row_idx, 2, line.nik or "", txt_fmt)
            sheet.write(row_idx, 3, line.tapper_name or "", txt_fmt)
            sheet.write(row_idx, 4, line.foreman_name or "", txt_fmt)
            sheet.write(row_idx, 5, line.division_name or "", txt_fmt)
            sheet.write(row_idx, 6, line.job_title or "TAPPER", txt_fmt)
            for offset, date_col in enumerate(date_columns):
                col_lp = first_date_col + offset * 3
                col_drc = col_lp + 1
                col_gd = col_lp + 2
                lp, drc, gd = line.get_daily_lp_drc_gd(date_col.production_date)
                if lp:
                    sheet.write(row_idx, col_lp, lp, num_fmt)
                    sheet.write(row_idx, col_drc, drc, num_fmt)
                    sheet.write(row_idx, col_gd, gd, num_fmt)
                else:
                    sheet.write(row_idx, col_lp, "", ctr_fmt)
                    sheet.write(row_idx, col_drc, "", ctr_fmt)
                    sheet.write(row_idx, col_gd, "", ctr_fmt)
            if line.total_hk:
                sheet.write(row_idx, total_hk_col, line.total_hk, ctr_fmt)
                sheet.write(row_idx, total_lp_col, line.total_lp, num_fmt)
                sheet.write(row_idx, avg_drc_col, line.avg_drc, num_fmt)
                sheet.write(row_idx, total_gd_col, line.total_gd, num_fmt)
            else:
                sheet.write(row_idx, total_hk_col, "-", ctr_fmt)
                sheet.write(row_idx, total_lp_col, "-", ctr_fmt)
                sheet.write(row_idx, avg_drc_col, "-", ctr_fmt)
                sheet.write(row_idx, total_gd_col, "-", ctr_fmt)
            row_idx += 1

        # Total row
        sheet.merge_range(row_idx, 0, row_idx, 6, "TOTAL", tot_lbl_fmt)
        for offset, date_col in enumerate(date_columns):
            col_lp = first_date_col + offset * 3
            col_drc = col_lp + 1
            col_gd = col_lp + 2
            if date_col.total_lp:
                sheet.write(row_idx, col_lp, date_col.total_lp, tot_num_fmt)
                sheet.write(row_idx, col_drc, date_col.avg_drc, tot_num_fmt)
                sheet.write(row_idx, col_gd, date_col.total_gd, tot_num_fmt)
            else:
                sheet.write(row_idx, col_lp, "", tot_lbl_fmt)
                sheet.write(row_idx, col_drc, "", tot_lbl_fmt)
                sheet.write(row_idx, col_gd, "", tot_lbl_fmt)
        sheet.write(row_idx, total_hk_col, self.total_hk, tot_num_fmt)
        sheet.write(row_idx, total_lp_col, self.total_lp, tot_num_fmt)
        sheet.write(row_idx, avg_drc_col, self.avg_drc, tot_num_fmt)
        sheet.write(row_idx, total_gd_col, self.total_gd, tot_num_fmt)

        workbook.close()
        output.seek(0)
        filename = "Laporan DRC - %s - %s.xlsx" % (self.date_start, self.date_end)
        attachment = self.env["ir.attachment"].create({
            "name": filename,
            "type": "binary",
            "datas": base64.b64encode(output.read()),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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
            "name": _("Laporan DRC"),
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    def get_date_chunks(self, chunk_size=5):
        """Split date columns into pages (5 dates per page for PDF with LP, DRC, GD)."""
        self.ensure_one()
        dates = self.date_column_ids.sorted("sequence")
        return [dates[i: i + chunk_size] for i in range(0, len(dates), chunk_size)]

    def _build_preview_html(self):
        self.ensure_one()
        date_columns = self.date_column_ids.sorted("sequence")
        lines = self.line_ids.sorted("sequence")

        TH = (
            'style="background:#C6EFCE;border:1px solid #6B7280;'
            'padding:5px 4px;text-align:center;vertical-align:middle;white-space:nowrap;"'
        )
        TD_CTR = (
            'style="border:1px solid #D1D5DB;padding:5px 4px;'
            'text-align:center;white-space:nowrap;"'
        )
        TD_LEFT = (
            'style="border:1px solid #D1D5DB;padding:5px 4px;'
            'text-align:left;white-space:nowrap;"'
        )
        TD_RIGHT = (
            'style="border:1px solid #D1D5DB;padding:5px 4px;'
            'text-align:right;white-space:nowrap;"'
        )
        TD_TOT = (
            'style="background:#F8FAFC;border:1px solid #9CA3AF;'
            'font-weight:700;padding:5px 4px;text-align:right;white-space:nowrap;"'
        )

        parts = [
            '<div style="overflow-x:auto;width:100%;font-size:11px;">',
            '<table style="border-collapse:collapse;width:100%;">',
            "<thead>",
            "<tr>",
        ]
        # Static col headers (rowspan=2)
        for hdr in ["NO", "ID", "NIK", "NAMA KARYAWAN", "NAMA MANDOR", "DIVISI", "PEKERJAAN"]:
            parts.append('<th rowspan="2" %s>%s</th>' % (TH, escape(hdr)))
        # Date headers (colspan=3 each)
        for dc in date_columns:
            parts.append(
                '<th colspan="3" %s>%s</th>'
                % (TH, escape(dc.production_date.strftime("%d/%m/%Y")))
            )
        # Grouped summary headers
        parts.append(
            '<th colspan="2" %s>PENERIMAAN KEBUN</th>' % TH
        )
        parts.append(
            '<th rowspan="2" %s>RATA-RATA<br/>DRC (%%)</th>' % TH
        )
        parts.append(
            '<th rowspan="2" %s>PENERIMAAN<br/>GUDANG</th>' % TH
        )
        parts.extend(["</tr>", "<tr>"])
        # Sub-headers LP/DRC/GD per date
        for _ in date_columns:
            parts.append('<th %s>LP</th><th %s>DRC</th><th %s>GD</th>' % (TH, TH, TH))
        # Sub-headers HK/KG under PENERIMAAN KEBUN
        parts.append('<th %s>HK</th><th %s>KG</th>' % (TH, TH))
        parts.extend(["</tr>", "</thead>", "<tbody>"])

        if not lines:
            cols = 7 + len(date_columns) * 3 + 4
            parts.append(
                '<tr><td colspan="%s" style="border:1px solid #D1D5DB;'
                'padding:12px;text-align:center;">Tidak ada data.</td></tr>' % cols
            )

        for line in lines:
            parts.append("<tr>")
            for val, align in [
                (line.sequence, TD_CTR),
                (line.badge_number or "", TD_LEFT),
                (line.nik or "", TD_LEFT),
                (line.tapper_name or "", TD_LEFT),
                (line.foreman_name or "", TD_LEFT),
                (line.division_name or "", TD_CTR),
                (line.job_title or "TAPPER", TD_CTR),
            ]:
                parts.append("<td %s>%s</td>" % (align, escape(str(val))))
            for dc in date_columns:
                lp, drc, gd = line.get_daily_lp_drc_gd(dc.production_date)
                if lp:
                    parts.append(
                        "<td %s>%s</td><td %s>%s</td><td %s>%s</td>"
                        % (TD_RIGHT, self._fmt(lp), TD_RIGHT, self._fmt(drc), TD_RIGHT, self._fmt(gd))
                    )
                else:
                    parts.append(
                        "<td %s></td><td %s></td><td %s></td>"
                        % (TD_RIGHT, TD_RIGHT, TD_RIGHT)
                    )
            if line.total_hk:
                parts.append(
                    "<td %s>%s</td><td %s>%s</td><td %s>%s</td><td %s>%s</td>"
                    % (TD_CTR, line.total_hk, TD_RIGHT, self._fmt(line.total_lp),
                       TD_RIGHT, self._fmt(line.avg_drc), TD_RIGHT, self._fmt(line.total_gd))
                )
            else:
                parts.append(
                    "<td %s>-</td><td %s>-</td><td %s>-</td><td %s>-</td>"
                    % (TD_CTR, TD_CTR, TD_CTR, TD_CTR)
                )
            parts.append("</tr>")

        # Total row
        parts.append("<tr>")
        parts.append('<td colspan="7" %s>TOTAL</td>' % TD_TOT)
        for dc in date_columns:
            if dc.total_lp:
                parts.append(
                    "<td %s>%s</td><td %s>%s</td><td %s>%s</td>"
                    % (TD_TOT, self._fmt(dc.total_lp), TD_TOT, self._fmt(dc.avg_drc), TD_TOT, self._fmt(dc.total_gd))
                )
            else:
                parts.append(
                    "<td %s></td><td %s></td><td %s></td>"
                    % (TD_TOT, TD_TOT, TD_TOT)
                )
        parts.append(
            "<td %s>%s</td><td %s>%s</td><td %s>%s</td><td %s>%s</td>"
            % (TD_TOT, self.total_hk, TD_TOT, self._fmt(self.total_lp),
               TD_TOT, self._fmt(self.avg_drc), TD_TOT, self._fmt(self.total_gd))
        )
        parts.extend(["</tr>", "</tbody>", "</table>", "</div>"])
        return Markup("".join(parts))

    @staticmethod
    def _fmt(value):
        if value is None or value == "":
            return ""
        return "{:,.1f}".format(value)


# ─────────────────────────────────────────────────────────────────────────────
class DrcReportDate(models.TransientModel):
    _name = "wt.drc.report.date"
    _description = "Laporan DRC - Kolom Tanggal"
    _order = "sequence, production_date"

    report_id = fields.Many2one("wt.drc.report", required=True, ondelete="cascade")
    sequence = fields.Integer(readonly=True)
    production_date = fields.Date(string="Tanggal", readonly=True)
    total_lp = fields.Float(string="Total LP", readonly=True)
    avg_drc = fields.Float(string="DRC (%)", readonly=True)
    total_gd = fields.Float(string="Total GD", readonly=True)


# ─────────────────────────────────────────────────────────────────────────────
class DrcReportLine(models.TransientModel):
    _name = "wt.drc.report.line"
    _description = "Laporan DRC - Baris Tapper"
    _order = "sequence, id"

    report_id = fields.Many2one("wt.drc.report", required=True, ondelete="cascade")
    sequence = fields.Integer(string="No.", readonly=True)
    badge_number = fields.Char(string="ID", readonly=True)
    nik = fields.Char(string="NIK", readonly=True)
    tapper_name = fields.Char(string="Nama Karyawan", readonly=True)
    foreman_name = fields.Char(string="Nama Mandor", readonly=True)
    division_name = fields.Char(string="Divisi", readonly=True)
    division_code = fields.Char(string="Division Code", readonly=True)
    job_title = fields.Char(string="Pekerjaan", readonly=True)
    # JSON: {"2026-09-01": {"lp": 90.0, "drc": 40.0, "gd": 36.0}, ...}
    daily_data = fields.Json(string="Daily LP/DRC/GD", readonly=True)
    total_hk = fields.Integer(string="Total HK", readonly=True)
    total_lp = fields.Float(string="Total LP", readonly=True)
    avg_drc = fields.Float(string="Rata-rata DRC (%)", readonly=True)
    total_gd = fields.Float(string="Total GD", readonly=True)

    def get_daily_lp_drc_gd(self, production_date):
        self.ensure_one()
        date_key = fields.Date.to_date(production_date).isoformat()
        entry = (self.daily_data or {}).get(date_key, {})
        return entry.get("lp", 0.0), entry.get("drc", 0.0), entry.get("gd", 0.0)

    def get_daily_lp_gd(self, production_date):
        lp, _drc, gd = self.get_daily_lp_drc_gd(production_date)
        return lp, gd


# ─────────────────────────────────────────────────────────────────────────────
class DrcReportWizard(models.TransientModel):
    _name = "wt.drc.report.wizard"
    _description = "Laporan DRC - Wizard Filter"

    report_id = fields.Many2one(
        "wt.drc.report", required=True, ondelete="cascade"
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    date_start = fields.Date(
        string="Tanggal Mulai",
        required=True,
        default=lambda self: fields.Date.start_of(
            fields.Date.context_today(self), "month"
        ),
    )
    date_end = fields.Date(
        string="Tanggal Selesai",
        required=True,
        default=fields.Date.context_today,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Divisi",
        domain="[('company_id', '=', company_id)]",
    )
    tapper_id = fields.Many2one(
        "wt.tapper",
        string="Tapper",
        domain=(
            "[('company_id', '=', company_id), "
            "('division_id', '=?', division_id)]"
        ),
    )

    @api.onchange("company_id")
    def _onchange_company_id(self):
        self.division_id = False
        self.tapper_id = False

    @api.onchange("division_id")
    def _onchange_division_id(self):
        if self.tapper_id and self.tapper_id.division_id != self.division_id:
            self.tapper_id = False

    @api.onchange("tapper_id")
    def _onchange_tapper_id(self):
        if self.tapper_id:
            self.division_id = self.tapper_id.division_id

    # ------------------------------------------------------------------
    # Data preparation
    # ------------------------------------------------------------------

    def _get_drc_percentage(self, division_id, production_date):
        """Return DRC percentage (0–100) for division on given date."""
        drc = self.env["wt.drc"].search(
            [
                ("division_id", "=", division_id),
                ("valid_from", "<=", production_date),
                ("valid_until", ">=", production_date),
            ],
            limit=1,
        )
        return drc.percentage if drc else 0.0

    def _prepare_report_data(self):
        self.ensure_one()
        if self.date_start > self.date_end:
            raise ValidationError(_("Tanggal Mulai tidak boleh lebih besar dari Tanggal Selesai."))

        # Build date list
        date_list = []
        cur = self.date_start
        while cur <= self.date_end:
            date_list.append(cur)
            cur += timedelta(days=1)

        # Build weighing domain
        domain = [
            ("company_id", "=", self.company_id.id),
            ("production_date", ">=", self.date_start),
            ("production_date", "<=", self.date_end),
        ]
        if self.division_id:
            domain.append(("division_id", "=", self.division_id.id))
        if self.tapper_id:
            domain.append(
                ("tapper_employee_id", "=", self.tapper_id.employee_id.id)
            )

        records = self.env["wt.weighing"].search(domain)

        # Pre-fetch DRC per (division_id, date) to avoid N+1
        drc_cache = {}

        def get_drc_pct(div_id, prod_date):
            key = (div_id, prod_date)
            if key not in drc_cache:
                drc_cache[key] = self._get_drc_percentage(div_id, prod_date)
            return drc_cache[key]

        # Group by tapper
        date_isos = {d.isoformat() for d in date_list}
        grouped = {}
        date_totals = {d.isoformat(): {"lp": 0.0, "drc": 0.0, "gd": 0.0} for d in date_list}

        for rec in records:
            prod_date = rec.production_date
            prod_iso = prod_date.isoformat()
            lp = rec.production_weight or 0.0
            div_id = rec.division_id.id or 0
            raw_drc_pct = get_drc_pct(div_id, prod_date)
            if raw_drc_pct:
                drc_pct = raw_drc_pct / 100.0
                gd = round(lp * drc_pct, 1)
            else:
                raw_drc_pct = 0.0
                gd = lp  # Jika tidak ada data DRC, GD full sesuai LP (100%)

            group_key = (div_id, rec.foreman_employee_id.id or 0, rec.tapper_employee_id.id or 0)
            row = grouped.setdefault(
                group_key,
                {
                    "badge_number": rec.tapper_barcode or "",
                    "nik": rec.tapper_employee_id.identification_id or "",
                    "tapper_name": rec.tapper_employee_id.name or "",
                    "foreman_name": rec.foreman_employee_id.name or "",
                    "division_name": rec.division_id.name or "",
                    "division_code": rec.division_id.code or "",
                    "job_title": "TAPPER",
                    "division_id": div_id,
                    "daily_data": {d.isoformat(): {"lp": 0.0, "drc": 0.0, "gd": 0.0} for d in date_list},
                    "total_hk": 0,
                    "total_lp": 0.0,
                    "total_gd": 0.0,
                },
            )
            row["daily_data"][prod_iso]["lp"] += lp
            row["daily_data"][prod_iso]["drc"] = raw_drc_pct
            row["daily_data"][prod_iso]["gd"] += gd
            row["total_lp"] += lp
            row["total_gd"] += gd
            date_totals[prod_iso]["lp"] += lp
            date_totals[prod_iso]["gd"] += gd

        # Compute HK and avg_drc per row
        for row in grouped.values():
            row["total_hk"] = sum(
                1 for v in row["daily_data"].values() if v["lp"] > 0
            )
            row["avg_drc"] = (
                round(row["total_gd"] / row["total_lp"] * 100, 1)
                if row["total_lp"]
                else 0.0
            )

        # Compute average DRC for date columns
        for dt_iso, dt_val in date_totals.items():
            dt_val["drc"] = (
                round(dt_val["gd"] / dt_val["lp"] * 100, 1)
                if dt_val["lp"]
                else 0.0
            )

        # Sort
        rows = sorted(
            grouped.values(),
            key=lambda r: (
                _natural_sort_key(r["division_code"]),
                (r["foreman_name"] or "").casefold(),
                (r["tapper_name"] or "").casefold(),
            ),
        )
        for seq, row in enumerate(rows, start=1):
            row["sequence"] = seq

        total_lp = sum(v["lp"] for v in date_totals.values())
        total_gd = sum(v["gd"] for v in date_totals.values())
        avg_drc = round(total_gd / total_lp * 100, 1) if total_lp else 0.0
        return {
            "dates": date_list,
            "date_totals": date_totals,
            "rows": rows,
            "total_hk": sum(r["total_hk"] for r in rows),
            "total_lp": total_lp,
            "avg_drc": avg_drc,
            "total_gd": total_gd,
        }

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
            "tapper_id": self.tapper_id.id,
            "total_hk": data["total_hk"],
            "total_lp": data["total_lp"],
            "avg_drc": data["avg_drc"],
            "total_gd": data["total_gd"],
            "preview_html": False,
        })
        self.env["wt.drc.report.date"].create([
            {
                "report_id": report.id,
                "sequence": seq,
                "production_date": prod_date,
                "total_lp": data["date_totals"][prod_date.isoformat()]["lp"],
                "avg_drc": data["date_totals"][prod_date.isoformat()]["drc"],
                "total_gd": data["date_totals"][prod_date.isoformat()]["gd"],
            }
            for seq, prod_date in enumerate(data["dates"], start=1)
        ])
        if data["rows"]:
            self.env["wt.drc.report.line"].create([
                {
                    "report_id": report.id,
                    "sequence": row["sequence"],
                    "badge_number": row["badge_number"],
                    "nik": row["nik"],
                    "tapper_name": row["tapper_name"],
                    "foreman_name": row["foreman_name"],
                    "division_name": row["division_name"],
                    "division_code": row["division_code"],
                    "job_title": row["job_title"],
                    "daily_data": row["daily_data"],
                    "total_hk": row["total_hk"],
                    "total_lp": row["total_lp"],
                    "avg_drc": row["avg_drc"],
                    "total_gd": row["total_gd"],
                }
                for row in data["rows"]
            ])
        report.preview_html = report._build_preview_html()
        return report._open_current_report_action()


def _natural_sort_key(value):
    return tuple(
        int(p) if p.isdigit() else p.casefold()
        for p in re.split(r"(\d+)", value or "")
    )


# ─────────────────────────────────────────────────────────────────────────────
class ReportDrc(models.AbstractModel):
    _name = "report.weightrack.report_drc_document"
    _description = "Laporan DRC"

    def _get_report_values(self, docids, data=None):
        docs = self.env["wt.drc.report"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "wt.drc.report",
            "docs": docs,
        }
