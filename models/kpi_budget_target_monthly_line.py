from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class KpiBudgetTargetMonthlyLine(models.Model):
    _name = "wt.kpi.budget.target.monthly.line"
    _description = "KPI Budget Target Monthly Line"
    _order = "line_type, sequence, id"
    _check_company_auto = True

    MONTH_SELECTION = [
        ("01", "Januari"),
        ("02", "Februari"),
        ("03", "Maret"),
        ("04", "April"),
        ("05", "Mei"),
        ("06", "Juni"),
        ("07", "Juli"),
        ("08", "Agustus"),
        ("09", "September"),
        ("10", "Oktober"),
        ("11", "November"),
        ("12", "Desember"),
    ]

    budget_target_id = fields.Many2one(
        "wt.kpi.budget.target",
        string="Budget Target",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        related="budget_target_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    year = fields.Integer(
        string="Tahun",
        related="budget_target_id.year",
        store=True,
        readonly=True,
        index=True,
    )
    line_type = fields.Selection(
        [
            ("factory_received", "Produksi Terima Pabrik"),
            ("dry_production", "Produksi Kering"),
        ],
        string="Tipe Produksi",
        required=True,
        index=True,
    )
    month = fields.Selection(
        MONTH_SELECTION,
        string="Bulan",
        required=True,
        index=True,
    )
    sequence = fields.Integer(string="Urutan", required=True, index=True)
    uom_name = fields.Char(
        string="Satuan",
        required=True,
        readonly=True,
        default="Kg Basah",
    )
    value = fields.Float(string="Nilai", default=0.0, digits=(16, 2))

    _budget_type_month_uniq = models.Constraint(
        "unique(budget_target_id, line_type, month)",
        "Bulan hanya boleh muncul satu kali untuk setiap tipe produksi.",
    )
    _value_non_negative = models.Constraint(
        "CHECK(value >= 0)",
        "Nilai produksi tidak boleh negatif.",
    )
    _sequence_range = models.Constraint(
        "CHECK(sequence BETWEEN 1 AND 12)",
        "Urutan bulan harus antara 1 dan 12.",
    )
    _uom_kg_basah = models.Constraint(
        "CHECK(uom_name = 'Kg Basah')",
        "Satuan produksi harus Kg Basah.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        budget_ids = {
            vals.get("budget_target_id")
            for vals in vals_list
            if vals.get("budget_target_id")
        }
        if self.env["wt.kpi.budget.target"].browse(budget_ids).filtered(
            lambda budget: budget.state != "draft"
        ):
            raise ValidationError(
                _("Baris produksi hanya dapat ditambahkan pada Budget Target Draft.")
            )
        keys = []
        for vals in vals_list:
            if vals.get("month"):
                vals["sequence"] = int(vals["month"])
            vals["uom_name"] = "Kg Basah"
            key = (
                vals.get("budget_target_id"),
                vals.get("line_type"),
                vals.get("month"),
            )
            if all(key):
                keys.append(key)
        if len(keys) != len(set(keys)):
            raise ValidationError(
                _("Bulan hanya boleh muncul satu kali untuk setiap tipe produksi.")
            )
        if keys:
            existing_keys = set(
                self.search(
                    [
                        ("budget_target_id", "in", list({key[0] for key in keys})),
                        ("line_type", "in", list({key[1] for key in keys})),
                        ("month", "in", list({key[2] for key in keys})),
                    ]
                ).mapped(
                    lambda line: (
                        line.budget_target_id.id,
                        line.line_type,
                        line.month,
                    )
                )
            )
            if existing_keys.intersection(keys):
                raise ValidationError(
                    _("Bulan hanya boleh muncul satu kali untuk setiap tipe produksi.")
                )
        return super().create(vals_list)

    def write(self, vals):
        if self.filtered(lambda line: line.budget_target_id.state != "draft"):
            raise ValidationError(
                _("Nilai produksi hanya dapat diubah pada Budget Target Draft.")
            )
        immutable_fields = {
            "budget_target_id",
            "line_type",
            "month",
            "sequence",
            "uom_name",
        }
        if immutable_fields.intersection(vals):
            raise ValidationError(
                _(
                    "Budget Target, tipe produksi, bulan, urutan, dan satuan "
                    "tidak dapat diubah."
                )
            )
        return super().write(vals)

    @api.constrains("value")
    def _check_non_negative_value(self):
        for line in self:
            if line.value < 0:
                raise ValidationError(_("Nilai produksi tidak boleh negatif."))

    @api.constrains("month", "sequence")
    def _check_month_sequence(self):
        for line in self:
            if line.month and line.sequence != int(line.month):
                raise ValidationError(_("Urutan bulan tidak sesuai dengan bulan."))
