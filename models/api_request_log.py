from odoo import fields, models


class ApiRequestLog(models.Model):
    _name = "wt.api.request.log"
    _description = "API Request Log"
    _order = "requested_at desc, id desc"

    request_id = fields.Char(
        string="Request ID",
        required=True,
        index=True,
        readonly=True,
    )
    endpoint = fields.Char(
        string="Endpoint",
        required=True,
        index=True,
        readonly=True,
    )
    method = fields.Char(
        string="Method",
        required=True,
        readonly=True,
    )
    status = fields.Selection(
        [
            ("success", "Success"),
            ("failed", "Failed"),
        ],
        required=True,
        index=True,
        readonly=True,
    )
    http_status = fields.Integer(
        string="HTTP Status",
        readonly=True,
    )
    error_code = fields.Char(
        string="Error Code",
        index=True,
        readonly=True,
    )
    error_message = fields.Text(
        string="Error Message",
        readonly=True,
    )
    device_id = fields.Char(
        string="Device ID",
        index=True,
        readonly=True,
    )
    device_record_id = fields.Many2one(
        "wt.device",
        string="Device",
        ondelete="set null",
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        readonly=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        readonly=True,
    )
    role = fields.Selection(
        [
            ("clerk", "Clerk"),
            ("foreman", "Foreman"),
            ("operator", "Operator"),
        ],
        string="Role",
        readonly=True,
    )
    request_ip = fields.Char(
        string="Request IP",
        readonly=True,
    )
    user_agent = fields.Char(
        string="User Agent",
        readonly=True,
    )
    duration_ms = fields.Integer(
        string="Duration (ms)",
        readonly=True,
    )
    requested_at = fields.Datetime(
        string="Requested At",
        required=True,
        readonly=True,
    )
    finished_at = fields.Datetime(
        string="Finished At",
        readonly=True,
    )
    payload_hash = fields.Char(
        string="Payload Hash",
        readonly=True,
    )
    payload = fields.Text(
        string="Payload",
        readonly=True,
    )
    response = fields.Text(
        string="Response",
        readonly=True,
    )
