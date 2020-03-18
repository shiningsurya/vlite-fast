
from collections import deque


class CandidateCache (deque):
    """Ordered list of fixed size for trigger dispatch"""
    def __init__ (self, cap=50, maxsize=-1):
        """
        Args:
            cap  (int)      : max number of triggers to process in one go
            maxsize (int)   : maximum number of triggers to ever have
                              -1 -> 4 times cap
            # comp (callable) : Something to be used to compare
        """
        if maxsize == -1:
            maxsize = 4 * cap
        #
        self.maxs   = maxsize
        super(CandidateCache, self).__init__ ([],self.maxs)
        self.cap    = cap

    def __iter__(self):
        """Iteration"""
        iter = min (self.cap, self.__len__())
        for i in range(iter):
            yield self.popleft ()

    def __repr__(self):
        """for printing"""
        return "CandidateCache of size={0} cap={1} maxsize={2}".format(self.__len__(), self.cap, self.maxs )
