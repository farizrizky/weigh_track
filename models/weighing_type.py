from odoo import models, fields

class WeighingType(models.Model):
    _name = 'wt.weighing.type'
    _description = 'Weighing Type'

    code = fields.Char(string='Code', required=True)
    name = fields.Char(string='Name', required=True)

    _unique_weighing_type_code = models.Constraint (
        'UNIQUE(code)',
        'Weighing Type Code must be unique.'
    )
    