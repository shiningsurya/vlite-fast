#!/usr/bin/env python3
"""
Probe an Mcast group
"""

# ip's
GROUP         = ('224.3.30.91',20004)
inject_group = ('224.3.30.91',20004)
SERVER        = ('', 53011)
TIMEOUT = 1 # seconds
SLEEPTIME = 10
INJECTION_STRUCT_T = "ffc"


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

def setup_msock ():
    group = socket.inet_aton (inject_group[0])
    sock = socket.socket (socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt (socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    mreq = struct.pack('4sL', group, socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.bind (inject_group)
    return sock

if __name__ == "__main__":
    # setup socks
    msock = setup_msock ()
    SF  = "Injecting amp={0:5.2f} dm={1:3.2f} wd={2:d}"
    print ("socket setup complete...")
    ## main select loop
    try:
        print ("waiting....")
        while True:
            rrsock, _ , _ = select.select ([msock], [], [], TIMEOUT)
            for rrs in rrsock:
                if rrs == msock:
                    data,_ = rrs.recvfrom (9)
                    ramp, rdm, rwd = struct.unpack (INJECTION_STRUCT_T, data)
                    wd = int.from_bytes (rwd, 'little', signed=False)
                    print (SF.format(ramp, rdm, wd))
            time.sleep (SLEEPTIME)
    except KeyboardInterrupt:
        print ("Received KeyboardInterrupt")
    finally:
        # close socket
        msock.close ()

