#!/usr/bin/python
# -*- coding:utf-8 -*-

"""
MQTT E-Paper Display Controller

This script creates a controller that:
1. Connects to an MQTT broker to receive room booking data
2. Displays the data on a Waveshare e-Paper display
3. Rotates between different screen views (room data, events, setup)
4. Handles connection monitoring and error recovery

The controller subscribes to MQTT topics and updates the display
based on received JSON data about room occupancy and calendar events.
"""

import sys
import os
import logging
import time
import json
import argparse
import traceback
import threading
import queue
from PIL import Image, ImageDraw, ImageFont
import pytz
from datetime import datetime
from functools import wraps
from contextlib import contextmanager

# ===== PATH CONFIGURATION =====
# Set up paths for resources (fonts, images) and libraries
picdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'pic')
libdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'lib')
if os.path.exists(libdir):
    sys.path.append(libdir)

# ===== LOGGING CONFIGURATION =====
# Set up logging to both file and console for debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("mqtt_display.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ===== LIBRARY IMPORTS =====
# Import required libraries with error handling
# Exit gracefully if critical libraries are missing
try:
    from waveshare_epd import epd2in13_V4 # E-paper display driver
    import paho.mqtt.client as mqtt       # MQTT client library
except ImportError as e:
    logger.error(f"Required library not found: {e}")
    sys.exit(1)

def error_handler(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"{func.__name__} error: {e}")
            logger.error(traceback.format_exc())
            return None
    return wrapper

@contextmanager
def display_context(epd):
    """
    Context manager for e-paper display operations.
    Ensures proper error handling during display operations
    without crashing the entire application.
    """
    try:
        yield epd
    except Exception as e:
        logger.error(f"Display operation error: {e}")
        logger.error(traceback.format_exc())

