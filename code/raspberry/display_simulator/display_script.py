#!/usr/bin/python
# -*- coding:utf-8 -*-
import sys
import os

import logging
from waveshare_epd import epd2in13_V4
import time
from PIL import Image, ImageDraw, ImageFont
import traceback

logging.basicConfig(level=logging.DEBUG)

try:
    logging.info("epd2in13_V4 Demo")

    # Initialize the display
    epd = epd2in13_V4.EPD()
    logging.info("Initializing the display...")
    epd.init()
    epd.Clear(0xFF)
    logging.info("Display initialized and cleared")


    # Prepare a blank image canvas
    time_image = Image.new('1', (epd.height, epd.height), 255)  # White background
    time_draw = ImageDraw.Draw(time_image)

    # Define the three pages of text
    page1 = ("Capacity: 10\nRoom Status: Occupied")
    page2 = ("Reservation Name: xyz")
    page3 = ("Reserved From: 10:00 - 14:00")

    # List of pages to cycle through
    pages = [page1, page2, page3]

    num = 0
    while True:
        epd.Clear()
        logging.info(f"Displaying Page {num + 1}")

        # Clear the screen for the new page
        time_image = Image.new('1', (epd.width, epd.height), 255)
        time_draw = ImageDraw.Draw(time_image)

        # Select the page to display
        page_text = pages[num % len(pages)]  # Cycles through the pages

        # Add a textbox (rectangle) around the text on page1
        # Define the position and size of the rectangle
        rect_x1, rect_y1 = 10, 10
        rect_x2, rect_y2 = epd.width - 10, 50  # Adjust as needed for padding

        # Draw a white rectangle around the text
        time_draw.rectangle([rect_x1, rect_y1, rect_x2, rect_y2], outline=0, width=1, fill=255)
        
        # Now draw the text inside the rectangle
        time_draw.text((rect_x1 + 5, rect_y1 + 5), page_text, fill=0)  # Added padding for text

        # Draw time info
        time_draw.rectangle((120, 80, 220, 105), fill=255)
        time_draw.text((120, 80), time.strftime('%H:%M'), fill=0)
        epd.displayPartial(epd.getbuffer(time_image))

        # Increment the page number and reset if it reaches the last page
        num += 1
        if num == 3:  # After showing the last page, reset to 0
            num = 0

        time.sleep(2)  # Display each page for 2 seconds


except IOError as e:
    logging.error(f"IOError occurred: {e}")

except KeyboardInterrupt:
    logging.info("ctrl + c detected, exiting...")
    epd.init()
    epd.Clear(0xFF)
    
    logging.info("Goto Sleep...")
    epd.sleep()
    epd2in13_V4.epdconfig.module_exit(cleanup=True)
    exit()

finally:
    # Ensure the display is cleaned up
    try:
        logging.info("Clearing the display and going to sleep...")
        epd.init()
        epd.Clear(0xFF)
        epd.sleep()
    except Exception as e:
        logging.error(f"Error during cleanup: {e}")
