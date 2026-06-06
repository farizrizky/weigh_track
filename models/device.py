import secrets

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Device(models.Model):
    _name = "wt.device"
    _description = "Device"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name, device_id"

    ROLE_SELECTION = [
        ("clerk", "Clerk"),
        ("foreman", "Foreman"),
        ("operator", "Operator"),
    ]

    STATUS_SELECTION = [
        ("inactive", "Inactive"),
        ("active", "Active"),
        ("blocked", "Blocked"),
        ("revoked", "Revoked"),
    ]

    DEVICE_TYPE_SELECTION = [
        ("mobile", "Mobile"),
        ("desktop", "Desktop"),
    ]

    LOCKED_STATUS = {"active", "blocked", "revoked"}
    LOCKED_STATUS_EDITABLE_FIELDS = {"name"}

    device_id = fields.Char(
        string="Device ID",
        index=True,
        tracking=True,
    )
    name = fields.Char(
        string="Name",
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )
    role = fields.Selection(
        ROLE_SELECTION,
        string="Role",
        required=True,
        index=True,
        tracking=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=True,
        ondelete="restrict",
        index=True,
        domain="[('id', 'in', allowed_employee_ids)]",
        tracking=True,
    )
    allowed_employee_ids = fields.Many2many(
        "hr.employee",
        compute="_compute_allowed_employee_ids",
        string="Allowed Employees",
    )
    status = fields.Selection(
        STATUS_SELECTION,
        required=True,
        default="inactive",
        index=True,
        tracking=True,
    )
    token = fields.Char(
        string="Token",
        copy=False,
        index=True,
    )
    actived_at = fields.Datetime(
        string="Actived At",
        tracking=True,
    )
    last_pull = fields.Datetime(
        string="Last Pull",
        tracking=True,
    )
    last_push = fields.Datetime(
        string="Last Push",
        tracking=True,
    )
    last_seen = fields.Datetime(
        string="Last Seen",
        tracking=True,
    )
    app_version = fields.Char(
        string="App Version",
        tracking=True,
    )
    device_type = fields.Selection(
        DEVICE_TYPE_SELECTION,
        string="Device Type",
        tracking=True,
    )
    blocked_at = fields.Datetime(
        string="Blocked At",
        tracking=True,
    )
    blocked_by = fields.Many2one(
        "res.users",
        string="Blocked By",
        ondelete="restrict",
        tracking=True,
    )
    blocked_reason = fields.Text(
        string="Blocked Reason",
        tracking=True,
    )
    reactivated_at = fields.Datetime(
        string="Reactivated At",
        tracking=True,
    )
    reactivated_by = fields.Many2one(
        "res.users",
        string="Reactivated By",
        ondelete="restrict",
        tracking=True,
    )
    revoked_at = fields.Datetime(
        string="Revoked At",
        tracking=True,
    )
    revoked_by = fields.Many2one(
        "res.users",
        string="Revoked By",
        ondelete="restrict",
        tracking=True,
    )
    revoked_reason = fields.Text(
        string="Revoked Reason",
        tracking=True,
    )

    _sql_constraints = [
        (
            "device_id_uniq",
            "unique(device_id)",
            "Device ID must be unique.",
        ),
        (
            "token_uniq",
            "unique(token)",
            "Device token must be unique.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault("status", "inactive")
            if not vals.get("token"):
                vals["token"] = self._generate_unique_token()
        return super().create(vals_list)

    def write(self, vals):
        if vals and not self.env.context.get("allow_device_state_update"):
            forbidden_fields = set(vals) - self.LOCKED_STATUS_EDITABLE_FIELDS
            if forbidden_fields and any(device.status in self.LOCKED_STATUS for device in self):
                raise ValidationError(
                    _("Only device name can be changed after the device has been activated.")
                )
        return super().write(vals)

    def action_block(self):
        self.ensure_one()
        if any(device.status != "active" for device in self):
            raise ValidationError(_("Only active devices can be blocked."))
        return self._action_open_reason_wizard("block")

    def action_confirm_block(self, reason):
        if any(device.status != "active" for device in self):
            raise ValidationError(_("Only active devices can be blocked."))
        if not reason:
            raise ValidationError(_("Reason is required."))
        now = fields.Datetime.now()
        self.with_context(allow_device_state_update=True).write(
            {
                "status": "blocked",
                "blocked_at": now,
                "blocked_by": self.env.user.id,
                "blocked_reason": reason,
            }
        )

    def action_reactivate(self):
        if any(device.status != "blocked" for device in self):
            raise ValidationError(_("Only blocked devices can be reactivated."))
        now = fields.Datetime.now()
        self.with_context(allow_device_state_update=True).write(
            {
                "status": "active",
                "reactivated_at": now,
                "reactivated_by": self.env.user.id,
            }
        )

    def action_revoke(self):
        self.ensure_one()
        if any(device.status not in {"active", "blocked"} for device in self):
            raise ValidationError(_("Only active or blocked devices can be revoked."))
        return self._action_open_reason_wizard("revoke")

    def action_confirm_revoke(self, reason):
        if any(device.status not in {"active", "blocked"} for device in self):
            raise ValidationError(_("Only active or blocked devices can be revoked."))
        if not reason:
            raise ValidationError(_("Reason is required."))
        now = fields.Datetime.now()
        self.with_context(allow_device_state_update=True).write(
            {
                "status": "revoked",
                "revoked_at": now,
                "revoked_by": self.env.user.id,
                "revoked_reason": reason,
            }
        )

    def _action_open_reason_wizard(self, action):
        self.ensure_one()
        action_labels = {
            "block": _("Block Device"),
            "revoke": _("Revoke Device"),
        }
        return {
            "type": "ir.actions.act_window",
            "name": action_labels[action],
            "res_model": "wt.device.state.reason.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_action": action,
                "default_device_id": self.id,
            },
        }

    def _generate_unique_token(self):
        for _attempt in range(10):
            token = secrets.token_urlsafe(32)
            if not self.sudo().search_count([("token", "=", token)]):
                return token
        raise ValidationError(_("Unable to generate a unique device token."))

    @api.depends("company_id", "role")
    def _compute_allowed_employee_ids(self):
        mapping_model = self.env["wt.employee.role.mapping"]
        for device in self:
            if not device.company_id or not device.role:
                device.allowed_employee_ids = False
                continue
            device.allowed_employee_ids = mapping_model.get_allowed_employees(
                device.company_id,
                device.role,
            )

    @api.onchange("company_id", "role")
    def _onchange_role(self):
        if self.employee_id and self.employee_id not in self.allowed_employee_ids:
            self.employee_id = False

        employee_domain = [("id", "=", False)]
        if self.company_id and self.role:
            employee_domain = self.env["wt.employee.role.mapping"].get_employee_domain(
                self.company_id,
                self.role,
            )

        return {
            "domain": {
                "employee_id": employee_domain
            }
        }

    @api.constrains("company_id", "role", "employee_id")
    def _check_employee_allowed(self):
        role_labels = dict(self.ROLE_SELECTION)
        for device in self:
            self.env["wt.employee.role.mapping"].check_employee_allowed(
                device.employee_id,
                device.company_id,
                device.role,
                _(role_labels.get(device.role, "Employee")),
            )
