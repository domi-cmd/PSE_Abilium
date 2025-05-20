from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)
class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    meeting_room = fields.Many2one(
        "res.partner",
        string='Room',
        help="Select a room (a partner marked as is_room)."
    )
    filter_room_by_capacity = fields.Boolean(
        string='Only show rooms with enough capacity',
        default=False,
    )
    location = fields.Char(compute="_compute_location", store=True)
    meeting_room_domain = fields.Char(
        compute='_compute_meeting_room_domain',
        store=False
    )

    @api.depends('filter_room_by_capacity', 'partner_ids')
    def _compute_meeting_room_domain(self):
        for record in self:
            domain = [('is_room', '=', True)]

            attendee_count = len(record.partner_ids.filtered(lambda p: not p.is_room))
            if attendee_count == 0:
                attendee_count = 1

            if record.filter_room_by_capacity:
                domain.append(('room_capacity', '>=', attendee_count))

            # Convert to a string domain to use in XML
            record.meeting_room_domain = str(domain)

    @api.onchange('meeting_room')
    def _onchange_meeting_room(self):
        """
        When a meeting room is selected, add it to partner_ids.
        When a meeting room is removed or changed, update partner_ids accordingly.
        Also check if the selected room has sufficient capacity.
        """
        # First, remove any existing room partners that are not the current meeting room
        room_partners_to_remove = self.partner_ids.filtered(
            lambda p: p.is_room and (not self.meeting_room or p.id != self.meeting_room.id)
        )

        # Create commands list to update partner_ids
        commands = []

        # Add commands to remove old rooms
        if room_partners_to_remove:
            for partner in room_partners_to_remove:
                commands.append((3, partner.id))  # (3, id) command unlinks without deletion

        # Add command to add new room if needed
        if self.meeting_room and self.meeting_room not in self.partner_ids:
            commands.append((4, self.meeting_room.id))  # (4, id) command links existing record

        # Apply the commands if we have any
        if commands:
            self.partner_ids = commands

        # Display warning if room capacity is insufficient
        if self.meeting_room and hasattr(self.meeting_room, 'room_capacity'):
            # Use the base attendees_count
            attendee_count = self.attendees_count or 1

            if self.meeting_room.room_capacity < attendee_count:
                return {
                    'warning': {
                        'title': 'Insufficient Room Capacity',
                        'message': f'Selected room "{self.meeting_room.name}" has capacity for {self.meeting_room.room_capacity} '
                                   f'people, but you have {attendee_count} attendees. This may be too crowded.'
                    }
                }


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
