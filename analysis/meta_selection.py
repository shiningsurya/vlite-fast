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

META_DIR = "/mnt/ssd/triggers/"
#META_DIR = "/home/vlite-master/surya/meta/"

OFL = "{code}_dbson_selection_df.pkl"

def read_dbson(x):
    ''' Reads dbson file'''
    m = None
    try:
        with open (os.path.join(META_DIR, x), "rb") as f:
            m = ubjson.load (f)
    except:
        print (" recording exception with dbson=",x)
    return m

def ParseArgs():
    import argparse
    '''For argument parsing'''
    ap = argparse.ArgumentParser(prog='dbson_select', description='A simple tool for gathering useful info about dbson.', epilog='Part of Asgard')
    add = ap.add_argument
    add('code', help = 'Code for the job, e.g. t1,t2,t3,t4', type=str, )
    add('-s,--sig', help='Signature', default='t3_dm26', dest='sig')
    add ('-v', help='Verbosity', action='store_true', dest='v')
    return ap.parse_args()


if __name__ == "__main__":
    args = ParseArgs ()
    ###
    mDBSON    = "{0}_mdbson.list".format(args.code)
    df   = pd.read_csv (mDBSON, names=['dbson'])
    ###
    df['ra']        = 0.0
    df['dec']       = 0.0
    df['dm']        = 0.0
    df['sn']        = 0.0
    df['peak_time'] = 0.0
    ###
    for idx in tqdm.tqdm (df.index, desc='DBSON', unit='dbson'):
        dd = read_dbson (df.dbson.loc[idx])
        if dd is None:
            continue
        df.sn.loc[idx]  = dd['sn']
        df.dm.loc[idx]  = dd['dm']
        df.ra.loc[idx]  = dd['parameters']['ra']
        df.dec.loc[idx] = dd['parameters']['dec']
        df.peak_time.loc[idx] = dd['indices']['i0'] - dd['indices']['epoch']
    ###
    print (df.head())
    df.to_pickle (OFL.format(code=args.code))
