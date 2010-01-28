# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.



import os
import os.path
import threading
import time
import signal
import sqlite3
import sys
import traceback

import cherrypy
import cherrypy.lib.auth_basic

import sickbeard

from sickbeard import db, webserve
from sickbeard.tv import TVShow
from sickbeard import logger
from sickbeard.common import *
from sickbeard.version import SICKBEARD_VERSION

from lib.configobj import ConfigObj

from multiprocessing import Process, freeze_support

signal.signal(signal.SIGINT, sickbeard.sig_handler)
signal.signal(signal.SIGTERM, sickbeard.sig_handler)

def loadShowsFromDB():

	myDB = db.DBConnection()
	sqlResults = myDB.select("SELECT * FROM tv_shows")
	
	myShowList = []
	
	for sqlShow in sqlResults:
		try:
			curShow = TVShow(sqlShow["location"])
			curShow.saveToDB()
			sickbeard.showList.append(curShow)
		except Exception as e:
			logger.log("There was an error creating the show in "+sqlShow["location"]+": "+str(e), logger.ERROR)
			logger.log(traceback.format_exc(), logger.DEBUG)
			
		#TODO: make it update the existing shows if the showlist has something in it

	

def main():

	# do some preliminary stuff
	sickbeard.PROG_DIR = os.path.dirname(os.path.normpath(os.path.abspath(sys.argv[0])))
	sickbeard.CONFIG_FILE = "config.ini"

	# rename the main thread
	threading.currentThread().name = "MAIN"
	
	print "Starting up Sick Beard "+SICKBEARD_VERSION+" from " + os.path.join(sickbeard.PROG_DIR, sickbeard.CONFIG_FILE)
	
	# load the config and publish it to the sickbeard package
	if not os.path.isfile(os.path.join(sickbeard.PROG_DIR, sickbeard.CONFIG_FILE)):
		logger.log("Unable to find config.ini, all settings will be default", logger.ERROR)

	sickbeard.CFG = ConfigObj(os.path.join(sickbeard.PROG_DIR, sickbeard.CONFIG_FILE))

	# initialize the config and our threads
	sickbeard.initialize()

	sickbeard.showList = []

	# setup cherrypy logging
	if os.path.isdir(sickbeard.LOG_DIR) and sickbeard.WEB_LOG:
		cherry_log = os.path.join(sickbeard.LOG_DIR, "cherrypy.log")
		logger.log("Using " + cherry_log + " for cherrypy log")
	else:
		cherry_log = None

	# cherrypy setup
	webRoot = webserve.WebInterface()
	cherrypy.config.update({
						    'server.socket_port': sickbeard.WEB_PORT,
						    'server.socket_host': '0.0.0.0',
						    'log.screen': False,
						    'log.access_file': cherry_log
	})
	
	userpassdict = {sickbeard.WEB_USERNAME: sickbeard.WEB_PASSWORD}
	checkpassword = cherrypy.lib.auth_basic.checkpassword_dict(userpassdict)
	
	if sickbeard.WEB_USERNAME == "" or sickbeard.WEB_PASSWORD == "":
		useAuth = False
	else:
		useAuth = True 
	
	conf = {'/': {
				  'tools.staticdir.root': os.path.join(sickbeard.PROG_DIR, 'data'),
				  'tools.auth_basic.on': useAuth,
				  'tools.auth_basic.realm': 'SickBeard',
				  'tools.auth_basic.checkpassword': checkpassword},
		    '/images': {'tools.staticdir.on': True,
				    'tools.staticdir.dir': 'images'},
			'/js': {'tools.staticdir.on': True,
				    'tools.staticdir.dir': 'js'},
			'/css': {'tools.staticdir.on': True,
					 'tools.staticdir.dir': 'css'},
	}

	cherrypy.tree.mount(webRoot, '/', conf)

	# launch a browser if we need to
	browserURL = 'http://localhost:' + str(sickbeard.WEB_PORT) + '/'

	try:
		cherrypy.server.start()
		cherrypy.server.wait()
	except IOError:
		logger.log("Unable to start web server, is something else running?", logger.ERROR)
		logger.log("Launching browser and exiting", logger.ERROR)
		sickbeard.launchBrowser(browserURL)
		sys.exit()

	# build from the DB to start with
	logger.log("Loading initial show list")
	loadShowsFromDB()

	# set up the lists
	sickbeard.updateAiringList()
	sickbeard.updateComingList()
	sickbeard.updateMissingList()
	
	# fire up all our threads
	sickbeard.start()

	# launch browser if we're supposed to
	if sickbeard.LAUNCH_BROWSER:
		sickbeard.launchBrowser(browserURL)

	# stay alive while my threads do the work
	while (True):
		
		time.sleep(1)
	
	return
		
if __name__ == "__main__":
	freeze_support()
	main()
