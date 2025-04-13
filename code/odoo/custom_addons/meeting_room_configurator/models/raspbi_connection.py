from odoo import models, fields, api, _
import logging
import json
from datetime import datetime
import threading

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
    mqtt_last_message = fields.Datetime(string='Last Message Received', readonly=True)
    mqtt_connection_state = fields.Selection([
        ('disconnected', 'Disconnected'),
        ('connecting', 'Connecting'),
        ('connected', 'Connected'),
        ('error', 'Error')
    ], string='Connection State', default='disconnected', readonly=True, tracking=True)
    
    # Raspberry Pi status fields
    rasp_temperature = fields.Float(string='CPU Temperature', readonly=True)
    rasp_memory_usage = fields.Float(string='Memory Usage %', readonly=True)
    rasp_cpu_usage = fields.Float(string='CPU Usage %', readonly=True)
    rasp_uptime = fields.Integer(string='Uptime (seconds)', readonly=True)
    rasp_last_update = fields.Datetime(string='Last Status Update', readonly=True)
    rasp_online = fields.Boolean(string='Raspberry Online', compute='_compute_rasp_online', store=True)
    
    # MQTT client instance (not stored in database)
    _mqtt_client = None
    _mqtt_thread = None
    
    # Lock for thread safety
    _mqtt_lock = threading.Lock()
    
    @api.depends('mqtt_last_message', 'rasp_last_update')
    def _compute_rasp_online(self):
        """Determine if Raspberry Pi is online based on recent updates"""
        for record in self:
            if not record.rasp_last_update:
                record.rasp_online = False
                continue
                
            # Consider Raspberry Pi offline if no update in last 2 minutes
            time_diff = fields.Datetime.now() - record.rasp_last_update
            record.rasp_online = time_diff.total_seconds() < 120
    
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

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """Callback when the client connects to the MQTT broker"""
        connection_id = userdata.get('connection_id')
        if not connection_id:
            _logger.error("MQTT connection callback without connection ID")
            return
            
        with api.Environment.manage():
            new_cr = self.env.registry.cursor()
            try:
                # Get a fresh environment with the new cursor
                env = api.Environment(new_cr, self.env.uid, self.env.context)
                connection = env['rasproom.connection'].browse(connection_id)
                
                if rc == 0:
                    connection.write({
                        'mqtt_connection_state': 'connected',
                        'mqtt_last_connection': fields.Datetime.now()
                    })
                    
                    # Subscribe to topics
                    main_topic = f"{connection.mqtt_topic_prefix}{connection.raspName}/#"
                    client.subscribe(main_topic, int(connection.mqtt_qos or 0))
                    
                    _logger.info(f"MQTT connected successfully. Subscribed to {main_topic}")
                    
                    # Let the Raspberry know we're connected by sending a ping
                    connection._send_ping_to_raspberry(client)
                    
                else:
                    error_messages = {
                        1: "Connection refused - incorrect protocol version",
                        2: "Connection refused - invalid client identifier",
                        3: "Connection refused - server unavailable",
                        4: "Connection refused - bad username or password",
                        5: "Connection refused - not authorized"
                    }
                    error_msg = error_messages.get(rc, f"Unknown error code: {rc}")
                    _logger.error(f"MQTT connection failed: {error_msg}")
                    
                    connection.write({
                        'mqtt_connection_state': 'error',
                    })
                
                new_cr.commit()
            except Exception as e:
                _logger.error(f"Error in MQTT connect callback: {str(e)}")
                new_cr.rollback()
            finally:
                new_cr.close()
    
    def _on_mqtt_disconnect(self, client, userdata, rc):
        """Callback when the client disconnects from the MQTT broker"""
        connection_id = userdata.get('connection_id')
        if not connection_id:
            _logger.error("MQTT disconnect callback without connection ID")
            return
            
        with api.Environment.manage():
            new_cr = self.env.registry.cursor()
            try:
                # Get a fresh environment with the new cursor
                env = api.Environment(new_cr, self.env.uid, self.env.context)
                connection = env['rasproom.connection'].browse(connection_id)
                
                if rc == 0:
                    # Normal disconnection
                    connection.write({
                        'mqtt_connection_state': 'disconnected',
                    })
                    _logger.info(f"MQTT disconnected normally for {connection.name}")
                else:
                    # Unexpected disconnection
                    connection.write({
                        'mqtt_connection_state': 'error',
                    })
                    _logger.warning(f"MQTT disconnected unexpectedly with code {rc} for {connection.name}")
                
                new_cr.commit()
            except Exception as e:
                _logger.error(f"Error in MQTT disconnect callback: {str(e)}")
                new_cr.rollback()
            finally:
                new_cr.close()
    
    def _on_mqtt_message(self, client, userdata, msg):
        """Callback when a message is received from the MQTT broker"""
        connection_id = userdata.get('connection_id')
        if not connection_id:
            _logger.error("MQTT message callback without connection ID")
            return
            
        try:
            payload = msg.payload.decode('utf-8')
            _logger.debug(f"MQTT message received on topic {msg.topic}: {payload}")
            
            with api.Environment.manage():
                new_cr = self.env.registry.cursor()
                try:
                    # Get a fresh environment with the new cursor
                    env = api.Environment(new_cr, self.env.uid, self.env.context)
                    connection = env['rasproom.connection'].browse(connection_id)
                    
                    # Update last message time
                    connection.write({
                        'mqtt_last_message': fields.Datetime.now()
                    })
                    
                    # Process message based on topic
                    topic_parts = msg.topic.split('/')
                    if len(topic_parts) < 3:
                        _logger.warning(f"Received message on unexpected topic format: {msg.topic}")
                        return
                    
                    # Extract the actual topic after the prefix and device name
                    topic_prefix = connection.mqtt_topic_prefix.rstrip('/')
                    prefix_parts = topic_prefix.split('/')
                    
                    # Skip the prefix and device name parts to get the actual command/topic
                    message_type = topic_parts[len(prefix_parts) + 1]
                    
                    # Process different message types
                    if message_type == 'status':
                        connection._process_status_message(payload)
                    elif message_type == 'pong':
                        _logger.debug(f"Received pong from {connection.raspName}")
                    elif message_type == 'log':
                        _logger.info(f"Raspberry Pi log - {connection.raspName}: {payload}")
                    elif message_type == 'sensor':
                        connection._process_sensor_data(payload, topic_parts)
                    else:
                        _logger.info(f"Unhandled message type {message_type} on topic {msg.topic}")
                    
                    new_cr.commit()
                except Exception as e:
                    _logger.error(f"Error processing MQTT message: {str(e)}")
                    new_cr.rollback()
                finally:
                    new_cr.close()
                    
        except Exception as e:
            _logger.error(f"Error decoding MQTT message: {str(e)}")
    
    def _process_status_message(self, payload):
        """Process a status message from the Raspberry Pi"""
        self.ensure_one()
        try:
            status_data = json.loads(payload)
            
            update_values = {
                'rasp_last_update': fields.Datetime.now()
            }
            
            # Extract status values
            if 'temperature' in status_data:
                update_values['rasp_temperature'] = float(status_data['temperature'])
            
            if 'memory_usage' in status_data:
                update_values['rasp_memory_usage'] = float(status_data['memory_usage'])
                
            if 'cpu_usage' in status_data:
                update_values['rasp_cpu_usage'] = float(status_data['cpu_usage'])
                
            if 'uptime' in status_data:
                update_values['rasp_uptime'] = int(status_data['uptime'])
            
            self.write(update_values)
            
        except json.JSONDecodeError:
            _logger.error(f"Invalid JSON in status message: {payload}")
        except Exception as e:
            _logger.error(f"Error processing status message: {str(e)}")
    
    def _process_sensor_data(self, payload, topic_parts):
        """Process sensor data from the Raspberry Pi"""
        self.ensure_one()
        # This is a placeholder method - extend based on your sensors
        # You might want to create a separate model for sensor data
        try:
            sensor_data = json.loads(payload)
            sensor_type = topic_parts[-1] if len(topic_parts) > 3 else 'unknown'
            
            _logger.info(f"Received {sensor_type} sensor data: {sensor_data}")
            
            # Here you would typically:
            # 1. Create a record in a sensor data model
            # 2. Trigger actions based on sensor readings
            # 3. Update UI elements
            
        except json.JSONDecodeError:
            _logger.error(f"Invalid JSON in sensor data: {payload}")
        except Exception as e:
            _logger.error(f"Error processing sensor data: {str(e)}")
    
    def _send_ping_to_raspberry(self, client=None):
        """Send a ping message to the Raspberry Pi"""
        self.ensure_one()
        
        if not client and not self._mqtt_client:
            _logger.warning("Cannot send ping: No MQTT client available")
            return False
            
        mqtt_client = client or self._mqtt_client
        
        topic = f"{self.mqtt_topic_prefix}{self.raspName}/ping"
        payload = json.dumps({
            'timestamp': datetime.now().isoformat(),
            'source': 'odoo'
        })
        
        try:
            mqtt_client.publish(topic, payload, int(self.mqtt_qos or 0))
            return True
        except Exception as e:
            _logger.error(f"Error sending ping: {str(e)}")
            return False
    
    def _mqtt_loop(self):
        """Run the MQTT client loop in a separate thread"""
        _logger.info("Starting MQTT client loop")
        try:
            # Run the network loop forever
            self._mqtt_client.loop_forever()
        except Exception as e:
            _logger.error(f"MQTT loop error: {str(e)}")
        finally:
            _logger.info("MQTT client loop ended")
    
    def connect_mqtt(self):
        """Connect to the MQTT broker"""
        self.ensure_one()
        
        if not HAS_MQTT:
            _logger.warning("Cannot connect to MQTT: paho-mqtt library not installed")
            return False
            
        if not self.use_mqtt:
            _logger.warning("MQTT is not enabled for this connection")
            return False
            
        if not self.mqtt_broker:
            _logger.warning("MQTT broker not configured")
            return False
            
        # Stop any existing connection
        self.disconnect_mqtt()
        
        with self._mqtt_lock:
            try:
                self.write({'mqtt_connection_state': 'connecting'})
                
                # Create a new client
                client_id = self.mqtt_client_id or f"odoo-{self.id}-{self.raspName}"
                self._mqtt_client = mqtt.Client(client_id=client_id, userdata={'connection_id': self.id})
                
                # Set callbacks
                self._mqtt_client.on_connect = self._on_mqtt_connect
                self._mqtt_client.on_disconnect = self._on_mqtt_disconnect
                self._mqtt_client.on_message = self._on_mqtt_message
                
                # Set authentication if needed
                if self.mqtt_username:
                    self._mqtt_client.username_pw_set(self.mqtt_username, self.mqtt_password)
                
                # Set TLS if needed
                if self.mqtt_use_tls:
                    self._mqtt_client.tls_set()
                
                # Set last will message so broker notifies other clients if we disconnect unexpectedly
                will_topic = f"{self.mqtt_topic_prefix}{self.raspName}/status"
                will_payload = json.dumps({'online': False, 'timestamp': datetime.now().isoformat()})
                self._mqtt_client.will_set(will_topic, will_payload, int(self.mqtt_qos or 0), retain=True)
                
                # Connect to broker
                self._mqtt_client.connect(self.mqtt_broker, self.mqtt_port, keepalive=self.mqtt_keep_alive)
                
                # Start the background thread
                self._mqtt_thread = threading.Thread(target=self._mqtt_loop)
                self._mqtt_thread.daemon = True
                self._mqtt_thread.start()
                
                return True
                
            except Exception as e:
                _logger.error(f"MQTT connection error: {str(e)}")
                self.write({'mqtt_connection_state': 'error'})
                self._mqtt_client = None
                return False

    def disconnect_mqtt(self):
        """Disconnect from the MQTT broker"""
        self.ensure_one()
        
        with self._mqtt_lock:
            if self._mqtt_client:
                try:
                    # Send offline status before disconnecting
                    status_topic = f"{self.mqtt_topic_prefix}{self.raspName}/status"
                    status_payload = json.dumps({'online': False, 'timestamp': datetime.now().isoformat()})
                    self._mqtt_client.publish(status_topic, status_payload, qos=int(self.mqtt_qos or 0), retain=True)
                    
                    # Disconnect cleanly
                    self._mqtt_client.disconnect()
                    
                    # Give the client time to process the disconnect
                    import time
                    time.sleep(1)
                    
                except Exception as e:
                    _logger.error(f"Error during MQTT disconnect: {str(e)}")
                
                self._mqtt_client = None
                self._mqtt_thread = None
            
            self.write({'mqtt_connection_state': 'disconnected'})
            return True
    
    def publish_mqtt_message(self, subtopic, payload, retain=False):
        """Publish a message to the MQTT broker"""
        self.ensure_one()
        
        if not HAS_MQTT:
            _logger.warning("Cannot publish MQTT message: paho-mqtt library not installed")
            return False
            
        if not self.use_mqtt:
            _logger.warning("MQTT is not enabled for this connection")
            return False
            
        if self.mqtt_connection_state != 'connected' or not self._mqtt_client:
            _logger.warning("MQTT client not connected")
            return False
        
        # Build the full topic
        full_topic = f"{self.mqtt_topic_prefix}{self.raspName}/{subtopic}"
        
        try:
            # Convert payload to string if it's not already
            if isinstance(payload, dict):
                payload = json.dumps(payload)
            elif not isinstance(payload, str):
                payload = str(payload)
            
            # Publish the message
            result = self._mqtt_client.publish(
                full_topic, 
                payload, 
                qos=int(self.mqtt_qos or 0), 
                retain=retain
            )
            
            # Check the result
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                _logger.error(f"Failed to publish message to {full_topic}: {mqtt.error_string(result.rc)}")
                return False
                
            _logger.debug(f"Published message to {full_topic}: {payload}")
            return True
            
        except Exception as e:
            _logger.error(f"Error publishing MQTT message: {str(e)}")
            return False
    
    def send_command_to_raspberry(self, command, params=None):
        """Send a command to the Raspberry Pi"""
        if params is None:
            params = {}
            
        payload = {
            'command': command,
            'params': params,
            'timestamp': datetime.now().isoformat()
        }
        
        return self.publish_mqtt_message('command', payload)
    
    def restart_raspberry_service(self):
        """Send a command to restart the service on the Raspberry Pi"""
        return self.send_command_to_raspberry('restart_service')
    
    def reboot_raspberry(self):
        """Send a command to reboot the Raspberry Pi"""
        return self.send_command_to_raspberry('reboot_system')
    
    def request_status_update(self):
        """Request a status update from the Raspberry Pi"""
        return self.send_command_to_raspberry('status_request')
    
    @api.model
    def _mqtt_cron_monitor_connections(self):
        """Cron job to monitor and maintain MQTT connections"""
        connections = self.search([
            ('use_mqtt', '=', True),
            ('status', '=', True)
        ])
        
        for connection in connections:
            # Check if connection should be active
            if connection.mqtt_connection_state == 'disconnected':
                _logger.info(f"Reconnecting MQTT for {connection.name}")
                connection.connect_mqtt()
            
            # Check if connection is stale
            elif connection.mqtt_connection_state == 'connected':
                # Send ping to keep connection alive
                connection._send_ping_to_raspberry()
                
                # Check if we haven't received a message in a while
                if connection.mqtt_last_message:
                    time_diff = fields.Datetime.now() - connection.mqtt_last_message
                    # If no message in 5 minutes, consider reconnecting
                    if time_diff.total_seconds() > 300:
                        _logger.warning(f"No messages received from {connection.name} in 5 minutes, reconnecting")
                        connection.disconnect_mqtt()
                        connection.connect_mqtt()
    
    @api.model
    def create(self, vals):
        """Override create to auto-connect if needed"""
        record = super(RoomRaspConnection, self).create(vals)
        if record.use_mqtt and record.status:
            record.connect_mqtt()
        return record
    
    def write(self, vals):
        """Override write to handle connection changes"""
        result = super(RoomRaspConnection, self).write(vals)
        
        # Handle changes that affect the MQTT connection
        mqtt_related_fields = [
            'use_mqtt', 'status', 'mqtt_broker', 'mqtt_port', 
            'mqtt_username', 'mqtt_password', 'mqtt_topic_prefix',
            'mqtt_use_tls', 'mqtt_client_id', 'mqtt_keep_alive'
        ]
        
        if any(field in vals for field in mqtt_related_fields):
            for record in self:
                if record.use_mqtt and record.status:
                    # Reconnect with new settings
                    record.disconnect_mqtt()
                    record.connect_mqtt()
                elif record._mqtt_client:
                    # Disconnect if MQTT is disabled
                    record.disconnect_mqtt()
        
        return result
    
    def unlink(self):
        """Override unlink to disconnect MQTT before deletion"""
        for record in self:
            if record._mqtt_client:
                record.disconnect_mqtt()
        return super(RoomRaspConnection, self).unlink()