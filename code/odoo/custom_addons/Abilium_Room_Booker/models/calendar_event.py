from odoo import models, fields, api

class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    meeting_room = fields.Many2many("res.partner", compute="_compute_room", store=True)
    location = fields.Char(compute="_compute_location", store=True)

    # add attendee to field if has is_room=True
    @api.depends("partner_ids")
    def _compute_room(self):
        for record in self:
            record.meeting_room = record.partner_ids.filtered(lambda p:p.is_room)

    # compute location dependent on meeting_room
    @api.depends("meeting_room")
    def _compute_location(self):
        for event in self:
            location = ''
            if event.meeting_room:
                # Look for a rasproom.connection linked to this partner
                connection = self.env['rasproom.connection'].search(
                    [('partner_id', '=', event.meeting_room.id)],
                    limit=1
                )
                if connection:
                    # Formatting the location string
                    parts = filter(None, [connection.street, connection.city, connection.floor])
                    location = ', '.join(parts)
            event.location = location
