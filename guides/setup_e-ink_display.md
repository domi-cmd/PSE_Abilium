# 1 - Hardware Setup
Configure the pins of the shareware display as seen in the following video at 0:53 onwards: https://www.youtube.com/watch?v=QU4LxcYIbuE

# 2 - Install Python

Run the following to install the newest version of Python:
```
sudo apt update
```

```
sudo apt install python3-pip python3-dev
```

# 3 - Create Virtual Environment (Optional?)
My Pi has issues with running pip commands, which are resolved using a venv. Run the following commands to first create a virtual environment, then to activate it:


```
sudo pip3 install virtualenv
```
```
python3 -m venv ~/myenv
```

# 4 Setup Packages in Virtual Env
Run the following commands to set up ur venv properly:
```
pip install colorzero
pip install gpiozero
pip install pigpio
pip install pillow
pip install RPi.GPIO
pip install spidev
```
You can verify that the environment as been set up by running:
```
pip freeze
```
This should give the following output:
```
colorzero==2.0
gpiozero==2.0.1
pigpio==1.78
pillow==11.1.0
RPi.GPIO==0.7.1
spidev==3.6
```

# 5. Running A Display Test!
Since we are using sharewares e-ink displays, run the following command to clone their repository, which includes tests for their different kinds of displays:
```
git clone https://github.com/waveshare/e-Paper.git
```
Then navigate to their test folder:
```
cd e-Paper/RaspberryPi_JetsonNano/python/examples/
````
From there, run the following command to run a test!
```
sudo python3 epd_2in13_V4_test.py
```
_**!! Important !!**_

On your display cardboard box, as well as on the display itself, it should be denoted what type (size) your display is. Make sure to run a test fitting your display type!
For example, since I have a 2 inch 13 display, I rung the command epd_**2inch13**_.....

To deactivate your virtual environment once you are done, run:
```
deactivate
```

Hope this works guyss
