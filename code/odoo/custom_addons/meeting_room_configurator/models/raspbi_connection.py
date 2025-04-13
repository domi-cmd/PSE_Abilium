from odoo import models, fields, api, _
import logging
import json
from datetime import datetime
import threading
import time
import ssl

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
    _rec_name = 'name'
    
    name = fields.Char(string='Connection Name', required=True, tracking=True)
    room_id = fields.Many2one('meeting.room', string='Room', required=True, tracking=True)
    raspName = fields.Char(string='Raspberry Name', required=True, tracking=True)
    status = fields.Boolean(string='Active', default=True, tracking=True)
    
    # MQTT Configuration Fields
    use_mqtt = fields.Boolean(string='Use MQTT', default=False)
    mqtt_broker = fields.Char(string='MQTT Broker', default=False)
    mqtt_port = fields.Integer(string='MQTT Port', default=False)
    mqtt_username = fields.Char(string='MQTT Username')
    mqtt_password = fields.Char(string='MQTT Password', password=True)
    mqtt_topic_prefix = fields.Char(string='Topic Prefix', default='meeting/room/')
    mqtt_use_tls = fields.Boolean(string='Use TLS', default=False)
    mqtt_client_id = fields.Char(string='Client ID', help="Leave empty for auto-generation")
    mqtt_qos = fields.Selection([
        ('0', 'At most once (0)'),
        ('1', 'At least once (1)'),
        ('2', 'Exactly once (2)')
    ], string='QoS Level', default='0')
    mqtt_keep_alive = fields.Integer(string='Keep Alive', default=60)
    mqtt_last_connection = fields.Datetime(string='Last Connection', readonly=True)
    mqtt_connection_state = fields.Selection([
        ('disconnected', 'Disconnected'),
        ('connecting', 'Connecting'),
        ('connected', 'Connected'),
        ('error', 'Error')
    ], string='Connection State', default='disconnected', readonly=True)
    mqtt_error_message = fields.Char(string='Last Error', readonly=True)
    
    # MQTT client instances stored as class variables (not stored in database)
    _mqtt_clients = {}
    _mqtt_threads = {}
    _mqtt_running = {}  # Track if thread should continue running
    
    # Lock for thread safety
    _mqtt_lock = threading.RLock()
    
    @api.depends('mqtt_connection_state')
    def _compute_connection_state_display(self):
        """Compute display value for connection state"""
        for record in self:
            if record.mqtt_connection_state == 'connected':
                record.connection_state_display = 'text-success'
            elif record.mqtt_connection_state == 'connecting':
                record.connection_state_display = 'text-warning'
            elif record.mqtt_connection_state == 'error':
                record.connection_state_display = 'text-danger'
            else:
                record.connection_state_display = 'text-muted'
    
    connection_state_display = fields.Char(
        string='Connection State Display', 
        compute='_compute_connection_state_display', 
        store=False
    )
    
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
                    'sticky': False,
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
                    'sticky': False,
                }
            }
        
        try:
            # Create a temporary client for testing
            timestamp = int(time.time())
            client_id = self.mqtt_client_id or f"odoo-test-{self.id}-{timestamp}"
            
            # Make sure client_id is unique and valid (max 23 chars for standard brokers)
            if len(client_id) > 23:
                client_id = f"odoo-{timestamp}"
                
            # Create client with clean session
            client = mqtt.Client(client_id=client_id, clean_session=True, protocol=mqtt.MQTTv311)
            client.enable_logger(_logger)
            
            # Connection success/failure flags
            connected = [False]
            connection_error = [None]
            
            # Define callbacks within this scope
            def on_connect(client, userdata, flags, rc):
                if rc == 0:
                    connected[0] = True
                else:
                    error_messages = {
                        1: "Connection refused - incorrect protocol version",
                        2: "Connection refused - invalid client identifier",
                        3: "Connection refused - server unavailable",
                        4: "Connection refused - bad username or password",
                        5: "Connection refused - not authorized"
                    }
                    connection_error[0] = error_messages.get(rc, f"Unknown error code: {rc}")
            
            def on_connect_fail(client, userdata):
                connection_error[0] = "Connection failed"
            
            # Set callbacks
            client.on_connect = on_connect
            client.on_connect_fail = on_connect_fail
            
            # Set authentication if needed
            if self.mqtt_username:
                client.username_pw_set(self.mqtt_username, self.mqtt_password)
                
            # Set TLS if needed
            if self.mqtt_use_tls:
                client.tls_set(
                    cert_reqs=ssl.CERT_REQUIRED,
                    tls_version=ssl.PROTOCOL_TLS,
                    ciphers=None
                )
                client.tls_insecure_set(False)
            
            # Start loop with timeout
            client.loop_start()
            
            # Connect with specific timeout
            client.connect(self.mqtt_broker, self.mqtt_port, keepalive=10)
            
            # Wait for connection with timeout
            connection_timeout = 10  # 10 seconds timeout
            start_time = time.time()
            
            while time.time() - start_time < connection_timeout:
                if connected[0] or connection_error[0]:
                    break
                time.sleep(0.2)
            
            # Stop the network loop
            client.loop_stop()
            
            # Disconnect if connected
            if connected[0]:
                client.disconnect()
                self.write({
                    'mqtt_last_connection': fields.Datetime.now(),
                    'mqtt_connection_state': 'connected',
                    'mqtt_error_message': False
                })
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _("MQTT Connection Test"),
                        'message': _("Successfully connected to MQTT broker %s") % self.mqtt_broker,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                error_msg = connection_error[0] or "Connection timeout. Could not connect to broker."
                self.write({
                    'mqtt_connection_state': 'error',
                    'mqtt_error_message': error_msg
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _("MQTT Connection Test"),
                        'message': _(error_msg),
                        'type': 'danger',
                        'sticky': True,
                    }
                }
                
        except Exception as e:
            error_msg = str(e)
            self.write({
                'mqtt_connection_state': 'error',
                'mqtt_error_message': error_msg
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("MQTT Connection Test"),
                    'message': _("Error: %s") % error_msg,
                    'type': 'danger',
                    'sticky': True,
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
                        'mqtt_last_connection': fields.Datetime.now(),
                        'mqtt_error_message': False
                    })
                    _logger.info(f"MQTT connected successfully for {connection.name}")
                    
                    # Subscribe to topics
                    topic = f"{connection.mqtt_topic_prefix}{connection.raspName}/#"
                    client.subscribe(topic, int(connection.mqtt_qos or 0))
                    _logger.info(f"Subscribed to MQTT topic: {topic}")
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
                        'mqtt_error_message': error_msg
                    })
                
                new_cr.commit()
            except Exception as e:
                _logger.error(f"Error in MQTT connect callback: {str(e)}")
                new_cr.rollback()
            finally:
                new_cr.close()
    
    def _on_mqtt_message(self, client, userdata, message):
        """Process incoming MQTT messages"""
        connection_id = userdata.get('connection_id')
        if not connection_id:
            _logger.error("MQTT message callback without connection ID")
            return
            
        try:
            topic = message.topic
            payload = message.payload.decode('utf-8')
            _logger.debug(f"MQTT message received: {topic} = {payload}")
            
            # Process message here based on topic
            # This is where you would handle incoming commands or data
            
        except Exception as e:
            _logger.error(f"Error processing MQTT message: {str(e)}")
    
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
                        'mqtt_error_message': f"Unexpected disconnect (code {rc})"
                    })
                    _logger.warning(f"MQTT disconnected unexpectedly with code {rc} for {connection.name}")
                
                new_cr.commit()
            except Exception as e:
                _logger.error(f"Error in MQTT disconnect callback: {str(e)}")
                new_cr.rollback()
            finally:
                new_cr.close()
    
    def _mqtt_loop(self):
        """Run the MQTT client loop in a separate thread"""
        connection_id = self.id
        _logger.info(f"Starting MQTT client loop for connection {connection_id}")
        
        try:
            # Get the client for this instance
            client = self._mqtt_clients.get(connection_id)
            if not client:
                _logger.error(f"No MQTT client found for connection {connection_id}")
                return
                
            # Use loop_start() for threaded network loop
            client.loop_start()
            
            # Check if connected with timeout
            connection_timeout = 15  # 15 seconds timeout
            start_time = time.time()
            connected = False
            
            while time.time() - start_time < connection_timeout:
                if client.is_connected():
                    connected = True
                    break
                time.sleep(0.5)
            
            if not connected:
                _logger.error(f"MQTT connection timeout for connection {connection_id}")
                with api.Environment.manage():
                    new_cr = self.env.registry.cursor()
                    try:
                        env = api.Environment(new_cr, self.env.uid, self.env.context)
                        connection = env['rasproom.connection'].browse(connection_id)
                        connection.write({
                            'mqtt_connection_state': 'error',
                            'mqtt_error_message': 'Connection timeout'
                        })
                        new_cr.commit()
                    except Exception as e:
                        _logger.error(f"Error updating connection status: {str(e)}")
                        new_cr.rollback()
                    finally:
                        new_cr.close()
                
                # Stopping the loop
                client.loop_stop()
                return
            
            # Set up reconnect logic
            client.reconnect_delay_set(min_delay=1, max_delay=60)
            
            # Keep running while connection is active
            while self._mqtt_running.get(connection_id, False):
                # Just check periodically if we should keep running
                time.sleep(2)
                
                # If connection is lost, attempt reconnect
                if not client.is_connected():
                    _logger.info(f"Connection lost, waiting for auto-reconnect for {connection_id}")
            
            # Cleanup when done
            client.loop_stop()
            
        except Exception as e:
            _logger.error(f"MQTT loop error: {str(e)}")
            
            # Update connection state to error
            with api.Environment.manage():
                new_cr = self.env.registry.cursor()
                try:
                    env = api.Environment(new_cr, self.env.uid, self.env.context)
                    connection = env['rasproom.connection'].browse(connection_id)
                    connection.write({
                        'mqtt_connection_state': 'error',
                        'mqtt_error_message': str(e)
                    })
                    new_cr.commit()
                except Exception as nested_e:
                    _logger.error(f"Error updating connection status: {str(nested_e)}")
                    new_cr.rollback()
                finally:
                    new_cr.close()
        finally:
            _logger.info(f"MQTT client loop ended for connection {connection_id}")
            
            # Ensure we clean up if the thread exits unexpectedly
            with self._mqtt_lock:
                if connection_id in self._mqtt_clients:
                    try:
                        self._mqtt_clients[connection_id].loop_stop()
                    except:
                        pass
                    
                    # Clean up references
                    self._mqtt_running[connection_id] = False
    
    def connect_mqtt(self):
        """Connect to the MQTT broker"""
        self.ensure_one()
        
        if not HAS_MQTT:
            _logger.warning("Cannot connect to MQTT: paho-mqtt library not installed")
            self.write({
                'mqtt_connection_state': 'error',
                'mqtt_error_message': 'paho-mqtt library not installed'
            })
            return False
            
        if not self.use_mqtt:
            _logger.warning("MQTT is not enabled for this connection")
            return False
            
        if not self.mqtt_broker:
            _logger.warning("MQTT broker not configured")
            self.write({
                'mqtt_connection_state': 'error',
                'mqtt_error_message': 'MQTT broker not configured'
            })
            return False
            
        # Stop any existing connection
        self.disconnect_mqtt()
        
        with self._mqtt_lock:
            try:
                self.write({
                    'mqtt_connection_state': 'connecting',
                    'mqtt_error_message': False
                })
                
                # Create a new client with a unique ID to avoid conflicts
                timestamp = int(time.time())
                client_id = self.mqtt_client_id or f"odoo-{self.id}-{timestamp}"
                
                # Make sure client_id is unique and valid (max 23 chars for standard brokers)
                if len(client_id) > 23:
                    client_id = f"odoo-{timestamp}"
                
                # Create client with specific protocol version and clean session
                new_client = mqtt.Client(
                    client_id=client_id,
                    clean_session=True,
                    userdata={'connection_id': self.id},
                    protocol=mqtt.MQTTv311
                )
                
                # Enable logging
                new_client.enable_logger(_logger)
                
                # Set callbacks
                new_client.on_connect = self._on_mqtt_connect
                new_client.on_disconnect = self._on_mqtt_disconnect
                new_client.on_message = self._on_mqtt_message
                
                # Set authentication if needed
                if self.mqtt_username:
                    new_client.username_pw_set(self.mqtt_username, self.mqtt_password)
                
                # Set TLS if needed
                if self.mqtt_use_tls:
                    new_client.tls_set(
                        cert_reqs=ssl.CERT_REQUIRED,
                        tls_version=ssl.PROTOCOL_TLS,
                        ciphers=None
                    )
                    new_client.tls_insecure_set(False)
                
                # Set other options
                new_client.reconnect_delay_set(min_delay=1, max_delay=60)
                
                # Connect to broker (using async connection)
                new_client.connect_async(
                    self.mqtt_broker, 
                    self.mqtt_port, 
                    keepalive=self.mqtt_keep_alive
                )
                
                # Store the client in the class dictionary
                self._mqtt_clients[self.id] = new_client
                
                # Mark this connection as running
                self._mqtt_running[self.id] = True
                
                # Start the background thread
                thread = threading.Thread(
                    target=self._mqtt_loop,
                    name=f"MQTT-{self.id}-{timestamp}"
                )
                thread.daemon = True
                thread.start()
                
                # Store the thread in the class dictionary
                self._mqtt_threads[self.id] = thread
                
                return True
                
            except Exception as e:
                error_msg = str(e)
                _logger.error(f"MQTT connection error: {error_msg}")
                self.write({
                    'mqtt_connection_state': 'error',
                    'mqtt_error_message': error_msg
                })
                
                if self.id in self._mqtt_clients:
                    del self._mqtt_clients[self.id]
                if self.id in self._mqtt_running:
                    del self._mqtt_running[self.id]
                return False

    def disconnect_mqtt(self):
        """Disconnect from the MQTT broker"""
        self.ensure_one()
        
        with self._mqtt_lock:
            # First mark this connection as not running to stop the thread
            self._mqtt_running[self.id] = False
            
            if self.id in self._mqtt_clients:
                try:
                    # Stop the network loop
                    self._mqtt_clients[self.id].loop_stop()
                    
                    # Disconnect cleanly
                    if self._mqtt_clients[self.id].is_connected():
                        self._mqtt_clients[self.id].disconnect()
                    
                    # Give the client time to process the disconnect
                    time.sleep(0.5)
                    
                except Exception as e:
                    _logger.error(f"Error during MQTT disconnect: {str(e)}")
                
                # Clean up references
                del self._mqtt_clients[self.id]
            
            if self.id in self._mqtt_threads:
                # Wait for thread to finish with timeout
                if threading.current_thread() != self._mqtt_threads[self.id]:
                    try:
                        self._mqtt_threads[self.id].join(timeout=2.0)
                    except Exception as e:
                        _logger.error(f"Error joining MQTT thread: {str(e)}")
                        
                del self._mqtt_threads[self.id]
            
            self.write({
                'mqtt_connection_state': 'disconnected',
                'mqtt_error_message': False
            })
            return True
    
    def write(self, vals):
        """Override write to handle connection changes"""
        result = super(RoomRaspConnection, self).write(vals)
        
        # Handle changes that affect the MQTT connection
        mqtt_related_fields = [
            'use_mqtt', 'mqtt_broker', 'mqtt_port', 
            'mqtt_username', 'mqtt_password', 'mqtt_topic_prefix',
            'mqtt_use_tls', 'mqtt_client_id', 'mqtt_keep_alive',
            'raspName'  # Added raspName as it affects subscription topics
        ]
        
        if any(field in vals for field in mqtt_related_fields):
            for record in self:
                if record.use_mqtt and record.status:
                    # Reconnect with new settings
                    record.disconnect_mqtt()
                    record.connect_mqtt()
                elif record.id in self._mqtt_clients:
                    # Disconnect if MQTT is disabled or record is inactive
                    record.disconnect_mqtt()
        
        # Handle status changes
        if 'status' in vals:
            for record in self:
                if not record.status and record.id in self._mqtt_clients:
                    # Disconnect if record becomes inactive
                    record.disconnect_mqtt()
                elif record.status and record.use_mqtt and record.id not in self._mqtt_clients:
                    # Connect if record becomes active and MQTT is enabled
                    record.connect_mqtt()
        
        return result
    
    def unlink(self):
        """Override unlink to disconnect MQTT before deletion"""
        for record in self:
            if record.id in self._mqtt_clients:
                record.disconnect_mqtt()
        return super(RoomRaspConnection, self).unlink()
    
    @api.model
    def _cron_mqtt_connection_monitor(self):
        """Cron job to monitor and maintain MQTT connections"""
        connections = self.search([
            ('use_mqtt', '=', True),
            ('status', '=', True)
        ])
        
        for connection in connections:
            # Check if connection is active in memory but marked as disconnected in DB
            if connection.id in self._mqtt_clients and connection.mqtt_connection_state != 'connected':
                if self._mqtt_clients[connection.id].is_connected():
                    connection.write({
                        'mqtt_connection_state': 'connected',
                        'mqtt_last_connection': fields.Datetime.now(),
                        'mqtt_error_message': False
                    })
            
            # Check if connection should be active but isn't
            if connection.id not in self._mqtt_clients:
                _logger.info(f"Reestablishing connection for {connection.name}")
                connection.connect_mqtt()