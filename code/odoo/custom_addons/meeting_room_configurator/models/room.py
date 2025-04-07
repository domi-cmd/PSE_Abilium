from odoo import models, fields

class MeetingRoom(models.Model):
    _name = 'meeting.room'
    _description = 'Meeting Room'

    name = fields.Char(string='Room Name', required=True)
    capacity = fields.Integer(string='Capacity', required=True)
    street = fields.Char(string='Street')
    city = fields.Char(string='City')
    floor = fields.Char(string='Floor')
    description = fields.Char(string='Description')
    availability = fields.Boolean(string='Available', default=True)
   