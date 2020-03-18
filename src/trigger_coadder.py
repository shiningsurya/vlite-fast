#!/usr/bin/python
"""
Gather candidates from heimdall, coincidence them, and issue trigger
for events above threshold.
"""

host = 'vlite-nrl'
HEIMDALL_PORT = 27555
TRIGGER_PORT = 27556

import socket
from collections import deque,defaultdict
from candidate import Candidate,coincidence
import ctypes
import struct

import time
import calendar

import os
import sys
import signal
import random

# combine events overlapping (multiple triggers) provided their total
# length doesn't exceed MAX_DUMP s
MAX_DUMP = 20
DM_DELAY = 4.15e-3*(0.320**-2-0.384**-2)
# one
SNMIN1 = 8.5
DMMIN1= 100
WMAX1  = 100E-3
# two
SNMIN2 = 6.0
DMMIN2= 100
WMAX2  = 20E-3
# options 
VDIF_ON = True
VDIF_SN = 25.0
# VDIFSM
VDIF_DMMIN=55.95
VDIF_DMMAX=57.45
VDIF_SNMIN=15
TEST_ON = False
# mcast groups
vdif_group             = ('224.3.29.71',20003)
single_fbson_group     = ('224.3.29.81',20003)
coadd_fbson_group      = ('224.3.29.91',20003)
test_group             = ('224.3.27.81',20003)

# diag log
def utc_diag_print(x):
    '''prints dict'''
    sf = "UTC {0: <24} #={1: <5} @ UTC {2: <24}"
    ntime = time.strftime("%Y-%m-%d-%H:%M:%S", time.gmtime())
    for k,v in x.items():
        print sf.format(k,len(v), ntime)

# set up a listening socket for heimdall server

def make_server (nmax=18):
    s = socket.socket (socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt (socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind ( ('vlite-nrl', HEIMDALL_PORT) )
    # at most nmax queued -- set to the no. of antennas
    s.listen (nmax)
    return s

def trigger(all_cands):
    """ Go through beam and determine if there is an event
    satisfying the trigger criteria.
    """
    triggers = []
    we = [1e100,-1e100]
    good_count = 0
    for cand in all_cands:
        if cand.width < we[0]:
            we[0] = cand.width
        if cand.width > we[1]:
            we[1] = cand.width
        c1 = cand.width < WMAX1
        c2 = cand.dm    > DMMIN1
        c3 = cand.sn    >= SNMIN1
        d1 = cand.width < WMAX2
        d2 = cand.dm    > DMMIN2
        d3 = cand.sn    >= SNMIN2
        e1 = cand.dm    > 26.2
        e2 = cand.dm    < 27.2
        e3 = cand.sn    > 8
        e4 = cand.width < WMAX2
        c0 = c1 and c2 and c3
        d0 = d1 and d2 and d3
        e0 = e1 and e2 and e3 and e4
        good_count += c0
        good_count += d0
        good_count += e0
        # send logic
        if (c0 or d0 or e0):
            triggers.append(cand)
    print 'min/max width: ',we[0],we[1]
    print 'len(all_cands)=%d'%(len(all_cands))
    print 'good_count = %d'%(good_count)
    print 'len(triggers)=%d'%(len(triggers))

    return triggers


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
    output = file('/home/vlite-master/surya/logs/tc.asc','a')
    try:
        while (True):
            clientsocket, address = server_socket.accept ()
            print 'Received a connection from %s:%s.\n'%(address[0],address[1])
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

            # check UTC for start of new observation
            if (utc not in utc_groups.keys()):
                utc_groups[utc] = deque()

            cgroups = utc_groups[utc]

            # add in Candidate objects to the appropriate beam
            cgroups.extend((Candidate(None,l) for l in lines[2:]))

            # get triggers
            sent_triggers = utc_sent_triggers[utc]
            current_triggers = trigger(cgroups)
            new_triggers = set(current_triggers).difference(sent_triggers)
            print 'new_triggers len: ',len(new_triggers) # DEBUG

            if len(new_triggers) == 0:
                continue

            for trig in new_triggers:
                print 'TRIGGERING ON CANDIDATE:',trig
                i0,i1 = trig.i0,trig.i1

                # send a trigger based on active_utc, i0, i1        
                dm_delay = trig.dm*DM_DELAY
                dump_offs = i0*trig.tsamp
                dump_len = 0.15 + dm_delay

                # TODO -- it would be nice to print out the latency between the candidate
                # peak time and the time the trigger is sent; it is 40-50 s with current 
                # gulp settings
                print 'Sending trigger for UTC %s with offset %d and length %.2f.'%(utc,dump_offs,dump_len)
                slack_push("Triggered on DM={0:3.2f} S/N={1:2.1f} width={4:2.1f} UTC={2} offset={3}".format(trig.dm, trig.sn, utc, dump_offs, 1e3*trig.width))
                s = "Trigger at UTC %s + %d"%(utc,dump_offs)
                t = time.strptime(utc,'%Y-%m-%d-%H:%M:%S')
                # add in 100ms buffer in case heimdall isn't perfectly accurate!
                pt = 0.2
                t0 = calendar.timegm(t) + dump_offs - pt
                t1 = t0 + dump_len + (30*DM_DELAY)
                print 't0=',t0,' t1=',t1
                t = struct.pack('ddffff128s',t0,t1,trig.sn,trig.dm,trig.width,pt,s)
                send_trigger(t, coadd_fbson_group)
                if random.random() <= 0.1:
                    send_trigger(t, single_fbson_group)
                if VDIF_ON and trig.sn >= VDIF_SN:
                    send_trigger(t, vdif_group)
                elif VDIF_DMMAX >= trig.dm and   \
                     VDIF_DMMIN <= trig.dm and   \
                     VDIF_SNMIN >= trig.sn:
                    send_trigger(t, vdif_group)
                if TEST_ON:
                    send_trigger(t, test_group)
                sent_triggers.add(trig)
    except KeyboardInterrupt:
        print ("exiting..")
    finally:
        output.close ()
        server_socket.close ()
        slack_push("Trigger stop {0}".format(time.ctime()))
