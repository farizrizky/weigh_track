from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FieldProduction(models.Model):
    _name = "wt.field.production"
    _description = "Field Production"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "production_date desc, id desc"

    name = fields.Char(
        string="Nomor",
        default="/",
        readonly=True,
        copy=False,
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        required=True,
        default=lambda self: self.env.company,
        readonly=True,
        index=True,
        tracking=True,
    )
    production_date = fields.Date(
        string="Tanggal Produksi",
        required=True,
        default=lambda self: fields.Date.context_today(self),
        index=True,
        tracking=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Divisi",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    production_receipt_ids = fields.Many2many(
        "wt.production.receipt",
        "wt_field_production_receipt_rel",
        "field_production_id",
        "receipt_id",
        string="Penerimaan Produksi",
        compute="_compute_production_receipts",
        store=True,
    )
    total_production_weight = fields.Float(
        string="Total Berat Produksi (kg)",
        digits=(16, 2),
        compute="_compute_production_receipts",
        store=True,
        tracking=True,
    )
    total_field_weight = fields.Float(
        string="Total Berat Field (kg)",
        digits=(16, 2),
        compute="_compute_total_field_weight",
        store=True,
    )
    field_line_ids = fields.One2many(
        "wt.field.production.line",
        "production_id",
        string="Field",
        copy=False,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("selesai", "Selesai"),
        ],
        string="Status",
        default="draft",
        required=True,
        index=True,
        tracking=True,
    )
    note = fields.Text(string="Catatan")

    @api.model_create_multi
    def create(self, vals_list):
        sequence_model = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "/":
                sequence_date = (
                    fields.Date.to_date(vals["production_date"])
                    if vals.get("production_date")
                    else fields.Date.context_today(self)
                )
                vals["name"] = sequence_model.next_by_code(
                    "wt.field.production",
                    sequence_date=sequence_date,
                )
                if not vals["name"]:
                    raise ValidationError(
                        _("Sequence Field Production belum dikonfigurasi.")
                    )
        return super().create(vals_list)

    @api.depends("production_date", "division_id", "company_id")
    def _compute_production_receipts(self):
        Receipt = self.env["wt.production.receipt"]
        for rec in self:
            if rec.production_date and rec.division_id and rec.company_id:
                receipts = Receipt.search([
                    ("company_id", "=", rec.company_id.id),
                    ("production_date", "=", rec.production_date),
                    ("division_id", "=", rec.division_id.id),
                    ("state", "=", "validated"),
                ])
                rec.production_receipt_ids = receipts
                rec.total_production_weight = sum(
                    receipts.mapped("total_stock_weight")
                )
            else:
                rec.production_receipt_ids = False
                rec.total_production_weight = 0.0

    @api.depends("field_line_ids.today_production_weight")
    def _compute_total_field_weight(self):
        for rec in self:
            rec.total_field_weight = sum(
                rec.field_line_ids.mapped("today_production_weight")
            )

    @api.onchange("division_id", "production_date")
    def _onchange_load_field_lines(self):
        """Auto-load field lines dari wt.field yang memiliki divisi ini."""
        self.field_line_ids = [(5, 0, 0)]
        if self.division_id:
            fields_in_division = self.env["wt.field"].search([
                ("active", "=", True),
                ("division_ids", "in", self.division_id.id),
            ])
            lines = []
            for wt_field in fields_in_division:
                lines.append((0, 0, {
                    "field_id": wt_field.id,
                    "today_production_weight": 0.0,
                }))
            self.field_line_ids = lines

    def action_validate(self):
        """Validasi: cek berat balance lalu set state selesai."""
        for rec in self:
            if not rec.production_receipt_ids:
                raise ValidationError(
                    _("Tidak ada Penerimaan Produksi yang tervalidasi untuk tanggal dan divisi ini.")
                )
            total_field = sum(rec.field_line_ids.mapped("today_production_weight"))
            if abs(total_field - rec.total_production_weight) > 0.01:
                raise ValidationError(
                    _(
                        "Total berat field (%.2f kg) harus sama persis dengan "
                        "total berat produksi dari penerimaan (%.2f kg)."
                    ) % (total_field, rec.total_production_weight)
                )
            rec.state = "selesai"

    def action_set_draft(self):
        """Reset ke Draft dari Selesai."""
        for rec in self:
            rec.state = "draft"

    def action_import_excel(self):
        """Buka wizard import Excel untuk mengisi berat produksi field."""
        self.ensure_one()
        return {
            "name": _("Import Excel"),
            "type": "ir.actions.act_window",
            "res_model": "wt.field.production.import.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_production_id": self.id,
            },
        }

    def action_export_excel(self):
        """Export data produksi field ke file Excel."""
        self.ensure_one()
        try:
            import base64
            import io
            import xlsxwriter
        except ImportError:
            raise ValidationError(_("Package xlsxwriter belum terinstall."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("Produksi Field")

        # --- Formats ---
        title_fmt = workbook.add_format({"bold": True, "font_size": 14, "align": "center"})
        label_fmt = workbook.add_format({"bold": True})
        header_fmt = workbook.add_format({
            "bold": True, "align": "center", "valign": "vcenter",
            "border": 1, "text_wrap": True, "bg_color": "#E2E8F0",
        })
        text_fmt = workbook.add_format({"border": 1, "valign": "vcenter"})
        center_fmt = workbook.add_format({"border": 1, "align": "center", "valign": "vcenter"})
        number_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.00", "valign": "vcenter"})
        total_label_fmt = workbook.add_format({
            "bold": True, "border": 1, "align": "right",
            "valign": "vcenter", "bg_color": "#F8FAFC",
        })
        total_number_fmt = workbook.add_format({
            "bold": True, "border": 1, "num_format": "#,##0.00",
            "valign": "vcenter", "bg_color": "#F8FAFC",
        })

        # --- Header info ---
        last_col = 5  # columns: No, Field, Clone, HA, Hari Ini, To Date
        sheet.merge_range(0, 0, 0, last_col, self.company_id.name or "", title_fmt)
        sheet.merge_range(1, 0, 1, last_col, "LAPORAN PRODUKSI FIELD", title_fmt)
        sheet.write(3, 0, "Nomor", label_fmt)
        sheet.write(3, 1, self.name or "")
        sheet.write(4, 0, "Tanggal Produksi", label_fmt)
        sheet.write(4, 1, self.production_date.strftime("%d/%m/%Y") if self.production_date else "")
        sheet.write(4, 3, "Divisi", label_fmt)
        sheet.write(4, 4, self.division_id.display_name or "")
        sheet.write(5, 0, "Status", label_fmt)
        sheet.write(5, 1, dict(self._fields["state"].selection).get(self.state, ""))

        # --- Column widths ---
        sheet.set_column(0, 0, 6)
        sheet.set_column(1, 1, 14)
        sheet.set_column(2, 2, 14)
        sheet.set_column(3, 3, 10)
        sheet.set_column(4, 4, 22)
        sheet.set_column(5, 5, 22)

        # --- Table header ---
        header_row = 7
        headers = ["No.", "Field", "Clone", "HA", "Produksi Hari Ini (kg)", "To Date (kg)"]
        for col, header in enumerate(headers):
            sheet.write(header_row, col, header, header_fmt)
        sheet.freeze_panes(header_row + 1, 0)

        # --- Data rows ---
        row = header_row + 1
        total_today = 0.0
        total_todate = 0.0
        for seq, line in enumerate(self.field_line_ids, start=1):
            to_date_val = line.to_date_weight if self.state == "selesai" else 0.0
            sheet.write(row, 0, seq, center_fmt)
            sheet.write(row, 1, line.field_id.display_name or "", text_fmt)
            sheet.write(row, 2, line.clone or "", text_fmt)
            sheet.write(row, 3, line.ha or 0.0, number_fmt)
            sheet.write(row, 4, line.today_production_weight or 0.0, number_fmt)
            sheet.write(row, 5, to_date_val, number_fmt)
            total_today += line.today_production_weight or 0.0
            total_todate += to_date_val
            row += 1

        # --- Total row ---
        sheet.merge_range(row, 0, row, 3, "Total", total_label_fmt)
        sheet.write(row, 4, total_today, total_number_fmt)
        sheet.write(row, 5, total_todate, total_number_fmt)

        workbook.close()
        output.seek(0)
        filename = "Produksi Field - %s - %s.xlsx" % (
            self.name,
            self.production_date.strftime("%Y%m%d") if self.production_date else "",
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

    def action_export_pdf(self):
        """Export laporan produksi field ke PDF."""
        self.ensure_one()
        return self.env.ref(
            "weightrack.action_report_field_production_pdf"
        ).report_action(self)


class FieldProductionLine(models.Model):
    _name = "wt.field.production.line"
    _description = "Field Production Line"
    _order = "sequence, id"

    production_id = fields.Many2one(
        "wt.field.production",
        string="Field Production",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(string="Urutan", default=10)
    field_id = fields.Many2one(
        "wt.field",
        string="Field",
        required=True,
        ondelete="restrict",
        index=True,
    )
    clone = fields.Char(
        string="Clone",
        related="field_id.clone",
        store=True,
        readonly=True,
    )
    ha = fields.Float(
        string="HA",
        digits=(16, 2),
        related="field_id.ha",
        store=True,
        readonly=True,
    )
    today_production_weight = fields.Float(
        string="Produksi Hari Ini (kg)",
        digits=(16, 2),
        default=0.0,
    )
    to_date_weight = fields.Float(
        string="To Date (kg)",
        digits=(16, 2),
        compute="_compute_to_date_weight",
        store=False,
        help=(
            "Akumulasi produksi field ini dari tanggal 1 hingga "
            "tanggal produksi dokumen ini dalam bulan yang sama."
        ),
    )

    def _compute_to_date_weight(self):
        """
        Hitung akumulasi today_production_weight untuk field yang sama,
        dari tanggal 1 s/d tanggal produksi induk, pada bulan & tahun yang sama,
        untuk dokumen yang berstatus 'selesai'.
        """
        Line = self.env["wt.field.production.line"]
        for line in self:
            prod = line.production_id
            if not prod or not prod.production_date or prod.state != "selesai":
                line.to_date_weight = 0.0
                continue
            prod_date = prod.production_date
            month_start = prod_date.replace(day=1)
            past_lines = Line.search([
                ("field_id", "=", line.field_id.id),
                ("production_id.company_id", "=", prod.company_id.id),
                ("production_id.production_date", ">=", month_start),
                ("production_id.production_date", "<=", prod_date),
                ("production_id.state", "=", "selesai"),
            ])
            line.to_date_weight = sum(past_lines.mapped("today_production_weight"))
