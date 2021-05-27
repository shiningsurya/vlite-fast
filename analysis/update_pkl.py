ROOT = 0
# imports
import os
import sys
import glob
import time
import ubjson

import numpy as np
import pickle as pkl

from mpi4py import MPI as mp
comm = mp.COMM_WORLD
SIZE = comm.Get_size()
RANK = comm.Get_rank()

GREP = "/mnt/ssd/dumps/*.vdif"

PKL = "/home/vlite-master/surya/meta/FIRST_LOOK_{0}_FILES.pkl"

#DRY=True
DRY=False

def delete_file (f) :
    ''' delete the file f'''
    cmd = "rm -f {}".format(f)
    if DRY:
        print (cmd)
    else:
        os.system (cmd)

def get_vdifs ():
    ''' globs, parses and presents
    '''
    dumps  = glob.glob (GREP)
    epc    = []
    for d in dumps:
        bname = os.path.basename (d)
        toks  = bname.split ('_')[-1]
        epc.append (int(toks[:-5]))
    #
    return epc,dumps
        
def ParseArgs():
    import argparse
    '''For argument parsing'''
    ap = argparse.ArgumentParser(prog='updates_pkls', description='A simple tool for gathering vdifs-paths in one place.', epilog='Part of Asgard')
    add = ap.add_argument
    add('-c,--check', help='Delete failed vdifs related to meta', action='store_true', dest='checkvdif')
    add ('-v', help='Verbosity', action='store_true', dest='v')
    # done
    return ap.parse_args()

############################
HOSTNAME = os.uname()[1]
meta  = None
epoch = None
vdifs = []

FPKL = PKL.format(HOSTNAME)

# flags
PICKLE   = False
VERBOSE  = False
CHECK    = False

if RANK == ROOT:
    args = ParseArgs()
    VERBOSE = args.v
    CHECK   = args.checkvdif

# flags
VERBOSE = comm.bcast (VERBOSE, root=ROOT)
CHECK   = comm.bcast (CHECK, root=ROOT)

available_epochs, available_dumps = get_vdifs ()

with open (FPKL, "wb") as f:
    pkl.dump ([available_epochs, available_dumps], f)


# gather in root
hn     = comm.gather (HOSTNAME, root=ROOT)
nvdifs = comm.gather (len(available_epochs), root=ROOT)
#vdifs  = comm.gather (files, root=ROOT)

# sanity check
SIZES = []
DELS  = []
for f in available_dumps:
    osr = os.stat (f)
    SIZES.append (osr.st_size)
    if osr.st_size == 0:
        DELS.append (f)

if CHECK:
    if len(DELS) != 0: 
        if VERBOSE:
            print (" delete = ", DELS)
        for f in DELS:
            delete_file (f)

if RANK == ROOT:
    if VERBOSE:
        for h,n in zip(hn, nvdifs):
            print (" {0} -->  {1}".format(h,n))

