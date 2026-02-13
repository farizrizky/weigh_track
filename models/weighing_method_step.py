from odoo import models, fields

class WeighingMethodStep(models.Model):
    _name = 'wt.weighing.method.step'
    _description = 'Weighing Method Step'

    weighing_type_id = fields.Many2one(
        'wt.weighing.type',
        string='Weighing Type',
        required=True
    )
    sequence = fields.Integer(string='Sequence', required=True)
    weighing_method_id = fields.Many2one(
        'wt.weighing.method',
        string='Weighing Method',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    _unique_weighing_method_step = models.Constraint (
        'UNIQUE(weighing_method_id, sequence)',
        'The combination of Weighing Method and Sequence must be unique.'
    )

    _unique_weighing_method_step_type = models.Constraint (
        'UNIQUE(weighing_method_id, weighing_type_id)',
        'A Weighing Type can only appear once per Weighing Method.'
    )