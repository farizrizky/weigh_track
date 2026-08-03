# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DailyStockAnalysisRefreshWizard(models.TransientModel):
    _name = "wt.daily.stock.analysis.refresh.wizard"
    _description = "Refresh Daily Stock Analysis"

    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        required=True,
        default=lambda self: self.env.company,
    )
    start_date = fields.Date(
        string="Tanggal Mulai",
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    end_date = fields.Date(
        string="Tanggal Selesai",
        required=True,
        default=fields.Date.context_today,
    )

    @api.constrains("start_date", "end_date")
    def _check_date_range(self):
        for wizard in self:
            if wizard.start_date and wizard.end_date and wizard.start_date > wizard.end_date:
                raise ValidationError(
                    _("Tanggal mulai tidak boleh lebih besar dari tanggal selesai.")
                )

    def action_refresh(self):
        self.ensure_one()
        self.env["wt.daily.stock.analysis.service"].refresh_range(
            self.company_id,
            self.start_date,
            self.end_date,
        )
        action = self.env.ref("weightrack.action_wt_daily_stock_analysis").read()[0]
        action["domain"] = [
            ("company_id", "=", self.company_id.id),
            ("report_date", ">=", self.start_date),
            ("report_date", "<=", self.end_date),
        ]
        return action
