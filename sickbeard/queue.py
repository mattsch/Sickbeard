from __future__ import with_statement

import os.path
import threading
import traceback

from lib.tvdb_api import tvdb_exceptions

from sickbeard.common import *

from sickbeard.tv import TVShow
from sickbeard import exceptions
from sickbeard import helpers
from sickbeard import logger


class ShowQueue:
    def __init__(self):

        self.currentItem = None
        self.queue = []
        
        self.thread = None

    def _isInQueue(self, show, actions):
        return show in [x.show for x in self.queue if x.action in actions]
    
    def _isBeingSomethinged(self, show, actions):
        return self.currentItem != None and show == self.currentItem.show and \
                self.currentItem.action in actions
    
    def isInUpdateQueue(self, show):
        return self._isInQueue(show, (QueueActions.UPDATE, QueueActions.FORCEUPDATE))

    def isInRefreshQueue(self, show):
        return self._isInQueue(show, (QueueActions.REFRESH,))

    def isBeingAdded(self, show):
        return self._isBeingSomethinged(show, (QueueActions.ADD,))

    def isBeingUpdated(self, show):
        return self._isBeingSomethinged(show, (QueueActions.UPDATE, QueueActions.FORCEUPDATE))

    def isBeingRefreshed(self, show):
        return self._isBeingSomethinged(show, (QueueActions.REFRESH,))

    def _getLoadingShowList(self):
        return [x for x in self.queue+[self.currentItem] if x != None and x.isLoading]

    loadingShowList = property(_getLoadingShowList)

    def run(self):
        
        # only start a new task if one isn't already going
        if self.thread == None or self.thread.isAlive() == False:

            # if the thread is dead then the current item should be finished
            if self.currentItem != None:
                self.currentItem.finish()
                self.currentItem = None

            # if there's something in the queue then run it in a thread and take it out of the queue
            if len(self.queue) > 0:
                
                queueItem = self.queue[0]
                
                logger.log("Starting new task: " + QueueActions.TEXT[queueItem.action] + " - " + queueItem.name)

                # launch the queue item in a thread
                # TODO: improve thread name
                threadName = "QUEUE-" + QueueActions.TEXT[queueItem.action].replace(" ","").upper()
                self.thread = threading.Thread(None, queueItem.execute, threadName)
                self.thread.start()

                self.currentItem = queueItem
                
                # take it out of the queue
                del self.queue[0]
        
    def updateShow(self, show, force=False):

        if self.isBeingAdded(show):
            raise exceptions.CantUpdateException("Show is still being added, wait until it is finished before you update.")
        
        if self.isBeingUpdated(show):
            raise exceptions.CantUpdateException("This show is already being updated, can't update again until it's done.")

        if self.isInUpdateQueue(show):
            raise exceptions.CantUpdateException("This show is already being updated, can't update again until it's done.")

        if not force:
            queueItemObj = QueueItemUpdate(show)
        else:
            queueItemObj = QueueItemForceUpdate(show)
        
        self.queue.append(queueItemObj)
        
        return queueItemObj

    def refreshShow(self, show):

        if self.isBeingRefreshed(show):
            raise exceptions.CantRefreshException("This show is already being refreshed, not refreshing again.")

        if self.isBeingUpdated(show) or self.isInUpdateQueue(show):
            logger.log("A refresh was attempted but there is already an update queued or in progress. Since updates do a refres at the end anyway I'm skipping this request.", logger.DEBUG)
            return
        
        queueItemObj = QueueItemRefresh(show)
        
        # refresh gets put at the front cause it's quick
        self.queue.insert(0, queueItemObj)
        
        return queueItemObj
    
    def addShow(self, showDir):
        queueItemObj = QueueItemAdd(showDir)
        self.queue.append(queueItemObj)
        
        return queueItemObj

class QueueActions:
    REFRESH=1
    ADD=2
    UPDATE=3
    FORCEUPDATE=4
    
    TEXT = {REFRESH: 'Refresh',
            ADD: 'Add',
            UPDATE: 'Update',
            FORCEUPDATE: 'Forced Update'
    }

class QueueItem:
    """
    Represents an item in the queue waiting to be executed
    
    Can be either:
    - show being added (may or may not be associated with a show object)
    - show being refreshed
    - show being updated
    - show being force updated
    """
    def __init__(self, action, show=None):
        self.action = action
        self.show = show
        
        self.inProgress = False
    
    def _getName(self):
        return self.show.name

    def _isLoading(self):
        return False

    name = property(_getName)
    
    isLoading = property(_isLoading)
    
    def isInQueue(self):
        return self in sickbeard.showQueueScheduler.action.queue+[sickbeard.showQueueScheduler.action.currentItem]
    
    def execute(self):
        """Should subclass this"""
        
        logger.log("Beginning task")
        self.inProgress = True

    def finish(self):
        
        logger.log("Finished performing a task")
        self.inProgress = False
        
