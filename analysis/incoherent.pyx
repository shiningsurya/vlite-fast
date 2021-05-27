# cython
cimport cython
# numpy 
import numpy  as np
cimport numpy as np

import constants as c

ctypedef fused datype:
    np.ndarray[np.float32_t, ndim=2]
    np.ndarray[np.uint8_t, ndim=2]

DDTYPE = np.uint64
ctypedef np.uint64_t DDTYPE_t

@cython.boundscheck (False)
@cython.wraparound  (False)
def FreqTable (np.uint64_t nchans):
    """foff is negative"""
    cdef np.ndarray[np.float32_t, ndim=1] ret = np.zeros (nchans, dtype=np.float32)
    cdef np.float32_t fch0 = c.FCH0
    cdef np.float32_t foff = c.FFT_FOFF
    for i in range (nchans):
        ret[i] = fch0 + ((nchans-i-1) * foff)
    return ret


@cython.boundscheck (False)
@cython.wraparound  (False)
def DMDelays (np.float32_t dm, np.float32_t tsamp, np.ndarray[np.float32_t, ndim=1] freq):
    """Freq in decreasing order"""
    cdef Py_ssize_t nchans  = freq.shape[0]
    cdef np.ndarray[np.uint64_t, ndim=1] ret = np.zeros (nchans, dtype=np.uint64)
    # 
    cdef np.float32_t f0    = freq[0] 
    cdef np.float32_t if02  = 1.0 / f0 / f0
    cdef np.float32_t f1    = 0.0
    cdef np.float32_t if12  = 0.0
    #
    for i in range (nchans):
        f1  = freq[i]
        if12  = 1.0 / f1 / f1
        ret[i] = <np.uint64_t>( dm * 4148.741601 * ( if12 - if02 ) / tsamp )
    #
    #ret = ret[::-1]
    return ret


@cython.boundscheck (False)
@cython.wraparound  (False)
def Incoherent (datype fb, np.ndarray[DDTYPE_t, ndim=1] delays, Py_ssize_t outsize = 0):
    if fb.shape[0] != delays.shape[0]:
        raise ValueError ("Incorrect delays size!")
    # constants 
    cdef Py_ssize_t nchans   = fb.shape[0]
    cdef Py_ssize_t nsamps   = fb.shape[1]
    cdef Py_ssize_t maxdelay = delays[nchans -1]
    if nsamps <= maxdelay:
        raise ValueError ("DM range too high!")
    cdef Py_ssize_t ddnsamps = nsamps - maxdelay
    if outsize != 0:
        ddnsamps = outsize
    cdef Py_ssize_t tidx     = 0
    # output array
    cdef datype ret = np.zeros ([nchans, ddnsamps], dtype=fb.dtype)
    # algo
    for isamp in range (ddnsamps):
        for ichan in range (nchans):
            tidx = isamp + delays[ichan]
            ret[ichan, isamp] = fb[ichan, tidx]
    #
    return ret

