# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Customer(models.Model):
    _name = "wt.customer"
    _description = "WeighTrack Customer"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "company_id, partner_id"

    active = fields.Boolean(default=True, tracking=True)
    name = fields.Char(
        compute="_compute_name",
        store=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        required=True,
        ondelete="restrict",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        tracking=True,
    )

    @api.depends("company_id", "partner_id")
    def _compute_name(self):
        for customer in self:
            customer.name = "%s - %s" % (
                customer.company_id.name or "",
                customer.partner_id.display_name or "",
            )

    def init(self):
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS wt_customer_company_partner_active_uniq
            ON wt_customer (company_id, partner_id)
            WHERE active
            """
        )

    @api.constrains("company_id", "partner_id")
    def _check_partner_company(self):
        for customer in self:
            if not (customer.company_id and customer.partner_id):
                continue
            partner_company = (
                customer.partner_id.company_id
                or customer.partner_id.commercial_partner_id.company_id
            )
            if partner_company and partner_company != customer.company_id:
                raise ValidationError(_(
                    "Customer contact must belong to the same company or be a shared contact."
                ))

    @api.constrains("company_id", "partner_id", "active")
    def _check_unique_active_customer(self):
        for customer in self:
            if not (customer.active and customer.company_id and customer.partner_id):
                continue
            duplicate = self.search(
                [
                    ("id", "!=", customer.id),
                    ("company_id", "=", customer.company_id.id),
                    ("partner_id", "=", customer.partner_id.id),
                    ("active", "=", True),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(_(
                    "Customer contact must be unique per company."
                ))

    @api.model
    def get_allowed_partners(self, company):
        if not company:
            return self.env["res.partner"].browse()
        return self.sudo().search([
            ("company_id", "=", company.id),
            ("active", "=", True),
        ]).mapped("partner_id")

    @api.model
    def is_allowed_partner(self, company, partner):
        if not (company and partner):
            return False
        return bool(self.sudo().search_count([
            ("company_id", "=", company.id),
            ("partner_id", "=", partner.id),
            ("active", "=", True),
        ]))
