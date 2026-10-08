from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class KpiBudgetTarget(models.Model):
    _name = "wt.kpi.budget.target"
    _description = "KPI Budget Target"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "year desc, create_date desc, id desc"
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
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("valid", "Valid"),
        ],
        string="Status",
        required=True,
        default="draft",
        copy=False,
        index=True,
        tracking=True,
    )
    production_target_line_ids = fields.One2many(
        "wt.kpi.budget.target.division.line",
        "budget_target_id",
        string="Target Produksi",
        domain=[("line_type", "=", "production_target")],
        copy=True,
    )
    sales_target_line_ids = fields.One2many(
        "wt.kpi.budget.target.division.line",
        "budget_target_id",
        string="Target Penjualan",
        domain=[("line_type", "=", "sales_target")],
        copy=True,
    )
    factory_received_line_ids = fields.One2many(
        "wt.kpi.budget.target.monthly.line",
        "budget_target_id",
        string="Produksi Terima Pabrik",
        domain=[("line_type", "=", "factory_received")],
        copy=True,
    )
    dry_production_line_ids = fields.One2many(
        "wt.kpi.budget.target.monthly.line",
        "budget_target_id",
        string="Produksi Kering",
        domain=[("line_type", "=", "dry_production")],
        copy=True,
    )

    _valid_year = models.Constraint(
        "CHECK(year BETWEEN 1000 AND 9999)",
        "Tahun harus berupa 4 digit.",
    )
    _company_year_uniq = models.Constraint(
        "unique(company_id, year)",
        "Budget Target untuk tahun tersebut sudah tersedia pada perusahaan ini.",
    )

    @api.constrains("year")
    def _check_year(self):
        for budget in self:
            if budget.year < 1000 or budget.year > 9999:
                raise ValidationError(_("Tahun harus berupa 4 digit."))

    @api.model_create_multi
    def create(self, vals_list):
        sequence_model = self.env["ir.sequence"]
        company_year_keys = set()
        for vals in vals_list:
            vals["state"] = "draft"
            year = vals.get("year")
            if not year or year < 1000 or year > 9999:
                raise ValidationError(_("Tahun harus berupa 4 digit."))
            company_id = vals.get("company_id") or self.env.company.id
            company_year_key = (company_id, year)
            if company_year_key in company_year_keys or self.sudo().search_count(
                [("company_id", "=", company_id), ("year", "=", year)],
                limit=1,
            ):
                raise ValidationError(
                    _(
                        "Budget Target tahun %(year)s sudah tersedia untuk "
                        "perusahaan ini.",
                        year=year,
                    )
                )
            company_year_keys.add(company_year_key)

        for vals in vals_list:
            year = vals["year"]
            company = self.env["res.company"].browse(
                vals.get("company_id") or self.env.company.id
            )
            vals["name"] = sequence_model.with_company(company).next_by_code(
                "wt.kpi.budget.target",
                sequence_date=date(year, 1, 1),
            )
            if not vals["name"]:
                raise ValidationError(
                    _("Sequence KPI Budget Target belum dikonfigurasi.")
                )

        budgets = super().create(vals_list)
        budgets._sync_missing_division_lines()
        budgets._sync_missing_monthly_lines()
        return budgets

    def write(self, vals):
        protected_fields = {
            "name",
            "year",
            "company_id",
            "production_target_line_ids",
            "sales_target_line_ids",
            "factory_received_line_ids",
            "dry_production_line_ids",
        }
        if (
            self.filtered(lambda budget: budget.state == "valid")
            and protected_fields.intersection(vals)
        ):
            raise ValidationError(
                _("Budget Target berstatus Valid tidak dapat diubah.")
            )
        if "name" in vals and any(budget.name != vals["name"] for budget in self):
            raise ValidationError(
                _("Nomor Budget Target dibuat otomatis dan tidak dapat diubah.")
            )
        if "year" in vals and any(budget.year != vals["year"] for budget in self):
            raise ValidationError(
                _("Tahun tidak dapat diubah setelah nomor Budget Target dibuat.")
            )
        if "company_id" in vals and any(
            budget.company_id.id != vals["company_id"] for budget in self
        ):
            raise ValidationError(
                _("Perusahaan tidak dapat diubah setelah Budget Target dibuat.")
            )
        return super().write(vals)

    def _active_divisions(self):
        self.ensure_one()
        return self.env["wt.division"].search(
            [
                ("active", "=", True),
                ("company_id", "=", self.company_id.id),
            ],
            order="code, name, id",
        )

    def _sync_missing_division_lines(self):
        line_model = self.env["wt.kpi.budget.target.division.line"]
        created_count = 0
        for budget in self:
            divisions = budget._active_divisions()
            existing_keys = set(
                line_model.search(
                    [("budget_target_id", "=", budget.id)]
                ).mapped(lambda line: (line.line_type, line.division_id.id))
            )
            values = [
                {
                    "budget_target_id": budget.id,
                    "line_type": line_type,
                    "division_id": division.id,
                }
                for line_type in ("production_target", "sales_target")
                for division in divisions
                if (line_type, division.id) not in existing_keys
            ]
            if values:
                line_model.create(values)
                created_count += len(values)
        return created_count

    def _sync_missing_monthly_lines(self):
        line_model = self.env["wt.kpi.budget.target.monthly.line"]
        for budget in self:
            existing_keys = set(
                line_model.search(
                    [("budget_target_id", "=", budget.id)]
                ).mapped(lambda line: (line.line_type, line.month))
            )
            values = [
                {
                    "budget_target_id": budget.id,
                    "line_type": line_type,
                    "month": month,
                    "sequence": sequence,
                }
                for line_type in ("factory_received", "dry_production")
                for sequence, (month, _month_name) in enumerate(
                    line_model.MONTH_SELECTION,
                    start=1,
                )
                if (line_type, month) not in existing_keys
            ]
            if values:
                line_model.create(values)

    def action_sync_divisions(self):
        if self.filtered(lambda budget: budget.state != "draft"):
            raise ValidationError(
                _("Sync Divisi hanya dapat dilakukan pada Budget Target Draft.")
            )
        created_count = self._sync_missing_division_lines()
        if created_count:
            message = _("Divisi berhasil disinkronkan.")
            notification_type = "success"
        else:
            message = _("Semua divisi sudah tersinkronisasi.")
            notification_type = "info"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Divisi"),
                "message": message,
                "type": notification_type,
                "sticky": False,
            },
        }

    def action_validate(self):
        draft_budgets = self.filtered(lambda budget: budget.state == "draft")
        draft_budgets._check_ready_for_validation()
        draft_budgets.write({"state": "valid"})
        return True

    def _check_ready_for_validation(self):
        division_month_fields = (
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
        expected_months = {
            month
            for month, _month_name in self.env[
                "wt.kpi.budget.target.monthly.line"
            ].MONTH_SELECTION
        }

        for budget in self:
            active_division_ids = set(budget._active_divisions().ids)
            if not active_division_ids:
                raise ValidationError(
                    _(
                        "Budget Target belum dapat divalidasi karena tidak ada "
                        "Divisi aktif pada perusahaan ini."
                    )
                )

            division_targets = (
                (_("Target Produksi"), budget.production_target_line_ids),
                (_("Target Penjualan"), budget.sales_target_line_ids),
            )
            for label, lines in division_targets:
                missing_division_ids = active_division_ids - set(
                    lines.mapped("division_id").ids
                )
                if missing_division_ids:
                    raise ValidationError(
                        _(
                            "%s belum memuat semua Divisi aktif. Klik Sync Divisi "
                            "lalu lengkapi nilainya.",
                            label,
                        )
                    )
                if any(
                    line[field_name] <= 0
                    for line in lines
                    for field_name in division_month_fields
                ):
                    raise ValidationError(
                        _(
                            "Semua nilai bulan pada %s wajib diisi lebih dari 0 "
                            "sebelum divalidasi.",
                            label,
                        )
                    )

            monthly_targets = (
                (_("Produksi Terima Pabrik"), budget.factory_received_line_ids),
                (_("Produksi Kering"), budget.dry_production_line_ids),
            )
            for label, lines in monthly_targets:
                if set(lines.mapped("month")) != expected_months:
                    raise ValidationError(
                        _(
                            "%s wajib memuat data Januari sampai Desember sebelum "
                            "divalidasi.",
                            label,
                        )
                    )
                if any(line.value <= 0 for line in lines):
                    raise ValidationError(
                        _(
                            "Semua nilai bulan pada %s wajib diisi lebih dari 0 "
                            "sebelum divalidasi.",
                            label,
                        )
                    )

    def action_set_draft(self):
        self.filtered(lambda budget: budget.state == "valid").write(
            {"state": "draft"}
        )
        return True
