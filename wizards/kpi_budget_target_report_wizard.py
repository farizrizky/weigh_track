# -*- coding: utf-8 -*-

import base64
import io
import re
from collections import OrderedDict
from datetime import date, datetime, time

from markupsafe import Markup, escape
from pytz import UTC, timezone

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


class KpiBudgetTargetReport(models.TransientModel):
    _name = "wt.kpi.budget.target.report"
    _inherit = "wt.shipping.provenance.mixin"
    _description = "Laporan Budget Target"

    name = fields.Char(
        string="Laporan",
        default="Laporan Budget Target",
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
    year = fields.Integer(
        string="Tahun",
        readonly=True,
    )
    year_display = fields.Char(string="Tahun", readonly=True)
    budget_target_id = fields.Many2one(
        "wt.kpi.budget.target",
        string="Budget Target",
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
            "name": _("Filter Laporan Budget Target"),
            "type": "ir.actions.act_window",
            "res_model": "wt.kpi.budget.target.report.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_report_id": self.id,
                "default_company_id": self.company_id.id or self.env.company.id,
                "default_year": str(
                    self.year or fields.Date.context_today(self).year
                ),
            },
        }

    @staticmethod
    def _sum_values(value_rows):
        return [sum(values[index] for values in value_rows) for index in range(12)]

    @staticmethod
    def _variance_values(budget_values, actual_values):
        return [
            actual - budget
            for budget, actual in zip(budget_values, actual_values)
        ]

    @staticmethod
    def _ratio_values(numerators, denominators):
        return [
            (numerator / denominator * 100.0) if denominator else 0.0
            for numerator, denominator in zip(numerators, denominators)
        ]

    @staticmethod
    def _annual_ratio(numerator_values, denominator_values):
        denominator = sum(denominator_values)
        return (sum(numerator_values) / denominator * 100.0) if denominator else 0.0

    @staticmethod
    def _line_values(line):
        return [line[field_name] or 0.0 for field_name, _label in MONTH_FIELDS]

    def _year_utc_range(self):
        self.ensure_one()
        user_tz = timezone(self.env.user.tz or "UTC")
        start_local = user_tz.localize(datetime.combine(date(self.year, 1, 1), time.min))
        end_local = user_tz.localize(
            datetime.combine(date(self.year + 1, 1, 1), time.min)
        )
        return (
            start_local.astimezone(UTC).replace(tzinfo=None),
            end_local.astimezone(UTC).replace(tzinfo=None),
        )

    def _get_production_actual_values(self, division_ids):
        values = {division_id: [0.0] * 12 for division_id in division_ids}
        if not division_ids:
            return values
        records = self.env["wt.weighing"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("division_id", "in", division_ids),
                ("production_date", ">=", date(self.year, 1, 1)),
                ("production_date", "<", date(self.year + 1, 1, 1)),
            ]
        )
        for record in records:
            if record.production_date and record.division_id.id in values:
                values[record.division_id.id][record.production_date.month - 1] += (
                    record.net_weight or 0.0
                )
        return values

    def _get_sales_actual_values(self, division_ids):
        values = {division_id: [0.0] * 12 for division_id in division_ids}
        if not division_ids:
            return values

        warehouses = self.env["stock.warehouse"].search(
            [("company_id", "=", self.company_id.id)]
        )
        start_dt, end_dt = self._year_utc_range()
        quantities = {}
        for event in self._iter_delivery_shipping_source_events(
            fields.Datetime.to_string(start_dt),
            fields.Datetime.to_string(end_dt),
            warehouses,
            end_operator="<",
            transit_quantity_basis="source",
        ):
            division = event["division"]
            if not division or division.id not in values:
                continue
            movement_date = fields.Datetime.to_datetime(event["movement_date"])
            local_date = fields.Datetime.context_timestamp(self, movement_date)
            key = (local_date.month - 1, division.id, event["lot"].id)
            quantities[key] = quantities.get(key, 0.0) + event["quantity"]

        shrinkage = {}
        deliveries = self.env["wt.delivery"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("state", "in", ["delivered", "done"]),
                ("transit_shrinkage_proportion_saved", "=", True),
            ]
        )
        deliveries = deliveries.filtered(
            lambda delivery: date(self.year, 1, 1)
            <= self._delivery_business_date(delivery)
            < date(self.year + 1, 1, 1)
        )
        proportions = self.env["wt.delivery.transit.shrinkage.proportion"].search(
            [
                ("delivery_id", "in", deliveries.ids),
                ("proportion_qty", ">", 0.0),
            ]
        )
        for proportion in proportions:
            lot = proportion.lot_id
            division = lot.division_id
            if not lot or not division or division.id not in values:
                continue
            month_index = self._delivery_business_date(
                proportion.delivery_id
            ).month - 1
            key = (month_index, division.id, lot.id)
            shrinkage[key] = shrinkage.get(key, 0.0) + (
                proportion.proportion_qty or 0.0
            )

        for key, quantity in quantities.items():
            month_index, division_id, _lot_id = key
            values[division_id][month_index] += max(
                0.0, quantity - shrinkage.get(key, 0.0)
            )
        return values

    @staticmethod
    def _delivery_business_date(delivery):
        return (
            delivery.backdate_effective_at.date()
            if delivery.backdate_effective_at
            else delivery.date
        )

    def _get_factory_received_actual_values(self):
        values = [0.0] * 12
        deliveries = self.env["wt.delivery"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("state", "=", "done"),
                ("received_qty", ">", 0.0),
            ]
        )
        for delivery in deliveries:
            business_date = self._delivery_business_date(delivery)
            if business_date and business_date.year == self.year:
                values[business_date.month - 1] += delivery.received_qty or 0.0
        return values

    def _get_factory_dry_actual_values(self):
        values = [0.0] * 12
        deliveries = self.env["wt.delivery"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("state", "=", "done"),
                ("factory_dry_qty", ">", 0.0),
            ]
        )
        for delivery in deliveries:
            business_date = self._delivery_business_date(delivery)
            if business_date and business_date.year == self.year:
                values[business_date.month - 1] += (
                    delivery.factory_dry_qty or 0.0
                )
        return values

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

    @staticmethod
    def _estate_sort_key(estate):
        estate_identity = "%s %s" % (estate.code or "", estate.name or "")
        normalized_identity = estate_identity.casefold()
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

    def _append_division_section(
        self,
        rows,
        lines,
        actual_values_by_division,
        number,
        title,
        total_label,
    ):
        rows.append({"kind": "subsection", "no": number, "label": title})
        rows.append({"kind": "label", "no": "", "label": _("Produksi Cuplump")})

        grouped_lines = OrderedDict()
        sorted_lines = lines.sorted(
            key=lambda line: (
                self._estate_sort_key(line.division_id.estate_id),
                line.division_id.code or "",
                line.division_id.name or "",
                line.id,
            )
        )
        for line in sorted_lines:
            estate = line.division_id.estate_id
            grouped_lines.setdefault(
                estate.id,
                {"name": estate.display_name, "lines": self.env[line._name]},
            )
            grouped_lines[estate.id]["lines"] |= line

        all_values = []
        all_actual_values = []
        estate_names = []
        for estate_data in grouped_lines.values():
            estate_names.append(estate_data["name"])
            rows.append(
                {"kind": "estate", "no": "", "label": estate_data["name"]}
            )
            estate_values = []
            estate_actual_values = []
            for line in estate_data["lines"]:
                values = self._line_values(line)
                actual_values = actual_values_by_division.get(
                    line.division_id.id, [0.0] * 12
                )
                estate_values.append(values)
                estate_actual_values.append(actual_values)
                all_values.append(values)
                all_actual_values.append(actual_values)
                rows.append(
                    {
                        "kind": "division",
                        "no": "",
                        "label": line.division_id.display_name,
                        "unit": line.uom_name,
                        "values": values,
                        "actual_values": actual_values,
                        "variance_values": self._variance_values(
                            values, actual_values
                        ),
                        "total": sum(values),
                        "actual_total": sum(actual_values),
                        "variance_total": sum(actual_values) - sum(values),
                    }
                )
            subtotal_values = self._sum_values(estate_values)
            subtotal_actual_values = self._sum_values(estate_actual_values)
            rows.append(
                {
                    "kind": "subtotal",
                    "no": "",
                    "label": _("Jumlah %s") % estate_data["name"],
                    "unit": "Kg Basah",
                    "values": subtotal_values,
                    "actual_values": subtotal_actual_values,
                    "variance_values": self._variance_values(
                        subtotal_values, subtotal_actual_values
                    ),
                    "total": sum(subtotal_values),
                    "actual_total": sum(subtotal_actual_values),
                    "variance_total": sum(subtotal_actual_values)
                    - sum(subtotal_values),
                }
            )

        total_values = self._sum_values(all_values)
        total_actual_values = self._sum_values(all_actual_values)
        if estate_names:
            total_label = "%s %s" % (total_label, " + ".join(estate_names))
        rows.append(
            {
                "kind": "grand_total",
                "no": "",
                "label": total_label,
                "unit": "Kg Basah",
                "values": total_values,
                "actual_values": total_actual_values,
                "variance_values": self._variance_values(
                    total_values, total_actual_values
                ),
                "total": sum(total_values),
                "actual_total": sum(total_actual_values),
                "variance_total": sum(total_actual_values) - sum(total_values),
            }
        )
        return total_values, total_actual_values

    def _get_report_rows(self):
        self.ensure_one()
        budget = self.budget_target_id
        if not budget:
            return []

        rows = [
            {
                "kind": "section",
                "no": "I",
                "label": _("TARGET PRODUKSI DAN PENJUALAN"),
            }
        ]
        division_ids = (
            budget.production_target_line_ids
            | budget.sales_target_line_ids
        ).mapped("division_id").ids
        production_actual_by_division = self._get_production_actual_values(
            division_ids
        )
        sales_actual_by_division = self._get_sales_actual_values(division_ids)

        production_values, production_actual_values = self._append_division_section(
            rows,
            budget.production_target_line_ids,
            production_actual_by_division,
            "1",
            _("TARGET PRODUKSI"),
            _("Jumlah Produksi"),
        )
        sales_values, sales_actual_values = self._append_division_section(
            rows,
            budget.sales_target_line_ids,
            sales_actual_by_division,
            "2",
            _("TARGET PENJUALAN"),
            _("Jumlah Penjualan"),
        )

        monthly_values = {
            line_type: {line.month: line.value for line in lines}
            for line_type, lines in (
                ("factory_received", budget.factory_received_line_ids),
                ("dry_production", budget.dry_production_line_ids),
            )
        }
        factory_values = [
            monthly_values["factory_received"].get("%02d" % month, 0.0)
            for month in range(1, 13)
        ]
        factory_actual_values = self._get_factory_received_actual_values()
        dry_values = [
            monthly_values["dry_production"].get("%02d" % month, 0.0)
            for month in range(1, 13)
        ]
        dry_actual_values = self._get_factory_dry_actual_values()
        storage_loss_values = self._ratio_values(
            [production - sales for production, sales in zip(production_values, sales_values)],
            production_values,
        )
        storage_loss_actual_values = self._ratio_values(
            [
                production - sales
                for production, sales in zip(
                    production_actual_values, sales_actual_values
                )
            ],
            production_actual_values,
        )
        transit_loss_values = self._ratio_values(
            [sales - factory for sales, factory in zip(sales_values, factory_values)],
            sales_values,
        )
        transit_loss_actual_values = self._ratio_values(
            [
                sales - factory
                for sales, factory in zip(
                    sales_actual_values, factory_actual_values
                )
            ],
            sales_actual_values,
        )
        drc_values = self._ratio_values(dry_values, factory_values)
        drc_actual_values = self._ratio_values(
            dry_actual_values, factory_actual_values
        )

        storage_loss_total = self._annual_ratio(
            [
                production - sales
                for production, sales in zip(production_values, sales_values)
            ],
            production_values,
        )
        storage_loss_actual_total = self._annual_ratio(
            [
                production - sales
                for production, sales in zip(
                    production_actual_values, sales_actual_values
                )
            ],
            production_actual_values,
        )
        transit_loss_total = self._annual_ratio(
            [
                sales - factory
                for sales, factory in zip(sales_values, factory_values)
            ],
            sales_values,
        )
        transit_loss_actual_total = self._annual_ratio(
            [
                sales - factory
                for sales, factory in zip(
                    sales_actual_values, factory_actual_values
                )
            ],
            sales_actual_values,
        )
        drc_total = self._annual_ratio(dry_values, factory_values)
        drc_actual_total = self._annual_ratio(
            dry_actual_values, factory_actual_values
        )

        rows.extend(
            [
                {
                    "kind": "metric",
                    "no": "3",
                    "label": _("Persentase Susut Penyimpanan"),
                    "unit": "%",
                    "values": storage_loss_values,
                    "actual_values": storage_loss_actual_values,
                    "variance_values": self._variance_values(
                        storage_loss_values, storage_loss_actual_values
                    ),
                    "total": storage_loss_total,
                    "actual_total": storage_loss_actual_total,
                    "variance_total": storage_loss_actual_total
                    - storage_loss_total,
                    "percentage": True,
                },
                {
                    "kind": "metric",
                    "no": "4",
                    "label": _("Susut Perjalanan ke Pabrik"),
                    "unit": "%",
                    "values": transit_loss_values,
                    "actual_values": transit_loss_actual_values,
                    "variance_values": self._variance_values(
                        transit_loss_values, transit_loss_actual_values
                    ),
                    "total": transit_loss_total,
                    "actual_total": transit_loss_actual_total,
                    "variance_total": transit_loss_actual_total
                    - transit_loss_total,
                    "percentage": True,
                },
                {
                    "kind": "metric",
                    "no": "5",
                    "label": _("Produksi Terima Pabrik"),
                    "unit": "Kg Basah",
                    "values": factory_values,
                    "actual_values": factory_actual_values,
                    "variance_values": self._variance_values(
                        factory_values, factory_actual_values
                    ),
                    "total": sum(factory_values),
                    "actual_total": sum(factory_actual_values),
                    "variance_total": sum(factory_actual_values)
                    - sum(factory_values),
                },
                {
                    "kind": "metric",
                    "no": "6",
                    "label": _("DRC"),
                    "unit": "%",
                    "values": drc_values,
                    "actual_values": drc_actual_values,
                    "variance_values": self._variance_values(
                        drc_values, drc_actual_values
                    ),
                    "total": drc_total,
                    "actual_total": drc_actual_total,
                    "variance_total": drc_actual_total - drc_total,
                    "percentage": True,
                },
                {
                    "kind": "metric",
                    "no": "7",
                    "label": _("Produksi Kering"),
                    "unit": "Kg Kering",
                    "values": dry_values,
                    "actual_values": dry_actual_values,
                    "variance_values": self._variance_values(
                        dry_values, dry_actual_values
                    ),
                    "total": sum(dry_values),
                    "actual_total": sum(dry_actual_values),
                    "variance_total": sum(dry_actual_values) - sum(dry_values),
                },
            ]
        )
        for row in rows:
            if "values" in row:
                row["achievement_values"] = self._ratio_values(
                    row["actual_values"], row["values"]
                )
                row["achievement_total"] = (
                    row["actual_total"] / row["total"] * 100.0
                    if row["total"] else 0.0
                )
        return rows

    @staticmethod
    def _format_number(value, percentage=False):
        return ("{:,.1f}" if percentage else "{:,.2f}").format(value or 0.0)

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
            '<table style="border-collapse:collapse;min-width:5600px;width:100%;">',
            "<thead><tr>",
        ]
        for header in (_("No"), _("Uraian"), _("Norma"), _("Satuan")):
            parts.append(
                '<th rowspan="2" style="background:#a9d18e;border:1px solid #475569;'
                'padding:6px;text-align:center;vertical-align:middle;">%s</th>'
                % escape(header)
            )
        for _field_name, month_label in MONTH_FIELDS:
            parts.append(
                '<th colspan="4" style="background:#a9d18e;border:1px solid #475569;'
                'padding:6px;text-align:center;white-space:nowrap;">%s</th>'
                % escape(month_label.upper())
            )
        parts.append(
            '<th colspan="4" style="background:#a9d18e;border:1px solid #475569;'
            'padding:6px;text-align:center;white-space:nowrap;">%s</th>'
            % escape(_("JUMLAH"))
        )
        parts.append("</tr><tr>")
        for _index in range(13):
            for header in (_("Budget"), _("Realisasi"), _("Selisih"), _("Ketercapaian (%)")):
                parts.append(
                    '<th style="background:#d9ead3;border:1px solid #475569;'
                    'padding:5px;text-align:center;white-space:nowrap;">%s</th>'
                    % escape(header)
                )
        parts.append("</tr></thead><tbody>")

        row_styles = {
            "section": "background:#d9ead3;font-weight:700;",
            "subsection": "font-weight:700;",
            "label": "font-weight:600;",
            "estate": "font-weight:600;",
            "subtotal": "background:#fff200;font-weight:700;",
            "grand_total": "background:#a9d18e;font-weight:700;",
            "metric": "font-weight:600;",
        }
        for row in rows:
            kind = row["kind"]
            style = row_styles.get(kind, "")
            if kind in {"section", "subsection", "label", "estate"}:
                parts.append("<tr>")
                parts.append(
                    '<td style="border:1px solid #94a3b8;padding:5px;'
                    'text-align:center;%s">%s</td>' % (style, escape(row["no"]))
                )
                parts.append(
                    '<td colspan="55" style="border:1px solid #94a3b8;'
                    'padding:5px;%s">%s</td>' % (style, escape(row["label"]))
                )
                parts.append("</tr>")
                continue

            parts.append("<tr>")
            parts.append(
                '<td style="border:1px solid #94a3b8;padding:5px;'
                'text-align:center;%s">%s</td>' % (style, escape(row["no"]))
            )
            parts.append(
                '<td style="border:1px solid #94a3b8;padding:5px;'
                'white-space:nowrap;%s">%s</td>' % (style, escape(row["label"]))
            )
            parts.append(
                '<td style="border:1px solid #94a3b8;padding:5px;%s"></td>' % style
            )
            parts.append(
                '<td style="border:1px solid #94a3b8;padding:5px;'
                'white-space:nowrap;%s">%s</td>' % (style, escape(row["unit"]))
            )
            percentage = row.get("percentage", False)
            for budget_value, actual_value, variance_value, achievement_value in zip(
                row["values"],
                row["actual_values"],
                row["variance_values"],
                row["achievement_values"],
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
                            self._format_number(value, percentage),
                        )
                    )
                parts.append(
                    '<td style="border:1px solid #94a3b8;padding:5px;'
                    'text-align:right;white-space:nowrap;%s">%s%%</td>'
                    % (style, self._format_number(achievement_value))
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
                        self._format_number(value, percentage),
                    )
                )
            parts.append(
                '<td style="border:1px solid #94a3b8;padding:5px;'
                'text-align:right;white-space:nowrap;%s">%s%%</td>'
                % (style, self._format_number(row["achievement_total"]))
            )
            parts.append("</tr>")
        parts.append("</tbody></table></div>")
        return Markup("".join(parts))

    def action_export_excel(self):
        self.ensure_one()
        if not self.is_filtered or not self.budget_target_id:
            raise ValidationError(
                _("Silakan terapkan filter sebelum mengekspor laporan.")
            )
        if xlsxwriter is None:
            raise ValidationError(_("Package xlsxwriter belum terinstall."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Budget Target %s" % self.year)
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
                "bg_color": "#A9D18E",
            }
        )
        subheader_format = workbook.add_format(
            {
                **base_font,
                "bold": True,
                "align": "center",
                "valign": "vcenter",
                "border": 1,
                "bg_color": "#D9EAD3",
            }
        )
        text_format = workbook.add_format({**base_font, "border": 1})
        number_format = workbook.add_format(
            {**base_font, "border": 1, "num_format": "#,##0.00"}
        )
        percent_format = workbook.add_format(
            {**base_font, "border": 1, "num_format": "0.0"}
        )
        section_format = workbook.add_format(
            {**base_font, "bold": True, "border": 1, "bg_color": "#D9EAD3"}
        )
        subsection_format = workbook.add_format(
            {**base_font, "bold": True, "border": 1}
        )
        label_format = workbook.add_format(
            {**base_font, "bold": True, "border": 1}
        )
        subtotal_text_format = workbook.add_format(
            {**base_font, "bold": True, "border": 1, "bg_color": "#FFF200"}
        )
        subtotal_number_format = workbook.add_format(
            {
                **base_font,
                "bold": True,
                "border": 1,
                "bg_color": "#FFF200",
                "num_format": "#,##0.00",
            }
        )
        total_text_format = workbook.add_format(
            {**base_font, "bold": True, "border": 1, "bg_color": "#A9D18E"}
        )
        total_number_format = workbook.add_format(
            {
                **base_font,
                "bold": True,
                "border": 1,
                "bg_color": "#A9D18E",
                "num_format": "#,##0.00",
            }
        )
        metric_text_format = workbook.add_format(
            {**base_font, "bold": True, "border": 1}
        )
        metric_number_format = workbook.add_format(
            {**base_font, "bold": True, "border": 1, "num_format": "#,##0.00"}
        )
        metric_percent_format = workbook.add_format(
            {**base_font, "bold": True, "border": 1, "num_format": "0.0"}
        )
        positive_variance_format = workbook.add_format(
            {"font_color": "#15803D"}
        )
        negative_variance_format = workbook.add_format(
            {"font_color": "#DC2626"}
        )
        achievement_formats = {
            kind: workbook.add_format({
                **base_font, "border": 1, "num_format": "0.00%", **style
            })
            for kind, style in (
                ("default", {}),
                ("subtotal", {"bold": True, "bg_color": "#FFF200"}),
                ("grand_total", {"bold": True, "bg_color": "#A9D18E"}),
                ("metric", {"bold": True}),
            )
        }

        sheet.set_column("A:A", 5)
        sheet.set_column("B:B", 38)
        sheet.set_column("C:C", 10)
        sheet.set_column("D:D", 12)
        sheet.set_column(4, 55, 13)

        last_column = 55
        sheet.merge_range(0, 0, 0, last_column, self.company_id.name or "", title_format)
        sheet.merge_range(1, 0, 1, last_column, _("BUDGET TARGET"), title_format)
        sheet.merge_range(
            2, 0, 2, last_column, _("TAHUN %s") % self.year, title_format
        )
        for column, header in enumerate((_("NO"), _("URAIAN"), _("NORMA"), _("SATUAN"))):
            sheet.merge_range(4, column, 5, column, header, header_format)
        for month_index, (_field_name, month_label) in enumerate(MONTH_FIELDS):
            start_column = 4 + (month_index * 4)
            sheet.merge_range(
                4,
                start_column,
                4,
                start_column + 3,
                month_label.upper(),
                header_format,
            )
            for offset, header in enumerate(
                (_("BUDGET"), _("REALISASI"), _("SELISIH"), _("KETERCAPAIAN (%)"))
            ):
                sheet.write(5, start_column + offset, header, subheader_format)
        total_start_column = 52
        sheet.merge_range(
            4,
            total_start_column,
            4,
            last_column,
            _("JUMLAH"),
            header_format,
        )
        for offset, header in enumerate(
            (_("BUDGET"), _("REALISASI"), _("SELISIH"), _("KETERCAPAIAN (%)"))
        ):
            sheet.write(5, total_start_column + offset, header, subheader_format)

        row_index = 6
        rows = self._get_report_rows()
        for row in rows:
            kind = row["kind"]
            if kind in {"section", "subsection", "label", "estate"}:
                row_format = (
                    section_format if kind == "section" else subsection_format
                )
                if kind in {"label", "estate"}:
                    row_format = label_format
                sheet.write(row_index, 0, row["no"], row_format)
                sheet.merge_range(
                    row_index, 1, row_index, last_column, row["label"], row_format
                )
                row_index += 1
                continue

            if kind == "subtotal":
                text_cell_format = subtotal_text_format
                value_cell_format = subtotal_number_format
            elif kind == "grand_total":
                text_cell_format = total_text_format
                value_cell_format = total_number_format
            elif kind == "metric":
                text_cell_format = metric_text_format
                value_cell_format = (
                    metric_percent_format
                    if row.get("percentage")
                    else metric_number_format
                )
            else:
                text_cell_format = text_format
                value_cell_format = percent_format if row.get("percentage") else number_format

            sheet.write(row_index, 0, row["no"], text_cell_format)
            sheet.write(row_index, 1, row["label"], text_cell_format)
            sheet.write(row_index, 2, "", text_cell_format)
            sheet.write(row_index, 3, row["unit"], text_cell_format)
            achievement_format = achievement_formats.get(kind, achievement_formats["default"])
            current_column = 4
            for budget_value, actual_value, variance_value, achievement_value in zip(
                row["values"],
                row["actual_values"],
                row["variance_values"],
                row["achievement_values"],
            ):
                for value in (budget_value, actual_value, variance_value):
                    sheet.write_number(
                        row_index, current_column, value, value_cell_format
                    )
                    current_column += 1
                sheet.write_number(row_index, current_column, achievement_value / 100.0, achievement_format)
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
            sheet.write_number(row_index, current_column, row["achievement_total"] / 100.0, achievement_format)
            row_index += 1

        variance_columns = [4 + (month_index * 4) + 2 for month_index in range(12)]
        variance_columns.append(total_start_column + 2)
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

        filename = "Laporan Budget Target - %s.xlsx" % self.year
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
            "weightrack.action_wt_kpi_budget_target_report"
        )
        action["res_id"] = self.id
        return action


class KpiBudgetTargetReportWizard(models.TransientModel):
    _name = "wt.kpi.budget.target.report.wizard"
    _description = "Filter Laporan Budget Target"

    report_id = fields.Many2one(
        "wt.kpi.budget.target.report",
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

    def action_apply_filter(self):
        self.ensure_one()
        year_number = self._year_number()
        budget = self.env["wt.kpi.budget.target"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("year", "=", year_number),
                ("state", "=", "valid"),
            ],
            limit=1,
        )
        if not budget:
            raise ValidationError(
                _(
                    "Budget Target Valid untuk tahun %(year)s tidak ditemukan.",
                    year=year_number,
                )
            )

        report = self.report_id
        report.write(
            {
                "name": _("Laporan Budget Target"),
                "is_filtered": True,
                "company_id": self.company_id.id,
                "year": year_number,
                "year_display": self.year,
                "budget_target_id": budget.id,
                "preview_html": False,
            }
        )
        report.preview_html = report._build_preview_html()
        return report._open_current_report_action()
