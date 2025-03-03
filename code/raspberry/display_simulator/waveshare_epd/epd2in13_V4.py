import logging
import time
from PIL import Image, ImageDraw

logging.basicConfig(level=logging.DEBUG)

# Simulated Display Size (match this with your Waveshare model!!!)
DISPLAY_WIDTH = 250 
DISPLAY_HEIGHT = 122  

# Upscale factor for the displayed image as to improve readability
# Change this to a factor of 1 if original (true) display size is desired
UPSCALE_FACTOR = 3

class EPD:
    """
    A class to simulate the behavior of an EPD (Electronic Paper Display) for testing and development.
    
    Attributes:
        width (int): The width of the simulated display.
        height (int): The height of the simulated display.
        image (PIL.Image): The image object representing the simulated screen.
        draw (PIL.ImageDraw): The drawing object for adding content to the image.
    """
    def __init__(self):
        """
        Initializes the simulated EPD display with a white canvas.
        
        The image size is set to the simulated display dimensions, and a drawing context is created.
        """
        self.width = DISPLAY_WIDTH
        self.height = DISPLAY_HEIGHT
        # White canvas for simulation (255)
        self.image = Image.new("1", (self.width, self.height), 255)  
        self.draw = ImageDraw.Draw(self.image)

    def init(self):
        """
        Simulates the initialization of the EPD display.
        
        Logs a message indicating that the display has been initialized.
        """
        logging.info("Simulated EPD initialized.")

    def Clear(self, color=0xFF):
        """
        Simulates clearing the screen by filling it with a specified color.
        
        Args:
            color (int): The color to fill the screen with (default is 0xFF for white).
        """
        self.image.paste(255 if color == 0xFF else 0, [0, 0, self.width, self.height])
        logging.info("Screen cleared.")

    def getbuffer(self, image):
        """
        Simulates obtaining the image buffer from the display.
        
        Args:
            image (PIL.Image): The image to be processed.
        
        Returns:
            PIL.Image: The same image that was passed in.
        """
        return image

    def displayPartial(self, image_buffer):
        """
        Simulates a partial update of the display with a given image buffer.
        
        This method resizes the image buffer (upscaling it for simulation purposes) 
        and then displays it using the upscaled version.
        
        Args:
            image_buffer (PIL.Image): The image to be displayed.
        """
        logging.info("Displaying partial update...")
        # Before displaying, upscale the final image
        upscaled_image = image_buffer.resize(
            (self.width * UPSCALE_FACTOR, self.height * UPSCALE_FACTOR), 
            Image.NEAREST
        )
        # Display the upscaled image in simulation
        upscaled_image.show()  

    def sleep(self):
        """
        Simulates putting the EPD display into sleep mode.
        
        Logs a message indicating that the display is going to sleep.
        """
        logging.info("Simulated EPD going to sleep.")

# Mocked epdconfig module (not actually needed in simulation)
class epdconfig:
    @staticmethod
    def module_exit(cleanup=True):
        """
        Simulates the exit of the module.
        
        Args:
            cleanup (bool): Whether to perform cleanup operations (default is True).
        """
        logging.info("Exiting module...")
