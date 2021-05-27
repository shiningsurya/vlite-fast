# coding: utf-8

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

def read_list (m,):
    '''reads list file'''
    with open (m, 'r') as f:
        ls = [ a.strip() for a in f.readlines()]
    return ls

def WriteFile (m, fl):
    '''parses file'''
    with open (m, 'w') as f:
        f.write ("\n".join(sorted(fl)))

OFL = "{0}_meta_vdifs_df.pkl"

def ParseArgs():
    import argparse
    '''For argument parsing'''
    ap = argparse.ArgumentParser(prog='generate_list_vdifs', description='Generate lists of vdifs accordingly', epilog='Part of Asgard')
    add = ap.add_argument
    add ('code', help = 'Code for the job, e.g. t1,t2,t3,t4', type=str, )
    add ('-d,--dbson', help='DBSON basename list', dest='dbson', required=True)
    add ('-v', help='Verbosity', action='store_true', dest='v')
    add ('--null', help='NULL vdifs', action='store_true', dest='null')
    return ap.parse_args()


if __name__ == "__main__":
    args = ParseArgs ()
    OFL       = "{0}_meta_vdifs_df.pkl".format(args.code)
    ## these are matched
    META      = "{0}_mmeta.list".format(args.code)
    DBSON     = "{0}_mdbson.list".format(args.code)

    if args.v:
        print ("Signature    = {0}".format(args.code))
        print ("DataFrame PKL= {0}".format(OFL))

    ##
    ## read pickle
    mdf       = pd.read_pickle (OFL)
    if args.v:
        print (mdf)

    ##
    ## build poorman's bidictionary
    metas     = read_list (META)
    dbsons    = read_list (DBSON)
    M2D       = dict ()
    D2M       = dict ()
    for k,v in zip (metas, dbsons):
        M2D[k] = v
        D2M[v] = k

    ##
    ## XXX any error here implies missing data
    ## dbson
    if args.dbson:
        sel_dbson = read_list (args.dbson+".list")
        #sel_meta  = [D2M[sd] for sd in sel_dbson]
        sel_meta  = []
        for sd in sel_dbson:
            msd = D2M["/mnt/ssd/triggers/"+sd.replace('png','dbson')]
            sel_meta.append (msd)
        smdf      = mdf.loc[sel_meta]
        smdf['dbson'] = sel_dbson
        ## write smdf as lists
        for h in names:
            ff = "{db}_{h}.list".format(db=args.dbson, h=h)
            WriteFile (ff, list(sum(smdf[h], [])))

        ## write smdf as pickle
        smdf.to_pickle (args.dbson+"_mdv.pkl")
        if args.v:
            print ('Writing METAS-VDIFS-DBSON dataframe=', args.dbson+"_mdv.pkl")
    ##
    ## null action
    if args.null:
        nn    = mdf.loc['null']
        for h in names:
            ff = "null_{sig}_{h}.list".format(sig=args.code, h=h)
            WriteFile (ff, nn[h])
