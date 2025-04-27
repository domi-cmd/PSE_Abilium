from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    # field resource_calendar_id is called "Working Hours" and contains a resource.calendar
    resource_calendar_id = fields.Many2one('resource.calendar', string="Working Hours")
    # field is_room defined as Boolean is called "Is Room?"
    is_room = fields.Boolean(string="Is Room?")
