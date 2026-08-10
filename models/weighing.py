# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..constants.roles import Role


class Weighing(models.Model):
    _name = "wt.weighing"
    _description = "Weighing"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "production_date desc, weighing_date desc, id desc"

    STATE_SELECTION = [
        ("not_receipted", "Not Receipted"),
        ("in_production_receipt", "In Production Receipt"),
        ("receipt_validated", "Receipt Validated"),
        ("receipt_cancelled", "Receipt Cancelled"),
    ]
    DATA_SOURCE_SELECTION = [
        ("manual", "Manual"),
        ("api", "API"),
    ]

    DATA_PROBLEM_SELECTION = [
        ("none", "None"),
        ("company_mismatch", "Company Mismatch"),
        ("estate_mismatch", "Estate Mismatch"),
        ("operator_mismatch", "Operator Mismatch"),
        ("weighing_location_mismatch", "Weighing Location Mismatch"),
        ("division_not_allowed", "Division Not Allowed"),
        ("receipt_rule_mismatch", "Receipt Rule Mismatch"),
        ("product_mapping_mismatch", "Product Mapping Mismatch"),
        ("clerk_mismatch", "Clerk Mismatch"),
        ("foreman_mismatch", "Foreman Mismatch"),
        ("tapper_mismatch", "Tapper Mismatch"),
        ("weight_formula_mismatch", "Weight Formula Mismatch"),
        ("initial_weighing_date_mismatch", "Initial Weighing Date Mismatch"),
        ("initial_weight_mismatch", "Initial Weight Mismatch"),
        ("shrinkage_tolerance_mismatch", "Shrinkage Tolerance Mismatch"),
        ("inactive_master", "Inactive Master"),
        ("missing_master", "Missing Master"),
        ("multiple_problem", "Multiple Problem"),
    ]
    DATA_PROBLEM_TRIGGER_FIELDS = {
        "company_id",
        "estate_id",
        "weighing_location_id",
        "division_id",
        "operator_employee_id",
        "clerk_employee_id",
        "foreman_id",
        "foreman_employee_id",
        "tapper_id",
        "tapper_employee_id",
        "product_id",
        "receipt_rule_id",
        "production_date",
        "weighing_date",
        "production_weight",
        "reject_weight",
        "slab_weight",
        "net_weight",
        "shrinkage_tolerance_percentage",
        "shrinkage_tolerance_weight",
        "initial_weighing_date",
        "initial_device_id",
        "initial_weighing_location_id",
        "initial_weight",
    }

    name = fields.Char(
        string="Number",
        default="/",
        readonly=True,
        copy=False,
        index=True,
        tracking=True,
    )
    local_id = fields.Char(
        string="Local ID",
        index=True,
        tracking=True,
    )
    device_id = fields.Char(
        string="Device ID",
        index=True,
        tracking=True,
    )
    device_record_id = fields.Many2one(
        "wt.device",
        string="Device",
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        index=True,
        tracking=True,
    )
    allowed_division_ids = fields.Many2many(
        "wt.division",
        string="Allowed Divisions",
        compute="_compute_allowed_division_ids",
    )
    production_date = fields.Date(
        string="Production Date",
        required=True,
        index=True,
        tracking=True,
    )
    weighing_date = fields.Datetime(
        string="Weighing Date",
        required=True,
        index=True,
        tracking=True,
    )
    master_synced_at = fields.Datetime(
        string="Master Synced At",
        tracking=True,
    )
    sent_at = fields.Datetime(
        string="Sent At",
        tracking=True,
    )
    received_at = fields.Datetime(
        string="Received At",
        tracking=True,
    )
    batch_local_id = fields.Char(
        string="Batch Local ID",
        index=True,
        tracking=True,
    )
    state = fields.Selection(
        STATE_SELECTION,
        string="Status",
        default="not_receipted",
        required=True,
        index=True,
        tracking=True,
    )
    production_receipt_id = fields.Many2one(
        "wt.production.receipt",
        string="Production Receipt",
        ondelete="set null",
        readonly=True,
        index=True,
        copy=False,
        tracking=True,
    )
    delivery_step_id = fields.Many2one(
        "wt.delivery.step",
        string="Delivery Step",
        ondelete="set null",
        index=True,
        copy=False,
        tracking=True,
        help="Tahapan pengiriman (Delivery Step) yang menggunakan sesi timbang ini.",
    )
    data_source = fields.Selection(
        DATA_SOURCE_SELECTION,
        string="Data Source",
        default="manual",
        required=True,
        store=True,
        index=True,
    )
    has_data_problem = fields.Boolean(
        string="Has Data Problem",
        default=False,
        index=True,
        tracking=True,
    )
    data_problem_code = fields.Selection(
        DATA_PROBLEM_SELECTION,
        string="Data Problem Code",
        default="none",
        tracking=True,
    )
    data_problem_note_en = fields.Text(
        string="Data Problem Note (English)",
        tracking=True,
    )
    data_problem_note_idn = fields.Text(
        string="Data Problem Note (Indonesian)",
        tracking=True,
    )
    data_problem_note = fields.Text(
        string="Data Problem Note",
        compute="_compute_data_problem_note",
    )
    device_snapshot_json = fields.Text(
        string="Device Snapshot",
        readonly=True,
    )
    odoo_snapshot_json = fields.Text(
        string="Odoo Snapshot",
        readonly=True,
    )

    estate_id = fields.Many2one(
        "wt.estate",
        string="Estate",
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    weighing_location_id = fields.Many2one(
        "wt.weighing.location",
        string="Weighing Location",
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    division_id = fields.Many2one(
        "wt.division",
        string="Division",
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        default=lambda self: self._configured_product_for_company(self.env.company),
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    receipt_rule_id = fields.Many2one(
        "wt.receipt.rule",
        string="Receipt Rule",
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    uom_id = fields.Many2one(
        "uom.uom",
        string="UoM",
        default=lambda self: self._configured_product_for_company(self.env.company).uom_id,
        ondelete="restrict",
        tracking=True,
    )

    operator_employee_id = fields.Many2one(
        "hr.employee",
        string="Name",
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    operator_name = fields.Char(
        string="Operator Name",
        related="operator_employee_id.name",
        store=True,
        readonly=True,
    )
    operator_barcode = fields.Char(
        string="Badge Number",
        related="operator_employee_id.barcode",
        store=True,
        readonly=True,
    )
    clerk_employee_id = fields.Many2one(
        "hr.employee",
        string="Name",
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    clerk_name = fields.Char(
        string="Clerk Name",
        related="clerk_employee_id.name",
        store=True,
        readonly=True,
    )
    clerk_barcode = fields.Char(
        string="Badge Number",
        related="clerk_employee_id.barcode",
        store=True,
        readonly=True,
    )
    foreman_id = fields.Many2one(
        "wt.foreman",
        string="Foreman",
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    foreman_employee_id = fields.Many2one(
        "hr.employee",
        string="Name",
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    foreman_name = fields.Char(
        string="Foreman Name",
        related="foreman_employee_id.name",
        store=True,
        readonly=True,
    )
    foreman_barcode = fields.Char(
        string="Badge Number",
        related="foreman_employee_id.barcode",
        store=True,
        readonly=True,
    )
    tapper_id = fields.Many2one(
        "wt.tapper",
        string="Tapper",
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    tapper_employee_id = fields.Many2one(
        "hr.employee",
        string="Name",
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    tapper_name = fields.Char(
        string="Tapper Name",
        related="tapper_employee_id.name",
        store=True,
        readonly=True,
    )
    tapper_barcode = fields.Char(
        string="Badge Number",
        related="tapper_employee_id.barcode",
        store=True,
        readonly=True,
    )

    total_bag = fields.Integer(
        string="Total Bag",
        tracking=True,
    )
    production_weight = fields.Float(
        string="Production Weight",
        tracking=True,
    )
    reject_weight = fields.Float(
        string="Reject Weight",
        tracking=True,
    )
    slab_weight = fields.Float(
        string="Slab Weight",
        tracking=True,
    )
    net_weight = fields.Float(
        string="Net Weight",
        tracking=True,
    )
    shrinkage_tolerance_percentage = fields.Float(
        string="Shrinkage Tolerance (%)",
        tracking=True,
    )
    shrinkage_tolerance_weight = fields.Float(
        string="Shrinkage Tolerance Weight",
        tracking=True,
    )
    shrinkage_tolerance_override = fields.Boolean(
        string="Shrinkage Tolerance Override",
        default=False,
        copy=False,
        tracking=True,
    )
    shrinkage_tolerance_override_reason = fields.Text(
        string="Shrinkage Tolerance Override Reason",
        copy=False,
        tracking=True,
    )
    shrinkage_tolerance_override_at = fields.Datetime(
        string="Shrinkage Tolerance Override At",
        readonly=True,
        copy=False,
        tracking=True,
    )
    shrinkage_tolerance_override_by_id = fields.Many2one(
        "res.users",
        string="Shrinkage Tolerance Override By",
        readonly=True,
        copy=False,
        tracking=True,
    )
    shrinkage_tolerance_override_id = fields.Many2one(
        "wt.shrinkage.tolerance.override",
        string="Shrinkage Tolerance Override Reference",
        readonly=True,
        copy=False,
        tracking=True,
    )
    original_shrinkage_tolerance_percentage = fields.Float(
        string="Original Shrinkage Tolerance (%)",
        readonly=True,
        copy=False,
    )
    original_shrinkage_tolerance_weight = fields.Float(
        string="Original Shrinkage Tolerance Weight",
        readonly=True,
        copy=False,
    )
    original_production_weight = fields.Float(
        string="Original Production Weight",
        readonly=True,
        copy=False,
    )
    original_net_weight = fields.Float(
        string="Original Net Weight",
        readonly=True,
        copy=False,
    )
    is_manual_weighing = fields.Boolean(
        string="Manual Weighing",
        tracking=True,
    )
    manual_weighing_reason = fields.Text(
        string="Manual Weighing Reason",
        tracking=True,
    )
    manual_log_local_id = fields.Char(
        string="Manual Log Local ID",
        related="manual_log_id.local_id",
        store=True,
        index=True,
        readonly=True,
    )
    manual_log_id = fields.Many2one(
        "wt.weighing.manual.log",
        string="Manual Log",
        ondelete="set null",
        index=True,
        tracking=True,
    )
    note = fields.Text(
        string="Note",
        tracking=True,
    )

    initial_weighing_date = fields.Datetime(
        string="Initial Weighing Date",
        tracking=True,
    )
    initial_weighing_location_id = fields.Many2one(
        "wt.weighing.location",
        string="Initial Weighing Location",
        ondelete="restrict",
        domain="[('company_id', '=', company_id), ('location_type', '=', 'field')]",
        tracking=True,
    )
    initial_device_id = fields.Many2one(
        "wt.device",
        string="By Device",
        ondelete="restrict",
        tracking=True,
    )
    initial_device_role = fields.Selection(
        Role.DEVICE_SELECTION,
        string="Role",
        related="initial_device_id.role",
        store=True,
        readonly=True,
    )
    initial_device_employee_id = fields.Many2one(
        "hr.employee",
        string="Device Owner",
        related="initial_device_id.employee_id",
        store=True,
        readonly=True,
    )
    initial_device_employee_name = fields.Char(
        string="Initial Device Employee Name",
        related="initial_device_employee_id.name",
        store=True,
        readonly=True,
    )
    initial_device_employee_barcode = fields.Char(
        string="Device Owner Badge Number",
        related="initial_device_employee_id.barcode",
        store=True,
        readonly=True,
    )
    initial_weight = fields.Float(
        string="Initial Weight",
        tracking=True,
    )
    initial_is_manual_weighing = fields.Boolean(
        string="Initial Manual Weighing",
        tracking=True,
    )
    initial_manual_weighing_reason = fields.Text(
        string="Initial Manual Weighing Reason",
        tracking=True,
    )
    initial_note = fields.Text(
        string="Initial Weighing Note",
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        sequence_model = self.env["ir.sequence"]
        for vals in vals_list:
            self._set_estate_from_location_vals(vals)
            self._set_product_from_company_vals(vals)
            self._set_uom_from_product_vals(vals)
            if not vals.get("name") or vals["name"] == "/":
                sequence_date = (
                    fields.Date.to_date(vals["production_date"])
                    if vals.get("production_date")
                    else fields.Date.context_today(self)
                )
                vals["name"] = sequence_model.next_by_code(
                    "wt.weighing",
                    sequence_date=sequence_date,
                )
                if not vals["name"]:
                    raise ValidationError(
                        _("Weighing sequence is not configured.")
                    )
            if vals.get("data_source", "manual") == "manual":
                vals.update(
                    {
                        "local_id": False,
                        "device_id": False,
                        "device_record_id": False,
                        "batch_local_id": False,
                    }
                )
        records = super().create(vals_list)
        for detail in records.filtered(lambda record: record.data_source == "manual"):
            detail.with_context(
                skip_auto_recheck_data_problem=True
            )._sync_assignment_refs_from_employees()
        records.filtered(lambda record: record.data_source == "manual").with_context(
            skip_auto_recheck_data_problem=True
        ).action_recheck_data_problem()
        return records

    def write(self, vals):
        vals = dict(vals)
        if not self.env.context.get("allow_production_receipt_update"):
            locked = self.filtered(
                lambda record: record.state == "receipt_validated"
            )
            allowed_locked_fields = {"state", "production_receipt_id"}
            if locked and (set(vals) - allowed_locked_fields):
                raise ValidationError(
                    _(
                        "Weighing detail is locked because its Production Receipt is validated."
                    )
                )
        self._set_estate_from_location_vals(vals)
        self._set_product_from_company_vals(vals)
        self._set_uom_from_product_vals(vals)
        result = super().write(vals)
        if set(vals) & {
            "division_id",
            "foreman_employee_id",
            "tapper_employee_id",
        }:
            self.filtered(
                lambda record: record.data_source == "manual"
                and record.state != "receipt_validated"
            ).with_context(
                skip_auto_recheck_data_problem=True
            )._sync_assignment_refs_from_employees()
        if not self.env.context.get("skip_auto_recheck_data_problem") and (
            set(vals) & self.DATA_PROBLEM_TRIGGER_FIELDS
        ):
            self.filtered(
                lambda record: record.state != "receipt_validated"
            ).with_context(skip_auto_recheck_data_problem=True).action_recheck_data_problem()
        return result

    def unlink(self):
        if self.filtered(lambda record: record.state == "receipt_validated"):
            raise ValidationError(
                _(
                    "Weighing detail is locked because its Production Receipt is validated."
                )
            )
        return super().unlink()

    def _set_estate_from_location_vals(self, vals):
        location_id = vals.get("weighing_location_id")
        if location_id:
            location = self.env["wt.weighing.location"].browse(location_id)
            vals["estate_id"] = location.estate_id.id

    def _set_uom_from_product_vals(self, vals):
        if "product_id" in vals and not vals.get("uom_id"):
            product = self.env["product.product"].browse(vals["product_id"])
            vals["uom_id"] = product.uom_id.id if product else False

    def _set_product_from_company_vals(self, vals):
        if not vals.get("company_id"):
            return
        product = self._configured_product_for_company(
            self.env["res.company"].browse(vals["company_id"])
        )
        if product:
            vals["product_id"] = product.id
            vals["uom_id"] = product.uom_id.id
        else:
            vals["product_id"] = False
            vals["uom_id"] = False

    def _configured_product_for_company(self, company):
        if not company:
            return self.env["product.product"]
        product_config = self.env["wt.product"].sudo().search(
            [("company_id", "=", company.id), ("active", "=", True)],
            limit=1,
        )
        return product_config.product_id

    @api.depends_context("lang")
    @api.depends("data_problem_note_en", "data_problem_note_idn")
    def _compute_data_problem_note(self):
        for detail in self:
            if detail.env.lang == "id_ID":
                detail.data_problem_note = (
                    detail.data_problem_note_idn or detail.data_problem_note_en
                )
            else:
                detail.data_problem_note = (
                    detail.data_problem_note_en or detail.data_problem_note_idn
                )

    def action_apply_shrinkage_tolerance_override(
        self, percentage, reason, override_record=False
    ):
        percentage = float(percentage or 0.0)
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError(
                _("Shrinkage tolerance override reason is required.")
            )
        if percentage < 0 or percentage > 100:
            raise ValidationError(
                _("Shrinkage tolerance override percentage must be between 0 and 100.")
            )
        for weighing in self:
            weighing._check_can_override_shrinkage_tolerance()
            tolerance_weight = weighing.initial_weight * percentage / 100.0
            production_weight = weighing.initial_weight - tolerance_weight
            net_weight = production_weight - weighing.reject_weight - weighing.slab_weight
            if production_weight <= 0:
                raise ValidationError(
                    _("Production Weight after override must be greater than zero.")
                )
            if net_weight <= 0:
                raise ValidationError(
                    _("Net Weight after override must be greater than zero.")
                )

            vals = {
                "shrinkage_tolerance_override": True,
                "shrinkage_tolerance_override_reason": reason,
                "shrinkage_tolerance_override_at": fields.Datetime.now(),
                "shrinkage_tolerance_override_by_id": self.env.user.id,
                "shrinkage_tolerance_percentage": percentage,
                "shrinkage_tolerance_weight": tolerance_weight,
                "production_weight": production_weight,
                "net_weight": net_weight,
            }
            if override_record:
                vals["shrinkage_tolerance_override_id"] = override_record.id
            if not weighing.shrinkage_tolerance_override:
                vals.update(
                    {
                        "original_shrinkage_tolerance_percentage": (
                            weighing.shrinkage_tolerance_percentage
                        ),
                        "original_shrinkage_tolerance_weight": (
                            weighing.shrinkage_tolerance_weight
                        ),
                        "original_production_weight": weighing.production_weight,
                        "original_net_weight": weighing.net_weight,
                    }
                )
            weighing.write(vals)

    def _check_can_override_shrinkage_tolerance(self):
        self.ensure_one()
        if self.state == "receipt_validated":
            raise ValidationError(
                _("Shrinkage tolerance cannot be overridden for Receipt Validated weighing.")
            )
        if self.has_data_problem:
            raise ValidationError(
                _("Shrinkage tolerance cannot be overridden for weighing with data problem.")
            )
        if not self.initial_weighing_date or self.initial_weight <= 0:
            raise ValidationError(
                _("Shrinkage tolerance override requires initial weighing data.")
            )

    def init(self):
        self.env.cr.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'wt_weighing'
                      AND column_name = 'data_problem_note'
                )
                AND EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'wt_weighing'
                      AND column_name = 'data_problem_note_en'
                )
                THEN
                    UPDATE wt_weighing
                       SET data_problem_note_en = data_problem_note
                     WHERE COALESCE(data_problem_note_en, '') = ''
                       AND COALESCE(data_problem_note, '') != '';
                END IF;
            END
            $$;
            """
        )
        self.env.cr.execute(
            """
            ALTER TABLE wt_weighing
            DROP CONSTRAINT IF EXISTS wt_weighing_device_product_local_uniq
            """
        )
        self.env.cr.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'wt_weighing'
                      AND column_name = 'receipt_status'
                )
                THEN
                    UPDATE wt_weighing
                       SET state = receipt_status
                     WHERE COALESCE(receipt_status, '') IN (
                         'not_receipted',
                         'in_production_receipt',
                         'receipt_validated',
                         'receipt_cancelled'
                     );
                END IF;

                UPDATE wt_weighing
                   SET state = 'not_receipted'
                 WHERE COALESCE(state, '') NOT IN (
                     'not_receipted',
                     'in_production_receipt',
                     'receipt_validated',
                     'receipt_cancelled'
                 );
            END
            $$;
            """
        )
        self.env.cr.execute(
            """
            DROP INDEX IF EXISTS wt_weighing_api_idempotency_uniq
            """
        )
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS wt_weighing_api_idempotency_uniq
            ON wt_weighing (device_id, local_id)
            WHERE data_source = 'api'
            """
        )

    @api.constrains(
        "data_source",
        "local_id",
        "device_id",
        "device_record_id",
    )
    def _check_api_identity_fields(self):
        for detail in self.filtered(lambda record: record.data_source == "api"):
            missing = []
            if not detail.local_id:
                missing.append(_("Local ID"))
            if not detail.device_id:
                missing.append(_("Device ID"))
            if not detail.device_record_id:
                missing.append(_("Device"))
            if missing:
                raise ValidationError(
                    _("API weighing requires: %s.") % ", ".join(missing)
                )

    def _sync_assignment_refs_from_employees(self):
        foreman_model = self.env["wt.foreman"].sudo()
        tapper_model = self.env["wt.tapper"].sudo()
        for detail in self:
            vals = {}
            foreman = foreman_model.browse()
            if detail.foreman_employee_id and detail.division_id:
                foreman = foreman_model.search(
                    [
                        ("employee_id", "=", detail.foreman_employee_id.id),
                        ("division_id", "=", detail.division_id.id),
                    ],
                    limit=1,
                )
            if detail.foreman_id != foreman:
                vals["foreman_id"] = foreman.id or False

            tapper = tapper_model.browse()
            if detail.tapper_employee_id:
                tapper = tapper_model.search(
                    [("employee_id", "=", detail.tapper_employee_id.id)],
                    limit=1,
                )
            if detail.tapper_id != tapper:
                vals["tapper_id"] = tapper.id or False

            if vals:
                detail.write(vals)

    @api.depends("weighing_location_id")
    def _compute_allowed_division_ids(self):
        for detail in self:
            detail.allowed_division_ids = detail.weighing_location_id.allowed_division_ids

    @api.onchange("estate_id")
    def _onchange_estate_id(self):
        if (
            self.weighing_location_id
            and self.weighing_location_id.estate_id != self.estate_id
        ):
            self.weighing_location_id = False
            self.division_id = False
            self.receipt_rule_id = False

    @api.onchange("weighing_location_id")
    def _onchange_weighing_location_id(self):
        if self.weighing_location_id:
            self.estate_id = self.weighing_location_id.estate_id
            self.company_id = self.weighing_location_id.company_id
            product = self._configured_product_for_company(self.company_id)
            self.product_id = product
            self.uom_id = product.uom_id if product else False
            if self.division_id not in self.weighing_location_id.allowed_division_ids:
                self.division_id = False
                self.receipt_rule_id = False
            self._set_receipt_rule_from_scope()

    @api.onchange("division_id")
    def _onchange_receipt_rule_scope(self):
        self._set_receipt_rule_from_scope()

    @api.onchange("company_id")
    def _onchange_company_id(self):
        if (
            self.initial_device_id
            and self.company_id
            and self.initial_device_id.company_id != self.company_id
        ):
            self.initial_device_id = False
        if (
            self.initial_weighing_location_id
            and self.company_id
            and self.initial_weighing_location_id.company_id != self.company_id
        ):
            self.initial_weighing_location_id = False
        product = self._configured_product_for_company(self.company_id)
        self.product_id = product
        self.uom_id = product.uom_id if product else False
        self.receipt_rule_id = False

    def _set_receipt_rule_from_scope(self):
        if not (self.weighing_location_id and self.division_id):
            self.receipt_rule_id = False
            return
        self.receipt_rule_id = self.env["wt.receipt.rule"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("weighing_location_id", "=", self.weighing_location_id.id),
                ("division_id", "=", self.division_id.id),
            ],
            limit=1,
        )

    @api.constrains("estate_id", "weighing_location_id")
    def _check_weighing_location_estate(self):
        for detail in self:
            if (
                detail.estate_id
                and detail.weighing_location_id
                and detail.weighing_location_id.estate_id != detail.estate_id
            ):
                raise ValidationError(
                    _("Weighing location must belong to the selected estate.")
                )

    @api.constrains("weighing_location_id")
    def _check_weighing_location_type(self):
        for detail in self:
            if (
                detail.weighing_location_id
                and detail.weighing_location_id.location_type != "warehouse"
            ):
                raise ValidationError(
                    _("Weighing Location must use Warehouse type.")
                )

    @api.constrains("company_id", "initial_weighing_location_id")
    def _check_initial_weighing_location(self):
        for detail in self:
            if not detail.initial_weighing_location_id:
                continue
            if detail.initial_weighing_location_id.location_type != "field":
                raise ValidationError(
                    _("Initial Weighing Location must use Field type.")
                )
            if (
                detail.company_id
                and detail.initial_weighing_location_id.company_id != detail.company_id
            ):
                raise ValidationError(
                    _("Initial Weighing Location must belong to the selected company.")
                )

    @api.constrains("production_date", "weighing_date")
    def _check_production_date_not_after_weighing_date(self):
        for detail in self:
            detail._check_production_date_not_after_weighing_date_one()

    @api.constrains("is_manual_weighing", "manual_weighing_reason")
    def _check_manual_weighing_required_fields(self):
        for detail in self:
            detail._check_manual_weighing_required_one()

    @api.constrains(
        "initial_weighing_date",
        "initial_device_id",
        "initial_weighing_location_id",
        "initial_weight",
        "initial_is_manual_weighing",
        "initial_manual_weighing_reason",
    )
    def _check_initial_weighing_required_fields(self):
        for detail in self:
            detail._check_initial_weighing_required_one()

    @api.onchange("foreman_employee_id")
    def _onchange_foreman_employee_id(self):
        if not self.foreman_employee_id:
            self.foreman_id = False
            return
        foreman = self.env["wt.foreman"].search(
            [
                ("employee_id", "=", self.foreman_employee_id.id),
                ("division_id", "=", self.division_id.id),
            ],
            limit=1,
        )
        self.foreman_id = foreman

    @api.onchange("tapper_employee_id")
    def _onchange_tapper_employee_id(self):
        if not self.tapper_employee_id:
            self.tapper_id = False
            return
        domain = [
            ("employee_id", "=", self.tapper_employee_id.id),
            ("division_id", "=", self.division_id.id),
        ]
        if self.foreman_id:
            domain.append(("foreman_id", "=", self.foreman_id.id))
        tapper = self.env["wt.tapper"].search(domain, limit=1)
        self.tapper_id = tapper

    def action_recheck_data_problem(self):
        locked = self.filtered(
            lambda detail: detail.state == "receipt_validated"
        )
        if locked:
            raise ValidationError(
                _(
                    "Data problem cannot be rechecked because the Production Receipt is validated."
                )
            )
        service = self.env["wt.weighing.service"].sudo()
        for detail in self:
            result = service.evaluate_data_problem_from_record(detail)
            detail.write(
                {
                    "has_data_problem": result["has_data_problem"],
                    "data_problem_code": result["data_problem_code"],
                    "data_problem_note_en": result["data_problem_note_en"],
                    "data_problem_note_idn": result["data_problem_note_idn"],
                    "odoo_snapshot_json": result["odoo_snapshot_json"],
                }
            )

    def action_validate(self):
        raise ValidationError(
            _("Weighing detail validation is handled from Production Receipt.")
        )

    def _check_required_for_validate(self):
        for detail in self:
            missing_labels = detail._missing_validate_required_labels()
            if missing_labels:
                raise ValidationError(
                    _("Please complete required fields before validate: %s.")
                    % ", ".join(missing_labels)
                )

            detail._check_production_date_not_after_weighing_date_one()
            detail._check_manual_weighing_required_one()
            detail._check_initial_weighing_required_one()

    def _missing_validate_required_labels(self):
        self.ensure_one()
        required_fields = (
            ("production_date", _("Production Date")),
            ("weighing_date", _("Weighing Date")),
            ("company_id", _("Company")),
            ("estate_id", _("Estate")),
            ("division_id", _("Division")),
            ("weighing_location_id", _("Weighing Location")),
            ("product_id", _("Product")),
            ("uom_id", _("UoM")),
            ("receipt_rule_id", _("Receipt Rule")),
            ("operator_employee_id", _("Operator Name")),
            ("clerk_employee_id", _("Clerk Name")),
            ("foreman_employee_id", _("Foreman Name")),
            ("tapper_employee_id", _("Tapper Name")),
        )
        missing = [label for field_name, label in required_fields if not self[field_name]]
        positive_fields = (
            ("total_bag", _("Total Bag")),
            ("production_weight", _("Production Weight")),
            ("net_weight", _("Net Weight")),
        )
        missing.extend(
            label for field_name, label in positive_fields if self[field_name] <= 0
        )
        return missing

    def _check_production_date_not_after_weighing_date_one(self):
        self.ensure_one()
        if not (self.production_date and self.weighing_date):
            return
        if self.production_date > self._datetime_date_part(self.weighing_date):
            raise ValidationError(
                _("Production Date cannot be later than Weighing Date.")
            )

    def _datetime_date_part(self, value):
        datetime_value = fields.Datetime.to_datetime(value)
        return fields.Datetime.context_timestamp(self, datetime_value).date()

    def _check_manual_weighing_required_one(self):
        self.ensure_one()
        if self.is_manual_weighing and not self.manual_weighing_reason:
            raise ValidationError(
                _("Manual Weighing Reason is required when Manual Weighing is checked.")
            )

    def _check_initial_weighing_required_one(self):
        self.ensure_one()
        if not self.initial_weighing_date:
            return
        if not self.initial_device_id:
            if self.data_source == "api":
                return
            raise ValidationError(
                _("By Device is required when Initial Weighing Date is filled.")
            )
        if not self.initial_weighing_location_id:
            if self.data_source == "api":
                return
            raise ValidationError(
                _("Initial Weighing Location is required when Initial Weighing Date is filled.")
            )
        if self.initial_weight <= 0:
            raise ValidationError(
                _("Initial Weight is required when Initial Weighing Date is filled.")
            )
        if self.initial_is_manual_weighing and not self.initial_manual_weighing_reason:
            raise ValidationError(
                _("Initial Manual Weighing Reason is required when Initial Manual Weighing is checked.")
            )

    def action_cancel_validate(self):
        raise ValidationError(
            _("Weighing detail validation is handled from Production Receipt.")
        )

    def action_view_manual_log(self):
        self.ensure_one()
        if not self.manual_log_id:
            return False
        return {
            "name": _("Detail Timbang Manual Log"),
            "type": "ir.actions.act_window",
            "res_model": "wt.weighing.manual.log",
            "res_id": self.manual_log_id.id,
            "view_mode": "form",
            "target": "new",
        }

