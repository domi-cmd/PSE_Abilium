from odoo import models, fields

class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    room_ids = fields.Many2many(
        'res.partner',
        'calendar_event_room_rel',
        'event_id',
        'room_partner_id',
        string='Rooms',
        domain=[('is_room', '=', True)],
    )

    # Add custom fields
    meeting_room = fields.Many2one(
        'rasproom.connection', 
        string="Choose Meeting Room", 
        # TODO: Check if this should be set to 'False'?
        required=False,
        # Ensure only available rooms are shown
        domain=[('status', '=', True)]  
    )