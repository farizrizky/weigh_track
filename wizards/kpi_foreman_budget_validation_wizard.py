from odoo import fields, models


class KpiForemanBudgetValidationWizard(models.TransientModel):
    _name = "wt.kpi.foreman.budget.validation.wizard"
    _description = "Konfirmasi Validasi Budget Target Mandor"

    budget_mandor_id = fields.Many2one(
        "wt.kpi.foreman.budget.target",
        string="Budget Target Mandor",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    warning_text = fields.Text(
        string="Detail Kekurangan",
        required=True,
        readonly=True,
    )

    def action_confirm_validation(self):
        self.ensure_one()
        self.budget_mandor_id.with_context(
            confirm_foreman_budget_shortage=True
        ).action_validate()
        return {"type": "ir.actions.act_window_close"}
