#!/usr/bin/env python3
"""
Receive vdif trigger mcasts 
for every trigger mcast, 
bundle 
-- vliteantennas.in
-- antprop
-- trigger meta data 
into a binary json with extension `meta`
"""

## options
DELAYS_PATH = "/home/vlite-master/mtk/vliteantennas.in"
DELAYS_COLS = [
    'va_id',
    'vlant',
    'hostname',
    'hostiface',
    'clkoffset',
    'pad',
    'lofiberlen',
    'enable'
]

# directories
ANTPROP_DIR  = "/home/vlite-master/surya/meta/antprop"
METADIR = "/home/vlite-master/surya/meta"

# ip's
ANTPROP_GROUP    = '239.192.3.1'
VDIF_GROUP       = '224.3.29.71'
VDIF_PORT        = 20003
SERVER           = ('', 53053)

TIMEOUT = 5 # seconds


import os
import sys
import socket
import select
import struct
import ubjson
import time
import xml.dom.minidom
import pickle as pkl
import numpy  as np
import pandas as pd

from xml.etree import ElementTree
from xml2dict import XmlDictConfig


def slack_push (msg):
    '''take msg and push to slack'''
    return os.system("/home/vlite-master/surya/asgard/bash/ag_slackpush \"{0}\"".format(msg))

def setup_antprop_sock ():
    group = socket.inet_aton (ANTPROP_GROUP)
    sock = socket.socket (socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt (socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    mreq = struct.pack('4sL', group, socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.bind (SERVER)
    return sock

def setup_vdiftrigger_sock ():
    group = socket.inet_aton (VDIF_GROUP)
    sock = socket.socket (socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.bind ((VDIF_GROUP, VDIF_PORT))
    sock.setsockopt (socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    mreq = struct.pack('4sL', group, socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    return sock


COLS_DTYPE = [
    np.uint8,
    np.uint8,
    str,
    str,
    np.float32,
    str,
    np.float32,
    np.uint8
]
DELAYS_DTYPES = {k:v for k,v in zip(DELAYS_COLS, COLS_DTYPE)}
def get_delays ():
    """returns nant, delays dict with schema as defined in VDIF_Meta.yml """
    # read file
    ds = pd.read_table (
        DELAYS_PATH, 
        sep = " ",
        names = DELAYS_COLS,
        dtype = DELAYS_DTYPES,
        comment = "#"
    )
    # pandas magic here
    ret = ds.to_dict (orient='list')
    nant = ds['enable'].sum()
    #
    return nant, ret

def get_antprop (data):
    """Returns dict parsed from the XML"""
    tree = ElementTree.XML (data)
    return  XmlDictConfig (tree)

def test_antprop (fn):
    with open (fn, "r") as f:
        AP = f.read()
    return  get_antprop (AP)

def trigger_action (data):
    """packs and writes"""
    nant, de = get_delays ()
    t0,t1,sn,dm,width,pt,_ = struct.unpack ('ddffff128s', data)
    print ("Triggered on DM={0:3.2f} S/N={1:2.1f} width={4:2.1f} I0={2}\n".format(dm, sn, t0, time.time(), 1e3*width))
    ##
    ret               = dict ()
    ret['sn']         = sn
    ret['dm']         = dm
    ret['width']      = width
    ret['peak_time']  = pt
    ret['t0']         = t0
    ret['t1']         = t1
    #ret['nant']       = nant
    ret['delays']     = de
    ret['antprops']   = ANTPROP
    ##
    i0 = int (t0)
    d0 = int (t1 - t0)
    fn = "{0}_i{1}_dm{2:05.2f}_sn{3:05.2f}_wd{4:05.2f}.meta".format (
                i0, d0, dm, sn, width*1e3)
    with open ( os.path.join (METADIR, fn), 'wb') as f:
        ubjson.dump (ret, f)

ANTPROP_SEC = 0
ANTPROP     = None

if __name__ == "__main__":
    # load antprop
    # testpath for antprop
    ANTPROP_PATH = os.path.join (ANTPROP_DIR, "antprop_1586118970.xml")
    ANTPROP_SEC  = 1586118970
    # default to latest in antprop
    ANTPROP      = test_antprop (ANTPROP_PATH)
    # setup socks
    apsock = setup_antprop_sock ()
    vdsock = setup_vdiftrigger_sock ()
    print ("socket setup complete...")
    slack_push("Meta track start at {0}".format(time.ctime()))
    ## main select loop
    try:
        while True:
            print ("receiving....",end='')
            rrsock, _ , _ = select.select ([vdsock, apsock], [], [], TIMEOUT)
            print (len(rrsock)," ready")
            for rrs in rrsock:
                if rrs == apsock:
                    data = rrs.recv (8192)
                    try:
                        this_antprop = get_antprop (data)
                    except:
                        print ("Error in antprop parsing.")
                        print ("recv'd {0} while requested {1}".format(len(data), 8192))
                        this_antprop = None
                    else:
                        if this_antprop:
                            ANTPROP = this_antprop
                            ANTPROP_SEC = int (time.time())
                elif rrs == vdsock:
                    data = rrs.recv (4096)
                    trigger_action (data)
    except KeyboardInterrupt:
        print ("Received KeyboardInterrupt")
    finally:
        slack_push("Meta track stop at {0}".format(time.ctime()))
        # close sockets
        apsock.close ()
        vdsock.close ()
        # if antprop in memory
        # write to disk
        if ANTPROP:
            with open (os.path.join(ANTPROP_DIR, "antprop_{0}.pkl".format(ANTPROP_SEC)), 'wb') as f:
                pkl.dump (ANTPROP, f)


