from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.misc import formatLang

from ..models.kpi_foreman_budget_target import MONTH_FIELDS


class KpiForemanBudgetReplacementWizard(models.TransientModel):
    _name = "wt.kpi.foreman.budget.replacement.wizard"
    _description = "Alihkan Target Budget Mandor"
    _check_company_auto = True

    line_id = fields.Many2one(
        "wt.kpi.foreman.budget.target.line",
        string="Target Mandor Lama", required=True, readonly=True, ondelete="cascade",
        check_company=True,
    )
    budget_mandor_id = fields.Many2one(related="line_id.budget_mandor_id", readonly=True)
    company_id = fields.Many2one(related="line_id.company_id", readonly=True)
    division_id = fields.Many2one(related="line_id.division_id", readonly=True)
    old_employee_id = fields.Many2one(related="line_id.employee_id", readonly=True)
    old_foreman_name = fields.Char(related="line_id.foreman_name", readonly=True)
    new_foreman_id = fields.Many2one(
        "wt.foreman", string="Mandor Pengganti", required=True, ondelete="restrict",
        check_company=True,
        domain="[('active', '=', True), ('company_id', '=', company_id), "
               "('division_id', '=', division_id), ('employee_id', '!=', old_employee_id)]",
    )
    start_month = fields.Selection(
        [(month, label) for _field, month, label in MONTH_FIELDS],
        string="Mulai Bulan", required=True,
        help="Pilih Januari untuk memindahkan seluruh target tahunan. "
             "Bulan sebelumnya tetap pada mandor lama jika baris lama dipertahankan.",
    )
    old_line_action = fields.Selection(
        [("zero", "Pertahankan baris; nolkan target mulai bulan pergantian"),
         ("delete", "Hapus seluruh baris mandor lama")],
        string="Baris Mandor Lama", required=True, default="zero",
    )
    transfer_total = fields.Float(
        string="Total Target Dialihkan (Kg Basah)", compute="_compute_transfer_total",
        digits=(16, 2),
    )

    @api.depends("start_month", "line_id", *[
        "line_id.%s" % field_name for field_name, _month, _label in MONTH_FIELDS
    ])
    def _compute_transfer_total(self):
        for wizard in self:
            wizard.transfer_total = sum(
                wizard.line_id[field_name] for field_name, month, _label in MONTH_FIELDS
                if wizard.line_id and wizard.start_month and month >= wizard.start_month
            )

    def action_apply(self):
        self.ensure_one()
        line = self.line_id.exists()
        if not line:
            raise ValidationError(_("Baris Mandor lama sudah tidak tersedia."))
        line.check_access("write")
        budget = line.budget_mandor_id
        budget.check_access("write")
        if budget.state != "draft":
            raise ValidationError(_("Pengalihan target hanya dapat dilakukan pada dokumen Draft."))
        foreman = self.new_foreman_id
        if (
            not foreman.active or foreman.company_id != budget.company_id
            or foreman.division_id != line.division_id
            or foreman.employee_id == line.employee_id
        ):
            raise ValidationError(_(
                "Mandor pengganti harus aktif, berbeda dari Mandor lama, "
                "dan ditugaskan pada Divisi serta Perusahaan yang sama."
            ))
        if not self.start_month:
            raise ValidationError(_("Bulan mulai pengalihan wajib dipilih."))
        old_action = self.old_line_action
        if old_action == "delete" and any(
            line[field_name] > 0.0
            for field_name, month, _label in MONTH_FIELDS if month < self.start_month
        ):
            raise ValidationError(_(
                "Masih ada target sebelum bulan pergantian. Pertahankan baris lama "
                "agar target bulan sebelumnya tidak hilang."
            ))
        if old_action == "delete" and budget._active_foremen().filtered(
            lambda master: master.employee_id == line.employee_id
            and master.division_id == line.division_id
        ):
            raise ValidationError(_(
                "Mandor lama masih aktif pada Divisi ini. Arsipkan atau ubah penugasannya "
                "sebelum menghapus baris, atau pilih mempertahankan baris dengan target 0."
            ))
        transfer = {
            field_name: line[field_name]
            for field_name, month, _label in MONTH_FIELDS if month >= self.start_month
        }
        old_name = line.foreman_name
        division_name = line.division_id.display_name
        transfer_details = "; ".join(
            "%s: %s kg" % (label, formatLang(self.env, transfer[field_name], digits=2))
            for field_name, _month, label in MONTH_FIELDS if field_name in transfer
        )
        with self.env.cr.savepoint():
            # Release the old allocation first, so every normal write stays within budget.
            line.write({field_name: 0.0 for field_name in transfer})
            target = budget.foreman_line_ids.filtered(
                lambda candidate: candidate.employee_id == foreman.employee_id
                and candidate.division_id == line.division_id
            )
            if not target:
                target = self.env["wt.kpi.foreman.budget.target.line"].create({
                    "budget_mandor_id": budget.id, "foreman_id": foreman.id,
                    "division_id": line.division_id.id,
                })
            target.write({
                field_name: target[field_name] + value
                for field_name, value in transfer.items()
            })
            if old_action == "delete":
                line.unlink()
            budget.message_post(body=_(
                "Target Mandor %(old)s dialihkan ke %(new)s pada Divisi %(division)s. "
                "%(details)s. Baris lama: %(action)s.",
                old=old_name, new=target.foreman_name, division=division_name,
                details=transfer_details,
                action=_("dihapus") if old_action == "delete" else _("dipertahankan"),
            ))
        return {"type": "ir.actions.act_window_close"}
