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



import urllib
import sqlite3
import datetime
import traceback

import sickbeard

from sickbeard.logging import *
from sickbeard.common import *

from sickbeard import db
from sickbeard import exceptions

from lib.tvdb_api import tvdb_api, tvdb_exceptions

class TVRage:
    
    def __init__(self, show):
        
        self.show = show
        
        self.lastEpInfo = None
        self.nextEpInfo = None
        
        pass
    
    def checkSync(self):
        
        if self.lastEpInfo == None or self.nextEpInfo == None:
            self._getLatestInfo()
        
        if self.nextEpInfo['season'] == 0 or self.nextEpInfo['episode'] == 0:
            return None
        
        try:
        
            airdate = None
        
            # make sure the last TVDB episode matches our last episode
            try:
                t = tvdb_api.Tvdb(lastTimeout=sickbeard.LAST_TVDB_TIMEOUT,
			apikey=sickbeard.TVDB_API_KEY)
                ep = t[self.show.tvdbid][self.lastEpInfo['season']][self.lastEpInfo['episode']]

                if ep["firstaired"] == "" or ep["firstaired"] == None:
                    return None

                rawAirdate = [int(x) for x in ep["firstaired"].split("-")]
                airdate = datetime.date(rawAirdate[0], rawAirdate[1], rawAirdate[2])
            
            except tvdb_exceptions.tvdb_exception as e:
                Logger().log("Unable to check TVRage info against TVDB: "+str(e))

                Logger().log("Trying against DB instead", DEBUG)

                myDB = db.DBConnection()
                sqlResults = myDB.select("SELECT * FROM tv_episodes WHERE showid = ? AND season = ? and episode = ?", [self.show.tvdbid, self.lastEpInfo['season'], self.lastEpInfo['episode']])
                
                if len(sqlResults) == 0:
                    raise exceptions.EpisodeNotFoundException("Unable to find episode in DB")
                else:
                    airdate = datetime.date.fromordinal(int(sqlResults[0]["airdate"]))
            
            Logger().log("Date from TVDB for episode " + str(self.lastEpInfo['season']) + "x" + str(self.lastEpInfo['episode']) + ": " + str(airdate), DEBUG)
            Logger().log("Date from TVRage for episode " + str(self.lastEpInfo['season']) + "x" + str(self.lastEpInfo['episode']) + ": " + str(self.lastEpInfo['airdate']), DEBUG)
        
            if self.lastEpInfo['airdate'] == airdate:
                return True
            
        except Exception as e:
            Logger().log("Error encountered while checking TVRage<->TVDB sync: " + str(e), ERROR)
            Logger().log(traceback.format_exc(), DEBUG)
        
        return False
    
    def _getLatestInfo(self):

        url = "http://services.tvrage.com/tools/quickinfo.php?" + urllib.urlencode({'show': self.show.name.encode('utf-8')})

        Logger().log("Loading TVRage info from URL: " + url, DEBUG)

        try:
            urlObj = urllib.urlopen(url)
        except (urllib.ContentTooShortError, IOError) as e:
            Logger().log("Unable to load TVRage info: " + str(e))
            raise exceptions.TVRageException("urlopen call to " + url + " failed")
        
        urlData = [x.decode('utf-8') for x in urlObj.readlines()]
        
        info = {}
        
        for x in urlData:
            key, value = x.split("@")
            info[key] = value.strip()
        
        if not info.has_key('Next Episode') or not info.has_key('Latest Episode'):
            raise exceptions.TVRageException("TVRage doesn't have all the required info for this show")
            
        self.lastEpInfo = self._getEpInfo(info['Latest Episode'])
        self.nextEpInfo = self._getEpInfo(info['Next Episode'])
        
        if self.lastEpInfo == None or self.nextEpInfo == None:
            raise exceptions.TVRageException("TVRage has malformed data, unable to update the show")


        
    def _getEpInfo(self, epString):

        Logger().log("Parsing info from TVRage: " + epString, DEBUG)
        
        epInfo = epString.split('^')
        
        numInfo = [int(x) for x in epInfo[0].split('x')]
        
        try:
            date = datetime.datetime.strptime(epInfo[2], "%b/%d/%Y").date()
        except ValueError as e:
            Logger().log("Unable to figure out the time from the TVRage data "+epInfo[2])
            return None
        
        toReturn = {'season': int(numInfo[0]), 'episode': numInfo[1], 'name': epInfo[1], 'airdate': date}
        
        Logger().log("Result of parse: " + str(toReturn), DEBUG)
        
        return toReturn

    def saveToDB(self):
        
        myDB = db.DBConnection()
        
        # double check that it's not already in there
        sqlResults = myDB.select("SELECT * FROM tv_episodes WHERE showid = " + str(self.show.tvdbid) + " AND season = " + str(self.nextEpInfo['season']) + " AND episode = " + str(self.nextEpInfo['episode']))
        
        if len(sqlResults) > 0:
            raise exceptions.TVRageException("Show is already in database, not adding the TVRage info")

        # insert it
        
        myDB.action("INSERT INTO tv_episodes (showid, tvdbid, name, season, episode, description, airdate, hasnfo, hastbn, status, location) VALUES (?,?,?,?,?,?,?,?,?,?,?)", \
                    [self.show.tvdbid, -1, self.nextEpInfo['name'], self.nextEpInfo['season'], self.nextEpInfo['episode'], '', self.nextEpInfo['airdate'].toordinal(), 0, 0, UNAIRED, ''])
        
    def getEpisode(self):
        
        ep = None
        
        try:
            ep = self.show.getEpisode(self.nextEpInfo['season'], self.nextEpInfo['episode'])
        except exceptions.SickBeardException as e:
            Logger().log("Unable to create episode from tvrage (could be for a variety of reasons): " + str(e))
    
        return ep
