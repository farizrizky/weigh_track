from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare
from odoo.tools.misc import formatLang


MONTH_FIELDS = (
    ("january", "01", "Januari"),
    ("february", "02", "Februari"),
    ("march", "03", "Maret"),
    ("april", "04", "April"),
    ("may", "05", "Mei"),
    ("june", "06", "Juni"),
    ("july", "07", "Juli"),
    ("august", "08", "Agustus"),
    ("september", "09", "September"),
    ("october", "10", "Oktober"),
    ("november", "11", "November"),
    ("december", "12", "Desember"),
)


class KpiForemanBudgetTarget(models.Model):
    _name = "wt.kpi.foreman.budget.target"
    _description = "KPI Budget Target Mandor"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "year desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        string="Nomor",
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _("New"),
        index=True,
    )
    year = fields.Integer(
        string="Tahun",
        required=True,
        index=True,
        tracking=True,
    )
    budget_target_id = fields.Many2one(
        "wt.kpi.budget.target",
        string="Budget Target Acuan",
        readonly=True,
        ondelete="restrict",
        check_company=True,
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    state = fields.Selection(
        [("draft", "Draft"), ("valid", "Valid")],
        string="Status",
        required=True,
        default="draft",
        copy=False,
        index=True,
        tracking=True,
    )
    foreman_line_ids = fields.One2many(
        "wt.kpi.foreman.budget.target.line",
        "budget_mandor_id",
        string="Target Mandor",
        copy=True,
    )
    control_line_ids = fields.One2many(
        "wt.kpi.foreman.budget.control.line",
        "budget_mandor_id",
        string="Kontrol Budget",
        copy=False,
    )

    _valid_year = models.Constraint(
        "CHECK(year BETWEEN 1000 AND 9999)",
        "Tahun harus berupa 4 digit.",
    )

    @api.constrains("year")
    def _check_year(self):
        for budget in self:
            if budget.year < 1000 or budget.year > 9999:
                raise ValidationError(_("Tahun harus berupa 4 digit."))

    @api.constrains("year", "company_id", "budget_target_id")
    def _check_budget_target_reference(self):
        for budget in self:
            if not budget.budget_target_id:
                raise ValidationError(
                    _("Budget Target Acuan wajib tersedia.")
                )
            if budget.budget_target_id.state != "valid":
                raise ValidationError(
                    _("Budget Target Acuan harus berstatus Valid.")
                )
            if budget.budget_target_id.year != budget.year:
                raise ValidationError(
                    _("Tahun Budget Target Acuan harus sama dengan Tahun dokumen.")
                )
            if budget.budget_target_id.company_id != budget.company_id:
                raise ValidationError(
                    _("Budget Target Acuan harus berasal dari perusahaan yang sama.")
                )

    @api.onchange("year", "company_id")
    def _onchange_year_company(self):
        for budget in self:
            budget.budget_target_id = False
            if budget.year and 1000 <= budget.year <= 9999 and budget.company_id:
                references = self.env["wt.kpi.budget.target"].search(
                    [
                        ("year", "=", budget.year),
                        ("company_id", "=", budget.company_id.id),
                        ("state", "=", "valid"),
                    ],
                    limit=2,
                )
                if len(references) == 1:
                    budget.budget_target_id = references

    @api.model
    def _find_valid_budget_target(self, year, company_id):
        references = self.env["wt.kpi.budget.target"].search(
            [
                ("year", "=", year),
                ("company_id", "=", company_id),
                ("state", "=", "valid"),
            ],
            limit=2,
        )
        if not references:
            raise ValidationError(
                _(
                    "Tidak dapat membuat Budget Target Mandor tahun %(year)s.\n\n"
                    "Belum tersedia Budget Target tahun %(year)s dengan status "
                    "Valid. Silakan validasi Budget Target terlebih dahulu.",
                    year=year,
                )
            )
        if len(references) > 1:
            raise ValidationError(
                _(
                    "Ditemukan lebih dari satu Budget Target Valid untuk tahun "
                    "%(year)s. Silakan periksa data Budget Target.",
                    year=year,
                )
            )
        return references

    @api.model_create_multi
    def create(self, vals_list):
        sequence_model = self.env["ir.sequence"]
        for vals in vals_list:
            vals["state"] = "draft"
            year = vals.get("year")
            if not year or year < 1000 or year > 9999:
                raise ValidationError(_("Tahun harus berupa 4 digit."))
            company_id = vals.get("company_id") or self.env.company.id
            reference = self._find_valid_budget_target(year, company_id)
            supplied_reference_id = vals.get("budget_target_id")
            if supplied_reference_id and supplied_reference_id != reference.id:
                raise ValidationError(
                    _(
                        "Budget Target Acuan ditentukan otomatis berdasarkan Tahun "
                        "dan Perusahaan."
                    )
                )
            vals["budget_target_id"] = reference.id
            company = self.env["res.company"].browse(company_id)
            vals["name"] = sequence_model.with_company(company).next_by_code(
                "wt.kpi.foreman.budget.target",
                sequence_date=date(year, 1, 1),
            )
            if not vals["name"]:
                raise ValidationError(
                    _("Sequence Budget Target Mandor belum dikonfigurasi.")
                )

        budgets = super().create(vals_list)
        budgets._sync_missing_foreman_lines()
        budgets._refresh_control_lines()
        return budgets

    def write(self, vals):
        immutable_fields = {"name", "year", "company_id", "budget_target_id"}
        protected_fields = immutable_fields | {"foreman_line_ids"}
        if self.filtered(lambda budget: budget.state == "valid") and (
            protected_fields & set(vals)
        ):
            raise ValidationError(
                _("Budget Target Mandor berstatus Valid tidak dapat diubah.")
            )
        if immutable_fields & set(vals):
            changed = self.filtered(
                lambda budget: any(
                    budget[field_name].id != vals[field_name]
                    if budget._fields[field_name].type == "many2one"
                    else budget[field_name] != vals[field_name]
                    for field_name in immutable_fields & set(vals)
                )
            )
            if changed:
                raise ValidationError(
                    _(
                        "Nomor, Tahun, Perusahaan, dan Budget Target Acuan tidak "
                        "dapat diubah setelah dokumen dibuat."
                    )
                )
        if "state" in vals and not self.env.context.get(
            "allow_foreman_budget_state_change"
        ):
            raise ValidationError(
                _("Perubahan status harus dilakukan melalui tombol dokumen.")
            )
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda budget: budget.state == "valid"):
            raise ValidationError(
                _("Budget Target Mandor berstatus Valid tidak dapat dihapus.")
            )
        return super().unlink()

    def _active_foremen(self):
        self.ensure_one()
        return self.env["wt.foreman"].search(
            [
                ("active", "=", True),
                ("company_id", "=", self.company_id.id),
            ],
            order="division_id, name, id",
        )

    def _sync_missing_foreman_lines(self):
        line_model = self.env["wt.kpi.foreman.budget.target.line"]
        created_count = 0
        for budget in self:
            existing_employee_ids = set(
                budget.foreman_line_ids.mapped("employee_id").ids
            )
            values = [
                {
                    "budget_mandor_id": budget.id,
                    "foreman_id": foreman.id,
                    "employee_id": foreman.employee_id.id,
                    "division_id": foreman.division_id.id,
                }
                for foreman in budget._active_foremen()
                if foreman.employee_id.id not in existing_employee_ids
            ]
            if values:
                line_model.create(values)
                created_count += len(values)
        return created_count

    def action_sync_foremen(self):
        if self.filtered(lambda budget: budget.state != "draft"):
            raise ValidationError(
                _("Sync Mandor hanya dapat dilakukan pada dokumen Draft.")
            )
        created_count = self._sync_missing_foreman_lines()
        self._refresh_control_lines()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Mandor"),
                "message": (
                    _("Mandor berhasil disinkronkan.")
                    if created_count
                    else _("Semua Mandor sudah tersinkronisasi.")
                ),
                "type": "success" if created_count else "info",
                "sticky": False,
                "next": {
                    "type": "ir.actions.client",
                    "tag": "reload",
                },
            },
        }

    def _comparison_rows(self):
        self.ensure_one()
        target_lines = self.budget_target_id.production_target_line_ids
        target_by_division = {
            line.division_id.id: line for line in target_lines
        }
        divisions = (
            target_lines.mapped("division_id")
            | self.foreman_line_ids.mapped("division_id")
        ).sorted(lambda division: (division.code or "", division.name or "", division.id))
        rows = []
        for division in divisions:
            target_line = target_by_division.get(division.id)
            foreman_lines = self.foreman_line_ids.filtered(
                lambda line: line.division_id == division
            )
            for sequence, (field_name, month, month_label) in enumerate(
                MONTH_FIELDS, start=1
            ):
                target = target_line[field_name] if target_line else 0.0
                total = sum(foreman_lines.mapped(field_name))
                comparison = float_compare(total, target, precision_digits=2)
                status = "over" if comparison > 0 else "matched" if comparison == 0 else "less"
                rows.append(
                    {
                        "division_id": division.id,
                        "month": month,
                        "month_label": month_label,
                        "sequence": sequence,
                        "target_production": target,
                        "total_foreman": total,
                        "remaining": target - total,
                        "allocation_percentage": (total / target * 100.0) if target else 0.0,
                        "allocation_status": status,
                    }
                )
        return rows

    def _refresh_control_lines(self):
        control_model = self.env["wt.kpi.foreman.budget.control.line"].with_context(
            kpi_control_sync=True
        )
        for budget in self:
            existing = {
                (line.division_id.id, line.month): line
                for line in budget.control_line_ids
            }
            expected_keys = set()
            create_values = []
            for row in budget._comparison_rows():
                key = (row["division_id"], row["month"])
                expected_keys.add(key)
                values = {
                    key_name: value
                    for key_name, value in row.items()
                    if key_name != "month_label"
                }
                line = existing.get(key)
                if line:
                    line.with_context(kpi_control_sync=True).write(values)
                else:
                    values["budget_mandor_id"] = budget.id
                    create_values.append(values)
            stale_lines = budget.control_line_ids.filtered(
                lambda line: (line.division_id.id, line.month) not in expected_keys
            )
            if stale_lines:
                stale_lines.with_context(kpi_control_sync=True).unlink()
            if create_values:
                control_model.create(create_values)

    def _first_over_budget_row(self):
        self.ensure_one()
        return next(
            (
                row
                for row in self._comparison_rows()
                if float_compare(
                    row["total_foreman"],
                    row["target_production"],
                    precision_digits=2,
                )
                > 0
            ),
            False,
        )

    def _check_no_over_budget(self):
        for budget in self:
            row = budget._first_over_budget_row()
            if not row:
                continue
            division = self.env["wt.division"].browse(row["division_id"])
            excess = row["total_foreman"] - row["target_production"]
            raise ValidationError(
                _(
                    "Target Mandor melebihi Target Produksi.\n\n"
                    "Divisi: %(division)s\n"
                    "Bulan: %(month)s\n\n"
                    "Target Produksi: %(target)s Kg Basah\n"
                    "Total Target Mandor: %(total)s Kg Basah\n"
                    "Melebihi: %(excess)s Kg Basah.",
                    division=division.display_name,
                    month=row["month_label"],
                    target=formatLang(self.env, row["target_production"], digits=2),
                    total=formatLang(self.env, row["total_foreman"], digits=2),
                    excess=formatLang(self.env, excess, digits=2),
                )
            )

    def _check_all_active_foremen_present(self):
        for budget in self:
            missing = budget._active_foremen().mapped(
                "employee_id"
            ) - budget.foreman_line_ids.mapped(
                "employee_id"
            )
            if missing:
                raise ValidationError(
                    _(
                        "Masih ada Mandor aktif yang belum masuk ke dokumen. "
                        "Klik Sync Mandor sebelum validasi."
                    )
                )

    def _shortage_rows(self):
        self.ensure_one()
        return [
            row
            for row in self._comparison_rows()
            if float_compare(
                row["total_foreman"],
                row["target_production"],
                precision_digits=2,
            )
            < 0
        ]

    def _shortage_warning_text(self, shortage_rows):
        self.ensure_one()
        lines = [_("Beberapa Target Mandor masih di bawah Target Produksi."), ""]
        for row in shortage_rows:
            division = self.env["wt.division"].browse(row["division_id"])
            lines.extend(
                [
                    _("%(division)s - %(month)s", division=division.display_name, month=row["month_label"]),
                    _("Target Produksi: %s Kg Basah", formatLang(self.env, row["target_production"], digits=2)),
                    _("Target Mandor: %s Kg Basah", formatLang(self.env, row["total_foreman"], digits=2)),
                    _("Sisa: %s Kg Basah", formatLang(self.env, row["remaining"], digits=2)),
                    "",
                ]
            )
        return "\n".join(lines).rstrip()

    def action_validate(self):
        self.ensure_one()
        if self.state != "draft":
            return True
        self._check_budget_target_reference()
        self._check_all_active_foremen_present()
        self._check_no_over_budget()
        self._refresh_control_lines()
        shortage_rows = self._shortage_rows()
        if shortage_rows and not self.env.context.get("confirm_foreman_budget_shortage"):
            wizard = self.env["wt.kpi.foreman.budget.validation.wizard"].create(
                {
                    "budget_mandor_id": self.id,
                    "warning_text": self._shortage_warning_text(shortage_rows),
                }
            )
            return {
                "type": "ir.actions.act_window",
                "name": _("Konfirmasi Validasi"),
                "res_model": wizard._name,
                "res_id": wizard.id,
                "view_mode": "form",
                "target": "new",
            }
        self.with_context(allow_foreman_budget_state_change=True).write(
            {"state": "valid"}
        )
        return True

    def action_set_draft(self):
        self.filtered(lambda budget: budget.state == "valid").with_context(
            allow_foreman_budget_state_change=True
        ).write({"state": "draft"})
        return True


