from odoo import models, fields, api

class RoomRaspConnection(models.Model):
    _name = 'rasproom.connection'
    _description = 'Raspberry & Room Connection'
    # _inherit = ['mail.thread', 'mail.activity.mixin'] - Commented out as not needed as of now

    name = fields.Char(string='Connection Name', required=True, tracking=True)
    room_name = fields.Char(string='Room', required=True, tracking=True)
    capacity = fields.Integer(string='Capacity', required=True)
    street = fields.Char(string='Street')
    city = fields.Char(string='City')
    floor = fields.Char(string='Floor')
    description = fields.Char(string='Description')
    raspName = fields.Char(string='Raspberry Name', required=True, tracking=True)
    status = fields.Boolean(string='Active', default=True, tracking=True)
    
    # MQTT Configuration Fields
    use_mqtt = fields.Boolean(string='Use MQTT', default=False, tracking=True)
    mqtt_broker = fields.Char(string='MQTT Broker', help="Hostname or IP address of the MQTT broker", tracking=True)
    mqtt_port = fields.Integer(string='MQTT Port', default=1883, tracking=True)
    mqtt_username = fields.Char(string='MQTT Username', tracking=True)
    mqtt_password = fields.Char(string='MQTT Password', password=True)
    mqtt_topic_prefix = fields.Char(string='Topic Prefix', default='meeting/room/', tracking=True)
    mqtt_use_tls = fields.Boolean(string='Use TLS', default=False, tracking=True)
    mqtt_client_id = fields.Char(string='Client ID', help="Unique identifier for this connection", tracking=True)
    mqtt_qos = fields.Selection([
        ('0', 'At most once (0)'),
        ('1', 'At least once (1)'),
        ('2', 'Exactly once (2)')
    ], string='QoS Level', default='0', tracking=True)
    mqtt_keep_alive = fields.Integer(string='Keep Alive', default=60, 
                                     help="Maximum period in seconds between communications with the broker",
                                     tracking=True)
    mqtt_last_connection = fields.Datetime(string='Last Connection', readonly=True)
    mqtt_connection_state = fields.Selection([
        ('disconnected', 'Disconnected'),
        ('connecting', 'Connecting'),
        ('connected', 'Connected'),
        ('error', 'Error')
    ], string='Connection State', default='disconnected', readonly=True, tracking=True)

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