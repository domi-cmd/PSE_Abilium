from odoo import models, fields

class MyCustomModel(models.Model):
    _name = 'my.custom.model'
    _description = 'My Custom Model'

    name = fields.Char(string="Name")
