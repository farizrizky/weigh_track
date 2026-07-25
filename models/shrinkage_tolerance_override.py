# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ShrinkageToleranceOverride(models.Model):
    _name = "wt.shrinkage.tolerance.override"
    _description = "Shrinkage Tolerance Override"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "production_date desc, id desc"

    STATE_SELECTION = [
        ("draft", "Draft"),
        ("applied", "Applied"),
    ]

    name = fields.Char(
        string="Number",
        default="/",
        readonly=True,
        copy=False,
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    estate_id = fields.Many2one(
        "wt.estate",
        string="Estate",
        required=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Division",
        required=True,
        domain="[('company_id', '=', company_id), ('estate_id', '=', estate_id)]",
        tracking=True,
    )
    foreman_id = fields.Many2one(
        "wt.foreman",
        string="Foreman",
        tracking=True,
    )
    tapper_id = fields.Many2one(
        "wt.tapper",
        string="Tapper",
        tracking=True,
    )
    production_date = fields.Date(
        string="Production Date",
        required=True,
        tracking=True,
    )
    shrinkage_tolerance_percentage = fields.Float(
        string="Shrinkage Tolerance (%)",
        required=True,
        tracking=True,
    )
    reason = fields.Text(
        string="Reason",
        required=True,
        tracking=True,
    )
    line_ids = fields.One2many(
        "wt.shrinkage.tolerance.override.line",
        "override_id",
        string="Lines",
        copy=False,
    )
    total_count = fields.Integer(
        string="Selected Weighing Count",
        compute="_compute_counts",
        store=True,
    )
    state = fields.Selection(
        STATE_SELECTION,
        string="Status",
        default="draft",
        required=True,
        tracking=True,
    )
    applied_at = fields.Datetime(
        string="Applied At",
        readonly=True,
        copy=False,
        tracking=True,
    )
    applied_by_id = fields.Many2one(
        "res.users",
        string="Applied By",
        readonly=True,
        copy=False,
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        sequence_model = self.env["ir.sequence"]
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "/":
                sequence_date = (
                    fields.Date.to_date(vals["production_date"])
                    if vals.get("production_date")
                    else fields.Date.context_today(self)
                )
                vals["name"] = sequence_model.next_by_code(
                    "wt.shrinkage.tolerance.override",
                    sequence_date=sequence_date,
                )
                if not vals["name"]:
                    raise ValidationError(
                        _("Shrinkage Tolerance Override sequence is not configured.")
                    )
        return super().create(vals_list)

    def write(self, vals):
        protected_fields = {
            "company_id",
            "estate_id",
            "division_id",
            "foreman_id",
            "tapper_id",
            "production_date",
            "shrinkage_tolerance_percentage",
            "reason",
            "line_ids",
        }
        if self.filtered(lambda record: record.state == "applied") and (
            protected_fields & set(vals)
        ):
            raise ValidationError(
                _("Applied Shrinkage Tolerance Override cannot be changed.")
            )
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda record: record.state == "applied"):
            raise ValidationError(
                _("Applied Shrinkage Tolerance Override cannot be deleted.")
            )
        return super().unlink()

    def init(self):
        sequence = self.env.ref(
            "weightrack.sequence_wt_shrinkage_tolerance_override",
            raise_if_not_found=False,
        )
        if sequence and sequence.prefix != "STO/%(year)s%(month)s%(day)s/":
            sequence.write({"prefix": "STO/%(year)s%(month)s%(day)s/"})

    @api.depends("line_ids")
    def _compute_counts(self):
        for override in self:
            override.total_count = len(override.line_ids)

    @api.onchange("company_id")
    def _onchange_company_id(self):
        for override in self:
            override.estate_id = False
            override.division_id = False
            override.foreman_id = False
            override.tapper_id = False

    @api.onchange("estate_id")
    def _onchange_estate_id(self):
        self.division_id = False
        self.foreman_id = False
        self.tapper_id = False
        domain = [("company_id", "=", self.company_id.id)]
        if self.estate_id:
            domain.append(("estate_id", "=", self.estate_id.id))
        return {"domain": {"division_id": domain}}

    @api.onchange("division_id")
    def _onchange_division_id(self):
        self.foreman_id = False
        self.tapper_id = False
        domain_foreman = []
        domain_tapper = []
        if self.division_id:
            domain_foreman.append(("division_id", "=", self.division_id.id))
            domain_tapper.append(("division_id", "=", self.division_id.id))
        elif self.estate_id:
            divisions = self.env["wt.division"].search(
                [("estate_id", "=", self.estate_id.id)]
            )
            domain_foreman.append(("division_id", "in", divisions.ids))
            domain_tapper.append(("division_id", "in", divisions.ids))
        elif self.company_id:
            domain_foreman.append(("company_id", "=", self.company_id.id))
            domain_tapper.append(("company_id", "=", self.company_id.id))
        return {"domain": {"foreman_id": domain_foreman, "tapper_id": domain_tapper}}

    @api.onchange("foreman_id")
    def _onchange_foreman_id(self):
        self.tapper_id = False
        domain = []
        if self.foreman_id:
            domain.append(("foreman_id", "=", self.foreman_id.id))
        elif self.division_id:
            domain.append(("division_id", "=", self.division_id.id))
        return {"domain": {"tapper_id": domain}}

    def action_preview(self):
        self.ensure_one()
        self._refresh_lines()
        return self._action_open()

    def action_apply(self):
        self.ensure_one()
        if self.state != "draft":
            raise ValidationError(_("Only Draft overrides can be applied."))
        self._check_required_inputs()
        lines = self.line_ids
        if not lines:
            raise ValidationError(_("No weighing records selected for override."))
        lines.mapped("weighing_id").action_apply_shrinkage_tolerance_override(
            self.shrinkage_tolerance_percentage,
            self.reason,
            override_record=self,
        )
        self.write(
            {
                "state": "applied",
                "applied_at": fields.Datetime.now(),
                "applied_by_id": self.env.user.id,
            }
        )
        return self._action_open()

    def _action_open(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Override Toleransi Susut"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def _refresh_lines(self):
        self.ensure_one()
        if self.state != "draft":
            raise ValidationError(_("Only Draft overrides can be previewed."))
        self._check_required_inputs()
        weighings = self.env["wt.weighing"].search(
            self._weighing_domain(),
            order="production_receipt_id, foreman_id, tapper_id, id",
        )
        commands = [(5, 0, 0)]
        for sequence, weighing in enumerate(weighings, start=1):
            values = self._preview_line_values(weighing)
            if not values:
                continue
            values["sequence"] = sequence
            commands.append((0, 0, values))
        self.write({"line_ids": commands})

    def _check_required_inputs(self):
        self.ensure_one()
        if not self.reason or not self.reason.strip():
            raise ValidationError(_("Shrinkage tolerance override reason is required."))
        if (
            self.shrinkage_tolerance_percentage < 0
            or self.shrinkage_tolerance_percentage > 100
        ):
            raise ValidationError(
                _("Shrinkage tolerance override percentage must be between 0 and 100.")
            )

    def _weighing_domain(self):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("estate_id", "=", self.estate_id.id),
            ("division_id", "=", self.division_id.id),
            ("production_date", "=", self.production_date),
            ("initial_weighing_date", "!=", False),
            ("initial_weight", ">", 0),
            ("has_data_problem", "=", False),
            ("state", "!=", "receipt_validated"),
        ]
        if self.foreman_id:
            domain.append(("foreman_id", "=", self.foreman_id.id))
        if self.tapper_id:
            domain.append(("tapper_id", "=", self.tapper_id.id))
        return domain

    def _preview_line_values(self, weighing):
        self.ensure_one()
        tolerance_weight = (
            weighing.initial_weight * self.shrinkage_tolerance_percentage / 100.0
        )
        production_weight = weighing.initial_weight - tolerance_weight
        net_weight = production_weight - weighing.reject_weight - weighing.slab_weight
        if production_weight <= 0:
            return False
        elif net_weight <= 0:
            return False
        return {
            "weighing_id": weighing.id,
            "production_receipt_id": weighing.production_receipt_id.id,
            "weighing_state": weighing.state,
            "foreman_id": weighing.foreman_id.id,
            "tapper_id": weighing.tapper_id.id,
            "initial_weight": weighing.initial_weight,
            "reject_weight": weighing.reject_weight,
            "slab_weight": weighing.slab_weight,
            "current_shrinkage_tolerance_percentage": (
                weighing.shrinkage_tolerance_percentage
            ),
            "current_shrinkage_tolerance_weight": weighing.shrinkage_tolerance_weight,
            "current_production_weight": weighing.production_weight,
            "current_net_weight": weighing.net_weight,
            "new_shrinkage_tolerance_weight": tolerance_weight,
            "new_production_weight": production_weight,
            "new_net_weight": net_weight,
            "already_overridden": weighing.shrinkage_tolerance_override,
        }


class ShrinkageToleranceOverrideLine(models.Model):
    _name = "wt.shrinkage.tolerance.override.line"
    _description = "Shrinkage Tolerance Override Line"
    _order = "override_id, sequence, id"

    def unlink(self):
        if self.filtered(lambda line: line.override_id.state != "draft"):
            raise ValidationError(
                _("Only Draft override lines can be deleted.")
            )
        return super().unlink()

    override_id = fields.Many2one(
        "wt.shrinkage.tolerance.override",
        string="Override",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    weighing_id = fields.Many2one(
        "wt.weighing",
        string="Weighing",
        readonly=True,
        index=True,
    )
    production_receipt_id = fields.Many2one(
        "wt.production.receipt",
        string="Production Receipt",
        readonly=True,
        index=True,
    )
    weighing_state = fields.Selection(
        [
            ("not_receipted", "Not Receipted"),
            ("in_production_receipt", "In Production Receipt"),
            ("receipt_validated", "Receipt Validated"),
            ("receipt_cancelled", "Receipt Cancelled"),
        ],
        string="Weighing Status",
        readonly=True,
    )
    foreman_id = fields.Many2one(
        "wt.foreman",
        string="Foreman",
        readonly=True,
    )
    tapper_id = fields.Many2one(
        "wt.tapper",
        string="Tapper",
        readonly=True,
    )
    initial_weight = fields.Float(
        string="Initial Weight",
        readonly=True,
    )
    reject_weight = fields.Float(
        string="Reject Weight",
        readonly=True,
    )
    slab_weight = fields.Float(
        string="Slab Weight",
        readonly=True,
    )
    current_shrinkage_tolerance_percentage = fields.Float(
        string="Current Shrinkage Tolerance (%)",
        readonly=True,
    )
    current_shrinkage_tolerance_weight = fields.Float(
        string="Current Shrinkage Tolerance Weight",
        readonly=True,
    )
    current_production_weight = fields.Float(
        string="Current Production Weight",
        readonly=True,
    )
    current_net_weight = fields.Float(
        string="Current Net Weight",
        readonly=True,
    )
    new_shrinkage_tolerance_weight = fields.Float(
        string="New Shrinkage Tolerance Weight",
        readonly=True,
    )
    new_production_weight = fields.Float(
        string="New Production Weight",
        readonly=True,
    )
    new_net_weight = fields.Float(
        string="New Net Weight",
        readonly=True,
    )
    already_overridden = fields.Boolean(
        string="Already Overridden",
        readonly=True,
    )
