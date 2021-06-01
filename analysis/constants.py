"""
File of constants
"""

import numpy as np

FCH0 = 320
BW   = 64

NFFT = 12500
NCHAN = NFFT//2 + 1
FFT_FOFF = BW / NCHAN

KEEPCHAN = 3072
KEEPFCH1 = FCH0 + (FFT_FOFF * KEEPCHAN)

def CHAN_MASK():
    m  = np.zeros((NCHAN,), dtype=np.int32)
    m[-3072:] = 1
    return m
