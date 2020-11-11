"""
File of constants
"""

import numpy as np

FCH1 = 384
FCH0 = 320
BW   = 64

NFFT = 6250



def CHAN_MASK():
    # explicitly zero out some RFI for the nchan=6251 case.
    mask = np.zeros(6251, dtype=np.bool)
    mask[2350:6200] = 1
    mask[3123:3128] = 0
    mask[4297] = 0
    mask[4988:4992] = 0
    return mask
