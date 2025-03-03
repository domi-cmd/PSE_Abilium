import logging
import time
from PIL import Image, ImageDraw

logging.basicConfig(level=logging.DEBUG)

# Simulated Display Size (match your Waveshare model)
DISPLAY_WIDTH = 250  # Update with actual dimensions
DISPLAY_HEIGHT = 122

class EPD:
    def __init__(self):
        self.width = DISPLAY_WIDTH
        self.height = DISPLAY_HEIGHT
        self.image = Image.new("1", (self.width, self.height), 255)  # White canvas
        self.draw = ImageDraw.Draw(self.image)

    def init(self):
        logging.info("Simulated EPD initialized.")

    def Clear(self, color=0xFF):
        """Simulate clearing the screen."""
        self.image.paste(255 if color == 0xFF else 0, [0, 0, self.width, self.height])
        logging.info("Screen cleared.")

    def getbuffer(self, image):
        """Simulate getting the image buffer (return image itself)."""
        return image

    def displayPartial(self, image_buffer):
        """Simulate partial display update."""
        logging.info("Displaying partial update...")
        self.image = image_buffer  # Store the new image
        self.image.show()  # Display the updated image

    def sleep(self):
        logging.info("Simulated EPD going to sleep.")

# Mocked epdconfig module (not actually needed in simulation)
class epdconfig:
    @staticmethod
    def module_exit(cleanup=True):
        logging.info("Exiting module...")

