# -*- coding: utf-8 -*-
# Python standard library imports
import traceback                         # For detailed error stack traces
from odoo import api, fields, models, _
import logging                           # Logging setup
import threading                         # For creating background threads
import time                              # For time-related operations and delays
import ssl                               # For secure socket layer connections
from contextlib import contextmanager    # For creating context managers
import json                              # For JSON data serialization/deserialization
# ValidationError import is needed for constraints
from odoo.exceptions import ValidationError     # type: ignore For custom validation errors
from odoo.exceptions import AccessError         # type: ignore For access control errors
from . import mqtt_connector                    # Local MQTT connection manager module

# Logger instance for this module
_logger = logging.getLogger(__name__)

# Optional MQTT library import with fallback handling
try:
    import paho.mqtt.client as mqtt # MQTT client library
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False
    _logger.warning("paho-mqtt library not installed. MQTT functionality disabled")


class RoomRaspConnection(models.Model):
    """
        Model for managing Raspberry Pi connections to meeting rooms.
        Handles MQTT connectivity, room configuration, and calendar integration.
        """
    # Odoo model configuration
    _name = 'rasproom.connection'                # Internal model name
    _description = 'Raspberry & Room Connection' # Human-readable description
    _rec_name = 'name'                           # Field to use as record nam
    _inherit = ['mail.thread', 'mail.activity.mixin'] #Commented out as not needed as of now
    # === BASIC ROOM INFORMATION FIELDS ===
    name = fields.Char(string='Room Name', required=True, tracking=True)
    profile_image = fields.Binary(string="Profile Image", attachment=True)
    capacity = fields.Integer(string='Capacity', required=True)
    street = fields.Char(string='Street')
    city = fields.Char(string='City')
    floor = fields.Char(string='Floor')
    description = fields.Char(string='Description')

    # Raspberry Pi identifier - auto-generated and read-only
    # Status and relationship fields
    raspName = fields.Char(string='Raspberry ID', required=True, tracking=True, default=lambda self: self._default_rasp_id(), readonly=True)
    active = fields.Boolean(string='Active', default=True, tracking=True)
    resource_id = fields.Many2one('resource.resource', string="Resource", ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string="Related Contact")
    room_calendar_id = fields.Many2one(
        related='partner_id.resource_calendar_id',
        string="Room Calendar",
        readonly=True
    )

    def _default_rasp_id(self):
        """Generate a default unique Raspberry ID with the format 'RASP-XXXX'"""
        # Get the highest existing number from all RASP- IDs
        highest_id = 0
        existing_ids = self.search([('raspName', 'like', 'RASP-%')])
        
        for record in existing_ids:
            try:
                # Extract the number part from RASP-XXXX
                num = int(record.raspName.split('-')[1])
                highest_id = max(highest_id, num)
            except (IndexError, ValueError):
                # Skip malformed IDs
                continue

        # Generate new ID with incremented number (4-digit padding)
        new_id = highest_id + 1
        return f"RASP-{new_id:04d}"

    # === DATA VALIDATION CONSTRAINTS ===
    # All following constraints enforce uniqueness and data integrity
    @api.constrains('name')
    def _check_unique_name(self):
        """Ensure that the connection name is unique."""
        for record in self:
            existing = self.search([
                ('name', '=', record.name),
                ('id', '!=', record.id) # Exclude current record from search
            ])
            if existing:
                raise ValidationError(f"The room name '{record.name}' is already in use.")

    #Constraint to ensure that the raspberry name is unique
    @api.constrains('raspName')
    def _check_unique_raspberry_name(self):
        """Ensure that the Raspberry Pi name is unique."""
        for record in self:
            existing = self.search([
                ('raspName', '=', record.raspName),
                ('id', '!=', record.id)
            ])
            if existing:
                raise ValidationError(f"The raspberry name '{record.raspName}' is already in use.")

    @api.constrains('capacity')
    def _check_capacity(self):
        """Ensure that the room capacity is greater than zero."""
        for record in self:
            if record.capacity < 1:
                raise ValidationError("The capacity of the room must be at least 1.")

    # === MQTT CONFIGURATION FIELDS ===
    # Fields for configuring MQTT broker connection
    use_mqtt = fields.Boolean(string='Use MQTT', default=True)
    mqtt_broker = fields.Char(string='MQTT Broker')             # Broker hostname/IP
    mqtt_port = fields.Integer(string='MQTT Port')              # Broker port (usually 1883 or 8883)
    mqtt_username = fields.Char(string='MQTT Username')         # Authentication username
    mqtt_password = fields.Char(string='MQTT Password')         # Authentication password
    mqtt_topic_prefix = fields.Char(string='Topic Prefix', default='test/room/') # Topic namespace
    mqtt_use_tls = fields.Boolean(string='Use TLS', default=True) # Enable SSL/TLS encryption
    mqtt_client_id = fields.Char(string='Client ID', help="Leave empty for auto-generation")
    # MQTT Quality of Service level
    mqtt_qos = fields.Selection([
        ('0', 'At most once (0)'),  # Fire and forget
        ('1', 'At least once (1)'), # Acknowledged delivery
        ('2', 'Exactly once (2)')   # Assured delivery
    ], string='QoS Level', default='0')
    mqtt_keep_alive = fields.Integer(string='Keep Alive', default=60)

    # === MQTT CONNECTION STATUS FIELDS ===
    # Read-only fields that track connection state
    mqtt_last_connection = fields.Datetime(string='Last Connection', readonly=True)
    mqtt_connection_state = fields.Selection([
        ('disconnected', 'Disconnected'),
        ('connecting', 'Connecting'),
        ('connected', 'Connected'),
        ('error', 'Error')
    ], string='Connection State', default='disconnected', readonly=True, tracking=True)
    mqtt_error_message = fields.Char(string='Last Error', readonly=True)
    connection_state_display = fields.Char(string='Connection State Display', compute='_compute_connection_state_display')


    @property
    def mqtt_manager(self):
        """Access the MQTT connection manager singleton."""
        return mqtt_connector.MqttConnectionManager()

    @contextmanager
    def _get_new_cursor(self):
        """Context manager for acquiring a new database cursor (thread-safe).
    
        Used internally by:
            - _update_connection_status()
            - _on_connect()
            - _on_disconnect()
            - _on_message()
            - _mqtt_loop_start()
            - _reconnect_mqtt()
            - _start_data_publisher()
        """
        new_cr = self.pool.cursor()
        try:
            yield new_cr
        finally:
            new_cr.close()

    @api.depends('mqtt_connection_state')
    def _compute_connection_state_display(self):
        """Computes the UI display class based on the MQTT connection state.
    
        Automatically triggered when 'mqtt_connection_state' changes.
        Used in UI views (via computed field).
        """
        # Map connection states to Bootstrap CSS classes
        state_mapping = {
            'connected': 'text-success',
            'connecting': 'text-warning',
            'error': 'text-danger',
            'disconnected': 'text-muted'
        }
        for record in self:
            record.connection_state_display = state_mapping.get(record.mqtt_connection_state, 'text-muted')

    def _update_connection_status(self, connection_id, state, error_msg=False):
        """Thread-safe update of MQTT connection status in the database.
        This method uses a separate database cursor to safely update status
        from background threads without interfering with the main thread.
        Called by:
            - _on_connect()
            - _on_disconnect()
            - _mqtt_loop_start()
            - _reconnect_mqtt()
        """
        try:
            with self._get_new_cursor() as cr:
                # Create new environment with separate cursor
                env = api.Environment(cr, self.env.uid, {})
                connection = env['rasproom.connection'].browse(connection_id)

                # Verify record still exists
                if not connection.exists():
                    return
                # Prepare update values
                vals = {'mqtt_connection_state': state}
                if state == 'connected':
                    vals['mqtt_last_connection'] = fields.Datetime.now()
                if error_msg:
                    vals['mqtt_error_message'] = error_msg
                # Update record and commit immediately
                connection.write(vals)
                cr.commit()
        except Exception as e:
            _logger.error("Failed to update connection status: %s", e)

    def _on_connect(self, client, userdata, flags, rc):
        """MQTT on_connect callback. Handles subscription and status update.

        This callback is triggered when the MQTT client connects to the broker.
        It updates the connection status and subscribes to relevant topics.

        Registered by:
            - _mqtt_loop_start()

        Calls:
            - _update_connection_status()
            - _get_new_cursor()
        """
        connection_id = userdata.get('connection_id')
        
        if not connection_id:
            return
            
        try:
            if rc == 0:
                # Connection successful
                self._update_connection_status(connection_id, 'connected')
                
                # Subscribe to topics
                with self._get_new_cursor() as cr:
                    env = api.Environment(cr, self.env.uid, {})
                    connection = env['rasproom.connection'].browse(connection_id)
                    if connection.exists():
                        topic = f"{connection.mqtt_topic_prefix}{connection.raspName}/#"
                        client.subscribe(topic, int(connection.mqtt_qos or 0))
                        _logger.info("Subscribed to %s", topic)
            else:
                # Connection failed - map error codes to human-readable messages
                errors = {
                    1: "Incorrect protocol version",
                    2: "Invalid client identifier",
                    3: "Server unavailable",
                    4: "Bad credentials",
                    5: "Not authorized"
                }
                error_msg = errors.get(rc, f"Unknown error: {rc}")
                self._update_connection_status(connection_id, 'error', error_msg)
                
        except Exception as e:
            _logger.error("Error in on_connect callback: %s", e)

    def _on_disconnect(self, client, userdata, rc):
        """MQTT on_disconnect callback. Manages reconnection and error handling.

        This callback is triggered when the MQTT client disconnects from the broker.
        It handles both planned and unexpected disconnections.

        Registered by:
            - _mqtt_loop_start()

        Calls:
            - _update_connection_status()
            - _reconnect_mqtt()
        """
        connection_id = userdata.get('connection_id')
        
        if not connection_id:
            return
            
        try:
            if rc == 0:
                # Normal disconnection
                self._update_connection_status(connection_id, 'disconnected')
            else:
                # Unexpected disconnection
                error_msg = f"Unexpected disconnect (code {rc})"
                self._update_connection_status(connection_id, 'error', error_msg)
                
                # Schedule reconnection attempt
                with self._get_new_cursor() as cr:
                    env = api.Environment(cr, self.env.uid, {})
                    connection = env['rasproom.connection'].browse(connection_id)
                    if connection.exists() and connection.active and connection.use_mqtt:
                        threading.Timer(5.0, lambda: self._reconnect_mqtt(connection_id)).start()
                        
        except Exception as e:
            _logger.error("Error in on_disconnect callback: %s", e)

    def _on_message(self, client, userdata, message):
        """MQTT message handler. Processes inbound messages from broker.
        Callback when MQTT message is received

        This callback is triggered when a message is received on a subscribed topic.
        Currently logs the message - extend this method to handle specific message types.
    
        Registered by:
            - _mqtt_loop_start()
        """
        connection_id = userdata.get('connection_id')
        
        if not connection_id:
            return
            
        try:
            with self._get_new_cursor() as cr:
                env = api.Environment(cr, self.env.uid, {})
                connection = env['rasproom.connection'].browse(connection_id)
                
                if not connection.exists():
                    return
                    
                topic = message.topic
                payload = message.payload.decode('utf-8')
                _logger.info("Received message: %s - %s", topic, payload)
                
                # Process message (implement your message handling logic here)
                
        except Exception as e:
            _logger.error("Error in on_message callback: %s", e)

    def _mqtt_loop_start(self, connection_id):
        """Initializes and starts the MQTT client and its event loop in a thread.

        This is the main method that sets up the MQTT client with all its
        configuration and starts the background connection loop.

        Called by:
            - connect_mqtt()
            - _reconnect_mqtt()

        Registers callbacks:
            - _on_connect
            - _on_disconnect
            - _on_message

        Calls:
            - mqtt_manager.register()
            - _start_data_publisher()
        """
        try:
            with self._get_new_cursor() as cr:
                env = api.Environment(cr, self.env.uid, {})
                connection = env['rasproom.connection'].browse(connection_id)
                
                if not connection.exists() or not connection.active or not connection.use_mqtt:
                    return
                    
                client = mqtt.Client(
                    client_id=connection.mqtt_client_id or f'odoo-{connection_id}-{int(time.time())}'[:23],
                    userdata={'connection_id': connection_id},
                    protocol=mqtt.MQTTv311
                )
                
                # Configure client
                client.on_connect = self._on_connect
                client.on_disconnect = self._on_disconnect
                client.on_message = self._on_message
                client.enable_logger(_logger)
                
                if connection.mqtt_username:
                    client.username_pw_set(connection.mqtt_username, connection.mqtt_password)
                    
                if connection.mqtt_use_tls:
                    client.tls_set(cert_reqs=ssl.CERT_NONE)
                    client.tls_insecure_set(True)
                
                # Connect asynchronously
                client.connect_async(connection.mqtt_broker, connection.mqtt_port, 
                                    keepalive=connection.mqtt_keep_alive)
                client.loop_start()
                
                # Register client
                self.mqtt_manager.register(connection_id, client)
                
                # Start periodic publisher
                self._start_data_publisher(connection_id, client)
                
                # Update status
                connection.write({'mqtt_connection_state': 'connecting'})
                cr.commit()
                
        except Exception as e:
            _logger.error("Failed to start MQTT loop: %s", e)
            self._update_connection_status(connection_id, 'error', str(e))

    def _reconnect_mqtt(self, connection_id):
        """Attempts to reconnect to the MQTT broker after a disconnection.
        This method handles automatic reconnection by cleaning up the old
        connection and starting a new one.

        Called by:
            - _on_disconnect() via Timer
        """
        try:
            with self._get_new_cursor() as cr:
                env = api.Environment(cr, self.env.uid, {})
                connection = env['rasproom.connection'].browse(connection_id)
                
                if not connection.exists() or not connection.active or not connection.use_mqtt:
                    return
                    
                _logger.info("Attempting to reconnect MQTT for %s", connection.name)
                
                # Force disconnect and clean up
                self.mqtt_manager.unregister(connection_id)
                
                # Start new connection
                self._mqtt_loop_start(connection_id)
                
        except Exception as e:
            _logger.error("Reconnection attempt failed: %s", e)

    # === PUBLIC API METHODS ===
    # These methods are called from UI buttons and other parts of the system
    def connect_mqtt(self):
        """Public method to initiate MQTT connection (connect to MQTT broker).
        This is the main entry point for establishing MQTT connectivity.
        Called by:
            - action_connect()
            - create()
            - write()
        """
        self.ensure_one()
        # Check if MQTT library is available
        if not HAS_MQTT:
            self.write({
                'mqtt_connection_state': 'error',
                'mqtt_error_message': _("MQTT functionality is not available. Please install paho-mqtt library.")
            })
            return False
        # Check if MQTT is enabled for this connection
        if not self.use_mqtt:
            return False
            
        # Disconnect any existing connection
        self.disconnect_mqtt()
        
        # Start new connection in a separate thread to avoid blocking UI
        self._mqtt_loop_start(self.id)
        
        return True

    def disconnect_mqtt(self):
        """Public method to cleanly disconnect from MQTT broker.
        This method ensures proper cleanup of MQTT connections.
        Called by:
            - connect_mqtt()
            - write()
            - unlink()
            - action_disconnect()
        """
        self.ensure_one()
        
        # Unregister from manager (handles client disconnection)
        if self.mqtt_manager.unregister(self.id):
            self.write({'mqtt_connection_state': 'disconnected'})
            
        return True

    def test_mqtt_connection(self):
        """Manually tests connection to the MQTT broker (UI button in Odoo).
        Creates a temporary MQTT client to test connectivity without
        affecting the main connection.
        Used by:
            - UI testing button
        """
        self.ensure_one()
        
        if not HAS_MQTT:
            return self._show_notification("MQTT Test", "paho-mqtt library not installed", 'warning')
            
        if not self.use_mqtt:
            return self._show_notification("MQTT Test", "MQTT is disabled for this connection", 'warning')
            
        try:
            # Create a temporary client for testing
            client_id = f'odoo-test-{self.id}-{int(time.time())}'[:23]
            client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
            
            if self.mqtt_username:
                client.username_pw_set(self.mqtt_username, self.mqtt_password)
                
            if self.mqtt_use_tls:
                client.tls_set(cert_reqs=ssl.CERT_NONE)
                client.tls_insecure_set(True)
            
            # Set up connection timeout
            connected = False
            
            def on_connect(client, userdata, flags, rc):
                nonlocal connected
                connected = (rc == 0)
            
            client.on_connect = on_connect
            
            # Try to connect
            client.connect(self.mqtt_broker, self.mqtt_port, keepalive=10)
            client.loop_start()
            
            # Wait for connection
            timeout = time.time() + 5  # 5 second timeout
            while time.time() < timeout and not connected:
                time.sleep(0.1)
            
            # Cleanup
            client.disconnect()
            client.loop_stop()
            
            if connected:
                return self._show_notification("MQTT Test", f"Successfully connected to {self.mqtt_broker}", 'success')
            else:
                return self._show_notification("MQTT Test", f"Failed to connect to {self.mqtt_broker}", 'danger')
                
        except Exception as e:
            return self._show_notification("MQTT Test", f"Error: {str(e)}", 'danger')

    def publish_test_message(self):
        """Publishes a test message to the MQTT broker for this connection.
        This method verifies the connection and publishes a simple test message
        to verify that publishing functionality is working correctly.
        Logs and verifies:
            - MQTT Python library availability
            - Whether MQTT is enabled for the current record
            - Whether the MQTT client is connected

        Constructs:
            - Topic as '<mqtt_topic_prefix><raspName>/test'
            - Payload as 'Test message from Odoo'

        Calls:
            - self.mqtt_manager.get_client()
            - client.publish()
            - self._show_notification()

        Returns:
            - Notification message indicating success, failure, or error
        """
        _logger.info(f"[MQTT] publish_test_message called for record ID {self.id}")
        """Publish test message to MQTT broker"""
        self.ensure_one()
        
        if not HAS_MQTT:
            return self._show_notification("MQTT Publish", "MQTT library not installed", 'danger')
            
        if not self.use_mqtt:
            return self._show_notification("MQTT Publish", "MQTT is disabled for this connection", 'danger')
            
        client = self.mqtt_manager.get_client(self.id)
        if not client or not client.is_connected():
            return self._show_notification("MQTT Publish", "Not connected to MQTT broker", 'danger')
        else:
            _logger.info(f"Publishing test message to topic '{topic}' with payload '{payload}'")
            
        try:
            topic = f"{self.mqtt_topic_prefix}{self.raspName}/test"
            payload = "Test message from Odoo"
            qos = int(self.mqtt_qos or 0)
            result = client.publish(topic, payload, qos=qos)
            _logger.info(f"Publishing test message to topic '{topic}' with payload '{payload}'")
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                return self._show_notification("MQTT Publish", f"Test message published to {topic}", 'success')
            else:
                return self._show_notification("MQTT Publish", f"Failed to publish test message: {result.rc}", 'danger')
                
        except Exception as e:
            return self._show_notification("MQTT Publish", f"Error: {str(e)}", 'danger')

    def _show_notification(self, title, message, notification_type='info'):
        """Helper to show a UI notification message in Odoo.
    
        Used by:
            - test_mqtt_connection()
            - publish_test_message()
            - action_connect()
            - action_disconnect()
        """
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _(title),
                'message': _(message),
                'type': notification_type,
                'sticky': notification_type == 'danger',
            }
        }

    # === ORM OVERRIDE METHODS ===
    # These methods override Odoo's default record lifecycle methods
    @api.model_create_multi
    def create(self, vals_list):
        """Overrides default create method to optionally auto-connect to MQTT.
        This method is called when new RoomRaspConnection records are created.
        It automatically creates associated resource and partner records, and
        optionally establishes MQTT connections.

        Called by:
            - ORM when a new RoomRaspConnection record is created.

        Calls:
            - connect_mqtt() if 'auto_connect' is True
        """
        # Pre-process each record to create associated resources
        for vals in vals_list:
            if not vals.get('resource_id'):
                resource = self.env['resource.resource'].create({
                    'name': vals.get('name'),
                    'resource_type': 'material',
                    'calendar_id': self.env.ref('resource.resource_calendar_std').id,
                })
                vals['resource_id'] = resource.id

        records = super().create(vals_list)

        for record in records:
            if not record.partner_id:
                #generate street in res.partner from street and floor
                street = record.street or ''
                if record.floor:
                  street += ', Floor: ' + record.floor
                # create linked res.partner with infos
                partner = self.env['res.partner'].create({
                    'name': record.name,
                    'resource_calendar_id': record.resource_id.calendar_id.id,
                    'is_room': True,
                    'image_1920': record.profile_image or False,
                    'city': record.city,
                    'street': street,
                    'room_capacity': record.capacity,
                })
                record.partner_id = partner

            if record.use_mqtt and record.active:
                record.connect_mqtt()

        return records


    def write(self, vals):
        """Overrides default write method to manage MQTT connections on updates.
        Updates records and manages MQTT connections

        Called by:
            - ORM when RoomRaspConnection records are updated.

        Calls:
            - disconnect_mqtt()
            - connect_mqtt()
        """
        # Normalize 'status' to 'active' if present
        if 'status' in vals:
            vals['active'] = vals.pop('status')
            
        result = super().write(vals)
        
        # Check if any relevant fields changed
        mqtt_fields = {
            'use_mqtt', 'mqtt_broker', 'mqtt_port', 'mqtt_username', 'mqtt_password',
            'mqtt_topic_prefix', 'mqtt_use_tls', 'mqtt_client_id', 'mqtt_keep_alive',
            'raspName', 'active'
        }
        
        if mqtt_fields.intersection(vals.keys()):
            for record in self:
                if record.use_mqtt and record.active:
                    record.disconnect_mqtt()
                    record.connect_mqtt()
                else:
                    record.disconnect_mqtt()
                    
        return result

    def unlink(self):
        """Overrides default unlink method to ensure MQTT disconnection on deletion.
        Disconnects MQTT, removes partner from calendar, cleans filters, and deletes partner

        Called by:
            - ORM when RoomRaspConnection records are deleted.

        Calls:
            - disconnect_mqtt()
        """
        CalendarEvent = self.env['calendar.event']
        CalendarFilter = self.env['calendar.filters']

        for record in self:
            record.disconnect_mqtt()

            partner = record.partner_id
            if partner:
                # Remove partner from all calendar events
                events = CalendarEvent.search([('partner_ids', 'in', partner.id)])
                for event in events:
                    event.partner_ids = [(3, partner.id)]

                # Remove from calendar filters (to avoid FK constraint failure)
                filters = CalendarFilter.search([('partner_id', '=', partner.id)])
                filters.unlink()

                # Now safe to delete partner
                partner.unlink()

        return super().unlink()

    # === SCHEDULED TASKS ===
    @api.model
    def _cron_mqtt_connection_monitor(self):
        """Cron job that checks MQTT connections and attempts reconnection if needed.
        This scheduled task runs periodically to monitor MQTT connection health
        and automatically reconnect any dropped connections.

        Called by:
            - Odoo scheduler (cron job).

        Calls:
            - mqtt_manager.get_client()
            - mqtt_manager.is_connected()
            - _reconnect_mqtt()
        """
        connections = self.search([
            ('use_mqtt', '=', True),
            ('active', '=', True)
        ])
        
        manager = mqtt_connector.MqttConnectionManager()
        
        for connection in connections:
            try:
                client = manager.get_client(connection.id)
                
                if not client or not client.is_connected():
                    _logger.info("(Re)connecting %s", connection.name)
                    connection.disconnect_mqtt()
                    connection.connect_mqtt()
                    
            except Exception as e:
                _logger.error("Monitor error for %s: %s", connection.name, e)

    def action_connect(self):
        """UI button action (in Odoo) to manually initiate MQTT connection (broker).

        Calls:
            - connect_mqtt()
            - _show_notification()
        """
        self.ensure_one()
        
        if not self.use_mqtt:
            return self._show_notification("MQTT Connection", "MQTT is disabled for this connection", 'warning')
            
        result = self.connect_mqtt()
        
        if result:
            return self._show_notification("MQTT Connection", "Connecting to MQTT broker", 'info')
        else:
            error_msg = self.mqtt_error_message or _("Failed to connect")
            return self._show_notification("MQTT Connection", error_msg, 'danger')
            
    def action_disconnect(self):
        """UI button action (in Odoo) to manually disconnect from MQTT (broker).

        Calls:
            - disconnect_mqtt()
            - _show_notification()
        """
        self.ensure_one()
        
        result = self.disconnect_mqtt()
        
        if result:
            return self._show_notification("MQTT Connection", "Disconnected from MQTT broker", 'info')
        else:
            return self._show_notification("MQTT Connection", "Failed to disconnect", 'danger')
        
    def _start_data_publisher(self, connection_id, client):
        """Start a periodic data publisher thread for sending room data to MQTT broker"""
        """Starts a background thread to publish periodic data to a topic.

        Called by:
            - _mqtt_loop_start()

        Calls:
            - _get_new_cursor()
        """
        def publish_loop():
            t = threading.current_thread()
            while getattr(t, "do_run", True):
                try:
                    with self._get_new_cursor() as cr:
                        env = api.Environment(cr, self.env.uid, {})
                        connection = env['rasproom.connection'].browse(connection_id)
                        
                        if not connection.exists() or not connection.active:
                            break
                        
                        # Diagnostic logging
                        _logger.info(f"MQTT Publisher: Processing connection ID {connection_id} - {connection.name}")
                        
                        # Get the partner associated with this room
                        partner = connection.partner_id
                        current_time = fields.Datetime.now()
                        
                        # Debug partner info
                        if partner:
                            _logger.info(f"Room partner: ID={partner.id}, Name={partner.name}, is_room={getattr(partner, 'is_room', False)}")
                        else:
                            _logger.warning(f"No partner associated with room {connection.name}")
                        
                        # Basic room data
                        room_data = {
                            'room': connection.name,
                            'raspberry': connection.raspName,
                            'timestamp': fields.Datetime.to_string(current_time),
                            'capacity': connection.capacity,
                            'is_occupied': False  # Default value
                        }
                        
                        # Fetch calendar events for this room
                        if partner and getattr(partner, 'is_room', False):
                            # Get current and next upcoming events
                            CalendarEvent = env['calendar.event']
                            
                            # Debug access rights
                            try:
                                CalendarEvent.check_access('read')
                                has_access = True
                            except AccessError:
                                has_access = False
                            _logger.info(f"Calendar event read access: {has_access}")
                            
                            # Search for events where this room is an attendee
                            domain = [
                                ('partner_ids', 'in', partner.id),
                                ('stop', '>=', fields.Datetime.now())  # Only future or current events
                            ]
                            
                            # Debug: Count total events for this partner regardless of date
                            all_events_count = CalendarEvent.search_count([('partner_ids', 'in', partner.id)])
                            _logger.info(f"Total events for partner {partner.id}: {all_events_count}")
                            
                            # Order by start date and limit to next 5 events
                            upcoming_events = CalendarEvent.search(domain, order='start', limit=5)
                            _logger.info(f"Found {len(upcoming_events)} upcoming events for room {connection.name}")
                            
                            if upcoming_events:
                                events_data = []
                                current_event = None
                                
                                for event in upcoming_events:
                                    # Format event data - use Odoo's serialization to ensure correct timezone handling
                                    event_data = {
                                        'name': event.name,
                                        'start': fields.Datetime.to_string(event.start),
                                        'stop': fields.Datetime.to_string(event.stop),
                                        'duration': event.duration,  # in hours
                                        'is_current': False
                                    }
                                    
                                    # Get organizer information
                                    if event.user_id:  # The user who created the event
                                        event_data['organizer'] = event.user_id.partner_id.name
                                    else:
                                        event_data['organizer'] = "Unknown"
                                    
                                    # Check if this is the current event
                                    if event.start <= current_time <= event.stop:
                                        event_data['is_current'] = True
                                        current_event = event_data
                                        room_data['is_occupied'] = True
                                    
                                    events_data.append(event_data)
                                
                                # Add events data to room data
                                room_data['events'] = events_data
                                
                                # Add current event to top level for easier access
                                if current_event:
                                    room_data['current_event'] = current_event

                        topic = f"{connection.mqtt_topic_prefix}{connection.raspName}/data"
                        payload = json.dumps(room_data)
                        qos = int(connection.mqtt_qos or 0)

                        result = client.publish(topic, payload, qos=qos)
                        _logger.info("Published room data to %s", topic)
                        _logger.debug("Payload: %s", payload)

                except Exception as e:
                    _logger.error("Error in data publishing thread: %s", e)
                    _logger.error(traceback.format_exc())

                # Sleep for 30 seconds before next update
                time.sleep(30)
        
        # Create the publisher thread
        publisher_thread = threading.Thread(
            target=publish_loop,
            name=f"mqtt_publisher_{connection_id}"
        )
        publisher_thread.daemon = True  # Make thread daemon so it exits when main thread exits
        publisher_thread.do_run = True  # Flag to control the loop
        
        # Start the thread
        publisher_thread.start()
        
        # Update the connection in the manager to include this publisher thread
        existing_conn = self.mqtt_manager._connections.get(connection_id, {})
        existing_client = existing_conn.get('client', client)
        existing_thread = existing_conn.get('thread')
        
        # Register with updated information
        self.mqtt_manager.register(
            connection_id,
            existing_client,
            existing_thread,
            publisher_thread
        )
        
        _logger.info(f"Started publisher thread for connection {connection_id}")
        
        return publisher_thread