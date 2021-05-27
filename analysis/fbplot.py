# coding: utf-8
import numpy as np
import matplotlib.pyplot   as plt
import matplotlib.gridspec as mgs
import matplotlib.colors   as mc
import pickle as pkl
from skimage.measure import block_reduce
import constants as c
#################################################
IFILE = "basebase.pkl"
# block reduce opts
bropt = (24, 1)
#################################################
with open (IFILE, "rb") as f:
    fbs, tsamp, ants = pkl.load (f)
    #fbs, [ww, dd] = pkl.load (f)
fbs     = np.concatenate(fbs, axis=0)
ants    = np.concatenate (ants, axis=0)

means   = fbs.mean(axis=(1,2)).reshape ((-1,1,1))
stds    = fbs.std(axis=(1,2)).reshape ((-1,1,1))
fbs    -= means
fbs    /= stds


fb_avg  = block_reduce (fbs, (1,)+bropt, func=np.mean)
c_fb    = fb_avg.mean (0)
numants, nchans, nsamps  = fb_avg.shape
ifreqs  = np.arange (nchans) * bropt[0] * c.FFT_FOFF
ifreqs += c.FCH0
ifreqs  = ifreqs[::-1]
itimes  = np.arange (nsamps) * bropt[1] * tsamp
extent  = [itimes[0], itimes[-1], ifreqs[-1], ifreqs[0]]


###############
imdict  = {'cmap':plt.cm.jet, 'aspect':'auto', 'extent':extent}
fig     = plt.figure ( figsize=(20., 15.) )
gs      = mgs.GridSpec (5, 8, figure=fig,)
ANT_LAY = np.arange (16).reshape((4,4))
MAPPER  = {}
"""
       0      1   2     3     4     5     6      7
0   | ... | _ t-cfb _ | t   | t   | t   | t   | ... |
1   | ... |           | ant | ant | ant | ant |  f  |
2   | ... |    cfb    | ant | ant | ant | ant |  f  |
3   | dmo |           | ant | ant | ant | ant |  f  |
4   | wdo |           | ant | ant | ant | ant |  f  |
"""

def fbaxer (g, ifb, ):
    if ifb >= numants:
        return
    ax = fig.add_subplot (g)
    ax.imshow (fb_avg[ifb], **imdict, )
    ax.set_title (ants[ifb])
    return ax

def ttaxer (g, ia):
    la = []
    for iia in ia:
        if iia < numants:
            la.append (iia)
    if len(la) == 0:
        return
    ax = fig.add_subplot (g)
    for iia in la:
        pp  = fb_avg[iia].mean(0)
        pp -= pp.mean()
        pp /= pp.std()
        ax.step (itimes,pp, where='mid')
    return ax

def ffaxer (g, ia):
    la = []
    for iia in ia:
        if iia < numants:
            la.append (iia)
    if len(la) == 0:
        return
    ax = fig.add_subplot (g)
    for iia in la:
        pp  = fb_avg[iia].mean(1)
        pp -= pp.mean()
        pp /= pp.std()
        ax.step (pp, ifreqs, where='mid')
    return ax

ax13 = fbaxer (gs[1,3], 0)
ax14 = fbaxer (gs[1,4], 1)
ax15 = fbaxer (gs[1,5], 2)
ax16 = fbaxer (gs[1,6], 3)

ax23 = fbaxer (gs[2,3], 4)
ax24 = fbaxer (gs[2,4], 5)
ax25 = fbaxer (gs[2,5], 6)
ax26 = fbaxer (gs[2,6], 7)

ax33 = fbaxer (gs[3,3], 8)
ax34 = fbaxer (gs[3,4], 9)
ax35 = fbaxer (gs[3,5], 10)
ax36 = fbaxer (gs[3,6], 11)

ax43 = fbaxer (gs[4,3], 12)
ax44 = fbaxer (gs[4,4], 13)
ax45 = fbaxer (gs[4,5], 14)
ax46 = fbaxer (gs[4,6], 15)

tx03 = ttaxer (gs[0,3], [0, 4,  8, 12])
tx04 = ttaxer (gs[0,4], [1, 5,  9, 13])
tx05 = ttaxer (gs[0,5], [2, 6, 10, 14])
tx06 = ttaxer (gs[0,6], [3, 7, 11, 15])

fx17 = ffaxer (gs[1,7], [0,  1,  2,  3])
fx27 = ffaxer (gs[2,7], [4,  5,  6,  7])
fx37 = ffaxer (gs[3,7], [8,  9, 10, 11])
fx47 = ffaxer (gs[4,7],[12, 13, 14, 15])

## 
## sharing
for ix in [ax14,ax15,ax16,ax23,ax24,ax25,ax36,ax33,ax34,ax35,ax36,ax43,ax44,ax45,ax46,tx03,tx04,tx05,tx06]:
    if ix:
        ax13.get_shared_x_axes().join (ax13, ix)
for ix in [ax14,ax15,ax16,ax23,ax24,ax25,ax36,ax33,ax34,ax35,ax36,ax43,ax44,ax45,ax46,fx17,fx27,fx37,fx47]:
    if ix:
        ax13.get_shared_y_axes().join (ax13, ix)

axcfb = fig.add_subplot (gs[1:, :3])
axcfb.imshow (c_fb, **imdict,)

axtcfb = fig.add_subplot (gs[0, :3])
pp = c_fb.mean(0)
pp -= pp.mean ()
pp /= pp.std()
axtcfb.step (itimes, pp, where='mid')
axtcfb.set_title ('ea99')

axcfb.get_shared_x_axes().join (axcfb, axtcfb)

##
## labels
axcfb.set_xlabel ('Time [s]')
axcfb.set_ylabel ('Freq [MHz]')


# axfcfb = fig.add_subplot (gs[1:,1])
# axfcfb.plot (c_fb.mean(1), np.arange (c_fb.shape[0]))
# axfcfb.set_xticks ([])
# axfcfb.set_yticks ([])

if False:
    axds   = fig.add_subplot (gs[3,0])
    axds.step (dd[0][0], dd[0][1])
    axds.step (dd[1][0], dd[1][1])
    axds.set_yticks([])

    axws   = fig.add_subplot (gs[4,0])
    axws.step (ww[0], ww[1])
    axws.step (ww[2], ww[3])
    axws.set_yticks([])


fig.tight_layout ()
fig.savefig ("diag0.png", dpi=300)
