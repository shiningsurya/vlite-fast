"""
First look at the voltages

Skipping optimization steps for speed
"""
import os
import sys
import glob
import time
import ubjson

import numpy as np
import matplotlib.pyplot   as plt
import matplotlib.gridspec as mgs
import matplotlib.colors   as mc
from skimage.measure import block_reduce

import constants as c
import incoherent as incoh
import optim


import baseband
import beamforming
from   baseband import VDIFHeader

DIR = "/fpra/bursts/01/sbethapudi/vlite/crab_2020_08/"

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

def get_args ():
    import argparse as agp
    ag = agp.ArgumentParser ('quicklook', description='Quick looks the VDIF dumps', epilog='Part of VLITE-Fast')
    add = ag.add_argument
    add ('-v,--verbose', dest='v', help='Verbose', action='store_true')
    add ('meta', help='META file',)
    add ('-d,--dir', help='VDIF directory to search', required=True, dest='vdir')
    add ('-o,--outdir', help='Output directory to store plots', default='./', dest='outdir')
    return ag.parse_args ()

if __name__ == "__main__":
    args = get_args ()
    META = args.meta
    DIR  = args.vdir
    ##################################################
    ## meta  
    if args.v:
        print ("META = ", META)
    ## ideally read the meta file
    meta   = read_meta (META)
    T0     = meta["t0"]
    T1     = meta["t1"]
    DM0    = meta["dm"]
    WD0    = meta["width"]

    ##
    ## load files
    if args.v:
        print ("Searching {0} directory ...".format(DIR))
    VDIFS  = []
    for ii in range (int(T0), int(T1)):
        VDIFS += glob.glob (os.path.join (DIR, "*ea*_{0:d}.vdif".format(ii)))
    fnames   = sorted (VDIFS)
    if args.v:
        print ("VDIFS [{0:d}] = ".format(len(fnames)), fnames)
    if len(fnames) == 0:
        raise IOError (" cannot find VDIFs ")

    data     = beamforming.load_dataset(fnames)
    antennas = data['antennas']
    if args.v:
        print (f"Found {len(antennas):d} antennas = ", antennas)
    numants = len(antennas)

    ##
    ## time sanity check
    DT0 = data[data['antennas'][0]]['header'].get_unix_timestamp()
    offset  = T0 - DT0

    ##
    ## filterbanking step
    allfbs, tsamp = build_filterbanks (data, navg=8, pol=-1)
    fb            = allfbs.mean (axis=0)
    nchans        = fb.shape[0]

    ##
    ## setup de-dispersion
    freqs         = incoh.FreqTable (nchans)
    delays0  = incoh.DMDelays (DM0, tsamp, freqs)

    ##
    ## de-disperse all single antennas 
    ddant = [ incoh.Incoherent (allfbs[i], delays0) for i in range(numants) ]

    ##################################################
    ## store intermediate
    #np.savez ("PACKED.npz", 

    ##
    ##################################################
    ## plotting
    # 
    bropt   = (16, 1)
    hWIDTH  = 0.1
    TLIM    = (offset-hWIDTH, offset+hWIDTH)
    II      = int ((offset-hWIDTH) / tsamp)
    JJ      = int ((offset+hWIDTH) / tsamp)
    ### log10
    fbs      = np.log10 (ddant)
    ### bandpass normalize
    bpass     = fbs.mean (axis=2)
    bpass_shape  = list(fbs.shape)
    bpass_shape[2] = 1
    fbs      /= bpass.reshape(tuple(bpass_shape))

    fb_avg  = block_reduce (fbs[:,-3072:,II:JJ], (1,)+bropt, func=np.mean)
    ifreqs  = block_reduce (freqs[-3072:], (bropt[0],), func=np.mean)

    c_fb    = fb_avg.mean (0)
    numants, nchans, nsamps  = fb_avg.shape

    itimes  = np.arange (nsamps) * bropt[1] * tsamp
    extent  = [itimes[0], itimes[-1], ifreqs[0], ifreqs[-1]]
    ###############
    imdict  = {'cmap':plt.cm.plasma, 'aspect':'auto', 'extent':extent, 'origin':'lower'}
    fig     = plt.figure ( figsize=(20., 15.) )
    gs      = mgs.GridSpec (5, 6, figure=fig,)
    ANT_LAY = np.arange (16).reshape((4,4))
    MAPPER  = {}
    """
           0    1     2     3     4     5     
    0   | _ t-cfb _ | t   | t   | t   | t   |
    1   |           | ant | ant | ant | ant |
    2   |    cfb    | ant | ant | ant | ant |
    3   |           | ant | ant | ant | ant |
    4   |           | ant | ant | ant | ant |
    """

    def fbaxer (g, ifb, ):
        if ifb >= numants:
            return
        ax = fig.add_subplot (g)
        ax.imshow (fb_avg[ifb], **imdict, )
        ax.set_title (antennas[ifb])
        return ax

    COLOR = 'rgbk'
    def ttaxer (g, ia):
        la = []
        for iia in ia:
            if iia < numants:
                la.append (iia)
        if len(la) == 0:
            return
        ax = fig.add_subplot (g)
        for iii,iia in enumerate (la):
            pp  = fb_avg[iia].mean(0)
            pp -= pp.mean()
            pp /= pp.std()
            ax.step (itimes,pp, where='mid', alpha=0.6, c=COLOR[iii])
        return ax

    ax12 = fbaxer (gs[1,2], 0)
    ax13 = fbaxer (gs[1,3], 1)
    ax14 = fbaxer (gs[1,4], 2)
    ax15 = fbaxer (gs[1,5], 3)

    ax22 = fbaxer (gs[2,2], 4)
    ax23 = fbaxer (gs[2,3], 5)
    ax24 = fbaxer (gs[2,4], 6)
    ax25 = fbaxer (gs[2,5], 7)

    ax32 = fbaxer (gs[3,2], 8)
    ax33 = fbaxer (gs[3,3], 9)
    ax34 = fbaxer (gs[3,4], 10)
    ax35 = fbaxer (gs[3,5], 11)

    ax42 = fbaxer (gs[4,2], 12)
    ax43 = fbaxer (gs[4,3], 13)
    ax44 = fbaxer (gs[4,4], 14)
    ax45 = fbaxer (gs[4,5], 15)

    tx02 = ttaxer (gs[0,2], [0, 4,  8, 12])
    tx03 = ttaxer (gs[0,3], [1, 5,  9, 13])
    tx04 = ttaxer (gs[0,4], [2, 6, 10, 14])
    tx05 = ttaxer (gs[0,5], [3, 7, 11, 15])

    ## 
    ## sharing
    for ix in [ax13,ax14,ax15,ax22,ax23,ax24,ax25,ax32,ax33,ax34,ax35,ax42,ax43,ax44,ax45,tx02,tx03,tx04,tx05]:
        if ix:
            ax12.get_shared_x_axes().join (ax12, ix)
    for ix in [ax13,ax14,ax15,ax22,ax23,ax24,ax25,ax32,ax33,ax34,ax35,ax42,ax43,ax44,ax45]:
        if ix:
            ax12.get_shared_y_axes().join (ax12, ix)

    axcfb = fig.add_subplot (gs[1:, :2])
    axcfb.imshow (c_fb, **imdict,)

    axtcfb = fig.add_subplot (gs[0, :2])
    pp = c_fb.mean(0)
    pp -= pp.mean ()
    pp /= pp.std()
    axtcfb.step (itimes, pp, where='mid')
    axtcfb.axvline (hWIDTH, ls='--', c='r', alpha=0.6)
    axtcfb.set_title ('ea99')

    axcfb.get_shared_x_axes().join (axcfb, axtcfb)
    #ax12.set_xlim (*TLIM)
    #axcfb.set_xlim (*TLIM)

    ##
    ## labels
    axcfb.set_xlabel ('Time [s]')
    axcfb.set_ylabel ('Freq [MHz]')

    ##
    ## save
    bM = os.path.basename (META)
    tx02.set_title (bM)
    fig.savefig (os.path.join (args.outdir, bM.replace('meta','png')), bbox_inches='tight', dpi=300)

