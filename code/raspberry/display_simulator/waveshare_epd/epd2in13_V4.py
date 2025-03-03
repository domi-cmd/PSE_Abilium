import logging
import time
from PIL import Image, ImageDraw

logging.basicConfig(level=logging.DEBUG)

# Simulated Display Size (match your Waveshare model)
DISPLAY_WIDTH = 250  # Actual display dimensions
DISPLAY_HEIGHT = 122  # Actual display dimensions

# Upscale factor for simulation (scale by 2 for the simulation)
UPSCALE_FACTOR = 3

class EPD:
    def __init__(self):
        self.width = DISPLAY_WIDTH
        self.height = DISPLAY_HEIGHT
        self.image = Image.new("1", (self.width, self.height), 255)  # White canvas for simulation
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
        # Before displaying, upscale the final image
        upscaled_image = image_buffer.resize(
            (self.width * UPSCALE_FACTOR, self.height * UPSCALE_FACTOR), 
            Image.NEAREST
        )
        upscaled_image.show()  # Display the upscaled image in simulation

    def sleep(self):
        logging.info("Simulated EPD going to sleep.")

# Mocked epdconfig module (not actually needed in simulation)
class epdconfig:
    @staticmethod
    def module_exit(cleanup=True):
        logging.info("Exiting module...")
