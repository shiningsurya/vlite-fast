"""
First look at the voltages
"""
import os
import glob
import time

import numpy as np
import matplotlib.pyplot as plt

import incoherent as inch
import optim


import baseband
import beamforming
from   baseband import VDIFHeader

def build_filterbanks(data,nsamp=12500,navg=10,antennas=None,pol=-1):
    """ Quick and dirty method for filterbanking and square-law detecting
    the voltage data.
    """

    nb = beamforming.NewBaseband(data)
    if pol == -1:
        bbi_p0 = nb.get_iterator(nsamp,thread=0,antennas=antennas)
        bbi_p1 = nb.get_iterator(nsamp,thread=1,antennas=antennas)
        ffti_p0 = beamforming.FFTIterator(bbi_p0)
        ffti_p1 = beamforming.FFTIterator(bbi_p1)
    else:
        bbi_p0 = nb.get_iterator(nsamp,thread=pol,antennas=antennas)
        ffti_p0 = beamforming.FFTIterator(bbi_p0)
        bbi_p1 = None
        ffti_p1 = None

    nout = len(ffti_p0)//navg
    tmp = ffti_p0[0]
    results = np.zeros([tmp.shape[0],tmp.shape[1],nout],dtype=np.float32)
    prof_t1 = time.time()
    counter = 0
    tmp = np.empty(tmp.shape,dtype=np.float32)
    for i in range(nout):
        for j in range(navg):
            px = ffti_p0[counter]
            np.abs(px,out=tmp)
            tmp *= tmp
            results[...,i] += tmp
            if pol >= 0:
                counter += 1
                continue
            py = ffti_p1[counter]
            np.abs(py,out=tmp)
            tmp *= tmp
            results[...,i] += tmp
            counter += 1

    prof_t2 = time.time()
    tsamp = (nsamp*navg)/128e6
    print('Filterbanking took %.2fs.'%(prof_t2-prof_t1))
    return results,tsamp

if __name__ == "__main__":
    data          = glob.glob ("/*.vdif")
    allfbs, tsamp = build_filterbanks (data, navg=8, pol=-1)
    fb            = filterbanks.mean (axis=0)[None,...]
    _,nchans      = fb.shape
    freqs         = incoh.FreqTable (nchans)

    ##
    ## De-disperse to original DM
    delays0  = incoh.DMDelays (DM0, tsamp, freqs)
    dd0  = incoh.Incoherent (fb, delays0)
    pp0  = dd0[:,mask].mean (0)

    ##
    ## WD1
    wd1s, wsn1, locs = optim.Width (pp0, I0, I1)
    WD1 = wd1s[wsn1.argmax()]
    ## DM1
    dm1s = optim.DM (fb, tsamp, DM0, I0, I1, delta_dm=0.1, dm_range=2, width=WD1)
    DM1  = dm1s[0][dm1s[1].argmax()]
    ## DM2
    dm2s = optim.DM (fb, tsamp, DM1, I0, I1, delta_dm=1e-3, dm_range=2e-2, width=WD1)
    DM2 = dm2s[0][dm2s[1].argmax()]

    ##
    ## Finalize DM refinement
    delays2  = incoh.DMDelays (DM2, tsamp, freqs)
    dd2  = incoh.Incoherent (fb, delays2)
    pp2  = dd2[:,mask].mean (0)

    ##
    ## Finalize WD refinement
    wd2s, wsn2, locs = optim.Width (pp2, I0, I1)
    WD2 = wd2s[wsn2.argmax()]

    ## 
    ## de-disperse all single antennas 
    ddant = [ incoh.Incoherent (allfbs[i], delays2) for i in range(numants) ]


