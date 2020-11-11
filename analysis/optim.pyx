cimport cython
# numpy 
import numpy  as np
cimport numpy as np
# scipy
import scipy.ndimage.filters as sndf

import constants as c
import incoherent as incoh

ctypedef np.uint64_t                      id_t
ctypedef fused datype:
    np.ndarray[np.float32_t, ndim=2]
    np.ndarray[np.uint8_t, ndim=2]
#ctypedef np.ndarray[np.float32_t, ndim=2] fb_t


@cython.boundscheck (False)
@cython.wraparound  (False)
def Qn (np.ndarray[np.float32_t, ndim=1] s):
    """Computes variance using absolute pairwise differences method
        
        XXX I do not fully understand this algorithm
        Will ask Matthew
    """
    cdef Py_ssize_t size = s.size
    cdef np.ndarray[np.float32_t, ndim=1] diffs = np.zeros ( size * (size-1) // 2 )

    cdef Py_ssize_t counter  = 0
    cdef Py_ssize_t newsamps = 0
    for i in range (size - 1):
        newsamps  = size - i - 1
        diffs[counter:counter+newsamps] = np.abs (s[i] - s[i+1:])
        counter   += newsamps

    return 2.2219 * np.percentile (diffs, 25)

@cython.boundscheck (False)
@cython.wraparound  (False)
def Width (np.ndarray[np.float32_t, ndim=1] ts, id_t start, id_t stop, id_t wmax = 32):
    """Optimizes width
    
    Arguments:
        ts (np.ndarray[np.float32_t, ndim=1]) time series
        start (np.uint64_t) start of the ON pulse
        stop  (np.uint64_t) stop  of the ON pulse
    """
    cdef Py_ssize_t nsamps = ts.shape[0]
    cdef np.ndarray[id_t, ndim=1] widths = np.arange (1, wmax+1, 2)
    cdef Py_ssize_t nwidths = widths.shape[0]

    cdef id_t onsamps  = stop - start

    # take the off pulse region
    cdef np.ndarray[np.uint8_t, ndim=1] on = np.zeros (nsamps, dtype=np.uint8)
    on[start:stop] = 1
    cdef np.ndarray[np.float32_t, ndim=1] offpulse = ts[np.logical_not(on)]

    # calculate Qn as robust estimate of variance
    cdef np.float32_t mean = np.median(offpulse)
    cdef np.float32_t std  = Qn (offpulse)

    cdef np.ndarray[np.float32_t, ndim=1] sns   = np.zeros(nwidths, dtype=np.float32)
    cdef np.ndarray[np.float32_t, ndim=1] locs  = np.zeros(nwidths, dtype=np.float32)

    cdef Py_ssize_t a = 0
    cdef np.ndarray[np.float32_t, ndim=1] sts
    for iw,w in enumerate(widths):
        sts = sndf.uniform_filter1d (ts, w)

        a = np.argmax (sts)
        locs[iw]   = a + w
        sns[iw]    = (sts[a] - mean) / std / w**0.5

    return widths,sns,locs

@cython.boundscheck (False)
@cython.wraparound  (False)
def DM (datype fb, np.float32_t tsamp, np.float32_t dm0, 
        id_t start, id_t stop, 
        np.float32_t delta_dm = 1e-3, np.float32_t dm_range = 1e-1,
        np.float32_t width = 0.0
        ):
    """ DM optimization  """
    cdef Py_ssize_t nstep  = int (round ( 2 * dm_range / delta_dm ))
    
    cdef np.ndarray[np.float32_t, ndim=1] dms = np.linspace (-dm_range, dm_range,nstep)
    dms += dm0
    
    
    cdef np.ndarray[np.float32_t, ndim=1] sns = np.zeros (nstep, dtype=np.float32)

    cdef Py_ssize_t nchans = fb.shape[1]
    cdef np.ndarray[np.float32_t, ndim=1] freqs = incoh.FreqTable (nchans)
    cdef np.ndarray[np.uint64_t, ndim=1]  delays
    cdef datype ddfb
    cdef np.ndarray[np.float32_t, ndim=1] pp
    cdef np.float32_t mean
    cdef np.float32_t std
    cdef np.ndarray[np.uint8_t, ndim=1] mask = c.CHAN_MASK()
    for idm, dm in enumerate (dms):
        delays = incoh.DMDelays (dm, tsamp, freqs)
        ddfb   = incoh.Incoherent (fb, delays)
        ddfb[:,mask] = 0
        pp     = ddfb[:,mask].mean(0)
        #
        mean   = np.median (pp[start:stop])
        std    = Qn (pp[start:stop])
        if width > 0.0:
            pp = sndf.uniform_filter1d (pp, width)
            std /= width**0.5
        sns[idm] = (pp.max() - mean ) / std

    return dms, sns




























