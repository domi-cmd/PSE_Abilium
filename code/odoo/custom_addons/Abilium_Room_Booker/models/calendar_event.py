from odoo import models, fields, api

class CalendarEvent(models.Model):
    _inherit = 'calendar.event'

    meeting_room = fields.Many2one("res.partner", compute="_compute_room", store=True)

    @api.depends("partner_ids")
    def _compute_room(self):
        for record in self:
            record.meeting_room = record.partner_ids.filtered(lambda p:p.is_room)

