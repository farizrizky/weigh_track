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
