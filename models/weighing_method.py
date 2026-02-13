from odoo import models, fields, api
from ..services.formula_engine import validate_strict_formula

class WeighingMethod(models.Model):
    _name = 'wt.weighing.method'
    _description = 'Weighing Method'

    code = fields.Char(string='Code', required=True)
    name = fields.Char(string='Name', required=True)
    formula = fields.Text(string='Formula', required=True)

    resulting_weighing_type_id = fields.Many2one(
        'wt.weighing.type',
        string='Resulting Weighing Type',
        required=True,
    )

    weighing_method_step_ids = fields.One2many(
        'wt.weighing.method.step',
        'weighing_method_id',
        string='Weighing Steps'
    )

    _unique_weighing_method_code = models.Constraint (
        'UNIQUE(code)',
        'Weighing Method Code must be unique.'
    )

    @api.constrains('formula')
    def _check_formula(self):
        for rec in self:
            validate_strict_formula(rec.formula)