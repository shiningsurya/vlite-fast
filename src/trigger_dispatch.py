#!/usr/bin/env python2.7
from __future__ import print_function
"""
Gather candidates from heimdall, 
issue trigger
for events above threshold.
"""
# Options 
VDIF_ON = True
TEST_ON = False
SINGLE  = False
GULPSIZE= 50
MAXSIZE = 150

SNMAXMAX = 250.0

##############
import socket
import ctypes
import struct
import time
import calendar
import os
import sys
import signal
import random
import math
import datetime as dt
import astropy.coordinates as asc
import astropy.units as au
from   collections import deque,defaultdict,namedtuple

from candidate import Candidate
from cancache  import CandidateCache

# cal options
TSEP  = 10 # s of separation between dumps
LSEP  = 10 * au.arcsec
N_DAY = 10
I_DAY = 0
MONSKY  = 10 # minimum onsky 
DUMP_TIME =  5 # s of dump
# calibrators
C3_RA = asc.Angle ( (5, 21, 9.887), unit='hourangle')
C3_DE = asc.Angle ( (16, 38, 22.06), unit=au.degree)
C3    = asc.SkyCoord (C3_RA, C3_DE, frame='icrs')
C3CAND= Candidate (None, "0.00 0 0.00 0 0 0.00 0 0 0")
# logic
LRA   = 10000.0
LDEC  = 10000.0
CP    = None
CPI   = 0.0   # epoch
CPT   = 0.0   # integration time
EPOCH = dt.datetime.utcfromtimestamp (0)
LT0   = 0.0

# utc datetime format 
UTC_DT = "%Y-%m-%d-%H:%M:%S"

# Structure
# Cuts is specified for one cut.
# Cuts2 is for region cuts.
Cuts     = namedtuple('Cuts' ,['snmin','dmmin','wmax'])
Cuts2    = namedtuple('Cuts2',['snmin','snmax','dmmin','dmmax','wmin','wmax'])
# selection cuts
base = Cuts(snmin=6.0, dmmin=50, wmax=100E-3)
one  = Cuts(snmin=8.5, dmmin=50, wmax=100E-3)
two  = Cuts(snmin=6.0, dmmin=50, wmax=20E-3)
vdif = Cuts(snmin=25.0,dmmin=50, wmax=100E-3)
crab_psr = Cuts2(snmin=50.0, snmax=10000, dmmin=55.95, dmmax=57.45, wmin=1E-3, wmax=5E-3)

def COMP (cu, c):
    """Comparator"""
    c1 = c.sn >= cu.snmin
    c2 = c.dm >= cu.dmmin
    c3 = c.width < cu.wmax
    return c1 and c2 and c3

def COMP2 (cu, c):
    """Comparator"""
    c1 = cu.snmin <= c.sn <= cu.snmax
    c2 = cu.dmmin <= c.dm <= cu.dmmax
    c3 = cu.wmin  <= c.width <= cu.wmax
    return c1 and c2 and c3

# Network
vdif_group             = ('224.3.29.71',20003)
single_fbson_group     = ('224.3.29.81',20003)
coadd_fbson_group      = ('224.3.29.91',20003)
test_group             = ('224.3.29.51',20003)
host                   = 'vlite-nrl'
HEIMDALL_PORT          = 27555
TRIGGER_PORT           = 27556
# for DM delay computation
DM_DELAY               = 4.15e-3*(0.320**-2-0.384**-2)

# diag log
def utc_diag_print(x):
    '''prints dict'''
    sf = "UTC {0: <24} #={1: <5} @ UTC {2: <24}"
    ntime = time.strftime("%Y-%m-%d-%H:%M:%S", time.gmtime())
    for k,v in x.items():
        print (sf.format(k,len(v), ntime))

