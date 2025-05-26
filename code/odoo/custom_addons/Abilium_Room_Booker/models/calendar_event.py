# Import required Odoo modules for model creation and API functionality
from odoo import models, fields, api

class CalendarEvent(models.Model):
    """
    Custom extension of the Odoo Calendar. Inherits from the 'calendar.event' model and adds functionality
    for managing meeting rooms and dynamically computing event locations at runtime.
    """
    # Inherit from Odoo's base calendar event model to extend its functionality
    _inherit = 'calendar.event'

    # Field for selecting a meeting room from partners marked as rooms
    meeting_room = fields.Many2one(
        "res.partner",
        string='Room',
        help="Select a room (a partner marked as is_room)."
    )

    # Boolean field to control whether to filter rooms by capacity requirements
    filter_room_by_capacity = fields.Boolean(
        string='Only show rooms with enough capacity',
        default=False,
    )
    # NOTE: This is a duplicate field definition - the meeting_room field is defined twice
    # This computed version overrides the manual selection field above
    # Related meeting room partner, computed from partner_ids with is_room=True
    meeting_room = fields.Many2one("res.partner", compute="_compute_room", store=True)

    # Meeting room location string, computed from the associated meeting room's connection details
    location = fields.Char(compute="_compute_location", store=True)
    # Computed field that creates a domain filter for meeting rooms based on capacity
    meeting_room_domain = fields.Char(
        compute='_compute_meeting_room_domain',
        store=False  # Not stored in database, computed on-the-fly
    )

    @api.depends('filter_room_by_capacity', 'partner_ids')
    def _compute_meeting_room_domain(self):
        """
        Computes a domain filter for meeting rooms based on capacity requirements.
        Creates a dynamic filter that shows only rooms with sufficient capacity when enabled.
        """
        for record in self:
            # Base domain: only show partners marked as rooms
            domain = [('is_room', '=', True)]
            # Count non-room attendees to determine capacity needs
            attendee_count = len(record.partner_ids.filtered(lambda p: not p.is_room))
            # Ensure minimum count of 1 (for the organizer)
            if attendee_count == 0:
                attendee_count = 1
            # Add capacity filter if enabled
            if record.filter_room_by_capacity:
                domain.append(('room_capacity', '>=', attendee_count))

            # Convert to a string domain to use in XML views
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

        # Create commands list to update partner_ids using Odoo's ORM command syntax
        commands = []

        # Add commands to remove old rooms from the event's attendees
        if room_partners_to_remove:
            for partner in room_partners_to_remove:
                commands.append((3, partner.id))  # (3, id) command unlinks without deletion

        # Add command to add new room if it's not already in the attendee list
        if self.meeting_room and self.meeting_room not in self.partner_ids:
            commands.append((4, self.meeting_room.id))  # (4, id) command links existing record

        # Apply the commands if we have any changes to make
        if commands:
            self.partner_ids = commands

        # Display warning if room capacity is insufficient for the number of attendees
        if self.meeting_room and hasattr(self.meeting_room, 'room_capacity'):
            # Count non-room attendees
            attendee_count = len(self.partner_ids.filtered(lambda p: not p.is_room))
            # Ensure minimum count of 1 (for the organizer)
            if attendee_count == 0:
                attendee_count = 1
            # Check if room capacity is less than required
            if self.meeting_room.room_capacity < attendee_count:
                return {
                    'warning': {
                        'title': 'Insufficient Room Capacity',
                        'message': f'Selected room "{self.meeting_room.name}" has capacity for {self.meeting_room.room_capacity} '
                                   f'people, but you have {attendee_count} attendees. This may be too crowded.'
                    }
                }

    # NOTE: Missing the _compute_room method that is referenced in the meeting_room field definition
    @api.depends("meeting_room")
    def _compute_location(self):
        """
        Computes the 'location' field based on the associated 'meeting_room'.
        It searches for a related 'rasproom.connection' record and builds a
        location string using its street, city, and floor.
        """
        for event in self:
            # Initialize location as empty string
            location = ''
            if event.meeting_room:
                # Look for a rasproom.connection linked to the meeting_room partner
                connection = self.env['rasproom.connection'].search(
                    [('partner_id', '=', event.meeting_room.id)],
                    limit=1 # Only get the first matching connection
                )
                if connection:
                    # Build the location string by joining available address fields
                    # filter(None, ...) removes empty/None values from the list
                    parts = filter(None, [connection.street, connection.city, connection.floor])
                    location = ', '.join(parts)
            # Assign the computed location to the event
            event.location = location