class QueueItemAdd(QueueItem):
    def __init__(self, show=None):

        self.showDir = show

        # if we can't create the dir, bail
        if not os.path.isdir(self.showDir):
            if not helpers.makeDir(self.showDir):
                raise exceptions.NoNFOException("Unable to create the show dir " + self.showDir)

        if not os.path.isfile(os.path.join(self.showDir, "tvshow.nfo")):
            raise exceptions.NoNFOException("No tvshow.nfo found")

        # this will initialize self.show to None
        QueueItem.__init__(self, QueueActions.ADD)

        self.initialShow = TVShow(self.showDir)

    def _getName(self):
        if self.show == None:
            return self.showDir
        return self.show.name

    name = property(_getName)

    def _isLoading(self):
        if self.show == None:
            return True
        return False

    isLoading = property(_isLoading)

    def execute(self):

        QueueItem.execute(self)

        logger.log("Starting to add show "+self.showDir)

        try:
            self.initialShow.getImages()
            self.initialShow.loadFromTVDB()
            
        except tvdb_exceptions.tvdb_exception, e:
            logger.log("Unable to add show due to an error with TVDB: "+str(e), logger.ERROR)
            self.finish()
            return
            
        except exceptions.NoNFOException:
            logger.log("Unable to load show from NFO", logger.ERROR)
            # take the show out of the loading list
            self.finish()
            return
            
        except exceptions.ShowNotFoundException:
            logger.log("The show in " + self.showDir + " couldn't be found on theTVDB, skipping", logger.ERROR)
            # take the show out of the loading list
            self.finish()
            return
    
        except exceptions.MultipleShowObjectsException:
            logger.log("The show in " + self.showDir + " is already in your show list, skipping", logger.ERROR)
            # take the show out of the loading list
            self.finish()
            return
        
        except Exception:
            self.finish()
            raise
    
        self.show = self.initialShow

        # add it to the show list
        sickbeard.showList.append(self.show)

        try:
            self.show.loadEpisodesFromDir()
        except Exception, e:
            logger.log("Error searching dir for episodes: " + str(e), logger.ERROR)
            logger.log(traceback.format_exc(), logger.DEBUG)
    
        try:
            self.show.loadEpisodesFromTVDB()
            self.show.setTVRID()
        except Exception, e:
            logger.log("Error with TVDB, not creating episode list: " + str(e), logger.ERROR)
            logger.log(traceback.format_exc(), logger.DEBUG)
    
        try:
            self.show.saveToDB()
        except Exception, e:
            logger.log("Error saving the episode to the database: " + str(e), logger.ERROR)
            logger.log(traceback.format_exc(), logger.DEBUG)
        
        self.show.flushEpisodes()

        self.finish()
        
        sickbeard.updateAiringList()
        sickbeard.updateComingList()
        sickbeard.updateMissingList()
        


class QueueItemRefresh(QueueItem):
    def __init__(self, show=None):
        QueueItem.__init__(self, QueueActions.REFRESH, show)

    def execute(self):

        QueueItem.execute(self)

        logger.log("Performing refresh on "+self.show.name)

        self.show.refreshDir()
        self.show.getImages()
        self.show.writeEpisodeNFOs()
        
        self.inProgress = False
        
class QueueItemUpdate(QueueItem):
    def __init__(self, show=None):
        QueueItem.__init__(self, QueueActions.UPDATE, show)
        self.force = False
    
    def execute(self):
        
        QueueItem.execute(self)
        
        logger.log("Beginning update of "+self.show.name)
        
        # get episode list from DB
        logger.log("Loading all episodes from the database", logger.DEBUG)
        DBEpList = self.show.loadEpisodesFromDB()
        
        # get episode list from TVDB
        logger.log("Loading all episodes from theTVDB", logger.DEBUG)
        TVDBEpList = self.show.loadEpisodesFromTVDB(cache=not self.force)
        
        if TVDBEpList == None:
            logger.log("No data returned from TVDB, unable to update this show", logger.ERROR)

        else:
        
            # for each ep we found on TVDB delete it from the DB list
            for curSeason in TVDBEpList:
                for curEpisode in TVDBEpList[curSeason]:
                    logger.log("Removing "+str(curSeason)+"x"+str(curEpisode)+" from the DB list", logger.DEBUG)
                    if curSeason in DBEpList and curEpisode in DBEpList[curSeason]:
                        del DBEpList[curSeason][curEpisode]
    
            # for the remaining episodes in the DB list just delete them from the DB
            for curSeason in DBEpList:
                for curEpisode in DBEpList[curSeason]:
                    logger.log("Permanently deleting episode "+str(curSeason)+"x"+str(curEpisode)+" from the database", logger.MESSAGE)
                    curEp = self.show.getEpisode(curSeason, curEpisode)
                    try:
                        curEp.deleteEpisode()
                    except exceptions.EpisodeDeletedException:
                        pass
        
        # now that we've updated the DB from TVDB see if there's anything we can add from TVRage
        with self.show.lock:
            logger.log("Attempting to supplement show info with info from TVRage", logger.DEBUG)
            self.show.loadLatestFromTVRage()
            if self.show.tvrid == 0:
                self.show.setTVRID()

        sickbeard.showQueueScheduler.action.refreshShow(self.show)

class QueueItemForceUpdate(QueueItemUpdate):
    def __init__(self, show=None):
        QueueItem.__init__(self, QueueActions.FORCEUPDATE, show)
        self.force = True

        