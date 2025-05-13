from odoo import models, fields, api

class CalendarEvent(models.Model):
    """
    Custom extension of the Odoo Calendar. Inherits from the 'calendar.event' model and adds functionality
    for managing meeting rooms and dynamically computing event locations at runtime.
    """
    _inherit = 'calendar.event'

    # Related meeting room partner, computed from partner_ids with is_room=True
    meeting_room = fields.Many2one("res.partner", compute="_compute_room", store=True)
    
    # Meeting room location string, computed from the associated meeting room's connection details
    location = fields.Char(compute="_compute_location", store=True)

    @api.depends("partner_ids")
    def _compute_room(self):
        """
        Computes the 'meeting_room' field by filtering the event's attendees (partner_ids)
        and selecting the first partner that has 'is_room' set to True.
        """
        for record in self:
            # Filter attendees for partners marked as rooms, take the first such room
            record.meeting_room = record.partner_ids.filtered(lambda p:p.is_room)[:1]

    @api.depends("meeting_room")
    def _compute_location(self):
        """
        Computes the 'location' field based on the associated 'meeting_room'.
        It searches for a related 'rasproom.connection' record and builds a 
        location string using its street, city, and floor.
        """
        for event in self:
            location = ''
            if event.meeting_room:
                # Look for a rasproom.connection linked to the meeting_room partner
                connection = self.env['rasproom.connection'].search(
                    [('partner_id', '=', event.meeting_room.id)],
                    limit=1
                )
                if connection:
                    # Build the location string by joining available fields
                    parts = filter(None, [connection.street, connection.city, connection.floor])
                    location = ', '.join(parts)
            # Assign the computed location to the event
            event.location = location
