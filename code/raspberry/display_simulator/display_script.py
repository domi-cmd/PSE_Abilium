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

# Load a DejaVu font from your project folder
# Path to your .ttf font file
font_path = "code/raspberry/display_simulator/assets/DejaVuSans-Bold.ttf"  
# 14 is the font size
font = ImageFont.truetype(font_path, 14)  

try:
    logging.info("epd2in13_V4 Demo")

    # Initialize the display
    epd = epd2in13_V4.EPD()
    logging.info("Initializing the display...")
    epd.init()
    epd.Clear(0xFF)
    logging.info("Display initialized and cleared")

    # Prepare a blank image canvas for drawing text
    # 255 makes the background white
    time_image = Image.new('1', (epd.height, epd.height), 255)  
    time_draw = ImageDraw.Draw(time_image)

    # Define the three pages of text to cycle through
    page1 = ("Capacity: 10\nRoom Status: Occupied")
    page2 = ("Reservation Name: xyz")
    page3 = ("Reserved From: 10:00 - 14:00")

    # List of pages to cycle through
    pages = [page1, page2, page3]

    num = 0
    while True:
        # Clear the display before drawing new content
        epd.Clear()
        logging.info(f"Displaying Page {num + 1}")

        # Clear the screen for the new page content
        time_image = Image.new('1', (epd.width, epd.height), 255)
        time_draw = ImageDraw.Draw(time_image)

        # Select the page to display (cycling through pages)
        page_text = pages[num % len(pages)]  

        # Add a textbox (rectangle) around the text on page1
        # Define the position and size of the rectangle
        rect_x1, rect_y1 = 10, 10
        # Adjust as needed for padding
        rect_x2, rect_y2 = epd.width - 10, 50 

        # Draw a white rectangle around the text
        time_draw.rectangle([rect_x1, rect_y1, rect_x2, rect_y2], outline=0, width=1, fill=255)

        # Now draw the text inside the rectangle with padding
        # Added padding for text
        time_draw.text((rect_x1 + 5, rect_y1 + 5), page_text, font=font, fill=0)  

        # Draw the time information
        # White box for time display (Change fill value to something else than 255 for visibility of box)
        #time_draw.rectangle((180, 80, 245, 110), fill=255, outline=0, width=1)  
        # Display current time and day
        time_draw.text((190, 80), time.strftime('%H:%M'), font=font, fill=0) 
        time_draw.text((180, 100), "Tuesday", font=font, fill=0)  

        # Send the drawn image to the display
        epd.displayPartial(epd.getbuffer(time_image))

        # Increment the page number and reset if it reaches the last page
        num += 1
        # After showing the last page, we reset to (page) 0
        if num == 3:  
            num = 0

        # Display each page for 2 seconds
        time.sleep(2) 


except IOError as e:
    # Handle IOErrors, typically display-related issues
    logging.error(f"IOError occurred: {e}")

except KeyboardInterrupt:
    # Handle keyboard interrupts gracefully
    logging.info("ctrl + c detected, exiting...")
    epd.init()
    epd.Clear(0xFF)

    logging.info("Goto Sleep...")
    # Put the display to sleep
    epd.sleep()  
    # Cleanup the display (this doesn't actually work yet as we display "rigid" images)
    epd2in13_V4.epdconfig.module_exit(cleanup=True)  
    # Exit the program
    exit()  

finally:
    # Ensure the display is cleaned up on program exit
    try:
        logging.info("Clearing the display and going to sleep...")
        epd.init()
        epd.Clear(0xFF)
        # Put the display to sleep
        epd.sleep()  
    except Exception as e:
        logging.error(f"Error during cleanup: {e}")
