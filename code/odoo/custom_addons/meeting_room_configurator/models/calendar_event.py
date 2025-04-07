from odoo import models, fields

class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    # Add custom fields
    meeting_room = fields.Many2one(
        'meeting.room', 
        string="Choose Meeting Room", 
        required=True,
        domain=[('availability', '=', True)]  # Ensure only available rooms are shown
    )