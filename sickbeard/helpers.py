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


import StringIO
import gzip
import os.path
import os
import sqlite3
import codecs
import urllib
import re

from sickbeard.exceptions import *
from sickbeard.logging import *
from sickbeard.common import mediaExtensions, XML_NSMAP

from sickbeard import db

from lib.tvdb_api import tvdb_api, tvdb_exceptions

from lxml import etree

def replaceExtension (file, newExt):
	sepFile = file.rpartition(".")
	if sepFile[0] == "":
		return file
	else:
		return sepFile[0] + "." + newExt

def isMediaFile (file):
	sepFile = file.rpartition(".")
	if sepFile[2] in mediaExtensions:
		return True
	else:
		return False

def sanitizeSceneName (name):
	for x in ":()'!":
		name = name.replace(x, "")
	return name
		
def sanitizeFileName (name):
	for x in ":\\/*":
		name = name.replace(x, "-")
	for x in "\"<>|?":
		name = name.replace(x, "")
	return name
		
def makeSceneShowSearchStrings(show):

	showName = show.name.replace(" ", ".").replace("&", "and").replace(". ", " ")

	if not showName.endswith(")") and show.startyear > 1900:
		showName += ".(" + str(show.startyear) + ")"

	results = []

	results.append(showName)

	if showName.find("(") != -1:
		showNameNoBrackets = showName.rpartition(".(")[0]
		results.append(sanitizeSceneName(showNameNoBrackets))
	
	return results


def makeSceneSearchString (episode):

	epString = ".S{0:0>2}E{1:0>2}".format(episode.season, episode.episode)

	showNames = makeSceneShowSearchStrings(episode.show)

	toReturn = []

	for curShow in showNames:
		toReturn.append(curShow + epString)

	return toReturn
	
def getGZippedURL (f):
	compressedResponse = f.read()
	compressedStream = StringIO.StringIO(compressedResponse)
	gzipper = gzip.GzipFile(fileobj=compressedStream)
	return gzipper.read()

def findCertainShow (showList, tvdbid):
	results = filter(lambda x: x.tvdbid == tvdbid, showList)
	if len(results) == 0:
		return None
	elif len(results) > 1:
		raise MultipleShowObjectsException()
	else:
		return results[0]
	
def findCertainTVRageShow (showList, tvrid):

	if tvrid == 0:
		return None

	results = filter(lambda x: x.tvrid == tvrid, showList)

	if len(results) == 0:
		return None
	elif len(results) > 1:
		raise MultipleShowObjectsException()
	else:
		return results[0]
	
	
def makeDir (dir):
	if not os.path.isdir(dir):
		try:
			os.makedirs(dir)
		except OSError:
			return False
	return True

def makeShowNFO(showID, showDir):

	Logger().log("Making NFO for show "+str(showID)+" in dir "+showDir, DEBUG)

	if not makeDir(showDir):
		Logger().log("Unable to create show dir, can't make NFO", ERROR)
		return False

	t = tvdb_api.Tvdb(apikey=sickbeard.TVDB_API_KEY)
	
	tvNode = etree.Element( "tvshow", nsmap=XML_NSMAP )
	nfo = etree.ElementTree( tvNode )

	try:
		myShow = t[int(showID)]
	except tvdb_exceptions.tvdb_shownotfound:
		Logger().log("Unable to find show with id " + str(showID) + " on tvdb, skipping it", ERROR)
		raise
		return False
	except tvdb_exceptions.tvdb_error:
		Logger().log("TVDB is down, can't use its data to add this show", ERROR)
		return False

	# check for title and id
	try:
		if myShow["seriesname"] == None or myShow["seriesname"] == "" or myShow["id"] == None or myShow["id"] == "":
			Logger().log("Incomplete info for show with id " + str(showID) + " on tvdb, skipping it", ERROR)
			return False
	except tvdb_exceptions.tvdb_attributenotfound:
		Logger().log("Incomplete info for show with id " + str(showID) + " on tvdb, skipping it", ERROR)
		return False
	
	title = etree.SubElement( tvNode, "title" )
	if myShow["seriesname"] != None:
		title.text = myShow["seriesname"]
		
	rating = etree.SubElement( tvNode, "rating" )
	if myShow["rating"] != None:
		rating.text = myShow["rating"]

	plot = etree.SubElement( tvNode, "plot" )
	if myShow["overview"] != None:
		plot.text = myShow["overview"]

	episodeguideurl = etree.SubElement( tvNode, "episodeguideurl" )
	episodeguide = etree.SubElement( tvNode, "episodeguide" )
	if myShow["id"] != None:
		showurl = sickbeard.TVDB_BASE_URL + '/series/' + myShow["id"] + '/all/en.zip'
		episodeguideurl.text = showurl
		episodeguide.text = showurl
		
	mpaa = etree.SubElement( tvNode, "mpaa" )
	if myShow["contentrating"] != None:
		mpaa.text = myShow["contentrating"]

	id = etree.SubElement( tvNode, "id" )
	if myShow["imdb_id"] != None:
		id.text = myShow["imdb_id"]
		
	tvdbid = etree.SubElement( tvNode, "tvdbid" )
	if myShow["id"] != None:
		tvdbid.text = myShow["id"]
		
	genre = etree.SubElement( tvNode, "genre" )
	if myShow["genre"] != None:
		genre.text = " / ".join([x for x in myShow["genre"].split('|') if x != ''])
		
	premiered = etree.SubElement( tvNode, "premiered" )
	if myShow["firstaired"] != None:
		premiered.text = myShow["firstaired"]
		
	studio = etree.SubElement( tvNode, "studio" )
	if myShow["network"] != None:
		studio.text = myShow["network"]
	
	Logger().log("Writing NFO to "+os.path.join(showDir, "tvshow.nfo"), DEBUG)
	nfo_fh = open(os.path.join(showDir, "tvshow.nfo"), 'w')
	nfo.write( nfo_fh, encoding="utf-8", xml_declaration=True,
		pretty_print=True )
	nfo_fh.close()

	return True


def searchDBForShow(showName):
	
	# if tvdb fails then try looking it up in the db
	myDB = db.DBConnection()
	sqlResults = myDB.select("SELECT * FROM tv_shows WHERE show_name LIKE ?", [showName+'%'])
	
	if len(sqlResults) != 1:
		if len(sqlResults) == 0:
			Logger().log("Unable to match a record in the DB for "+showName, DEBUG)
		else:
			Logger().log("Multiple results for "+showName+" in the DB, unable to match show name", DEBUG)
		return None
	
	return (int(sqlResults[0]["tvdb_id"]), sqlResults[0]["show_name"])

def findLatestRev():

	regex = "http\://sickbeard\.googlecode\.com/files/SickBeard\-r(\d+)\.zip"
	
	svnFile = urllib.urlopen("http://code.google.com/p/sickbeard/downloads/list")
	
	for curLine in svnFile.readlines():
		match = re.search(regex, curLine)
		if match:
			groups = match.groups()
			return int(groups[0])

	return None
