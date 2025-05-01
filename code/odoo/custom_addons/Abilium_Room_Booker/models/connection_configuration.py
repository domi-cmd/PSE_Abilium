# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import logging
import threading
import time
import ssl
from contextlib import contextmanager
import json

_logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False
    _logger.warning("paho-mqtt library not installed. MQTT functionality disabled")
    

class RoomRaspConnection(models.Model):
    _name = 'rasproom.connection'
    _description = 'Raspberry & Room Connection'
    _inherit = ['mail.thread', 'mail.activity.mixin'] #Commented out as not needed as of now

    name = fields.Char(string='Connection Name', required=True, tracking=True)
    room_name = fields.Char(string='Room', required=True, tracking=True)
    capacity = fields.Integer(string='Capacity', required=True)
    street = fields.Char(string='Street')
    city = fields.Char(string='City')
    floor = fields.Char(string='Floor')
    description = fields.Char(string='Description')
    raspName = fields.Char(string='Raspberry Name', required=True, tracking=True)
    status = fields.Boolean(string='Active', default=True, tracking=True)
    resource_id = fields.Many2one('resource.resource', string="Resource", ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string="Related Contact")
    room_calendar_id = fields.Many2one(
        related='partner_id.resource_calendar_id',
        string="Room Calendar",
        readonly=True
    )

    @api.model
    def create(self, vals):
        vals = dict(vals)  # make sure we can modify vals
        if not vals.get('resource_id'):
            # Create a linked resource if not given
            resource = self.env['resource.resource'].create({
                'name': vals.get('name'),
                'resource_type': 'material',
                'calendar_id': self.env.ref('resource.resource_calendar_std').id,  # <-- This line sets availability
            })
            vals['resource_id'] = resource.id
        room = super().create(vals)

        if not vals.get('partner_id'):
            partner = self.env['res.partner'].create({
                'name': room.name,
                'resource_calendar_id': resource.calendar_id.id,
                'is_room': True,
            })
            room.partner_id = partner
        return room
    
    # MQTT Configuration Fields
    # TODO: Add comments
    use_mqtt = fields.Boolean(string='Use MQTT', default=True)
    mqtt_broker = fields.Char(string='MQTT Broker', default='test.mosquitto.org')
    mqtt_port = fields.Integer(string='MQTT Port', default=8883)
    mqtt_username = fields.Char(string='MQTT Username')
    mqtt_password = fields.Char(string='MQTT Password', password=True)
    mqtt_topic_prefix = fields.Char(string='Topic Prefix', default='test/room/')
    # outdated: mqtt_topic_prefix = fields.Char(string='Topic Prefix', default='meeting/room/', tracking=True)
    mqtt_use_tls = fields.Boolean(string='Use TLS', default=True)
    mqtt_client_id = fields.Char(string='Client ID', help="Leave empty for auto-generation")
    mqtt_qos = fields.Selection([
        ('0', 'At most once (0)'),
        ('1', 'At least once (1)'),
        ('2', 'Exactly once (2)')
    ], string='QoS Level', default='0')
    mqtt_keep_alive = fields.Integer(string='Keep Alive', default=60)
    
    # MQTT Connection Status Fields
    mqtt_last_connection = fields.Datetime(string='Last Connection', readonly=True)
    mqtt_connection_state = fields.Selection([
        ('disconnected', 'Disconnected'),
        ('connecting', 'Connecting'),
        ('connected', 'Connected'),
        ('error', 'Error')
    ], string='Connection State', default='disconnected', readonly=True, tracking=True)
    mqtt_error_message = fields.Char(string='Last Error', readonly=True)
    connection_state_display = fields.Char(string='Connection State Display', compute='_compute_connection_state_display')


    # Connection Test and Status Method (placeholder)
    def test_mqtt_connection(self):
        """Test the MQTT connection with current settings"""
        # Implementation will be added later
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'MQTT Connection Test',
                'message': 'This is a placeholder. Actual connection test will be implemented later.',
                'sticky': False,
            }
        }

    # Placeholder for connection method
    def connect_mqtt(self):
        """Establish connection to the MQTT broker"""
        # Implementation will be added later
        pass

    # Placeholder for disconnect method
    def disconnect_mqtt(self):
        """Disconnect from the MQTT broker"""
        # Implementation will be added later
        pass