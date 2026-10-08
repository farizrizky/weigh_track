from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class KpiBudgetTargetDivisionLine(models.Model):
    _name = "wt.kpi.budget.target.division.line"
    _description = "KPI Budget Target Division Line"
    _order = "line_type, division_id, id"
    _check_company_auto = True

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
            ("production_target", "Target Produksi"),
            ("sales_target", "Target Penjualan"),
        ],
        string="Tipe Target",
        required=True,
        index=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Divisi",
        required=True,
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    uom_name = fields.Char(
        string="Satuan",
        required=True,
        readonly=True,
        default="Kg Basah",
    )
    january = fields.Float(string="Januari", default=0.0, digits=(16, 2))
    february = fields.Float(string="Februari", default=0.0, digits=(16, 2))
    march = fields.Float(string="Maret", default=0.0, digits=(16, 2))
    april = fields.Float(string="April", default=0.0, digits=(16, 2))
    may = fields.Float(string="Mei", default=0.0, digits=(16, 2))
    june = fields.Float(string="Juni", default=0.0, digits=(16, 2))
    july = fields.Float(string="Juli", default=0.0, digits=(16, 2))
    august = fields.Float(string="Agustus", default=0.0, digits=(16, 2))
    september = fields.Float(string="September", default=0.0, digits=(16, 2))
    october = fields.Float(string="Oktober", default=0.0, digits=(16, 2))
    november = fields.Float(string="November", default=0.0, digits=(16, 2))
    december = fields.Float(string="Desember", default=0.0, digits=(16, 2))

    _budget_type_division_uniq = models.Constraint(
        "unique(budget_target_id, line_type, division_id)",
        "Divisi hanya boleh muncul satu kali untuk setiap tipe target.",
    )
    _monthly_values_non_negative = models.Constraint(
        "CHECK(january >= 0 AND february >= 0 AND march >= 0 AND april >= 0 "
        "AND may >= 0 AND june >= 0 AND july >= 0 AND august >= 0 "
        "AND september >= 0 AND october >= 0 AND november >= 0 "
        "AND december >= 0)",
        "Nilai target bulanan tidak boleh negatif.",
    )
    _uom_kg_basah = models.Constraint(
        "CHECK(uom_name = 'Kg Basah')",
        "Satuan target harus Kg Basah.",
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
                _("Baris target hanya dapat ditambahkan pada Budget Target Draft.")
            )
        keys = []
        for vals in vals_list:
            vals["uom_name"] = "Kg Basah"
            key = (
                vals.get("budget_target_id"),
                vals.get("line_type"),
                vals.get("division_id"),
            )
            if all(key):
                keys.append(key)
        if len(keys) != len(set(keys)):
            raise ValidationError(
                _("Divisi hanya boleh muncul satu kali untuk setiap tipe target.")
            )
        if keys:
            existing_keys = set(
                self.search(
                    [
                        ("budget_target_id", "in", list({key[0] for key in keys})),
                        ("line_type", "in", list({key[1] for key in keys})),
                        ("division_id", "in", list({key[2] for key in keys})),
                    ]
                ).mapped(
                    lambda line: (
                        line.budget_target_id.id,
                        line.line_type,
                        line.division_id.id,
                    )
                )
            )
            if existing_keys.intersection(keys):
                raise ValidationError(
                    _("Divisi hanya boleh muncul satu kali untuk setiap tipe target.")
                )
        return super().create(vals_list)

    def write(self, vals):
        if self.filtered(lambda line: line.budget_target_id.state != "draft"):
            raise ValidationError(
                _("Nilai target hanya dapat diubah pada Budget Target Draft.")
            )
        immutable_fields = {"budget_target_id", "line_type", "division_id", "uom_name"}
        if immutable_fields.intersection(vals):
            raise ValidationError(
                _("Budget Target, tipe target, divisi, dan satuan tidak dapat diubah.")
            )
        return super().write(vals)

    @api.constrains(
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    )
    def _check_non_negative_values(self):
        month_fields = (
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        )
        for line in self:
            if any(line[field_name] < 0 for field_name in month_fields):
                raise ValidationError(_("Nilai target bulanan tidak boleh negatif."))

    @api.constrains("budget_target_id", "division_id")
    def _check_division_company(self):
        for line in self:
            if line.division_id.company_id != line.budget_target_id.company_id:
                raise ValidationError(
                    _("Divisi harus berasal dari perusahaan Budget Target yang sama.")
                )
