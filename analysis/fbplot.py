# coding: utf-8
import numpy as np
import matplotlib.pyplot   as plt
import matplotlib.gridspec as mgs
import matplotlib.colors   as mc
import pickle as pkl
from skimage.measure import block_reduce
#################################################
IFILE = "./prelim0_prelim.pkl"
tsamp = 781.25E-6
NCHAN = 3072 # from bottom 
# block reduce opts
bropt = (48, 10)
#################################################
with open (IFILE, "rb") as f:
    fbs, dd, ww = pkl.load (f)
fb_avg  = block_reduce (fbs[:,-3072:,:], (1,)+bropt, func=np.mean)
c_fb    = fb_avg.mean (0)


###############
imdict  = {'cmap':plt.cm.jet, 'aspect':'auto', 'origin':'lower'}
fig     = plt.figure ( figsize=(20., 15.) )
gs      = mgs.GridSpec (5, 8, figure=fig,)

"""
       0      1   2     3     4     5     6      7
0   | ... | _ t-cfb _ | t   | t   | t   | t   | ... |
1   | ... |           | ant | ant | ant | ant |  f  |
2   | ... |    cfb    | ant | ant | ant | ant |  f  |
3   | dmo |           | ant | ant | ant | ant |  f  |
4   | wdo |           | ant | ant | ant | ant |  f  |
"""

def fbaxer (g, ifb, ):
    ax = fig.add_subplot (g)
    ax.imshow (fb_avg[ifb], **imdict)
    ax.set_xticks ([])
    ax.set_yticks ([])
    return ax

def ttaxer (g, ia):
    ax = fig.add_subplot (g)
    for iia in ia:
        pp  = fb_avg[iia].mean(0)
        pp -= pp.mean()
        ax.plot (pp)
    ax.set_xticks ([])
    ax.set_yticks ([])
    return ax

def ffaxer (g, ia):
    ax = fig.add_subplot (g)
    _,nch,_ = fb_avg.shape
    xx = np.arange (nch)
    for iia in ia:
        pp  = fb_avg[iia].mean(1)
        pp -= pp.mean()
        ax.plot (pp, xx,)
    ax.set_xticks ([])
    ax.set_yticks ([])
    return ax

fbaxer (gs[1,3], 0)
fbaxer (gs[1,4], 1)
fbaxer (gs[1,5], 2)
fbaxer (gs[1,6], 3)

fbaxer (gs[2,3], 4)
fbaxer (gs[2,4], 5)
fbaxer (gs[2,5], 6)
fbaxer (gs[2,6], 7)

fbaxer (gs[3,3], 8)
fbaxer (gs[3,4], 9)
fbaxer (gs[3,5], 10)
fbaxer (gs[3,6], 11)

fbaxer (gs[4,3], 12)
fbaxer (gs[4,4], 13)
fbaxer (gs[4,5], 14)
fbaxer (gs[4,6], 15)

ttaxer (gs[0,3], [0, 4,  8, 12])
ttaxer (gs[0,4], [1, 5,  9, 13])
ttaxer (gs[0,5], [2, 6, 10, 14])
ttaxer (gs[0,6], [3, 7, 11, 15])

ffaxer (gs[1,7], [0,  1,  2,  3])
ffaxer (gs[2,7], [4,  5,  6,  7])
ffaxer (gs[3,7], [8,  9, 10, 11])
ffaxer (gs[4,7],[12, 13, 14, 15])

axcfb = fig.add_subplot (gs[1:, 1:3])
axcfb.imshow (c_fb, **imdict)
axcfb.set_xticks ([])
axcfb.set_yticks ([])

axtcfb = fig.add_subplot (gs[0, 1:3])
axtcfb.plot (c_fb.mean(0))
axtcfb.set_xticks ([])
axtcfb.set_yticks ([])

# axfcfb = fig.add_subplot (gs[1:,1])
# axfcfb.plot (c_fb.mean(1), np.arange (c_fb.shape[0]))
# axfcfb.set_xticks ([])
# axfcfb.set_yticks ([])

axds   = fig.add_subplot (gs[3,0])
axds.step (dd[0], dd[1])
axds.step (dd[2], dd[3])
axds.set_yticks([])

axws   = fig.add_subplot (gs[4,0])
axws.step (ww[0], ww[1])
axws.step (ww[2], ww[3])
axws.set_yticks([])

fig.tight_layout ()
fig.savefig ("diag0.png", dpi=300)
