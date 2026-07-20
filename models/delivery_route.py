# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DeliveryRoute(models.Model):
    _name = "wt.delivery.route"
    _description = "Rute Pengiriman"
    _order = "name"

    name = fields.Char(
        string="Nama",
        required=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        required=True,
        default=lambda self: self.env.company,
    )
    description = fields.Text(
        string="Description",
    )
    line_ids = fields.One2many(
        "wt.delivery.route.line",
        "route_id",
        string="Rute",
        copy=True,
    )
    active = fields.Boolean(
        string="Aktif",
        default=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_required_lines()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._check_required_lines()
        return result

    def _check_required_lines(self):
        for rec in self:
            if not rec.line_ids:
                raise ValidationError(_(
                    "Rute pengiriman '%s' harus memiliki minimal satu line."
                ) % rec.display_name)

    @api.constrains("line_ids")
    def _check_line_ids(self):
        self._check_required_lines()


class DeliveryRouteLine(models.Model):
    _name = "wt.delivery.route.line"
    _description = "Line Rute Pengiriman"
    _order = "route_id, sequence, id"

    route_id = fields.Many2one(
        "wt.delivery.route",
        string="Rute Pengiriman",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Perusahaan",
        related="route_id.company_id",
        store=True,
        readonly=True,
    )
    sequence = fields.Integer(
        string="Sequence",
        required=True,
        default=10,
    )
    route_type = fields.Selection(
        [
            ("transit", "Transit"),
            ("outgoing", "Outgoing"),
        ],
        string="Route Type",
        required=True,
        default="transit",
    )
    picking_type_id = fields.Many2one(
        "stock.picking.type",
        string="Operation Type",
        required=True,
        domain="[('code', '=', route_type == 'transit' and 'internal' or 'outgoing')]",
    )
    allowed_source_location_ids = fields.Many2many(
        "stock.location",
        compute="_compute_allowed_source_location_ids",
        string="Allowed Source Locations",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Location Source",
        required=True,
        domain="[('id', 'in', allowed_source_location_ids)]",
    )
    location_dest_id = fields.Many2one(
        "stock.location",
        string="Location Destination",
        required=True,
        domain="[('usage', 'in', ('internal', 'transit', 'customer'))]",
    )

    @api.depends("picking_type_id", "company_id")
    def _compute_allowed_source_location_ids(self):
        location_model = self.env["stock.location"]
        for rec in self:
            domain = [("usage", "=", "internal")]
            warehouse = rec.picking_type_id.warehouse_id
            if warehouse and warehouse.view_location_id:
                domain.append(("id", "child_of", warehouse.view_location_id.id))
            if rec.company_id:
                domain.append(("company_id", "in", [False, rec.company_id.id]))
            rec.allowed_source_location_ids = location_model.search(domain)

    @api.onchange("route_type")
    def _onchange_route_type(self):
        for rec in self:
            if rec.picking_type_id:
                expected_code = rec._expected_operation_code()
                if rec.picking_type_id.code != expected_code:
                    rec.picking_type_id = False
                    rec.location_id = False
                    rec.location_dest_id = False

    @api.onchange("picking_type_id")
    def _onchange_picking_type_id(self):
        for rec in self:
            if rec.location_id and rec.location_id not in rec.allowed_source_location_ids:
                rec.location_id = False

    def _expected_operation_code(self):
        self.ensure_one()
        return "internal" if self.route_type == "transit" else "outgoing"

    @api.constrains("sequence")
    def _check_sequence(self):
        for rec in self:
            if rec.sequence <= 0:
                raise ValidationError(_("Sequence harus lebih besar dari 0."))

    @api.constrains("route_id", "sequence")
    def _check_unique_sequence_per_route(self):
        for rec in self:
            if not rec.route_id or not rec.sequence:
                continue
            duplicate_count = self.search_count([
                ("id", "!=", rec.id),
                ("route_id", "=", rec.route_id.id),
                ("sequence", "=", rec.sequence),
            ])
            if duplicate_count:
                raise ValidationError(_(
                    "Sequence %s sudah digunakan pada rute '%s'."
                ) % (rec.sequence, rec.route_id.display_name))

    @api.constrains("location_id", "location_dest_id")
    def _check_locations_different(self):
        for rec in self:
            if rec.location_id == rec.location_dest_id:
                raise ValidationError(_(
                    "Location Source dan Location Destination tidak boleh sama pada rute '%s'."
                ) % rec.route_id.display_name)

    @api.constrains("company_id", "picking_type_id", "location_id", "location_dest_id")
    def _check_company_consistency(self):
        for rec in self:
            company = rec.company_id
            if not company:
                continue
            if rec.picking_type_id.company_id and rec.picking_type_id.company_id != company:
                raise ValidationError(_(
                    "Operation Type '%s' bukan milik perusahaan '%s'."
                ) % (rec.picking_type_id.display_name, company.display_name))
            for location in rec.location_id | rec.location_dest_id:
                if location.company_id and location.company_id != company:
                    raise ValidationError(_(
                        "Lokasi '%s' bukan milik perusahaan '%s'."
                    ) % (location.display_name, company.display_name))

    @api.constrains("picking_type_id", "location_id")
    def _check_source_location_in_operation_warehouse(self):
        for rec in self:
            warehouse = rec.picking_type_id.warehouse_id
            if not warehouse or not warehouse.view_location_id or not rec.location_id:
                continue
            valid_location = self.env["stock.location"].search_count([
                ("id", "=", rec.location_id.id),
                ("id", "child_of", warehouse.view_location_id.id),
            ])
            if not valid_location:
                raise ValidationError(_(
                    "Location Source '%s' harus berada di bawah gudang '%s' dari Operation Type '%s'."
                ) % (
                    rec.location_id.display_name,
                    warehouse.display_name,
                    rec.picking_type_id.display_name,
                ))

    @api.constrains("route_type", "picking_type_id", "location_dest_id")
    def _check_operation_flow(self):
        for rec in self:
            operation_code = rec.picking_type_id.code
            destination_usage = rec.location_dest_id.usage
            expected_code = rec._expected_operation_code()

            if operation_code != expected_code:
                raise ValidationError(_(
                    "Route Type '%s' tidak sesuai dengan Operation Type '%s'."
                ) % (dict(rec._fields["route_type"].selection).get(rec.route_type), rec.picking_type_id.display_name))

            if rec.route_type == "transit" and destination_usage == "customer":
                raise ValidationError(_(
                    "Route Type Transit tidak boleh menuju lokasi customer."
                ))

            if rec.route_type == "outgoing" and destination_usage != "customer":
                raise ValidationError(_(
                    "Route Type Outgoing harus menuju lokasi customer."
                ))

            if operation_code == "outgoing" and destination_usage != "customer":
                raise ValidationError(_(
                    "Operation Type Delivery Order harus menuju lokasi customer."
                ))

            if operation_code == "internal" and destination_usage == "customer":
                raise ValidationError(_(
                    "Operation Type Internal Transfer tidak boleh menuju lokasi customer."
                ))
