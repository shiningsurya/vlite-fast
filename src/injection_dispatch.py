#!/usr/bin/python
""" Allow user to injection parameters over the socket.
"""
import numpy as np
import socket
import struct
import time

SIG = "decimate4"
NNN = 50 * 15
SLEEPTIME = 14
INJECTION_STRUCT_T = "ffc"

#define MULTI_OBSINFO_PORT 53001
inject_group = ('224.3.30.91',20004)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(0.2)
ttl = struct.pack('b', 1)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
def send_inject(inject_struct, multicast_group):
    sock.sendto(inject_struct, multicast_group)

if __name__ == '__main__':
    ofile = "/home/vlite-master/surya/injected/injections_{1}_{0:10d}.log"
    nowT = int(time.time())
    output = open(ofile.format(nowT, SIG),'w+')
    print ("Starting at T={0} with N={1}".format(nowT, NNN))
    output.write ("# Starting at T={0} with N={1}\n".format(nowT, NNN))
    ### str-format
    SF  = "Injecting amp={0:6.4e} dm={1:3.2f} wd={2:d} i={3:3.2f}"
    SFF = "Injecting amp={0} dm={1} wd={2} i={3}\n"
    #### generate 
    SN  = 1e-2 * np.random.rand (NNN,)
    #SN = np.zeros (NNN,)
    #SN += 1.0 * np.sqrt (35)
    SN += 1.0 
    ## dm is in [50, 1000] both inclusive
    DM  = 50.0 + (950.0 * np.random.rand (NNN,))
    #DM  = np.arange (60, 900.+60, NNN)
    ## wd will be in [1, 128] both inclusive.
    ## hence we go to 129
    WD  = np.random.randint (1, 32, size=NNN, dtype=np.uint8)
    #WD  = np.zeros(NNN, dtype=np.uint8)
    #WD += 8
    ####
    try:
        for i in range (NNN):
            sn = SN[i]
            dm = DM[i]
            wd = WD[i]
            ## correction
            ii = max (0, (dm - 500.)/100.)
            sn += ii*1e-3
            ##
            packed = struct.pack (INJECTION_STRUCT_T, sn,dm, bytes([wd]))
            print (SF.format(sn,dm,wd, ii))
            output.write (SFF.format(sn,dm,wd, i))
            ##
            send_inject (packed, inject_group)
            ##
            time.sleep (SLEEPTIME)
    except KeyboardInterrupt:
        print ("Exiting....")
    finally:
        sock.close()
        output.close ()


