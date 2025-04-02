from odoo import models, fields

class RoomRaspConnection(models.Model):
    _name = 'rasproom.connection'
    _description = 'Raspberry & Room Connection'

    name = fields.Char(string='Connection Name', required=True)
    room_id = fields.Many2one('meeting.room', string='Room', required=True)
    raspName = fields.Char(string='Raspberry Name', required=True)
    status = fields.Boolean(string='Active', default=True)