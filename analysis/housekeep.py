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

def searcher (epoch, epc, dumps):
    ''' globs and searches and returns
      
      Arguments:
       epoch (list): list of UTC epoch of dump 
       epc (list): list of available vdif dump utc epochs

      Returns:
        ret (list) with vdif dump and None if not found
    '''
    ret  = []
    for e,d in zip (epc, dumps):
        if e in epoch:
            ret.append (d)
        #else:
        #    ret.append (None)
    return sorted(ret)
        
def read_meta (x):
    ''' Reads meta file'''
    with open (x, "rb") as f:
        m = ubjson.load (f)
    return m

def ParseArgs():
    import argparse
    '''For argument parsing'''
    ap = argparse.ArgumentParser(prog='filegrab', description='A simple tool for gathering vdifs-paths in one place.', epilog='Part of Asgard')
    add = ap.add_argument
    add('meta', help = 'Meta file', type=str, default=None)
    add('--mprefix', help='prefix to meta file', default='/home/vlite-master/surya/meta/', dest='mprefix')
    add('-d,--delete', help='Delete vdifs related to meta', action='store_true', dest='delvdif')
    add('-c,--check', help='Delete failed vdifs related to meta', action='store_true', dest='checkvdif')
    add('-p,--pickle', help='Use pickled glob results', action='store_true', dest='pickle')
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
DELETE   = False

if RANK == ROOT:
    args = ParseArgs()
    PICKLE  = args.pickle
    VERBOSE = args.v
    CHECK   = args.checkvdif
    DELETE  = args.delvdif
    # warn if delete
    if DELETE:
        print (" !!! Deleting !!!")
    meta = read_meta (os.path.join (args.mprefix, args.meta))
    if args.v:
        print (" META = {0}".format(args.meta))
    ####
    t0   = meta["t0"]
    t1   = meta["t1"]
    it0  = int(t0)
    it1  = int(t1)
    nn   = it1 - it0
    epoch=range (it0, it1)
    if args.v:
        print (" Length of epoch {0}".format (len(epoch)))

# flags
PICKLE  = comm.bcast (PICKLE, root=ROOT)
VERBOSE = comm.bcast (VERBOSE, root=ROOT)
CHECK   = comm.bcast (CHECK, root=ROOT)
DELETE  = comm.bcast (DELETE, root=ROOT)


# glob files
if PICKLE:
    with open (FPKL, "rb") as f:
        available_epochs, available_dumps = pkl.load (f)
else:
    available_epochs, available_dumps = get_vdifs ()

    with open (FPKL, "wb") as f:
        pkl.dump ([available_epochs, available_dumps], f)

# search for vdif files
epoch = comm.bcast(epoch, root=ROOT)
files = searcher (epoch, available_epochs, available_dumps)
if VERBOSE:
    print (" {0} --> {1}".format(HOSTNAME, files))

# gather in root
nvdifs = comm.reduce (len(files), root=ROOT)
#vdifs  = comm.gather (files, root=ROOT)

# sanity check
SIZES = []
for f in files:
    osr = os.stat (f)
    SIZES.append (osr.st_size)

if CHECK:
    if len(files) != 0: 
        uSize = np.unique (SIZES)
        if 0 in uSize:
            print (" Found files with size 0 at {}".format(HOSTNAME))
            if VERBOSE:
                print (" delete = ", files)
            for f in files:
                delete_file (f)

if DELETE:
    for f in files:
        if VERBOSE:
            print (" delete = ", files)
        delete_file (f)

if RANK == ROOT:
    nfac = nvdifs // nn
    if VERBOSE:
        print (" # of vdifs {0} | # of vdif sets {1}".format(nvdifs, nfac))

