from odoo import models, fields

class ResPartner(models.Model):
    """
    Extension of the res.partner model to add room and scheduling functionality

    This class inherits from the base res.partner model and adds fields for
    managing partners as rooms with capacity and working hours scheduling.
    """
    # Inherit from the existing res.partner model
    _inherit = 'res.partner'

    # Many2one relationship to resource.calendar model
    # Allows associating working hours/schedule with a partner
    resource_calendar_id = fields.Many2one('resource.calendar', string="Working Hours")

    # Boolean field to identify if this partner represents a room
    # Useful for filtering and categorizing partners in room management scenarios
    is_room = fields.Boolean(string="Is Room?")

    # Integer field to specify room capacity
    # Only relevant when is_room is True, but can be set independently
    room_capacity = fields.Integer(string="Capacity")
