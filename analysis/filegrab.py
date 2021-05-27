
# imports
import os
import sys
import glob
import ubjson

import numpy as np
import pickle as pkl

def searcher (epoch, epc, dumps):
    ''' globs and searches and returns
      
      Arguments:
       epoch (list): list of UTC epoch of dump 
       epc (list): list of available vdif dump utc epochs

      Returns:
        ret (list) with vdif dump and None if not found
    '''
    ret  = []
    for e in epoch:
        if e in epc:
            ret.append (dumps[epc.index(e)])
        #else:
        #    ret.append (None)
    return len(ret)
        
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
    add('meta', help = 'Meta file or list of metas', type=str, default=None)
    add('--mprefix', help='prefix to meta file', default='/home/vlite-master/surya/meta/', dest='mprefix')
    add ('-v', help='Verbosity', action='store_true', dest='v')
    # begin
    # aggreate to a file
    # done
    return ap.parse_args()

############################
epochs = []
vdifs  = []

available_epochs, available_dumps = get_vdifs ()

if RANK == ROOT:
    args = ParseArgs()
    with open (args.meta, 'r') as f:
        ml   =  [a.strip() for a in f.readlines()]

    for m in ml:
        meta = read_meta (os.path.join (args.mprefix, m))
        ####
        t0   = meta["t0"]
        t1   = meta["t1"]
        it0  = int(t0)
        it1  = int(t1)
        epochs.append (range (it0, it1))
    if args.v:
        print (" Length of epochs {0}".format (len(epochs)))

# search for vdif files
epochs = comm.bcast(epochs, root=ROOT)
files  = []
for e in epochs:
    files.append (searcher (e, available_epochs, available_dumps))


# gather in root
vdifs  = comm.gather (files, root=ROOT)

if RANK == ROOT:
    if args.v:
        print (" Length of files {0}".format (len(files)))
        print (" Length of vdifs {0}".format (len(vdifs)))

if RANK == ROOT:
    for i, m in enumerate (ml):
        ANY = 0
        for j,v in enumerate (vdifs):
            ANY = ANY + v[i]
        if ANY != 0:
            print (ml[i])
        
