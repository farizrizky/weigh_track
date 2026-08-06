# -*- coding: utf-8 -*-

import base64
import io
from datetime import datetime, time, timedelta

from pytz import UTC, timezone

from odoo import _, fields, models
from odoo.exceptions import ValidationError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


LOCATION_TYPE_SELECTION = [
    ("warehouse", "Warehouse"),
    ("field", "Field"),
]

WEIGHING_STATE_SELECTION = [
    ("not_receipted", "Not Receipted"),
    ("in_production_receipt", "In Production Receipt"),
    ("receipt_validated", "Receipt Validated"),
    ("receipt_cancelled", "Receipt Cancelled"),
]


class ManualWeighingReport(models.TransientModel):
    _name = "wt.manual.weighing.report"
    _description = "Manual Weighing Report"

    name = fields.Char(
        string="Report",
        default="Manual Weighing Report",
        readonly=True,
    )
    is_filtered = fields.Boolean(
        string="Filtered",
        default=False,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        readonly=True,
    )
    date_start = fields.Date(
        string="Start Date",
        readonly=True,
    )
    date_end = fields.Date(
        string="End Date",
        readonly=True,
    )
    location_type = fields.Selection(
        LOCATION_TYPE_SELECTION,
        string="Weighing Location Type",
        readonly=True,
    )
    total_records = fields.Integer(
        string="Total Records",
        readonly=True,
    )
    line_ids = fields.One2many(
        "wt.manual.weighing.report.line",
        "report_id",
        string="Lines",
        readonly=True,
    )

    def action_open_filter(self):
        self.ensure_one()
        return {
            "name": _("Filter Manual Weighing Report"),
            "type": "ir.actions.act_window",
            "res_model": "wt.manual.weighing.report.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_report_id": self.id,
                "default_company_id": self.company_id.id or self.env.company.id,
                "default_date_start": self.date_start
                or fields.Date.start_of(fields.Date.context_today(self), "month"),
                "default_date_end": self.date_end or fields.Date.context_today(self),
                "default_location_type": self.location_type or "warehouse",
            },
        }

    def action_print_pdf(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Please apply a filter before printing the report."))
        return self.env.ref(
            "weightrack.action_report_manual_weighing_pdf"
        ).report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not self.is_filtered:
            raise ValidationError(_("Please apply a filter before exporting the report."))
        if xlsxwriter is None:
            raise ValidationError(_("The xlsxwriter Python package is not installed."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Penimbangan Manual")

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
        text_format = workbook.add_format(
            {"border": 1, "valign": "top", "text_wrap": True}
        )
        center_format = workbook.add_format(
            {
                "border": 1,
                "align": "center",
                "valign": "top",
                "text_wrap": True,
            }
        )

        headers = [
            _("Date"),
            _("Weighing Number"),
            _("Estate"),
            _("Division"),
            _("Tapper"),
            _("Foreman"),
            _("Operator"),
            _("Device Name"),
            _("Device ID"),
            _("Weighing Location"),
            _("Weighing Location Type"),
            _("Manual Weighing Reason"),
            _("Status"),
        ]
        last_column = len(headers) - 1
        sheet.merge_range(0, 0, 0, last_column, self.company_id.name or "", title_format)
        sheet.merge_range(
            1,
            0,
            1,
            last_column,
            _("MANUAL WEIGHING REPORT"),
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
        sheet.write(4, 0, _("Weighing Location Type"), label_format)
        sheet.write(4, 1, self._get_location_type_display())
        sheet.write(4, 3, _("Total Records"), label_format)
        sheet.write(4, 4, self.total_records)

        widths = [18, 24, 18, 18, 22, 22, 22, 20, 20, 24, 18, 34, 22]
        header_row = 6
        for column, (header, width) in enumerate(zip(headers, widths)):
            sheet.set_column(column, column, width)
            sheet.write(header_row, column, header, header_format)
        sheet.freeze_panes(header_row + 1, 2)
        if self.line_ids:
            sheet.autofilter(header_row, 0, header_row + len(self.line_ids), last_column)

        row_index = header_row + 1
        for line in self.line_ids.sorted("sequence"):
            values = [
                line.get_event_date_display(),
                line.weighing_number or "",
                line.estate_name or "",
                line.division_name or "",
                line.tapper_name or "",
                line.foreman_name or "",
                line.operator_name or "",
                line.device_name or "",
                line.device_identifier or "",
                line.weighing_location_name or "",
                line.get_location_type_display(),
                line.manual_weighing_reason or "",
                line.get_state_display(),
            ]
            for column, value in enumerate(values):
                cell_format = center_format if column in {0, 10, 12} else text_format
                sheet.write(row_index, column, value, cell_format)
            row_index += 1

        workbook.close()
        output.seek(0)
        filename = "Laporan Penimbangan Manual - %s - %s.xlsx" % (
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

    def _get_location_type_display(self):
        self.ensure_one()
        return dict(
            self._fields["location_type"]._description_selection(self.env)
        ).get(self.location_type, "")

    def _open_current_report_action(self):
        self.ensure_one()
        return {
            "name": _("Manual Weighing Report"),
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }


class ManualWeighingReportLine(models.TransientModel):
    _name = "wt.manual.weighing.report.line"
    _description = "Manual Weighing Report Line"
    _order = "sequence, id"

    report_id = fields.Many2one(
        "wt.manual.weighing.report",
        string="Report",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(
        string="Sequence",
        readonly=True,
    )
    event_date = fields.Datetime(
        string="Date",
        readonly=True,
    )
    weighing_number = fields.Char(
        string="Weighing Number",
        readonly=True,
    )
    estate_name = fields.Char(
        string="Estate",
        readonly=True,
    )
    division_name = fields.Char(
        string="Division",
        readonly=True,
    )
    tapper_name = fields.Char(
        string="Tapper",
        readonly=True,
    )
    foreman_name = fields.Char(
        string="Foreman",
        readonly=True,
    )
    operator_name = fields.Char(
        string="Operator",
        readonly=True,
    )
    device_name = fields.Char(
        string="Device Name",
        readonly=True,
    )
    device_identifier = fields.Char(
        string="Device ID",
        readonly=True,
    )
    weighing_location_name = fields.Char(
        string="Weighing Location",
        readonly=True,
    )
    location_type = fields.Selection(
        LOCATION_TYPE_SELECTION,
        string="Weighing Location Type",
        readonly=True,
    )
    manual_weighing_reason = fields.Text(
        string="Manual Weighing Reason",
        readonly=True,
    )
    state = fields.Selection(
        WEIGHING_STATE_SELECTION,
        string="Status",
        readonly=True,
    )

    def get_event_date_display(self):
        self.ensure_one()
        if not self.event_date:
            return ""
        local_date = fields.Datetime.context_timestamp(self, self.event_date)
        return local_date.strftime("%d/%m/%Y %H:%M")

    def get_location_type_display(self):
        self.ensure_one()
        return dict(
            self._fields["location_type"]._description_selection(self.env)
        ).get(self.location_type, "")

    def get_state_display(self):
        self.ensure_one()
        return dict(
            self._fields["state"]._description_selection(self.env)
        ).get(self.state, "")


class ManualWeighingReportWizard(models.TransientModel):
    _name = "wt.manual.weighing.report.wizard"
    _description = "Manual Weighing Report Wizard"

    report_id = fields.Many2one(
        "wt.manual.weighing.report",
        string="Report",
        required=True,
        ondelete="cascade",
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
    location_type = fields.Selection(
        LOCATION_TYPE_SELECTION,
        string="Weighing Location Type",
        required=True,
        default="warehouse",
    )

    def _get_utc_range(self):
        self.ensure_one()
        if self.date_start > self.date_end:
            raise ValidationError(_("Start Date cannot be later than End Date."))
        try:
            user_timezone = timezone(self.env.user.tz or "UTC")
        except Exception:
            user_timezone = UTC
        start_local = user_timezone.localize(
            datetime.combine(self.date_start, time.min)
        )
        end_local = user_timezone.localize(
            datetime.combine(self.date_end + timedelta(days=1), time.min)
        )
        return (
            start_local.astimezone(UTC).replace(tzinfo=None),
            end_local.astimezone(UTC).replace(tzinfo=None),
        )

    def _get_domain_and_order(self):
        self.ensure_one()
        start_utc, end_utc = self._get_utc_range()
        if self.location_type == "warehouse":
            date_field = "weighing_date"
            manual_field = "is_manual_weighing"
        else:
            date_field = "initial_weighing_date"
            manual_field = "initial_is_manual_weighing"
        return (
            [
                ("company_id", "=", self.company_id.id),
                (manual_field, "=", True),
                (date_field, ">=", start_utc),
                (date_field, "<", end_utc),
            ],
            "%s, name, id" % date_field,
        )

    def _prepare_line_values(self, record, sequence):
        self.ensure_one()
        if self.location_type == "warehouse":
            device = record.device_record_id
            event_date = record.weighing_date
            operator_name = record.operator_employee_id.name or ""
            device_name = device.name or ""
            device_identifier = record.device_id or device.device_id or ""
            location_name = record.weighing_location_id.display_name or ""
            manual_reason = record.manual_weighing_reason or ""
        else:
            device = record.initial_device_id
            event_date = record.initial_weighing_date
            operator_name = (
                record.initial_device_employee_name
                or record.operator_employee_id.name
                or ""
            )
            device_name = device.name or ""
            device_identifier = device.device_id or ""
            location_name = record.initial_weighing_location_id.display_name or ""
            manual_reason = record.initial_manual_weighing_reason or ""

        return {
            "sequence": sequence,
            "event_date": event_date,
            "weighing_number": record.name or "",
            "estate_name": record.estate_id.name or "",
            "division_name": record.division_id.name or "",
            "tapper_name": record.tapper_employee_id.name or "",
            "foreman_name": record.foreman_employee_id.name or "",
            "operator_name": operator_name,
            "device_name": device_name,
            "device_identifier": device_identifier,
            "weighing_location_name": location_name,
            "location_type": self.location_type,
            "manual_weighing_reason": manual_reason,
            "state": record.state,
        }

    def action_apply_filter(self):
        self.ensure_one()
        domain, order = self._get_domain_and_order()
        records = self.env["wt.weighing"].search(domain, order=order)
        report = self.report_id
        report.line_ids.unlink()
        report.write(
            {
                "is_filtered": True,
                "company_id": self.company_id.id,
                "date_start": self.date_start,
                "date_end": self.date_end,
                "location_type": self.location_type,
                "total_records": len(records),
            }
        )
        if records:
            self.env["wt.manual.weighing.report.line"].create(
                [
                    {
                        "report_id": report.id,
                        **self._prepare_line_values(record, sequence),
                    }
                    for sequence, record in enumerate(records, start=1)
                ]
            )
        return report._open_current_report_action()


class ReportManualWeighing(models.AbstractModel):
    _name = "report.weightrack.report_manual_weighing_document"
    _description = "Manual Weighing Report"

    def _get_report_values(self, docids, data=None):
        docs = self.env["wt.manual.weighing.report"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "wt.manual.weighing.report",
            "docs": docs,
        }
