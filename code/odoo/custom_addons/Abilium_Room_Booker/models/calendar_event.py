from odoo import models, fields

class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    # Add custom fields
    meeting_room = fields.Many2one(
        'rasproom.connection', 
        string="Choose Meeting Room", 
        # TODO: Check if this should be set to 'False'?
        required=False,
        # Ensure only available rooms are shown
        domain=[('status', '=', True)]  
    )