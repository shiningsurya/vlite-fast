#!/usr/bin/python
"""
Send fake triggers for debugging
"""

host = 'vlite-nrl'
HEIMDALL_PORT = 27555
TRIGGER_PORT = 27556

import socket
import ctypes
import struct

import time
import calendar

_DLY  = 9
DM    = 120
SN    = -15
WD    = 10
PT    = 10.0
ST    = "FAKEFAKEFAKE"
_DM_D = 4.15e-3*(0.320**-2-0.384**-2)

trigger_group = ('224.3.29.71',20003)

def send_trigger(trigger_struct):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.2)
    ttl = struct.pack('b', 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
    sock.sendto(trigger_struct,trigger_group)
    #sock.shutdown(socket.SHUT_RDWR)
    sock.close()

if __name__ == '__main__':
    now = time.time()
    t1 = now - _DLY
    t0 = t1  - (_DM_D*DM)
    print "t0=",t0
    print "t1=",t1
    t = struct.pack('ddffff128s',t0,t1,SN,DM,WD,PT,ST)
    send_trigger (t)

