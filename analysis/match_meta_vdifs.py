# imports
import os
import sys
import glob
import time
import ubjson

import tqdm

import numpy as np
import pandas as pd
import pickle as pkl

names = [
    'vlite-difx1',
    'vlite-difx2',
    'vlite-difx3',
    'vlite-difx4',
    'vlite-difx5',
    'vlite-difx6',
    'vlite-difx7',
    'vlite-difx8',
    'vlite-difx9',
    'vlite-difx10',
    'vlite-difx11',
    'vlite-difx12',
  ]

GREP = "/mnt/ssd/dumps/*.vdif"
PKL = "/home/vlite-master/surya/meta/FIRST_LOOK_{0}_FILES.pkl"

C = "{0}_{1}.list"

OFL = "{0}_meta_vdifs_df.pkl"

def searcher (epoch, e_v):
    ''' globs and searches and returns
      
      Arguments:
       epoch (list): list of UTC epoch of dump 
       e_v (dict): epochs --> vdifs dictionary

      Returns:
        ret (list) with vdif dump and None if not found
    '''
    ret  = []
    e_keys = list(e_v.keys())
    for e in epoch:
        if e in e_keys:
            ret.append (e_v[e])
    return sorted(ret)
        
def read_meta (x):
    ''' Reads meta file'''
    with open (x, "rb") as f:
        m = ubjson.load (f)
    return m

"""
We don't know if a dump was successfull or partially successful. 
We also want to delete all the zombie vdifs
"""

def ParseArgs():
    import argparse
    '''For argument parsing'''
    ap = argparse.ArgumentParser(prog='match_meta_vdifs', description='Checks if meta is full-dumped', epilog='Part of Asgard')
    add = ap.add_argument
    add('code', help = 'Code for the job, e.g. t1,t2,t3,t4', type=str, )
    add('--mprefix', help='prefix to meta file', default='/home/vlite-master/surya/meta/', dest='mprefix')
    add ('-v', help='Verbosity', action='store_true', dest='v')
    return ap.parse_args()


if __name__ == "__main__":
    args = ParseArgs ()
    META      = "{0}_metas.list".format(args.code)
    OFL       = "{0}_meta_vdifs_df.pkl".format(args.code)
    #
    metas = []
    with open (META, 'r') as f:
        metas = metas + [a.strip() for a in f.readlines()]
    #
    ## hostname [Epochs --> vdifs]
    vd_E_V   = dict() 
    for h in names:
        with open(PKL.format(h), 'rb') as f:
            xx  = pkl.load (f)
        vd_E_V[h] = {k:v for k,v in zip(xx[0], xx[1])}

    if args.v:
        for k,v in vd_E_V.items():
            print (" {0} --> {1} vdifs".format(k,len(v)))
    #
    ######################################################
    MDICT = dict()
    MARK  = {n:set() for n in names}
    for m in tqdm.tqdm (metas, desc='META', unit='m'):
        ##
        ##
        MDICT[m] = {n:[] for n in names}
        ##
        ## reading meta
        try:
            meta = read_meta (os.path.join (args.mprefix, m))
        except FileNotFoundError:
            continue
        t0   = meta["t0"]
        t1   = meta["t1"]
        it0  = int(t0)
        it1  = int(t1)
        nn   = it1 - it0 + 1
        epoch=range (it0, it1 + 1)
        MDICT[m]['len'] = nn

        for h in names:
            pkg         = searcher (epoch, vd_E_V[h])
            MDICT[m][h] += pkg
            MARK[h].update (set(pkg))
    ###############
    ## add null
    MDICT['null'] = {'len': 0}
    for h in names:
        MDICT['null'][h] = list (set(vd_E_V[h].values()).difference (MARK[h]))
    ######################################################
    mdf = pd.DataFrame (data=MDICT.values(), index=MDICT.keys())
    mdf.to_pickle (OFL)
