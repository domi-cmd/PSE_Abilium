from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    resource_calendar_id = fields.Many2one('resource.calendar', string="Working Hours")
