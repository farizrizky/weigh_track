from odoo import models, fields

class Division(models.Model):
    _name = 'wt.division'
    _description = 'Division'

    name = fields.Char(string='Division Name', required=True)
    code = fields.Char(string='Division Code', required=True, unique=True)
    