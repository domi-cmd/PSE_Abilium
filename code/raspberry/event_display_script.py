#!/usr/bin/python
# -*- coding:utf-8 -*-

"""
MQTT E-Paper Display Controller
Connects to MQTT broker and displays received data on a Waveshare e-Paper display.
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
from datetime import datetime, timedelta
from functools import wraps
from contextlib import contextmanager

# Path setup
picdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'pic')
libdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'lib')
if os.path.exists(libdir):
    sys.path.append(libdir)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("mqtt_display.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Importing required libraries
try:
    from waveshare_epd import epd2in13_V4
    import paho.mqtt.client as mqtt
except ImportError as e:
    logger.error(f"Required library not found: {e}")
    sys.exit(1)

# Constants
MQTT_RECONNECT_DELAY = 5
CONNECTION_CHECK_INTERVAL = 30
DISPLAY_UPDATE_INTERVAL = 15

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
    """Context manager for e-paper display"""
    try:
        yield epd
    except Exception as e:
        logger.error(f"Display operation error: {e}")
        logger.error(traceback.format_exc())

class MQTTDisplay:
    """Controller class for the MQTT E-Paper display"""
    
    def __init__(self, broker, port, rasp_name, topic_prefix, username=None, 
                 password=None, use_tls=True, timezone=None, keepalive=30):
        # MQTT parameters
        self.broker = broker
        self.port = port
        self.rasp_name = rasp_name
        self.topic_prefix = topic_prefix
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.keepalive = keepalive
        self.ping_interval = max(keepalive // 2, 10)
        
        self.client = None
        self.connected = False
        self.timezone = self._setup_timezone(timezone)
        
        # Display parameters
        self.epd = None
        self.last_data = {}
        self.setup_screen_displayed = False
        self.last_display_update = 0
        self.display_queue = queue.Queue()
        
        # Thread control
        self.threads = {}
        self.running = False
        
        # Display update control
        self.pending_updates = {}
    
    def _setup_timezone(self, timezone):
        if timezone:
            try:
                tz = pytz.timezone(timezone)
                logger.info(f"Using timezone: {timezone}")
                return tz
            except pytz.exceptions.UnknownTimeZoneError:
                logger.warning(f"Unknown timezone: {timezone}, using UTC")
        
        # Always return a timezone, never None
        logger.info("No timezone specified, using UTC")
        return pytz.timezone('UTC')
            
    def get_current_time(self):
        return datetime.now(self.timezone)
    
    @error_handler
    def setup_display(self):
        logger.info("Initializing E-Paper Display")
        self.epd = epd2in13_V4.EPD()
        self.epd.init()
        self.epd.Clear(0xFF)
        return True
    
    @error_handler
    def connect_mqtt(self):
        # Create unique client ID
        client_id = f"raspberry-{self.rasp_name}-{int(time.time())}"[:23]
        
        # Initialize MQTT client
        self.client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311, clean_session=True)
        
        # Set callbacks
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        
        # Set authentication if provided
        if self.username:
            self.client.username_pw_set(self.username, self.password)
            
        # Set TLS if enabled
        if self.use_tls:
            import ssl
            self.client.tls_set(cert_reqs=ssl.CERT_NONE)
            self.client.tls_insecure_set(True)
        
        # Set last will message
        last_will_topic = f"{self.topic_prefix}{self.rasp_name}/status"
        self.client.will_set(last_will_topic, "offline", qos=1, retain=True)
            
        # Connect to broker
        logger.info(f"Connecting to MQTT broker at {self.broker}:{self.port}")
        self.client.connect(self.broker, self.port, keepalive=self.keepalive)
        
        # Start loop in a separate thread
        self.client.loop_start()
        return True
            
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            logger.info("Connected to MQTT broker")
            
            # Subscribe to topics
            topic = f"{self.topic_prefix}{self.rasp_name}/#"
            client.subscribe(topic, 1)
            logger.info(f"Subscribed to topic: {topic}")
            
            # Publish online status
            status_topic = f"{self.topic_prefix}{self.rasp_name}/status"
            client.publish(status_topic, "online", qos=1, retain=True)
            
            # Display setup screen if needed
            if not self.setup_screen_displayed:
                self.schedule_display_update('setup', None)
                self.setup_screen_displayed = True
        else:
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
        self.connected = False
        if rc == 0:
            logger.info("Disconnected from MQTT broker")
        else:
            logger.warning(f"Unexpected disconnect (code {rc})")
            if self.last_data:
                self.schedule_display_update('data', self.last_data)
    
    @error_handler
    def monitor_connection(self):
        while self.running:
            if self.client and not self.connected:
                logger.info("Connection monitor: attempting reconnection")
                try:
                    self.client.reconnect()
                except:
                    logger.warning("Reconnection failed, recreating client")
                    self.client.loop_stop()
                    time.sleep(1)
                    self.connect_mqtt()
            
            elif self.client and self.connected:
                try:
                    ping_topic = f"{self.topic_prefix}{self.rasp_name}/ping"
                    self.client.publish(ping_topic, str(time.time()), qos=0)
                    logger.debug("Sent ping message")
                except Exception as e:
                    logger.error(f"Failed to send ping: {e}")
            
            time.sleep(self.ping_interval)
    
    def on_message(self, client, userdata, message):
        try:
            topic = message.topic
            payload = message.payload.decode('utf-8')
            logger.info(f"Received message: {topic} - {payload}")
            
            if topic.endswith('/test'):
                pass
                
            elif topic.endswith('/data'):
                try:
                    data = json.loads(payload)
                    data['timestamp'] = self.get_current_time().isoformat()
                    self.last_data = data
                    self.schedule_display_update('data', data)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON payload: {payload}")
                    
            elif topic.endswith('/clear'):
                if payload.lower() == 'true':
                    self.last_data = {}
                    self.setup_screen_displayed = False
                    self.schedule_display_update('setup', None)
                
        except Exception as e:
            logger.error(f"Message processing error: {e}")
            logger.error(traceback.format_exc())
    
    def schedule_display_update(self, display_type, content):
        self.pending_updates[display_type] = content
        logger.info(f"Display update scheduled for type: {display_type}")
                    
    @error_handler
    def stagger_worker(self):
        while self.running:
            current_time = time.time()
            time_since_last_update = current_time - self.last_display_update
            
            if self.pending_updates and time_since_last_update >= DISPLAY_UPDATE_INTERVAL:
                logger.info(f"Processing scheduled display update after {time_since_last_update:.1f} seconds")
                
                display_type, content = next(iter(self.pending_updates.items()))
                self.display_queue.put((display_type, content))
                
                del self.pending_updates[display_type]
                self.last_display_update = current_time
            
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
        while self.running:
            if self.last_data:
                self.last_data['timestamp'] = self.get_current_time().isoformat()
                self.schedule_display_update('data', self.last_data)
                logger.info("Display refresh scheduled")
            
            for _ in range(5):  # 5 minutes
                if not self.running:
                    break
                time.sleep(60)
    
    def display_setup_screen(self):
        if not self.epd and not self.setup_display():
            return
            
        with display_context(self.epd):
            image = Image.new('1', (self.epd.height, self.epd.width), 255)
            draw = ImageDraw.Draw(image)
            width, height = self.epd.height, self.epd.width
            
            font_title = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 22)
            font_text = ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 16)
            
            # Draw header
            draw.rectangle([(0, 0), (width, 30)], outline=0, fill=0)
            title = "MQTT Display Setup"
            title_width = draw.textbbox((0, 0), title, font=font_title)[2]
            draw.text(((width - title_width) // 2, 4), title, font=font_title, fill=255)
            
            # Draw connection info
            y_pos = 40
            info_items = [
                f"Raspberry: {self.rasp_name}",
                f"Broker: {self.broker[:22] + '...' if len(self.broker) > 25 else self.broker}",
                f"Port: {self.port}",
                f"Status: {'Connected' if self.connected else 'Disconnected'}"
            ]
            
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
                split_point = next((i for i in range(len(topic)//2, 0, -1) if topic[i] == '/'), len(topic)//2)
                draw.text((10, y_pos), topic[:split_point+1], font=font_text, fill=0)
                draw.text((10, y_pos+18), topic[split_point+1:], font=font_text, fill=0)
            else:
                draw.text((10, y_pos), topic, font=font_text, fill=0)
            
            self.epd.display(self.epd.getbuffer(image))
            logger.info("Setup screen displayed on e-paper")

    def display_room_data(self, data):
        if not self.epd and not self.setup_display():
            return
            
        with display_context(self.epd):
            image = Image.new('1', (self.epd.height, self.epd.width), 255)
            draw = ImageDraw.Draw(image)
            width, height = self.epd.height, self.epd.width
            
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
            # Calculate center position based on text width
            room_name_width = draw.textbbox((0, 0), room_name, font=fonts['title'])[2]
            draw.text(((width - room_name_width) // 2, 4), room_name, font=fonts['title'], fill=255)
            
            # Draw time section
            draw.line([(0, 26), (width, 26)], fill=0, width=1)
            current_time = self.get_current_time().strftime('%H:%M:%S')
            
            capacity = data.get('capacity', 'N/A')
            capacity_text = f"Capacity: {capacity}"
            update_text = f"Last Update: {current_time}"
            
            # Calculate text widths to position them properly
            update_width = draw.textbbox((0, 0), update_text, font=fonts['text'])[2]
            capacity_width = draw.textbbox((0, 0), capacity_text, font=fonts['text'])[2]
            
            # If both texts together are too wide for the display
            if update_width + capacity_width + 15 > width:
                # Use shorter format for time to save space
                short_time = self.get_current_time().strftime('%H:%M')
                update_text = f"Update: {short_time}"
                update_width = draw.textbbox((0, 0), update_text, font=fonts['text'])[2]
            
            # Draw update time on left
            draw.text((5, 28), update_text, font=fonts['text'], fill=0)
            
            # Draw capacity on right, leaving some margin
            right_position = width - capacity_width - 5
            draw.text((right_position, 28), capacity_text, font=fonts['text'], fill=0)
                        
            # Draw status section
            content_top = 45
            is_occupied = data.get('is_occupied', False)
            current_event = data.get('current_event')
            
            draw.line([(0, content_top), (width, content_top)], fill=0, width=1)
            
            # Display room status (occupied or free)
            status_text = "OCCUPIED" if is_occupied else "FREE"
            status_font = fonts['bold']
            
            if is_occupied:
                draw.rectangle([(5, content_top+2), (width-5, content_top+20)], outline=0, fill=0)
                draw.text((10, content_top+4), status_text, font=status_font, fill=255)
            else:
                draw.text((10, content_top+4), status_text, font=status_font, fill=0)
            
            content_top += 22
            
            # Draw divider before events
            draw.line([(0, content_top), (width, content_top)], fill=0, width=1)
            content_top += 2
            
            # Handle calendar events
            events = data.get('events', [])
            
            if events:
                if current_event:
                    # Format times
                    start_time = self._format_event_time(current_event['start'])
                    end_time = self._format_event_time(current_event['stop'])
                    
                    draw.text((5, content_top), "Current Meeting:", font=fonts['heading'], fill=0)
                    content_top += 16
                    
                    # Draw event name with word wrap
                    event_name = current_event['name']
                    if len(event_name) > 28:
                        name_parts = self._wrap_text(event_name, 28)
                        for part in name_parts[:2]:  # Limit to 2 lines
                            draw.text((10, content_top), part, font=fonts['text'], fill=0)
                            content_top += 14
                    else:
                        draw.text((10, content_top), event_name, font=fonts['text'], fill=0)
                        content_top += 14
                    
                    # Draw organizer and time period
                    draw.text((10, content_top), f"By: {current_event['organizer']}", font=fonts['small'], fill=0)
                    content_top += 12
                    draw.text((10, content_top), f"Time: {start_time} - {end_time}", font=fonts['small'], fill=0)
                    content_top += 16
                    
                    # Add indicator for more events
                    if len(events) > 1:
                        draw.text((5, content_top), f"▼ {len(events)-1} more event(s)", font=fonts['small'], fill=0)
                else:
                    draw.text((5, content_top), "No current meeting", font=fonts['text'], fill=0)
                    content_top += 16
                    
                    if len(events) > 0:
                        draw.text((5, content_top), f"▼ {len(events)} upcoming event(s)", font=fonts['small'], fill=0)
            else:
                draw.text((5, content_top + 10), "No upcoming meetings", font=fonts['text'], fill=0)
            
            self.epd.display(self.epd.getbuffer(image))
            logger.info("Room data displayed on e-paper")
            
            # Schedule the events screen if there are events
            if events:
                threading.Timer(DISPLAY_UPDATE_INTERVAL / 2, 
                            lambda: self.schedule_display_update('events', data)).start()

    def display_events_screen(self, data):
        if not self.epd and not self.setup_display():
            return
            
        with display_context(self.epd):
            image = Image.new('1', (self.epd.height, self.epd.width), 255)
            draw = ImageDraw.Draw(image)
            width, height = self.epd.height, self.epd.width
            
            fonts = {
                'title': ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 18),
                'heading': ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 16),
                'text': ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 14),
                'small': ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 12),
                'bold': ImageFont.truetype(os.path.join(picdir, 'Font.ttc'), 16)
            }
            
            # Draw header
            draw.rectangle([(0, 0), (width, 24)], outline=0, fill=0)
            title = "Upcoming Meetings"
            title_width = draw.textbbox((0, 0), title, font=fonts['title'])[2]
            draw.text(((width - title_width) // 2, 3), title, font=fonts['title'], fill=255)
            
            # Get room name and events
            room_name = data.get('room', 'Unknown Room')
            all_events = data.get('events', [])
            
            # Filter out events that have already ended
            current_time = self.get_current_time()
            valid_events = []
            
            for event in all_events:
                try:
                    end_time = datetime.fromisoformat(event['stop'])
                    
                    # Compare with current time based on timezone awareness
                    if end_time.tzinfo is not None and current_time.tzinfo is not None:
                        if end_time > current_time:
                            valid_events.append(event)
                    # For naive datetimes, compare directly
                    elif end_time.tzinfo is None and current_time.tzinfo is None:
                        if end_time > current_time:
                            valid_events.append(event)
                    # Mixed timezone awareness - normalize for comparison
                    else:
                        # Mixed timezone awareness - use time comparison as fallback
                        if (end_time.hour > current_time.hour or 
                            (end_time.hour == current_time.hour and end_time.minute >= current_time.minute)):
                            valid_events.append(event)
                except (ValueError, KeyError):
                    continue
            
            # Show room name, date, and last update time
            current_date = current_time.strftime('%Y-%m-%d')
            update_time = current_time.strftime('%H:%M:%S')
            info_text = f"{room_name} | {current_date} | Last Update: {update_time}"
            
            # Making sure the text fits, otherwise abbreviate
            text_width = draw.textbbox((0, 0), info_text, font=fonts['small'])[2]
            if text_width > width - 10:  # If too long for display
                room_abbrev = room_name[:10] + "..." if len(room_name) > 13 else room_name
                info_text = f"{room_abbrev} | {current_date} | {update_time}"
            
            draw.text((5, 27), info_text, font=fonts['small'], fill=0)
            
            content_top = 42
            draw.line([(0, content_top), (width, content_top)], fill=0, width=1)
            content_top += 3
            
            if not valid_events:
                draw.text((5, content_top + 10), "No upcoming events", font=fonts['text'], fill=0)
            else:
                # Sorting events by start time
                valid_events.sort(key=lambda x: x.get('start', ''))
                
                # Display events (up to 3 events for better readability)
                max_events = min(3, len(valid_events))
                events_to_show = valid_events[:max_events]
                
                for i, event in enumerate(events_to_show):
                    start_time = self._format_event_time(event['start'])
                    end_time = self._format_event_time(event['stop'])
                    
                    is_current = event.get('is_current', False)
                    
                    # Event block
                    if is_current:
                        draw.rectangle([(3, content_top-2), (width-3, content_top+44)], outline=0, fill=0)
                        text_color = 255  # White text on black background
                        status_text = " (CURRENT)"
                    else:
                        text_color = 0  # Black text
                        status_text = ""
                    
                    # Event name with word wrap
                    event_name = event['name']
                    name_parts = self._wrap_text(event_name, 28)
                    
                    for j, part in enumerate(name_parts[:1]):  # Limit to 1 line
                        draw.text((8, content_top), part, font=fonts['bold' if is_current else 'text'], fill=0)
                        content_top += 16
                    
                    # Reservation info
                    draw.text((8, content_top), f"Reserved by: {event['organizer']}", font=fonts['small'], fill=0)
                    content_top += 14
                    
                    # Time info
                    draw.text((8, content_top), f"When: {start_time} - {end_time}", font=fonts['small'], fill=0)
                    content_top += 16
                    
                    # Add divider between events
                    if i < max_events - 1:
                        draw.line([(0, content_top), (width, content_top)], fill=0, width=1)
                        content_top += 3
                
                # If there are more events than shown
                if len(valid_events) > max_events:
                    draw.text((5, height - 15), f"+ {len(valid_events) - max_events} more events...", font=fonts['small'], fill=0)
            
            self.epd.display(self.epd.getbuffer(image))
            logger.info("Events screen displayed on e-paper")
            
            # Schedule switching back to data screen
            threading.Timer(DISPLAY_UPDATE_INTERVAL,
                        lambda: self.schedule_display_update('data', data)).start()
            
    def _format_event_time(self, iso_time_str):
        """Parse event time handling both ISO and custom formats, converting to local timezone"""
        try:
            # Try ISO format first (new format from publisher)
            dt = datetime.fromisoformat(iso_time_str)
            
            # If the datetime is timezone-aware, convert to local timezone
            if dt.tzinfo is not None:
                local_dt = dt.astimezone(self.timezone)
                return local_dt.strftime('%H:%M')
            else:
                # If naive datetime, assume it's UTC and convert
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
        if len(text) <= max_chars_per_line:
            return [text]
            
        result = []
        current_line = ""
        
        for word in text.split():
            test_line = current_line + " " + word if current_line else word
            
            if len(test_line) <= max_chars_per_line:
                current_line = test_line
            else:
                if current_line:
                    result.append(current_line)
                current_line = word
                
        if current_line:
            result.append(current_line)
            
        return result
    
    def start_thread(self, name, target):
        thread = threading.Thread(target=target, name=name)
        thread.daemon = True
        thread.start()
        self.threads[name] = thread
        return thread
    
    def start(self):
        self.running = True
        
        if not self.setup_display():
            logger.error("Failed to initialize display")
            return False
            
        if not self.connect_mqtt():
            logger.error("Failed to connect to MQTT broker")
            return False
        
        # Start worker threads
        self.start_thread('display', self.display_worker)
        self.start_thread('stagger', self.stagger_worker)
        self.start_thread('refresh', self.periodic_refresh)
        self.start_thread('connection', self.monitor_connection)
        
        # Schedule setup screen display
        self.schedule_display_update('setup', None)
        
        logger.info("MQTT Display controller started")
        logger.info(f"Display updates staggered every {DISPLAY_UPDATE_INTERVAL} seconds")
        
        return True
        
    def stop(self):
        self.running = False
        
        # Disconnect MQTT client
        if self.client:
            try:
                if self.connected:
                    status_topic = f"{self.topic_prefix}{self.rasp_name}/status"
                    self.client.publish(status_topic, "offline", qos=1, retain=True)
                    time.sleep(0.5)
                
                self.client.loop_stop()
                self.client.disconnect()
            except Exception as e:
                logger.error(f"Error during MQTT disconnect: {e}")
            
        # Wait for threads to finish
        for name, thread in self.threads.items():
            if thread.is_alive():
                thread.join(timeout=2.0)
            
        # Put display to sleep
        if self.epd:
            try:
                logger.info("Putting display to sleep")
                self.epd.sleep()
            except Exception as e:
                logger.error(f"Error putting display to sleep: {e}")
                
        logger.info("MQTT Display controller stopped")

def parse_arguments():
    parser = argparse.ArgumentParser(description='MQTT E-Paper Display Controller')
    
    parser.add_argument('--broker', type=str, default='test.mosquitto.org',
                        help='MQTT broker address')
    parser.add_argument('--port', type=int, default=8883,
                        help='MQTT broker port')
    parser.add_argument('--rasp-name', type=str, required=True,
                        help='Raspberry Pi name (must match Odoo configuration)')
    parser.add_argument('--topic-prefix', type=str, default='test/room/',
                        help='MQTT topic prefix')
    parser.add_argument('--username', type=str,
                        help='MQTT username')
    parser.add_argument('--password', type=str,
                        help='MQTT password')
    parser.add_argument('--no-tls', action='store_true',
                        help='Disable TLS for MQTT connection')
    parser.add_argument('--timezone', type=str,
                        help='Optional timezone for displaying dates (default: system time)')
    parser.add_argument('--keepalive', type=int, default=30,
                        help='MQTT keepalive interval in seconds (default: 30)')
                        
    return parser.parse_args()

def main():
    args = parse_arguments()
    
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
    
    if controller.start():
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            controller.stop()
    else:
        logger.error("Failed to start MQTT Display controller")

if __name__ == "__main__":
    main()