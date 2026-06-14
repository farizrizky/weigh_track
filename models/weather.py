# -*- coding: utf-8 -*-

from odoo import fields, models


class Weather(models.Model):
    _name = "wt.weather"
    _description = "Weather"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(
        string="Name",
        required=True,
        index=True,
        tracking=True,
    )
    description = fields.Text(
        string="Description",
        tracking=True,
    )
