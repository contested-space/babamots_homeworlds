
# Represents piece position, ownership, and partial turns

from sys import path
path.append('..')
from state import GameState,NoSuchChildException

from stash import Stash
from turn import Turn
import event
from color import colors
import piece
from system import System,fromSaveTuple as systemFromTuple
from hwExceptions import TurnNotOverException
from text2turn import applyTextTurn

divideSysStr = '='*30

def fromTuple(t):
    # Create a state from a standard tuple
    onmove = t[0]
    alive = list(t[1])
    nplayers = len(alive)
    systems = [systemFromTuple(s) for s in t[2]]
    #TODO somehow, this puts two states in rem
    return HWState(nplayers,onmove,systems,alive=alive)
            

class HWState(GameState):
    def __init__(self,
                 nplayers=2,
                 onmove=0,
                 systems=None,
                 stash=None,
                 alive=None, # list of player statuses, None for not yet created
                 ):
        '''
        Although game states can be modified,
        the HASH and TUPLE version for the state are fixed upon construction
        This can be confusing, so be careful
        '''
        self.nplayers = nplayers

        if systems is None:
            systems = []
            alive = [None]*nplayers
        self.systems = systems

        if stash is None:
            stash = Stash(nplayers+1)
            for sys in systems:
                for m in sys.markers:
                    stash.request(m)
                for s in sys.ships:
                    stash.request(s.piece)
        self.stash = stash

        if alive is None:
            # This assumes that players with no home have been eliminated
            alive = [False]*nplayers
            for sys in systems:
                if not sys.home is None:
                    alive[sys.home] = True

        self.alive = alive
        # This turn will be built one event as a time 
        self.curTurn = Turn(self)

        self.tupled = None

        GameState.__init__(self,onmove)

    def deepCopy(self):
        systems = [s.deepCopy() for s in self.systems]
        stash = self.stash.deepCopy()
        alive = list(self.alive)
        return HWState(
            self.nplayers,
            self.onmove,
            systems,
            stash,
            alive
        )

    def creationOver(self):
        return self.alive.count(None) == 0

    def addSystem(self,system):
        self.systems.append(system)

    def removeSystem(self,system):
        self.systems.pop(self.systems.index(system))

    def findHome(self,player):
        for sys in self.systems:
            if sys.home == player:
                return sys
        # Player's home is missing
        return None

    def cancelTurn(self):
        self.curTurn.undoAll()

    def addEvent(self,e):
        # Event should be a Creation, Action, Catastrophe, or Pass
        # Fade events are checked for and triggered here

        self.curTurn.addEvent(e)
        e.enact(self)

        # Check for Fades (but not for home systems)
        sys = e.getThreatenedSystem()
        if (not sys is None) and (sys.home is None) and sys.isVoid():
            fade = sys.getFade()
            self.curTurn.addEvent(fade)
            fade.enact(self)

        for sys in self.systems:
            if sys.isEmpty() and sys.home is None:
                print 'Problem event seems to have been'
                print e
                raise Exception('Void not faded')

    def finishTurn(self):
        # Checks for home system fades and eliminations
        if not self.curTurn.isCompleted():
            raise TurnNotOverException('Turn does not appear to be complete (did you mean to pass?)')

        # Check for elimination
        # TODO this is better for huge numbers of players, but slower otherwise
#        players = self.curTurn.getThreatenedPlayers()
#        for player in players:
        for player in range(self.nplayers):
            if self.alive[player] != True:
                # Player is either already known to be dead or hasn't created a home
                continue
            # Player is believed to be alive but may have just been eliminated
            home = self.findHome(player)
            if not home.hasPresence(player):
                # This player is now dead
                elim = event.Elimination(player,self.onmove)
                self.curTurn.addEvent(elim)
                elim.enact(self)
            # If this home is empty, it was prevented from fading immediately
            if home.isVoid():
                fade = home.getFade()
                self.curTurn.addEvent(fade)
                fade.enact(self)

    def startNewTurn(self):
        self.advanceOnmove()
        self.curTurn = Turn(self)

    def advanceOnmove(self,d=1):
        # set d=-1 to get previous player
        self.onmove = self.getNextPlayer(d)

    def getNextPlayer(self,d=1):
        # set d=-1 to get previous player
        i = (self.onmove+1)%self.nplayers
        # TODO if current player is somehow dead, this is an endless loop
        while self.alive[i] == False:
            i = (i+1)%self.nplayers
        return i

    def saveTuple(self):
        # Returns a tuple appropriate for saving the game
        # Systems are not sorted, so not appropriate for comparing states
        # Includes system names
        stuples = [s.saveTuple() for s in self.systems]
        return (self.onmove,tuple(self.alive),tuple(stuples))

    def tuplify(self):
        if not self.tupled is None:
            return self.tupled
        stuples = [s.tuplify() for s in self.systems]
        stuples.sort()
        self.tupled = (self.onmove,tuple(self.alive),tuple(stuples))
        return self.tupled

    def calcHash(self):
        return hash(self.tuplify())

    def _isEnd(self):
        # TODO implement other win conditions
        return self.alive.count(True) == 1 and self.creationOver()

    def __eq__(self,other):
        return self.tuplify() == other.tuplify()

    def __str__(self):
        movestr = 'Player %s to move'%self.onmove
        stashStr = str(self.stash)
        sysStr = ('\n%s\n'%divideSysStr).join([str(s) for s in self.systems])
        return '%s\n%s\n%s'%(movestr,stashStr,sysStr)

    def getConnections(self,sys):
        # Return a list of systems connected to sys INCLUDING DISCOVERIES
        # TODO remember connections so this doesn't have to keep getting called
        connects = []
        # Existing systems
        for s in self.systems:
            if s.connectsTo(sys):
                connects.append(s)

        # Discoveries
        for size in piece.sizes:
            for m in sys.markers:
                if m.size == size:
                    break
            else:
                # Inner loop exited normally, discoveries may have this size
                for c in colors:
                    if self.stash.isAvailable(c,size):
                        p = piece.Piece(size,c)
                        connects.append(System([p]))
        return connects

    def getKey(self,child):
        # Get the turn that produces child
        pairs =  self.curTurn.getContinuations(getTurn=True)
        for c,t in pairs:
            if c == child:
                return t
        raise NoSuchChildException('Child not found')

    def _getChildren(self):
#        print '\nGetting children of\n',self
#        print self.curTurn
        c = self.curTurn.getContinuations()
        print '\n\nRECEIVED CONTINUATIONS\n\n'
        for child in c:
            print child
            print '\n#############\n#############\n'
        return c
    def _getChild(self,key):
        applyTextTurn(key,self)
        self.advanceOnmove(1)
        copy = self.deepCopy()
        self.advanceOnmove(-1)
        self.curTurn.undoAll()
        return copy
        # TODO when not debugging, catch errors gracefully (version below)
#        try:
#            applyTextTurn(key,self)
#            copy = self.deepCopy()
#        except Exception as e:
#            raise e
#        finally:
#            self.curTurn.undoAll()
#        return copy

        

