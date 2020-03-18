#!/usr/bin/python
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
from   collections import deque,defaultdict,namedtuple

from candidate import Candidate
from cancache  import CandidateCache


# Structure
# Cuts is specified for one cut.
# Cuts2 is for region cuts.
Cuts     = namedtuple('Cuts' ,['snmin','dmmin','wmax'])
Cuts2    = namedtuple('Cuts2',['snmin','snmax','dmmin','dmmax','wmin','wmax'])
# selection cuts
one  = Cuts(snmin=8.5, dmmin=50, wmax=100E-3)
two  = Cuts(snmin=6.0, dmmin=50, wmax=20E-3)
vdif = Cuts(snmin=20.0,dmmin=00, wmax=100E-3)
crab_psr = Cuts2(snmin=15.0, snmax=10000, dmmin=55.95, dmmax=57.45, wmin=1E-3, wmax=5E-3)

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
test_group             = ('224.3.27.81',20003)
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
        print sf.format(k,len(v), ntime)

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
    print "Made server"
    utc_groups = dict()
    utc_sent_triggers = defaultdict(set)
    ##
    cc = CandidateCache (GULPSIZE, MAXSIZE)
    ##
    output = file('/home/vlite-master/surya/logs/tc.asc','a')
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
            lines = filter(lambda l: len(l) > 0,
                map(str.strip,''.join(payload).split('\n')))
            #output.write('\n'.join(lines))
            # ^ no need to write *all* the candidates to file
            print 'Received %d new candidates.'%(len(lines)-1)

            # do I want empty entries?
            if len(lines) == 2:
                continue

            # this is file start
            toks = lines[0].split()
            # NB at least right now this appears to be local time
            utc = toks[0]

            # add candidates to cc
            for l in lines[2:]:
                xc = Candidate (None, l)
                rone = COMP (one, xc)
                rtwo = COMP (two, xc)
                rvdi = COMP (vdif, xc)
                rpsr = COMP2 (crab_psr, xc)
                if rone or rtwo or rvdi or rpsr:
                  cc.append (xc)

            for trig in cc:
                print 'TRIGGERING ON CANDIDATE:',trig
                i0,i1 = trig.i0,trig.i1

                # send a trigger based on active_utc, i0, i1        
                dm_delay = trig.dm*DM_DELAY
                dump_offs = i0*trig.tsamp
                dump_len = (i1-i0)*trig.tsamp + dm_delay

                # TODO -- it would be nice to print out the latency between the candidate
                # peak time and the time the trigger is sent; it is 40-50 s with current 
                # gulp settings
                print 'Sending trigger for UTC %s with offset %d and length %.2f.'%(utc,dump_offs,dump_len)
                slack_push("Triggered on DM={0:3.2f} S/N={1:2.1f} width={4:2.1f} UTC={2} offset={3}".format(trig.dm, trig.sn, utc, dump_offs, 1e3*trig.width))
                s = "Trigger at UTC %s + %d"%(utc,dump_offs)
                t = time.strptime(utc,'%Y-%m-%d-%H:%M:%S')
                # add in 100ms buffer in case heimdall isn't perfectly accurate!
                t0 = calendar.timegm(t) + dump_offs - (1.5*dm_delay)
                t1 = t0 + dump_len + (1.5*dm_delay)
                print 't0=',t0,' t1=',t1
                t = struct.pack('ddffff128s',t0,t1,trig.sn,trig.dm,trig.width,trig.peak_time,s)
                send_trigger(t, coadd_fbson_group)
                if SINGLE and random.random() <= 0.25:
                    send_trigger(t, single_fbson_group)
                if VDIF_ON and COMP (vdif, trig):
                    send_trigger(t, vdif_group)
                if VDIF_ON and COMP2 (crab_psr, trig):
                    send_trigger(t, vdif_group)
                if TEST_ON:
                    send_trigger(t, test_group)
    except KeyboardInterrupt:
        print ("exiting..")
    finally:
        print ("Outward CandidateCache state")
        print (cc)
        output.close ()
        server_socket.close ()
        slack_push("Trigger stop {0}".format(time.ctime()))