class MQTTDisplay:
    """
    Controller class for the MQTT E-Paper display system.

    This class manages:
    - MQTT connection and message handling
    - E-paper display updates
    - Screen rotation between different views
    - Connection monitoring and recovery
    - Data timeout handling
    """
    
    def __init__(self, broker, port, rasp_name, topic_prefix, username=None, 
                 password=None, use_tls=True, timezone=None, keepalive=30):
        """
        Initialize the MQTT Display controller.

        Args:
        broker (str): MQTT broker hostname or IP
        port (int): MQTT broker port
        rasp_name (str): Unique identifier for this Raspberry Pi
        topic_prefix (str): Prefix for MQTT topics
        username (str, optional): MQTT authentication username
        password (str, optional): MQTT authentication password
        use_tls (bool): Whether to use TLS encryption
        timezone (str, optional): Timezone for display timestamps
        keepalive (int): MQTT keepalive interval in seconds
        """
        # MQTT parameters
        self.broker = broker
        self.port = port
        self.rasp_name = rasp_name
        self.topic_prefix = topic_prefix
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.keepalive = keepalive
        self.ping_interval = max(keepalive // 2, 10) # Ping frequency for connection monitoring

        # MQTT client state
        self.client = None
        self.connected = False
        self.timezone = self._setup_timezone(timezone)

        # Screen rotation settings
        self.screen_rotation_interval = 20  # Fixed 30 seconds between screens
        self.current_screen_type = 'data'   # Track current screen ('data', 'events', 'setup')
        self.screen_rotation_timer = None   # Timer for automatic screen rotation
        self.rotation_active = False        # Flag to track if rotation is running
        
        # Display parameters
        self.epd = None                         # E-paper display object
        self.last_data = {}                     # Store the most recent room data
        self.setup_screen_displayed = False     # Track if setup screen has been shown
        self.last_display_update = 0            # Timestamp of last display update (for rate limiting)
        self.display_queue = queue.Queue()      # Queue for display update requests

        # Data timeout handling - returns to setup screen if no data received
        self.last_data_time = 0     # Track when we last received data
        self.data_timeout = 60      # 60 seconds timeout
        self.timeout_timer = None   # Timer for data timeout handling
        
        # Thread management
        self.threads = {}       # Dictionary to track running threads
        self.running = False    # Global flag to stop all threads

        # Thread-safe data access
        self.data_lock = threading.Lock() # Prevents race conditions when accessing last_data
    
    def _setup_timezone(self, timezone):
        """
        Set up timezone for timestamp display.

        Args:
            timezone (str): Timezone name (e.g., 'US/Eastern', 'Europe/London')

        Returns:
            pytz.timezone: Timezone object, defaults to UTC if invalid or None
        """
        if timezone:
            try:
                tz = pytz.timezone(timezone)
                logger.info(f"Using timezone: {timezone}")
                return tz
            except pytz.exceptions.UnknownTimeZoneError:
                logger.warning(f"Unknown timezone: {timezone}, using UTC")
        
        # Always return a timezone, never None to prevent errors
        logger.info("No timezone specified, using UTC")
        return pytz.timezone('UTC')
            
    def get_current_time(self):
        """
        Get current time in the configured timezone.

        Returns:
            datetime: Current time with timezone info
        """
        return datetime.now(self.timezone)
    
    @error_handler
    def setup_display(self):
        """
        Initialize the e-paper display hardware.

        Returns:
            bool: True if successful, None if failed
        """
        logger.info("Initializing E-Paper Display")
        self.epd = epd2in13_V4.EPD()        # Create display object
        self.epd.init()                     # Initialize hardware
        self.epd.Clear(0xFF)                # Clear display to white
        return True
    
    @error_handler
    def connect_mqtt(self):
        """
        Establish connection to MQTT broker.

        Returns:
            bool: True if successful, None if failed
        """
        # Create unique client ID
        client_id = f"raspberry-{self.rasp_name}-{int(time.time())}"[:23]
        
        # Initialize MQTT client with specific protocol version
        self.client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311, clean_session=True)
        
        # Set callbacks functions for MQTT events
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        
        # Set authentication credentials if provided
        if self.username:
            self.client.username_pw_set(self.username, self.password)

        # Configure TLS encryption if enabled
        if self.use_tls:
            import ssl
            self.client.tls_set(cert_reqs=ssl.CERT_NONE)
            self.client.tls_insecure_set(True)
        
        # Set last will message - published when client disconnects unexpectedly
        last_will_topic = f"{self.topic_prefix}{self.rasp_name}/status"
        self.client.will_set(last_will_topic, "offline", qos=1, retain=True)

        # Attempt connection to broker
        logger.info(f"Connecting to MQTT broker at {self.broker}:{self.port}")
        self.client.connect(self.broker, self.port, keepalive=self.keepalive)
        
        # Start network loop in separate thread
        self.client.loop_start()
        return True
            
    def on_connect(self, client, userdata, flags, rc):
        """
        Callback when MQTT connection is established.

        Args:
            client: MQTT client instance
            userdata: User-defined data (unused)
            flags: Connection flags
            rc (int): Connection result code (0 = success)
        """

        if rc == 0:
            # Connection successful
            self.connected = True
            logger.info("Connected to MQTT broker")
            
            # Subscribe to all topics for this device
            topic = f"{self.topic_prefix}{self.rasp_name}/#"
            client.subscribe(topic, 1) # Subscribe with QoS 1
            logger.info(f"Subscribed to topic: {topic}")
            
            # Publish online status with retain flag
            status_topic = f"{self.topic_prefix}{self.rasp_name}/status"
            client.publish(status_topic, "online", qos=1, retain=True)
            
            # Update setup screen to show "Waiting for messages..." if no data yet
            if not self.last_data:
                self.force_display_update('setup', None)
                logger.info("Connected - updated setup screen to show waiting for messages")
                self.setup_screen_displayed = True
        else:
            # Connection failed - log specific error
            self.connected = False
            errors = {
                1: "Incorrect protocol version",
                2: "Invalid client identifier",
                3: "Server unavailable",
                4: "Bad credentials",
                5: "Not authorized"
            }
            error_msg = errors.get(rc, f"Unknown error: {rc}")
            logger.error(f"Connection failed: {error_msg}")
                
    def on_disconnect(self, client, userdata, rc):
        """
        Callback when MQTT connection is lost.

        Args:
            client: MQTT client instance
            userdata: User-defined data (unused)
            rc (int): Disconnect result code (0 = clean disconnect)
        """

        self.connected = False
        if rc == 0:
            logger.info("Disconnected from MQTT broker")
        else:
            logger.warning(f"Unexpected disconnect (code {rc})")
        
        # When disconnected, show setup screen to display connection status
        # Stop any ongoing rotation since we can't receive new data
        self.stop_screen_rotation()
        self.stop_timeout_timer()  # Stop timeout timer during disconnect
        
        # Force update to setup screen to show "Waiting for WiFi..." status
        self.current_screen_type = 'setup'
        self.force_display_update('setup', None)
        logger.info("Connection lost - displaying setup screen with waiting for WiFi status")
    
    @error_handler
    def monitor_connection(self):
        """
        Monitor MQTT connection health and attempt reconnection if needed.
        This runs in a separate thread and continuously checks connection status.
        """
        consecutive_failures = 0
        max_failures = 3  # After 3 failed pings, assume connection is dead
        
        while self.running:
            if self.client and not self.connected:
                logger.info("Connection monitor: attempting reconnection")
                try:
                    self.client.reconnect()
                    consecutive_failures = 0  # Reset on successful reconnect attempt
                except:
                    consecutive_failures += 1
                    logger.warning(f"Reconnection failed (attempt {consecutive_failures}), recreating client")
                    
                    # If we've failed multiple times, ensure setup screen is shown
                    if consecutive_failures >= max_failures:
                        self.current_screen_type = 'setup'
                        self.force_display_update('setup', None)
                        consecutive_failures = 0  # Reset counter

                    # Recreate MQTT client on repeated failures
                    self.client.loop_stop()
                    time.sleep(1)
                    self.connect_mqtt()
            
            elif self.client and self.connected:
                # Connection is up - send keepalive ping
                try:
                    ping_topic = f"{self.topic_prefix}{self.rasp_name}/ping"
                    self.client.publish(ping_topic, str(time.time()), qos=0)
                    logger.debug("Sent ping message")
                    consecutive_failures = 0  # Reset on successful ping
                except Exception as e:
                    logger.error(f"Failed to send ping: {e}")
                    consecutive_failures += 1
                    
                    # If ping fails multiple times, the connection might be dead
                    if consecutive_failures >= max_failures:
                        logger.warning("Multiple ping failures - connection may be dead")
                        self.connected = False  # Force reconnection logic

            # Wait before next check
            time.sleep(self.ping_interval)

    def on_message(self, client, userdata, message):
        """
        Callback when MQTT message is received.
        Processes different message types and updates display accordingly.

        Args:
            client: MQTT client instance
            userdata: User-defined data (unused)
            message: MQTT message object with topic and payload
        """
        try:
            topic = message.topic
            payload = message.payload.decode('utf-8')
            logger.info(f"Received message: {topic} - {payload}")

            # Handle test messages (ignore them)
            if topic.endswith('/test'):
                pass

            # Handle room data messages
            elif topic.endswith('/data'):
                try:
                    data = json.loads(payload)
                    data['timestamp'] = self.get_current_time().isoformat()
                    
                    # RESET TIMEOUT TIMER WHEN DATA IS RECEIVED
                    # This prevents timeout while we're actively receiving data
                    self.reset_timeout_timer()
                    
                    # Use thread-safe data access
                    with self.data_lock:
                        # Check for significant changes that warrant immediate update
                        immediate_update_needed = False
                        
                        if not self.last_data:
                            # First data received - start rotation system
                            immediate_update_needed = True
                            logger.info("First data received - starting display system")
                            
                            # Stop any existing rotation and start fresh
                            if self.rotation_active:
                                self.stop_screen_rotation()
                            
                            # Update stored data first
                            self.last_data = data.copy()  # Use copy() for safety
                            
                            # Force immediate display of data screen
                            self.current_screen_type = 'data'
                            self.force_display_update('data', data.copy())
                            
                            # Start rotation after a short delay
                            def delayed_rotation_start():
                                time.sleep(3)  # Give time for first display
                                if self.running:
                                    self.start_screen_rotation()
                            
                            rotation_thread = threading.Thread(target=delayed_rotation_start)
                            rotation_thread.daemon = True
                            rotation_thread.start()
                            
                            return  # Exit early to avoid duplicate processing
                        else:
                            # Check for room occupancy changes
                            old_occupied = self.last_data.get('is_occupied', False)
                            new_occupied = data.get('is_occupied', False)
                            if old_occupied != new_occupied:
                                immediate_update_needed = True
                                logger.info(f"Room occupancy changed: {old_occupied} -> {new_occupied}")
                            
                            # Check for current event changes
                            old_current = self.last_data.get('current_event')
                            new_current = data.get('current_event')
                            if old_current != new_current:
                                immediate_update_needed = True
                                logger.info("Current event changed - immediate update")
                        
                        # Update stored data
                        self.last_data = data.copy()  # Use copy() for safety
                        
                        if immediate_update_needed:
                            # Force immediate update of current screen with new data
                            self.force_display_update(self.current_screen_type, data.copy())
                        else:
                            # Just update the current screen content (will be picked up by next rotation)
                            logger.info("Data updated - will be shown on next screen refresh")
                            
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON payload: {payload}")
                    
            elif topic.endswith('/clear'):
                if payload.lower() == 'true':
                    logger.info("Clear command received")
                    with self.data_lock:  # Thread-safe access
                        self.stop_screen_rotation()
                        self.stop_timeout_timer()  # Stop timeout timer when clearing
                        self.last_data = {}
                        self.setup_screen_displayed = False
                        self.current_screen_type = 'setup'
                        self.force_display_update('setup', None)
            
        except Exception as e:
            logger.error(f"Message processing error: {e}")
            logger.error(traceback.format_exc())
                        
    @error_handler
    def stagger_worker(self):
        """Simplified worker that only handles rate limiting for forced updates"""
        while self.running:
            current_time = time.time()
            time_since_last_update = current_time - self.last_display_update
            
            # Only enforce rate limiting for back-to-back updates
            if time_since_last_update < 2.0:  # Minimum 2 seconds between any updates
                time.sleep(0.5)
                continue
            
            time.sleep(1.0)

    @error_handler
    def display_worker(self):
        while self.running:
            try:
                message_type, content = self.display_queue.get(timeout=1.0)
                
                if message_type == 'setup':
                    self.display_setup_screen()
                elif message_type == 'data':
                    self.display_room_data(content)
                elif message_type == 'events':
                    self.display_events_screen(content)
                    
                self.display_queue.task_done()
                
            except queue.Empty:
                continue
    
    @error_handler
    def periodic_refresh(self):
        """Periodic refresh to update timestamps and ensure display stays current"""
        while self.running:
            if self.last_data:
                # Update timestamp in data
                self.last_data['timestamp'] = self.get_current_time().isoformat()
                logger.info("Periodic data refresh completed")
            
            # Wait 5 minutes before next refresh
            for _ in range(5):
                if not self.running:
                    break
                time.sleep(60)

    def start_screen_rotation(self):
        """Start fixed-time screen rotation independent of data updates"""
        def rotate_screen():
            if not self.running:
                return
                
            # Only rotate if we have data
            if not self.last_data:
                logger.info("No data available for rotation, staying on setup screen")
                # Schedule next check in case data arrives
                if self.running:
                    self.screen_rotation_timer = threading.Timer(self.screen_rotation_interval, rotate_screen)
                    self.screen_rotation_timer.daemon = True
                    self.screen_rotation_timer.start()
                return
            
            # Determine next screen based on available content
            if self.last_data.get('events') and len(self.last_data['events']) > 0:
                # Switch between data and events screens
                if self.current_screen_type == 'data':
                    self.current_screen_type = 'events'
                    logger.info("Rotating to events screen")
                else:
                    self.current_screen_type = 'data'
                    logger.info("Rotating to data screen")
            else:
                # No events, always show data screen
                self.current_screen_type = 'data'
                logger.info("No events available, showing data screen")
            
            # Update the display with current data
            self.display_queue.put((self.current_screen_type, self.last_data.copy()))
            
            # Schedule next rotation
            if self.running:
                self.screen_rotation_timer = threading.Timer(self.screen_rotation_interval, rotate_screen)
                self.screen_rotation_timer.daemon = True
                self.screen_rotation_timer.start()
        
        # Only start rotation if we have data
        if self.last_data:
            self.rotation_active = True
            logger.info(f"Starting screen rotation with {self.screen_rotation_interval}s intervals")
            rotate_screen()
        else:
            logger.info("No data available yet, delaying rotation start")

    def stop_screen_rotation(self):
        """Stop the screen rotation timer"""
        self.rotation_active = False
        if self.screen_rotation_timer:
            self.screen_rotation_timer.cancel()
            self.screen_rotation_timer = None
            logger.info("Screen rotation stopped")

    def force_display_update(self, display_type, content):
        """Force an immediate display update without affecting rotation schedule"""
        # Clear any pending updates of the same type to avoid queue buildup
        temp_queue = queue.Queue()
        while not self.display_queue.empty():
            try:
                item = self.display_queue.get_nowait()
                if item[0] != display_type:  # Keep items that are different type
                    temp_queue.put(item)
                self.display_queue.task_done()
            except queue.Empty:
                break
        
        # Put back the items we want to keep
        while not temp_queue.empty():
            self.display_queue.put(temp_queue.get())
        
        # Add the new update
        self.display_queue.put((display_type, content))
        self.last_display_update = time.time()
        logger.info(f"Forced display update: {display_type}")
    
    def schedule_display_update(self, display_type, content):
        """Schedule a display update (used for non-urgent updates)"""
        self.display_queue.put((display_type, content))
        logger.debug(f"Scheduled display update: {display_type}")

    def reset_timeout_timer(self):
        """Reset the timeout timer when new data is received"""
        self.last_data_time = time.time()
        
        # Cancel existing timer
        if self.timeout_timer:
            self.timeout_timer.cancel()
        
        # Start new timer
        self.timeout_timer = threading.Timer(self.data_timeout, self.handle_data_timeout)
        self.timeout_timer.daemon = True
        self.timeout_timer.start()
        logger.debug(f"Timeout timer reset - will trigger in {self.data_timeout} seconds")

    def handle_data_timeout(self):
        """Called when no data received for timeout period"""
        logger.info(f"No data received for {self.data_timeout} seconds - returning to setup screen")
        
        with self.data_lock:
            # Stop rotation and clear data
            self.stop_screen_rotation()
            self.last_data = {}
            self.setup_screen_displayed = False
            self.current_screen_type = 'setup'
            
            # Force display update to setup screen
            self.force_display_update('setup', None)
            logger.info("Timeout handled - setup screen queued for display")
            
    def stop_timeout_timer(self):
        """Stop the timeout timer"""
        if self.timeout_timer:
            self.timeout_timer.cancel()
            self.timeout_timer = None
            logger.debug("Timeout timer stopped")
    
    def display_setup_screen(self):
        """
        Display the setup/status screen showing connection information.
        This screen shows:
        - Connection status
        - Device configuration
        - Subscribed topics
        - Current time
        """
        if not self.epd and not self.setup_display():
            return
            
        with display_context(self.epd):
            # Create blank white image
            image = Image.new('1', (self.epd.height, self.epd.width), 255)
            draw = ImageDraw.Draw(image)
            width, height = self.epd.height, self.epd.width

            # Load fonts for different text sizes
            font_title = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 22)
            font_text = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 16)
            
            # Dynamic title based on connection status
            if self.connected:
                title = "Waiting for messages..."
            else:
                title = "Connecting to broker..."
            
            # Draw header
            draw.rectangle([(0, 0), (width, 30)], outline=0, fill=0)
            title_width = draw.textbbox((0, 0), title, font=font_title)[2]
            draw.text(((width - title_width) // 2, 4), title, font=font_title, fill=255)
            
            # Draw connection info with black background
            y_pos = 40
            info_items = [
                f"Raspberry: {self.rasp_name}",
                f"Broker: {self.broker[:22] + '...' if len(self.broker) > 25 else self.broker}",
                f"Port: {self.port}",
                f"Status: {'Connected' if self.connected else 'Disconnected'}"
            ]

            # Display each info item
            for item in info_items:
                draw.text((10, y_pos), item, font=font_text, fill=0)
                y_pos += 18
            
            # Topic subscription section
            y_pos += 7
            draw.line([(0, y_pos - 5), (width, y_pos - 5)], fill=0, width=1)
            draw.text((10, y_pos), "Subscribed Topics:", font=font_text, fill=0)
            y_pos += 20
            
            # Display topic with word wrap if needed
            topic = f"{self.topic_prefix}{self.rasp_name}/data"
            if len(topic) * 8 > width - 20:  # Approximate character width
                # Split topic at a convenient point (typically a slash)
                split_point = next((i for i in range(len(topic)//2, 0, -1) if topic[i] == '/'), len(topic)//2)
                draw.text((10, y_pos), topic[:split_point+1], font=font_text, fill=0)
                draw.text((10, y_pos+18), topic[split_point+1:], font=font_text, fill=0)
            else:
                draw.text((10, y_pos), topic, font=font_text, fill=0)

            # Update the physical display
            self.epd.display(self.epd.getbuffer(image))
            logger.info("Setup screen displayed on e-paper")

    def display_room_data(self, data):
        """
        Display the main room data screen showing:
        - Room name and capacity
        - Current occupancy status
        - Current meeting information
        - Upcoming events summary

        Args:
            data (dict): Room data from MQTT message
        """
        if not self.epd and not self.setup_display():
            return
            
        with display_context(self.epd):
            # Create blank white image
            image = Image.new('1', (self.epd.height, self.epd.width), 255)
            draw = ImageDraw.Draw(image)
            width, height = self.epd.height, self.epd.width

            # Define fonts for different text elements
            fonts = {
                'title': ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 18),
                'heading': ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 14),
                'text': ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 13),
                'small': ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 11),
                'bold': ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 14)
            }
            
            # Draw header with room name
            draw.rectangle([(0, 0), (width, 24)], outline=0, fill=0)
            room_name = data.get('room', 'Unknown Room')
            room_name_width = draw.textbbox((0, 0), room_name, font=fonts['title'])[2]
            draw.text(((width - room_name_width) // 2, 4), room_name, font=fonts['title'], fill=255)
            
            # Draw time and capacity information line
            draw.line([(0, 26), (width, 26)], fill=0, width=1)
            current_time = self.get_current_time().strftime('%H:%M:%S')

            # Get capacity information from data payload
            capacity = data.get('capacity', 'N/A')
            capacity_text = f"Capacity: {capacity}"
            update_text = f"Last Update: {current_time}"

            # Calculate text widths to determine if they fit on one line
            update_width = draw.textbbox((0, 0), update_text, font=fonts['text'])[2]
            capacity_width = draw.textbbox((0, 0), capacity_text, font=fonts['text'])[2]

            # If both texts don't fit, shorten the time format
            if update_width + capacity_width + 15 > width:
                short_time = self.get_current_time().strftime('%H:%M')
                update_text = f"Update: {short_time}"
                update_width = draw.textbbox((0, 0), update_text, font=fonts['text'])[2]

            # Draw update time on left, capacity on right
            draw.text((5, 28), update_text, font=fonts['text'], fill=0)
            right_position = width - capacity_width - 5
            draw.text((right_position, 28), capacity_text, font=fonts['text'], fill=0)
                        
            # Draw status section - shows if room is occupied or free
            content_top = 45
            is_occupied = data.get('is_occupied', False)
            current_event = data.get('current_event')

            # Draw separator line above status
            draw.line([(0, content_top), (width, content_top)], fill=0, width=1)

            # Display occupancy status with visual emphasis
            status_text = "OCCUPIED" if is_occupied else "FREE"
            status_font = fonts['bold']
            
            if is_occupied:
                # Draw black background rectangle for occupied status
                draw.rectangle([(5, content_top+2), (width-5, content_top+20)], outline=0, fill=0)
                draw.text((10, content_top+4), status_text, font=status_font, fill=255)
            else:
                # Just draw text for free status
                draw.text((10, content_top+4), status_text, font=status_font, fill=0)
            
            content_top += 22
            draw.line([(0, content_top), (width, content_top)], fill=0, width=1)
            content_top += 2
            
            # Handle calendar events display
            events = data.get('events', [])
            
            if events:
                if current_event:
                    # Display current meeting information
                    start_time = self._format_event_time(current_event['start'])
                    end_time = self._format_event_time(current_event['stop'])
                    
                    draw.text((5, content_top), "Current Meeting:", font=fonts['heading'], fill=0)
                    content_top += 16

                    # Handle long event names by wrapping text
                    event_name = current_event['name']
                    if len(event_name) > 28:
                        name_parts = self._wrap_text(event_name, 28)
                        for part in name_parts[:2]:
                            draw.text((10, content_top), part, font=fonts['text'], fill=0)
                            content_top += 14
                    else:
                        draw.text((10, content_top), event_name, font=fonts['text'], fill=0)
                        content_top += 14

                    # Display organizer and time information
                    draw.text((10, content_top), f"By: {current_event['organizer']}", font=fonts['small'], fill=0)
                    content_top += 12
                    draw.text((10, content_top), f"Time: {start_time} - {end_time}", font=fonts['small'], fill=0)
                    content_top += 16

                    # Show indicator if there are more events
                    if len(events) > 1:
                        draw.text((5, content_top), f"▼ {len(events)-1} more event(s)", font=fonts['small'], fill=0)
                else:
                    # No current meeting, show upcoming events count
                    draw.text((5, content_top), "No current meeting", font=fonts['text'], fill=0)
                    content_top += 16
                    
                    if len(events) > 0:
                        draw.text((5, content_top), f"▼ {len(events)} upcoming event(s)", font=fonts['small'], fill=0)
            else:
                #No events at all
                draw.text((5, content_top + 10), "No upcoming meetings", font=fonts['text'], fill=0)
            # Update the e-paper display with the rendered image
            self.epd.display(self.epd.getbuffer(image))
            logger.info("Room data displayed on e-paper")

    def display_events_screen(self, data):
        """Display detailed upcoming events in a 2x2 grid layout"""
        if not self.epd and not self.setup_display():
            return
            
        with display_context(self.epd):
            # Create new image canvas for the display
            image = Image.new('1', (self.epd.height, self.epd.width), 255)
            draw = ImageDraw.Draw(image)
            width, height = self.epd.height, self.epd.width

            # Define font sizes for different text elements
            fonts = {
                'title': ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 18),
                'heading': ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 16),
                'text': ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 14),
                'small': ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 12),
                'bold': ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 16)
            }

            # Draw header with title on black background
            draw.rectangle([(0, 0), (width, 24)], outline=0, fill=0)
            title = "Upcoming Meetings"
            title_width = draw.textbbox((0, 0), title, font=fonts['title'])[2]
            draw.text(((width - title_width) // 2, 3), title, font=fonts['title'], fill=255)
            
            room_name = data.get('room', 'Unknown Room')
            all_events = data.get('events', [])
            
            # Filter events to exclude current meeting and past events
            current_time = self.get_current_time()
            current_event = data.get('current_event')
            valid_events = []
            
            for event in all_events:
                try:
                    # Skip current meeting (compare by name and start time to be safe)
                    if current_event and (event.get('name') == current_event.get('name') and 
                                        event.get('start') == current_event.get('start')):
                        continue
                    
                    # For upcoming events, check if they start in the future
                    start_time = datetime.fromisoformat(event['start'])
                    
                    # Handle timezone-aware comparison
                    if start_time.tzinfo is not None and current_time.tzinfo is not None:
                        if start_time > current_time:
                            valid_events.append(event)
                    elif start_time.tzinfo is None and current_time.tzinfo is None:
                        if start_time > current_time:
                            valid_events.append(event)
                    else:
                        # Convert naive datetime for comparison
                        if start_time.tzinfo is None:
                            start_time = start_time.replace(tzinfo=pytz.UTC)
                        if current_time.tzinfo is None:
                            current_time = current_time.replace(tzinfo=pytz.UTC)
                        if start_time > current_time:
                            valid_events.append(event)
                            
                except (ValueError, KeyError) as e:
                    logger.warning(f"Error processing event: {e}")
                    continue

            # Display room information and current date/time
            current_date = current_time.strftime('%Y-%m-%d')
            update_time = current_time.strftime('%H:%M:%S')
            info_text = f"{room_name} | {current_date} | Last Update: {update_time}"

            # Shorten text if it doesn't fit
            text_width = draw.textbbox((0, 0), info_text, font=fonts['small'])[2]
            if text_width > width - 10:
                room_abbrev = room_name[:10] + "..." if len(room_name) > 13 else room_name
                info_text = f"{room_abbrev} | {current_date} | {update_time}"
            
            draw.text((5, 27), info_text, font=fonts['small'], fill=0)

            # Set up content area for events
            content_top = 42
            draw.line([(0, content_top), (width, content_top)], fill=0, width=1)
            content_top += 3
            
            if not valid_events:
                # No upcoming events to display
                draw.text((5, content_top + 10), "No upcoming events", font=fonts['text'], fill=0)
            else:
                # Sort events by start time and limit to 4 events
                valid_events.sort(key=lambda x: x.get('start', ''))
                # Show maximum 4 events in 2x2 layout
                max_events = min(4, len(valid_events))
                events_to_show = valid_events[:max_events]
                
                # Calculate layout dimensions for 2x2 grid
                available_height = height - content_top - 10  # Leave some bottom margin
                available_width = width - 10  # Leave side margins
                
                # Define compartment dimensions for grid layout
                compartment_width = available_width // 2
                compartment_height = available_height // 2

                # Calculate starting positions for each grid cell
                left_column_start = 5
                right_column_start = 5 + compartment_width
                top_row_start = content_top + 8
                bottom_row_start = content_top + 8 + compartment_height + 4

                # Display each event in its grid position
                for i, event in enumerate(events_to_show):
                    start_time = self._format_event_time(event['start'])
                    end_time = self._format_event_time(event['stop'])
                    
                    # Truncate event name for 2-column layout
                    event_name = event['name']
                    max_chars = 18  # Shorter for 2-column layout
                    if len(event_name) > max_chars:
                        event_name = event_name[:max_chars-3] + "..."
                    
                    time_range = f"{start_time} - {end_time}"
                    
                    # Determine grid position (2x2 grid)
                    if i == 0:  # Top-left
                        compartment_x = left_column_start
                        compartment_y = top_row_start
                    elif i == 1:  # Bottom-left
                        compartment_x = left_column_start
                        compartment_y = bottom_row_start
                    elif i == 2:  # Top-right
                        compartment_x = right_column_start
                        compartment_y = top_row_start
                    else:  # Bottom-right
                        compartment_x = right_column_start
                        compartment_y = bottom_row_start
                    
                    # Calculate text dimensions for centering
                    name_width = draw.textbbox((0, 0), event_name, font=fonts['text'])[2]
                    time_width = draw.textbbox((0, 0), time_range, font=fonts['small'])[2]
                    
                    # Center the text within the compartment
                    name_x = compartment_x + (compartment_width - name_width) // 2
                    time_x = compartment_x + (compartment_width - time_width) // 2
                    
                    # Vertical centering - account for both lines of text, moved slightly up
                    text_block_height = 14 + 12  # Height of both text lines
                    vertical_center_y = compartment_y + (compartment_height - text_block_height) // 2 - 6
                    
                    # Draw centered event text
                    draw.text((name_x, vertical_center_y), event_name, font=fonts['text'], fill=0)
                    draw.text((time_x, vertical_center_y + 14), time_range, font=fonts['small'], fill=0)
                
                # Draw grid lines to separate compartments
                # Vertical separator line
                separator_x = 5 + compartment_width
                draw.line([(separator_x, content_top), (separator_x, height - 5)], fill=0, width=1)
                
                # Horizontal separator line (only if we have events in bottom row)
                if len(events_to_show) > 2:
                    separator_y = content_top + 8 + compartment_height - 3
                    draw.line([(5, separator_y), (width - 5, separator_y)], fill=0, width=1)

            # Update the e-paper display with the events screen
            self.epd.display(self.epd.getbuffer(image))
            logger.info("Events screen displayed on e-paper")

    def _format_event_time(self, iso_time_str):
        """
        Parse event time from various formats and convert to local timezone
        Handles both ISO format and custom datetime strings
        """

        try:
            # Try ISO format first (new format from publisher)
            dt = datetime.fromisoformat(iso_time_str)
            
            # If the datetime is timezone-aware, convert to local timezone
            if dt.tzinfo is not None:
                local_dt = dt.astimezone(self.timezone)
                return local_dt.strftime('%H:%M')
            else:
                # Assume naive datetime is UTC and convert to local
                utc_dt = dt.replace(tzinfo=pytz.UTC)
                local_dt = utc_dt.astimezone(self.timezone)
                return local_dt.strftime('%H:%M')
                
        except (ValueError, TypeError):
            try:
                # Try custom datetime format (fallback for old format)
                dt = datetime.strptime(iso_time_str, '%Y-%m-%d %H:%M:%S')
                # Assume this is UTC and convert to local timezone
                utc_dt = dt.replace(tzinfo=pytz.UTC)
                local_dt = utc_dt.astimezone(self.timezone)
                return local_dt.strftime('%H:%M')
            except (ValueError, TypeError):
                # If all parsing fails, return placeholder
                return "??:??"
        
    def _wrap_text(self, text, max_chars_per_line):
        """
        Wrap text to fit within specified character limit per line
        Breaks on word boundaries when possible
        """
        if len(text) <= max_chars_per_line:
            return [text]
            
        result = []
        current_line = ""

        # Split text into words and build lines
        for word in text.split():
            test_line = current_line + " " + word if current_line else word
            
            if len(test_line) <= max_chars_per_line:
                # Word fits on current line
                current_line = test_line
            else:
                # Word doesn't fit, start new line
                if current_line:
                    result.append(current_line)
                current_line = word

        # Add the last line if it has content
        if current_line:
            result.append(current_line)
            
        return result
    
    def start_thread(self, name, target):
        """Create and start a daemon thread with the given name and target function"""
        thread = threading.Thread(target=target, name=name)
        thread.daemon = True
        thread.start()
        self.threads[name] = thread
        return thread
    
    def start(self):
        """Initialize and start the MQTT display controller"""
        self.running = True

        # Initialize the e-paper display hardware
        if not self.setup_display():
            logger.error("Failed to initialize display")
            return False

        # Connect to MQTT broker
        if not self.connect_mqtt():
            logger.error("Failed to connect to MQTT broker")
            return False
        
        # Start background worker threads
        self.start_thread('display', self.display_worker)
        self.start_thread('stagger', self.stagger_worker)
        self.start_thread('refresh', self.periodic_refresh)
        self.start_thread('connection', self.monitor_connection)
        
        # Display initial setup screen while waiting for data
        self.current_screen_type = 'setup'
        self.schedule_display_update('setup', None)
        
        # Note: Screen rotation will start automatically when first data is received
        logger.info("MQTT Display controller started")
        logger.info("Waiting for data to begin screen rotation...")
        
        return True
        
    def stop(self):
        """Gracefully shutdown the MQTT display controller"""
        self.running = False
        
        # Stop screen rotation
        self.stop_screen_rotation()
        
        # NEW: Stop timeout timer
        self.stop_timeout_timer()
        
        # Disconnect MQTT client
        if self.client:
            try:
                if self.connected:
                    # Send offline status message before disconnecting
                    status_topic = f"{self.topic_prefix}{self.rasp_name}/status"
                    self.client.publish(status_topic, "offline", qos=1, retain=True)
                    time.sleep(0.5)

                # Stop MQTT client loop and disconnect
                self.client.loop_stop()
                self.client.disconnect()
            except Exception as e:
                logger.error(f"Error during MQTT disconnect: {e}")
            
        # Wait for threads to finish
        for name, thread in self.threads.items():
            if thread.is_alive():
                thread.join(timeout=2.0)
            
        # Put e-paper display into sleep mode to save power
        if self.epd:
            try:
                logger.info("Putting display to sleep")
                self.epd.sleep()
            except Exception as e:
                logger.error(f"Error putting display to sleep: {e}")
                
        logger.info("MQTT Display controller stopped")

def parse_arguments():
    """Parse command line arguments for configuring the MQTT display controller"""
    parser = argparse.ArgumentParser(description='MQTT E-Paper Display Controller')

    # MQTT connection settings
    parser.add_argument('--broker', type=str, default='test.mosquitto.org',
                        help='MQTT broker address')
    parser.add_argument('--port', type=int, default=8883,
                        help='MQTT broker port')
    parser.add_argument('--rasp-name', type=str, required=True,
                        help='Raspberry Pi name (must match Odoo configuration)')
    parser.add_argument('--topic-prefix', type=str, default='test/room/',
                        help='MQTT topic prefix')
    # Authentication settings
    parser.add_argument('--username', type=str,
                        help='MQTT username')
    parser.add_argument('--password', type=str,
                        help='MQTT password')
    # Security and connection settings
    parser.add_argument('--no-tls', action='store_true',
                        help='Disable TLS for MQTT connection')

    parser.add_argument('--timezone', type=str,         # Display settings
                        help='Optional timezone for displaying dates (default: system time)')
    parser.add_argument('--keepalive', type=int, default=30,
                        help='MQTT keepalive interval in seconds (default: 30)')
                        
    return parser.parse_args()

def main():
    """Main entry point - parse arguments and start the display controller"""
    args = parse_arguments()
    # Create display controller instance with parsed arguments
    controller = MQTTDisplay(
        broker=args.broker,
        port=args.port,
        rasp_name=args.rasp_name,
        topic_prefix=args.topic_prefix,
        username=args.username,
        password=args.password,
        use_tls=not args.no_tls,
        timezone=args.timezone,
        keepalive=args.keepalive
    )
    # Start the controller and run until interrupted
    if controller.start():
        try:
            # Keep main thread alive
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            # Ensure clean shutdown
            controller.stop()
    else:
        logger.error("Failed to start MQTT Display controller")

if __name__ == "__main__":
    main()