class KpiForemanBudgetTargetLine(models.Model):
    _name = "wt.kpi.foreman.budget.target.line"
    _description = "KPI Budget Target Mandor Line"
    _order = "division_id, employee_id, id"
    _check_company_auto = True

    budget_mandor_id = fields.Many2one(
        "wt.kpi.foreman.budget.target",
        string="Budget Target Mandor",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="budget_mandor_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    year = fields.Integer(
        related="budget_mandor_id.year",
        store=True,
        readonly=True,
        index=True,
    )
    foreman_id = fields.Many2one(
        "wt.foreman",
        string="Sumber Master Mandor",
        readonly=True,
        ondelete="set null",
        check_company=True,
        index=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Mandor",
        required=True,
        readonly=True,
        ondelete="restrict",
        check_company=True,
        index=True,
        help="Employee Mandor yang disimpan pada saat baris dibuat.",
    )
    foreman_name = fields.Char(
        string="Nama Mandor Snapshot",
        required=True,
        readonly=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Divisi",
        required=True,
        readonly=True,
        ondelete="restrict",
        check_company=True,
        index=True,
        help="Snapshot Divisi Mandor saat baris dibuat.",
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

    _budget_employee_uniq = models.Constraint(
        "unique(budget_mandor_id, employee_id)",
        "Mandor hanya boleh muncul satu kali dalam satu Budget Target Mandor.",
    )
    _monthly_values_non_negative = models.Constraint(
        "CHECK(january >= 0 AND february >= 0 AND march >= 0 AND april >= 0 "
        "AND may >= 0 AND june >= 0 AND july >= 0 AND august >= 0 "
        "AND september >= 0 AND october >= 0 AND november >= 0 "
        "AND december >= 0)",
        "Nilai target Mandor tidak boleh negatif.",
    )
    _uom_kg_basah = models.Constraint(
        "CHECK(uom_name = 'Kg Basah')",
        "Satuan target Mandor harus Kg Basah.",
    )

    def init(self):
        self.env.cr.execute(
            """
            ALTER TABLE wt_kpi_foreman_budget_target_line
            DROP CONSTRAINT IF EXISTS
                wt_kpi_foreman_budget_target_line_budget_foreman_uniq
            """
        )

    @api.model_create_multi
    def create(self, vals_list):
        keys = []
        for vals in vals_list:
            budget = self.env["wt.kpi.foreman.budget.target"].browse(
                vals.get("budget_mandor_id")
            )
            if budget and budget.state != "draft":
                raise ValidationError(
                    _("Baris Mandor hanya dapat ditambahkan pada dokumen Draft.")
                )
            foreman = self.env["wt.foreman"].browse(vals.get("foreman_id"))
            if foreman:
                supplied_employee_id = vals.get("employee_id")
                if supplied_employee_id and supplied_employee_id != foreman.employee_id.id:
                    raise ValidationError(
                        _("Employee Mandor tidak sesuai dengan Master Mandor.")
                    )
                vals["employee_id"] = foreman.employee_id.id
                if not vals.get("division_id"):
                    vals["division_id"] = foreman.division_id.id
            employee = self.env["hr.employee"].browse(vals.get("employee_id"))
            if not employee:
                raise ValidationError(_("Employee Mandor wajib tersedia."))
            vals["foreman_name"] = vals.get("foreman_name") or employee.name
            vals["uom_name"] = "Kg Basah"
            key = (vals.get("budget_mandor_id"), vals.get("employee_id"))
            if all(key):
                keys.append(key)
        if len(keys) != len(set(keys)):
            raise ValidationError(
                _("Mandor hanya boleh muncul satu kali dalam satu dokumen.")
            )
        if keys:
            existing_keys = set(
                self.search(
                    [
                        ("budget_mandor_id", "in", list({key[0] for key in keys})),
                        ("employee_id", "in", list({key[1] for key in keys})),
                    ]
                ).mapped(
                    lambda line: (line.budget_mandor_id.id, line.employee_id.id)
                )
            )
            if existing_keys.intersection(keys):
                raise ValidationError(
                    _("Mandor hanya boleh muncul satu kali dalam satu dokumen.")
                )
        lines = super().create(vals_list)
        lines._check_snapshot_company()
        budgets = lines.mapped("budget_mandor_id")
        budgets._check_no_over_budget()
        budgets._refresh_control_lines()
        return lines

    def write(self, vals):
        if self.filtered(lambda line: line.budget_mandor_id.state != "draft"):
            raise ValidationError(
                _("Target Mandor hanya dapat diubah pada dokumen Draft.")
            )
        immutable_fields = {
            "budget_mandor_id",
            "foreman_id",
            "employee_id",
            "foreman_name",
            "division_id",
            "uom_name",
        }
        if immutable_fields & set(vals):
            raise ValidationError(
                _("Dokumen, Mandor, Divisi snapshot, dan Satuan tidak dapat diubah.")
            )
        result = super().write(vals)
        budgets = self.mapped("budget_mandor_id")
        budgets._check_no_over_budget()
        budgets._refresh_control_lines()
        return result

    def unlink(self):
        if self.filtered(lambda line: line.budget_mandor_id.state != "draft"):
            raise ValidationError(
                _("Baris Mandor pada dokumen Valid tidak dapat dihapus.")
            )
        budgets = self.mapped("budget_mandor_id")
        result = super().unlink()
        budgets._refresh_control_lines()
        return result

    @api.constrains(*(field_name for field_name, _month, _label in MONTH_FIELDS))
    def _check_non_negative_values(self):
        for line in self:
            if any(line[field_name] < 0 for field_name, _month, _label in MONTH_FIELDS):
                raise ValidationError(_("Nilai target Mandor tidak boleh negatif."))

    @api.constrains(
        "budget_mandor_id", "foreman_id", "employee_id", "division_id"
    )
    def _check_snapshot_company(self):
        for line in self:
            if (
                line.foreman_id
                and line.foreman_id.company_id != line.budget_mandor_id.company_id
            ):
                raise ValidationError(
                    _("Mandor harus berasal dari perusahaan dokumen yang sama.")
                )
            if line.employee_id.company_id != line.budget_mandor_id.company_id:
                raise ValidationError(
                    _("Employee Mandor harus berasal dari perusahaan yang sama.")
                )
            if line.division_id.company_id != line.budget_mandor_id.company_id:
                raise ValidationError(
                    _("Divisi snapshot harus berasal dari perusahaan yang sama.")
                )


class KpiForemanBudgetControlLine(models.Model):
    _name = "wt.kpi.foreman.budget.control.line"
    _description = "KPI Budget Target Mandor Control Line"
    _order = "division_id, sequence, id"
    _check_company_auto = True

    budget_mandor_id = fields.Many2one(
        "wt.kpi.foreman.budget.target",
        string="Budget Target Mandor",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="budget_mandor_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    year = fields.Integer(
        related="budget_mandor_id.year",
        store=True,
        readonly=True,
        index=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Divisi",
        required=True,
        readonly=True,
        ondelete="restrict",
        check_company=True,
        index=True,
    )
    month = fields.Selection(
        [(month, label) for _field, month, label in MONTH_FIELDS],
        string="Bulan",
        required=True,
        readonly=True,
        index=True,
    )
    sequence = fields.Integer(required=True, readonly=True)
    target_production = fields.Float(
        string="Target Produksi", digits=(16, 2), readonly=True
    )
    total_foreman = fields.Float(
        string="Total Target Mandor", digits=(16, 2), readonly=True
    )
    remaining = fields.Float(string="Sisa", digits=(16, 2), readonly=True)
    allocation_percentage = fields.Float(
        string="Persentase Alokasi (%)", digits=(16, 2), readonly=True
    )
    allocation_status = fields.Selection(
        [("less", "Kurang"), ("matched", "Sesuai"), ("over", "Melebihi")],
        string="Status",
        required=True,
        readonly=True,
    )

    _budget_division_month_uniq = models.Constraint(
        "unique(budget_mandor_id, division_id, month)",
        "Kontrol Budget hanya boleh satu baris per Divisi dan Bulan.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("kpi_control_sync"):
            raise ValidationError(_("Kontrol Budget dihitung otomatis oleh sistem."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get("kpi_control_sync"):
            raise ValidationError(_("Kontrol Budget dihitung otomatis oleh sistem."))
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get("kpi_control_sync"):
            raise ValidationError(_("Kontrol Budget dihitung otomatis oleh sistem."))
        return super().unlink()
