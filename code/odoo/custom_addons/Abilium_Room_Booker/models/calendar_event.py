from odoo import models, fields, api
import json

class CalendarEvent(models.Model):
    """
    Custom extension of the Odoo Calendar. Inherits from the 'calendar.event' model and adds functionality
    for managing meeting rooms and dynamically computing event locations at runtime.
    """
    _inherit = 'calendar.event'

    filter_room_by_capacity = fields.Boolean(
        string='Only show rooms with enough capacity',
        default=False,
    )
    # Related meeting room partner, computed from partner_ids with is_room=True
    meeting_room = fields.Many2one("res.partner", compute="_compute_room", store=True,
                                   string='Room',
                                   help="Select a room (a partner marked as is_room)."
    )

    # Meeting room location string, computed from the associated meeting room's connection details
    location = fields.Char(compute="_compute_location", store=True)
    meeting_room_domain = fields.Char(
        compute='_compute_meeting_room_domain',
        store=False
    )

    # list of meeting_rooms that are book at the time of this meeting
    booked_room_ids = fields.Many2many(
        'res.partner',
        compute='_onchange_booked_rooms',
        store=False
    )

    @api.depends('filter_room_by_capacity', 'partner_ids', 'booked_room_ids')
    def _compute_meeting_room_domain(self):
        for record in self:
            # Base domain: only rooms
            domain = [('is_room', '=', True)]

            # Exclude already booked rooms
            if record.booked_room_ids:
                booked_ids = record.booked_room_ids.ids
                domain.append(('id', 'not in', booked_ids))

            # Count attendees (excluding room resources)
            attendee_count = len(record.partner_ids.filtered(lambda p: not p.is_room)) or 1

            # Filter by capacity if enabled
            if record.filter_room_by_capacity:
                domain.append(('room_capacity', '>=', attendee_count))

        # Convert domain to JSON string for safe evaluation
        record.meeting_room_domain = json.dumps(domain)

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
            attendee_count = len(self.partner_ids.filtered(lambda p: not p.is_room))
            if attendee_count == 0:
                attendee_count = 1

            if self.meeting_room.room_capacity < attendee_count:
                return {
                    'warning': {
                        'title': 'Insufficient Room Capacity',
                        'message': f'Selected room "{self.meeting_room.name}" has capacity for {self.meeting_room.room_capacity} '
                                   f'people, but you have {attendee_count} attendees. This may be too crowded.'
                    }
                }


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


    @api.constrains('meeting_room', 'start', 'stop')
    def _check_meeting_room_availability(self):
        """
        raises error if the meeting_room of this event is
        already booked during a timeframe
        """
        for event in self:
            if not event.meeting_room:
                continue
            overlapping = self.search([
                ('id', '!=', event.id),
                ('meeting_room', '=', event.meeting_room.id),
                ('start', '<', event.stop),
                ('stop', '>', event.start),
            ])
            if overlapping:
                raise ValidationError(f"Room {event.meeting_room.name} is already booked.")


    @api.onchange('meeting_room', 'start', 'stop')
    def _onchange_booked_rooms(self):
        """
        creates a list of meeting rooms in meetings
        during the timeframe of this meeting and
        saves it in booked_room_ids.
        """
        if self.start and self.stop:
            overlapping_events = self.env['calendar.event'].search([
                ('id', '!=', self.id),
                ('meeting_room', '!=', False),
                ('start', '<', self.stop),
                ('stop', '>', self.start),
            ])
            self.booked_room_ids = overlapping_events.mapped('meeting_room').ids
        else:
            self.booked_room_ids = []