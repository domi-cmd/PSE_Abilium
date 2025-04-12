from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

# Import paho.mqtt conditionally to avoid startup errors
try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False
    _logger.warning("paho-mqtt library not installed. MQTT functionality will be disabled.")

class RoomRaspConnection(models.Model):
    _name = 'rasproom.connection'
    _description = 'Raspberry & Room Connection'
    # _inherit = ['mail.thread', 'mail.activity.mixin'] - Commented out as it may not be needed

    name = fields.Char(string='Connection Name', required=True, tracking=True)
    room_id = fields.Many2one('meeting.room', string='Room', required=True, tracking=True)
    raspName = fields.Char(string='Raspberry Name', required=True, tracking=True)
    status = fields.Boolean(string='Active', default=True, tracking=True)
    
    # MQTT Configuration Fields
    use_mqtt = fields.Boolean(string='Use MQTT', default=False, tracking=True)
    mqtt_broker = fields.Char(string='MQTT Broker', tracking=True)
    mqtt_port = fields.Integer(string='MQTT Port', default=1883, tracking=True)
    mqtt_username = fields.Char(string='MQTT Username', tracking=True)
    mqtt_password = fields.Char(string='MQTT Password', password=True)
    mqtt_topic_prefix = fields.Char(string='Topic Prefix', default='meeting/room/', tracking=True)
    mqtt_use_tls = fields.Boolean(string='Use TLS', default=False, tracking=True)
    mqtt_client_id = fields.Char(string='Client ID', tracking=True)
    mqtt_qos = fields.Selection([
        ('0', 'At most once (0)'),
        ('1', 'At least once (1)'),
        ('2', 'Exactly once (2)')
    ], string='QoS Level', default='0', tracking=True)
    mqtt_keep_alive = fields.Integer(string='Keep Alive', default=60, tracking=True)
    mqtt_last_connection = fields.Datetime(string='Last Connection', readonly=True)
    mqtt_connection_state = fields.Selection([
        ('disconnected', 'Disconnected'),
        ('connected', 'Connected'),
        ('error', 'Error')
    ], string='Connection State', default='disconnected', readonly=True, tracking=True)
    
    def test_mqtt_connection(self):
        """Test the MQTT connection with current settings"""
        self.ensure_one()
        
        if not HAS_MQTT:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("MQTT Connection Test"),
                    'message': _("The paho-mqtt library is not installed. Please install it with: pip install paho-mqtt"),
                    'type': 'warning',
                }
            }
            
        if not self.use_mqtt:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("MQTT Connection Test"),
                    'message': _("MQTT is not enabled for this connection."),
                    'type': 'warning',
                }
            }
        
        try:
            # Create a temporary client for testing
            client_id = self.mqtt_client_id or f"odoo-test-{self.id}"
            client = mqtt.Client(client_id=client_id)
            
            if self.mqtt_username:
                client.username_pw_set(self.mqtt_username, self.mqtt_password)
                
            if self.mqtt_use_tls:
                client.tls_set()
            
            # Connect with a short timeout
            client.connect(self.mqtt_broker, self.mqtt_port, keepalive=10)
            
            # Disconnect immediately
            client.disconnect()
            
            self.mqtt_last_connection = fields.Datetime.now()
            self.mqtt_connection_state = 'connected'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("MQTT Connection Test"),
                    'message': _("Successfully connected to MQTT broker."),
                    'type': 'success',
                }
            }
                
        except Exception as e:
            self.mqtt_connection_state = 'error'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("MQTT Connection Test"),
                    'message': _("Error: %s") % str(e),
                    'type': 'danger',
                }
            }

    def connect_mqtt(self):
        """Method stub for connecting to MQTT"""
        self.ensure_one()
        if not HAS_MQTT:
            _logger.warning("Cannot connect to MQTT: paho-mqtt library not installed")
            return False
            
        # For now, just update the state
        # You can implement the actual connection logic later
        self.mqtt_connection_state = 'connected'
        self.mqtt_last_connection = fields.Datetime.now()
        return True

    def disconnect_mqtt(self):
        """Method stub for disconnecting from MQTT"""
        self.ensure_one()
        # For now, just update the state
        # You can implement the actual disconnection logic later
        self.mqtt_connection_state = 'disconnected'
        return True

    def publish_mqtt_message(self, subtopic, payload, retain=False):
        """Method stub for publishing MQTT messages"""
        self.ensure_one()
        if not HAS_MQTT:
            _logger.warning("Cannot publish MQTT message: paho-mqtt library not installed")
            return False
            
        if not self.use_mqtt or self.mqtt_connection_state != 'connected':
            return False
            
        # Log the intent to publish
        _logger.info(
            "Would publish to topic '%s%s': %s", 
            self.mqtt_topic_prefix, subtopic, payload
        )
        return True