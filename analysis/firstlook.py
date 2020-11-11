"""
First look at the voltages
"""
import os
import sys
import glob
import time
import ubjson

import numpy as np
import matplotlib.pyplot as plt

import constants as c
import incoherent as incoh
import optim


import baseband
import beamforming
from   baseband import VDIFHeader

def read_meta (x):
    """ Reads meta file """
    with open (x, "rb") as f:
        m = ubjson.load (f)
    return m

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
    DIR = "/data/vlite-fast/voltages/crab_2020_08"
    VD   = "*ea?5*1347*.vdif"
    META = "1598013475_i1_dm56.75_sn55.51_wd03.91.meta"
    ##
    ## ideally read the meta file
    meta   = read_meta (os.path.join (DIR, META))
    T0     = meta["t0"]
    DM0    = meta["dm"]
    width  = meta["width"]

    fnames   = sorted (glob.glob (os.path.join (DIR, VD) ))

    data     = beamforming.load_dataset(fnames)
    antennas = data['antennas']
    print ("Found antennas=", antennas)
    numants = len(antennas)
    #sys.exit (0) 
    allfbs, tsamp = build_filterbanks (data, navg=8, pol=-1)
    fb            = allfbs.mean (axis=0)
    nchans        = fb.shape[0]
    freqs         = incoh.FreqTable (nchans)
    print (nchans)

    mask          = c.CHAN_MASK ()


    I0 = int(round((T0-data[data['antennas'][0]]['header'].get_unix_timestamp())/tsamp))
    I1 = int(round((T0-data[data['antennas'][0]]['header'].get_unix_timestamp()+0.2)/tsamp))

    prof_odm = time.time()
    ##
    ## De-disperse to original DM
    delays0  = incoh.DMDelays (DM0, tsamp, freqs)
    dd0  = incoh.Incoherent (fb, delays0)
    pp0  = dd0[mask, :].mean (0)

    prof_ref = time.time()
    ##
    ## WD1
    wd1s, wsn1, locs = optim.Width (pp0, I0, I1)
    WD1 = wd1s[wsn1.argmax()]
    ## DM1
    dm1s = optim.DM (fb, tsamp, DM0, I0, I1, delta_dm=0.1, dm_range=2, width=WD1)
    DM1  = dm1s[0][dm1s[1].argmax()]
    ## DM2
    dm2s = optim.DM (fb, tsamp, DM1, I0, I1, delta_dm=2e-3, dm_range=2e-2, width=WD1)
    DM2 = dm2s[0][dm2s[1].argmax()]

    ##
    ## Finalize DM refinement
    delays2  = incoh.DMDelays (DM2, tsamp, freqs)
    dd2  = incoh.Incoherent (fb, delays2)
    pp2  = dd2[mask, :].mean (0)

    ##
    ## Finalize WD refinement
    wd2s, wsn2, locs = optim.Width (pp2, I0, I1)
    WD2 = wd2s[wsn2.argmax()]

    prof_all = time.time()
    ## 
    ## de-disperse all single antennas 
    ddant = [ incoh.Incoherent (allfbs[i], delays2) for i in range(numants) ]

    prof_end = time.time()

    print ("original-dm=",prof_ref - prof_odm)
    print ("refinement=", prof_all - prof_ref)
    print ("all_antenans=",prof_end - prof_all)

