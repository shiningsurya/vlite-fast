# imports
import re
import os
import sys
import glob
import time
import ubjson

from collections import defaultdict

import astropy.time as at
import astropy.units as au

import numpy as np
import pickle as pkl

GREP = "/mnt/ssd/dumps/*.vdif"
PKL = "/home/vlite-master/surya/meta/FIRST_LOOK_{0}_FILES.pkl"

############################
def ParseFile (m):
    '''parses file'''
    with open (m, 'r') as f:
        fm = [a.strip() for a in f.readlines()]
    return fm

def WriteFile (m, fl):
    '''parses file'''
    with open (m, 'w') as f:
        f.write ("\n".join(fl))

def ParseArgs():
    import argparse
    '''For argument parsing'''
    ap = argparse.ArgumentParser(prog='match_meta_dbson', description='A simple tool for matching meta with dbson+png.', epilog='Part of Asgard')
    add = ap.add_argument
    add('code', help = 'Code for the job, e.g. t1,t2,t3,t4', type=str, )
    add ('-v', help='Verbosity', action='store_true', dest='v')
    add ('--png', help='dbsonlist is png', action='store_true', dest='png')
    # done
    return ap.parse_args()

DFMT = "%Y%m%d_%H%M%S" 
get_time = lambda x : at.Time.strptime (x, DFMT)
MIN_TIME = 96 * au.hour
def resolver (ms, ls):
    """resolves many dbsons to many meta

    Assumes 1-1 relation between meta and dbson
    so returns only one dbson
    """
    ## parse dbsons
    dbsons = [d.split('/')[-1] for d in ls]
    dtimes = [get_time ('_'.join(d.split('_')[:2])) for d in dbsons] 
    ##
    ## parse metas
    metas  = [m.split('/')[-1] for m in ms]
    mtimes = [at.Time (int(m.split('_')[0]), format='unix', scale='utc') for m in metas]
    ##
    ## logic
    ## returns
    rd     = []
    rm     = []
    ##
    for i,mt in enumerate (mtimes):
        rmin   = MIN_TIME

        choose = None
        for j,dt in enumerate (dtimes):
            diff = (mt - dt)
            if diff < rmin:
                rmin   = diff
                choose = j
        if choose is not None:
            rd.append (ls[j])
            rm.append (ms[i])

    # print (meta, mtime, sep='\t')
    # print ()
    # print (dbsons, dtimes, sep='\t')
    return dict (dbson=rd, meta=rm)


if __name__ == "__main__":
    args = ParseArgs()
    META      = "{0}_metas.list".format(args.code)
    DBSON     = "{0}_dbsons.list".format(args.code)
    mDBSON    = "{0}_mdbson.list".format(args.code)
    umMETA    = "{0}_un.list".format(args.code)
    mMETA     = "{0}_mmeta.list".format(args.code)
    ###
    metas   = ParseFile (META)
    dbsons  = ParseFile (DBSON)
    ###
    mdict   = defaultdict(list)
    for m in metas:
        mt   = m[:-5]
        toks = mt.split('_')
        key  = '_'.join(toks[2:])
        mdict[key].append (m)
    ###
    ddict   = defaultdict(list)
    for d in dbsons:
        if 'ml' in d:
            dt = d[:-9]
        else:
            dt = d[:-6]
        toks = dt.split('_')
        key  = '_'.join(toks[4:])
        ddict[key].append (d)

    if args.v:
        print (f" META  parsed={len(metas)}  key'd={len(mdict.keys())}")
        print (f" DBSON parsed={len(dbsons)} key'd={len(ddict.keys())}")
        k    = list(mdict.keys())[0]
        print (f" META[{k}]  = {mdict[k]}")
        k    = list(ddict.keys())[0]
        print (f" DBSON[{k}] = {ddict[k]}")
    ###########################
    set_meta  = set(mdict.keys())
    set_dbson = set(ddict.keys())
    MKEYS     = list(set_meta.intersection (set_dbson))
    UMKEYS    = list(set_meta.difference   (set_dbson))
    UDKEYS    = list(set_dbson.difference  (set_meta))

    if args.v:
        print (f" Matched  {len(MKEYS)}")
        print (f" meta YES dbson NO  {len(UMKEYS)}")
        print (f" meta NO  dbson YES {len(UDKEYS)}")
    ###########################
    ###
    uMIST = [mdict[k][0] for k in UMKEYS]
    MLIST = []
    DLIST = []
    for m  in MKEYS:
        mm    = mdict[m]
        ll    = ddict[m]
        ##################
        rr    = resolver (mm, ll)
        ##################
        MLIST += rr['meta']
        DLIST += rr['dbson']
    ###
    if args.v:
        print (" Found {0} dbsons matched with {1} metas".format(len(DLIST), len(MLIST)))
        print (" Found {0} dbsons NOT matched ".format(len(uMIST)))

    if len(MLIST) != len(metas):
        print (" META mismatch: Read {0} metas and matched {1}".format(len(metas), len(MLIST)))
    ##
    WriteFile (mDBSON, DLIST)
    WriteFile (umMETA, uMIST)
    WriteFile (mMETA, MLIST)
