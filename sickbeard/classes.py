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



import sickbeard

import urllib
from common import *

class AuthURLOpener(urllib.FancyURLopener):
    def __init__(self, user, pw):
        self.username = user
        self.password = pw
        self.numTries = 0
        urllib.FancyURLopener.__init__(self)
    
    def prompt_user_passwd(self, host, realm):
        if self.numTries == 0:
            self.numTries = 1
            return (self.username, self.password)
        else:
            return ('', '')

    def openit(self, url):
        self.numTries = 0
        return urllib.FancyURLopener.open(self, url)

class SearchResult:

    def __init__(self, episode):
        self.provider = -1
        self.url = ""
        self.extraInfo = []
        self.episode = episode
        self.predownloaded = False
        self.quality = -1

    def __str__(self):
        myString = providerNames[self.provider] + " @ " + self.url + "\n"
        myString += "Extra Info:\n"
        for extra in self.extraInfo:
            myString += "  " + extra + "\n"
        return myString

    def fileName(self):
        return self.episode.prettyName() + "." + self.resultType

class NZBSearchResult(SearchResult):
    resultType = "nzb"


class TorrentSearchResult(SearchResult):
    resultType = "torrent"


class ShowListUI:
    def __init__(self, config, log):
        self.config = config
        self.log = log

    def selectSeries(self, allSeries):
        idList = [x.tvdbid for x in sickbeard.showList]

        # try to pick a show that's in my show list
        for curShow in allSeries:
            if int(curShow['sid']) in idList:
                return curShow
        
        # if nothing matches then just go with the first match I guess
        return allSeries[0]
