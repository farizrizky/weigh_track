from odoo import fields, models


class DeviceStateReasonWizard(models.TransientModel):
    _name = "wt.device.state.reason.wizard"
    _description = "Device State Reason Wizard"

    action = fields.Selection(
        [
            ("block", "Block"),
            ("revoke", "Revoke"),
        ],
        required=True,
    )
    device_id = fields.Many2one(
        "wt.device",
        string="Device",
        required=True,
        readonly=True,
    )
    reason = fields.Text(
        string="Reason",
        required=True,
    )

    def action_confirm(self):
        self.ensure_one()
        if self.action == "block":
            self.device_id.action_confirm_block(self.reason)
        elif self.action == "revoke":
            self.device_id.action_confirm_revoke(self.reason)
        return {"type": "ir.actions.act_window_close"}
