# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WeatherData(models.Model):
    _name = "wt.weather.data"
    _description = "Weather Data"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "weather_date desc, estate_id"

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )
    weather_date = fields.Date(
        string="Date",
        required=True,
        index=True,
        tracking=True,
    )
    estate_id = fields.Many2one(
        "wt.estate",
        string="Estate",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="estate_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    weather_id = fields.Many2one(
        "wt.weather",
        string="Weather",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )

    _sql_constraints = [
        (
            "estate_date_uniq",
            "unique(estate_id, weather_date)",
            "Weather data must be unique per estate and date.",
        ),
    ]

    @api.depends("weather_date", "estate_id", "weather_id")
    def _compute_name(self):
        for weather_data in self:
            weather_data.name = "%s - %s - %s" % (
                weather_data.weather_date or "",
                weather_data.estate_id.name or "",
                weather_data.weather_id.name or "",
            )

    @api.constrains("estate_id", "weather_date")
    def _check_unique_estate_date(self):
        for weather_data in self:
            if not weather_data.estate_id or not weather_data.weather_date:
                continue
            duplicate = self.search(
                [
                    ("id", "!=", weather_data.id),
                    ("estate_id", "=", weather_data.estate_id.id),
                    ("weather_date", "=", weather_data.weather_date),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _(
                        "Weather data already exists for estate '%(estate)s' and date '%(date)s'."
                    )
                    % {
                        "estate": weather_data.estate_id.display_name,
                        "date": weather_data.weather_date,
                    }
                )
