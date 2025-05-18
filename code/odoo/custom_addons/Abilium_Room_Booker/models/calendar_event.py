from odoo import models, fields, api

class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    meeting_room = fields.Many2one(
        "res.partner",
        string='Room',
        domain="[('is_room', '=', True)]",  # domain we override dynamically in onchange
        help="Select a room (a partner marked as is_room)."
    )
    filter_room_by_capacity = fields.Boolean(
        string='Only show rooms with enough capacity',
        default=False,
    )
    location = fields.Char(compute="_compute_location", store=True)

    @api.onchange('filter_room_by_capacity', 'attendee_ids')
    def _onchange_filter_room(self):
        domain = [('is_room', '=', True)]
        if self.filter_room_by_capacity:
            domain.append(('room_capacity', '>=', self.attendees_count))
        return {
            'domain': {
                'meeting_room': domain
            }
        }


    @api.onchange('meeting_room')
    def _onchange_meeting_room(self):
        """

        """
        if not self.meeting_room:
            return  # Nothing to do if no room selected

        # Remove any previously selected room from attendees and partners
        room_attendees = self.attendee_ids.filtered(lambda a: a.partner_id.is_room)
        self.attendee_ids = self.attendee_ids - room_attendees
        self.partner_ids = self.partner_ids - room_attendees.mapped('partner_id')

        # Check if this room is already in attendees
        existing = self.attendee_ids.filtered(lambda a: a.partner_id == self.meeting_room)

        if not existing:
            attendee_vals = {
                'partner_id': self.meeting_room.id,
                'email': self.meeting_room.email or '',  # Email optional but may be required
            }

            if self.id:
                # Saved event — create real attendee record
                attendee_vals['event_id'] = self.id
                self.env['calendar.attendee'].create(attendee_vals)
            else:
                # Unsaved form — use new() to attach it in memory
                attendee = self.env['calendar.attendee'].new(attendee_vals)
                self.attendee_ids += attendee

            # Capacity check warning, always triggered when room is selected
            if self.meeting_room.room_capacity and self.attendees_count > self.meeting_room.room_capacity:
                return {
                    'warning': {
                        'title': 'Room Overcapacity',
                        'message': (
                            f"The selected room '{self.meeting_room.name}' only supports "
                            f"{self.meeting_room.room_capacity} people, but you have {self.attendees_count} attendees."
                        )
                    }
                }

        # Also add room to partner_ids so it's shown in attendee widget
        if self.meeting_room not in self.partner_ids:
            self.partner_ids += self.meeting_room


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
