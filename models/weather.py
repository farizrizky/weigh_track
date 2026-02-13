from odoo import models, fields

class Weather(models.Model):
    _name = 'wt.weather'
    _description = 'Weather'

    code = fields.Char(string='Code', required=True)
    name = fields.Char(string='Name', required=True)

    _unique_weather_code = models.Constraint (
        'UNIQUE(code)',
        'Weather Code must be unique.'
    )