from odoo import models, fields

class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    # Add custom fields
    meeting_room = fields.Many2one(
        'rasproom.connection', 
        string="Choose Meeting Room", 
        required=False,
        domain=[('status', '=', True)]  # Ensure only available rooms are shown
    )