# set up a listening socket for heimdall server
def make_server (nmax=2):
    s = socket.socket (socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt (socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind ( ('vlite-nrl', HEIMDALL_PORT) )
    # at most nmax queued -- set to the no. of antennas
    s.listen (nmax)
    return s

def slack_push (msg):
    '''take msg and push to slack'''
    return os.system("/home/vlite-master/surya/asgard/bash/ag_slackpush \"{0}\"".format(msg))

def send_trigger(trigger_struct, mcast_group):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.2)
    ttl = struct.pack('b', 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
    sock.sendto(trigger_struct,mcast_group)
    #sock.shutdown(socket.SHUT_RDWR)
    sock.close()

if __name__ == '__main__':

    slack_push("Trigger start at {0}".format(time.ctime()))
    server_socket = make_server()
    print ("Made server")
    utc_groups = dict()
    utc_sent_triggers = defaultdict(set)
    ##
    cc = CandidateCache (GULPSIZE, MAXSIZE)
    ##
    ofile = "/home/vlite-master/surya/logs/triggerdispatch_{0:10d}.log"
    output = open(ofile.format(int(time.time())),'w+')
    try:
        while (True):
            clientsocket, address = server_socket.accept ()
            # print 'Received a connection from %s:%s.\n'%(address[0],address[1])
            #output.write('Received a connection from %s:%s.\n'%(address[0],address[1]))
            # ^ we are only receiving from the root
            payload = deque()
            while (True):
                msg = clientsocket.recv (4096)
                if len(msg) == 0:
                    break
                payload.append(msg)
            sl = ''.join (payload).split ('\n')
            lines = list(filter(lambda l: len(l) > 0,
                map(str.strip, sl)))
            #output.write('\n'.join(lines))
            # ^ no need to write *all* the candidates to file
            print ('Received {0} new candidates.'.format(len(lines)-1))

            # do I want empty entries?
            if len(lines) == 2:
                continue

            # this is file start
            toks = lines[0].split()

            # if no candidates continue
            if toks[-1] == '0':
                continue

            # NB at least right now this appears to be local time
            utc = toks[0]
            UTD = dt.datetime.strptime (utc, UTC_DT)
            CPs = (UTD - EPOCH).total_seconds ()
            TDE = time.time () - CPs

            print (toks)
            print (lines[1])

            l1s = lines[1].split ()
            RA  = float (l1s[0])
            DEC = float (l1s[1])
            if RA != LRA and DEC != LDEC:
                LRA   = RA
                LDEC  = DEC
                CPI   = CPs
                CP    = asc.SkyCoord (RA, DEC, unit='rad', frame='icrs')
                CPT   = TDE
            elif RA == LRA and DEC == LDEC:
                CPT   = CPT + TDE

            print ("Pointing at {0}{1} for {2:3.2f}s".format(CP.ra.to_string(au.hour), CP.dec.to_string(au.degree, alwayssign=1), CPT))

            # add cal dump to cc
            if CP.separation (C3) <= LSEP and I_DAY <= N_DAY and CPT >= MONSKY and LT0 >= CPI + TSEP:
                t0 = CPI + CPT
                t1 = t0 + DUMP_TIME
                t = struct.pack('ddffff128s',t0,t1,0.0,0.0,0.0,0.0,"CAL_TRIGGER")
                send_trigger(t, vdif_group)
                slack_push ("Calibrator trigger.")
                I_DAY = I_DAY + 1
                LT0   = t0

            # add candidates to cc
            for l in lines[2:]:
                xc = Candidate (None, l)
                if COMP (base, xc):
                  cc.append (xc)

            for trig in cc:
                if trig.sn > SNMAXMAX:
                    continue
                print ('TRIGGERING ON CANDIDATE:',trig)
                i0,i1 = trig.i0,trig.i1

                # send a trigger based on active_utc, i0, i1        
                dm_delay = trig.dm*DM_DELAY
                dump_offs = i0*trig.tsamp
                dump_len = 0.15 + dm_delay

                # TODO -- it would be nice to print out the latency between the candidate
                # peak time and the time the trigger is sent; it is 40-50 s with current 
                # gulp settings
                print ('Sending trigger for UTC {0} with offset {1} and length {2:.2f}.'.format(utc,dump_offs,dump_len))
                output.write ("[{3}] Triggered on DM={0:3.2f} S/N={1:2.1f} width={4:2.1f} I0={2}\n".format(trig.dm, trig.sn, i0, time.time(), 1e3*trig.width))
                s = "Trigger at UTC %s + %d"%(utc,dump_offs)
                t = time.strptime(utc,'%Y-%m-%d-%H:%M:%S')
                # add in 100ms buffer in case heimdall isn't perfectly accurate!
                pt = 0.2
                t0 = calendar.timegm(t) + dump_offs - pt
                t1 = t0 + dump_len + (30*DM_DELAY)
                print ("t0={0} t1={1}".format(t0,t1))
                t = struct.pack('ddffff128s',t0,t1,trig.sn,trig.dm,trig.width,pt,s)
                send_trigger(t, coadd_fbson_group)
                if SINGLE and random.random() <= 0.25:
                    send_trigger(t, single_fbson_group)
                if VDIF_ON and COMP (vdif, trig):
                    send_trigger(t, vdif_group)
                    slack_push("Triggered on DM={0:3.2f} S/N={1:2.1f} width={4:2.1f} UTC={2} offset={3}".format(trig.dm, trig.sn, utc, dump_offs, 1e3*trig.width))
                if VDIF_ON and COMP2 (crab_psr, trig):
                    send_trigger(t, vdif_group)
                    slack_push("Triggered on DM={0:3.2f} S/N={1:2.1f} width={4:2.1f} UTC={2} offset={3}".format(trig.dm, trig.sn, utc, dump_offs, 1e3*trig.width))
                if TEST_ON:
                    print ("TEST TEST TEST sent")
                    send_trigger(t, test_group)
    except KeyboardInterrupt:
        print ("exiting..")
    finally:
        print ("Outward CandidateCache state")
        print (cc)
        output.close ()
        server_socket.close ()
        slack_push("Trigger stop {0}".format(time.ctime()))
