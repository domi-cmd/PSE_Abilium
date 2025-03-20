# Installation and Setup Of Odoo18

# General Idea Of What We Are Doing (Skippable if not interested)
For running Odoo, we will need to install and setup Odoo18 so that it can run its server on our device remotely.
Since we want to have source control (github) and shared files to be able to work on our custom app together, we need to have each of us Odoo18 and its server installed individually on our device, but have a shared custom_addons folder in the github which contains the app we are working on, aswell as a shared odoo.conf file which allows us to have a shared database later on. This means that we will run the server each of us seperately, but pass to the server as parameters the app and database configs which are stored in a path outside of the server, namely our github repo.
This means that for setting up Odoo18 as we need it, we need to do the following steps as fully detailed below:
1. Installing Odoo18 (this includes postgres)

2. Cloning Our Repository (should already be the case, but nonetheless essential, as our repository will contain the custom app/custom_addons aswell as the config file needed to run the server).

3. Setting Up Python - Python is required for the server to run, and since we want to do so in the terminal, aswell as access files outside of the odoo18 folder, namely config and custom_addons, we need to install Python globally on our device

4. Running The Server - Once everything is setup, we can then run the server via terminal.

# Installing Odoo18
## 1. Downloading Odoo18
The first step is to head to odoos homepage and download the Odoo18 Community Version for Windows
[Herunterladen | Odoo](https://www.odoo.com/de_DE/page/download?msockid=39f4aad28e496d093fcab8658f426c19)

**_The information given on email, name etc is probably optional, but make sure to save the registered data somewhere just in case (screenshot?). The phone number definitely is optional and can be left empty._**


## 2. Installation Process
- Choose any installation language then press "OK"
- Click "Next", then "I Agree"
- Now when prompted to choose which odoo components to install, click the dropdown and choose **_"Odoo Server And PostgreSQL Server"_**. Then hit "next" If this is not a given option, and the PSQL clickbox is grayed out, this means you already have postgres installed. Follow any youtube video on how to deinstall it, as odoo struggles with preinstalled psql.
- Now when prompted to choose a Path where you want to install Odoo: 

**1. Make sure to _rename_ your installed Odoo18 in this step _from "Odoo 18.2o414u3something" to "odoo18"_ for easier access later on via terminal**

**_2. Choosing the path to be "C:\odoo18" is recommended as it makes following the rest of this guide easier due to identical pathing._**

- Follow the rest of the installation guide. When asked about your PSQL database settings, keep the values as follows:
  
  Hostname: localhost

  Port: 5432

  Username: openpg 

  Password: openpgpwd

- When setup is finished, uncheck "Start odoo" and go to the next step in the guide.

# Cloning Our Repository
Since we want to be working on the same app, we need to have the app (custom module) aswell as the server config file for a shared database both on our github repository, which we will then use as parameters to start the server.
The rest of the server files will be saved locally on our individual devices and setup via the Odoo setup.exe.

To clone our repository containing the app and the config file:
1. Open Git Bash and navigate in the terminal to the folder in which you want the repository folder to be in.
2. Once in the chosen place, clone the remote repository by typing:
```
git clone https://github.com/domi-cmd/PSE_Abilium.git
```
3. Type the following two to bring your remote repository is up to date:
```
git fetch
git pull
```
4. To make sure it is up to date with the remote repo, enter:
```
git status
```
   it should look as follows:
```
$ git status
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
```
5. Now you will have the files of our github repository stored in the folder you chose! This includes the config and the custom_modules that we will now require for running the server.





# Setting Up Python
We will need Python for running the server. In a first step, we will install python itself **No Version Newer Than 3.12, Do Not Install 3.13**, and in a second step, we will download the packages required for running our server.
## 1. Installing Python itself
Install Python (**_not newer than 3.12, version 3.13 does not work yet with our dependencies_**) from the following link:
https://www.python.org/downloads/windows/

In the setup, click "Add bin to path". Optionally to this, you can manually add python to you system variables after installation has finished. Guide for this: https://www.youtube.com/watch?v=91SGaK7_eeY

You can check that Python has been setup properly by opening command line by pressing "Windows + s" and then searching for "cmd". Once in the command line, either type 
```
py
```
or type
```
python
```
if for neither the current installed version of Python is returned, restart your device and then try again. If this does not fix it, Python has not yet been added to path properly. Check step above to fix this.


## 2. Installing The Required Packages
For this, Odoo itself provides a list of all requirements needed which is saved within "path/to/odoo18/server/requirements.txt".
To install said packages, open up a terminal via "windows key + s" and typing "cmd", then once within the terminal, install the packages by typing:
```
pip install -r /path/to/odoo18/server/requirements.txt.
```
**_REPLACE THE PATH WITH THE ACTUAL PATH, DEPENDING ON WHERE YOU INSTALLED ODOO AND HOW YOU NAMED IT DURING INSTALLATION_**
If no error messages are thrown, all packages are installed properly! If you installed a version newer than Python 3.12, i.e., 3.13, it probably won't work (didnt work 2 days ago), hence make sure your Python version isn't 3.13.


# Running The Server
## 1. Starting The Server
To run the server via terminal (this allows us to specify which parameters we pass when starting the server, which is required so that we can use our custom shared config and custom_modules app which is stored outside the server folder in the cloned repo folder), we use a command of the following structure:
```
py "PATH\TO\ODOOFOLDER\odoo18\server\odoo-bin" -c "PATH\TO\REPOFOLDER\PSE_Abilium\code\odoo\server_configs\odoo.conf" --addons-path="PATH\TO\REPO\CUSTOM_ADDONS\PSE_Abilium\code\odoo\custom_addons" -u all
```

**_The actual paths will differ, depending on where you installed your Odoo, aswell as on where you cloned our remote repository._** For example, I installed Odoo in C:\ and named it odoo18 during installing, and cloned our repository within the odoo (DONT RECOMMEND THIS PART). Hence, for me the actual path values look as follows:

```
py C:\odoo18\server\odoo-bin -c C:\odoo18\PSE_Abilium\code\odoo\server_configs\odoo.conf --addons-path="C:\odoo18\PSE_Abilium\code\odoo\custom_addons" -u all
```

**IMPORTANT**
Depending on whether you installed Python under "py" or "python", the command will either start with py or python. For me this is "py", just try out either and see if it works.

## 2. Interacting With Server/Odoo
If no error messages are printed upon running the start server command above, and a log has been given to terminal something like "Registry completed in 25s", the server is up and running locally on your device on Port 8069.

To now interact with the server and our app etc, open any browser you like, and in the URL, enter:
```
http://localhost:8069/
```

Upon doing this for the first time, you will be prompted to choose/setup a database on which the server will run. Enter "test_db" for its name, and propably opengpg for username and openpgpwd for password.
**_VERY IMPORTANT: MAKE SURE TO SAVE YOUR MASTER PASSWORD SOMEWHERE. WITHOUT IT, YOU WILL NOT BE ABLE TO CHANGE, CREATE OR DELETE DATABASES IN THE FUTURE._**

Next you will be prompted to log in, then you are in odoo. Make sure you are in dev mode, either by scrolling all the way to the bottom in settings, or by adding "?debug=1" to the URL. Now go to Apps and enter "reserv". Our current app dummy version should pop up.


If this is the case then everything has been set up properly! :)
