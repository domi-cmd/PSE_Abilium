from odoo import models, fields

class RoomRaspConnection(models.Model):
    _name = 'rasproom.connection'
    _description = 'Raspberry & Room Connection'

    name = fields.Char(string='Connection Name', required=True)
    roomName = fields.Char(string='Room Name', required=True)
    raspName = fields.Char(string='Raspberry Name', required=True)
    capacity = fields.Integer(string='Capacity', required=True)
    location = fields.Char(string='Location')
    availability = fields.Boolean(string='Available', default=True)