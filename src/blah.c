
  size_t size_dump_times=300, num_dump_times=0 ,idx_dump_times=0;
  time_t dump_times[size_dump_times];
      time_t* dump_times, int max_dump_times,
      char** bufs_to_write)
    }
    for (int i=0; i<max_triggers; ++i)
      if (trigger_queue[i] == NULL) break;
        
        // check to see if there is a previous dump ongoing
        // TODO -- want to see whether should be so conservative.  E.g., in a recording
        // mode with a trigger every 1s, we might want some slop to have overlapping thread
        // launches
        int ready_to_write = 1;

        for (int iio=0; iio < nthreadios; ++iio)
        {
          if (threadios[iio]->status != 0)
          {
            // previous dump still happening
            multilog (log, LOG_INFO,
                "Previous I/O still ongoing, skipping this CMD_EVENT.");
            ready_to_write = 0;
            break;
          }
          if (threadios[iio]->status > 0)
          {
            // some problem with previous dump; skip new dumps for now
            multilog (log, LOG_ERR,
                "Previous I/O errored, skipping this CMD_EVENT.");
            ready_to_write = 0;
            break;
          }
        }

        if (!ready_to_write)
          break;

        multilog (log, LOG_INFO, "Launching threads for buffer dump.\n");

        // free previous structs
        for (int iio=0; iio < nthreadios; ++iio)
          if (threadios[iio])
            free (threadios[iio]);
        if (threadios)
          free (threadios); threadios = NULL;
        nthreadios = 0;

        // determine which buffers to write
        ipcbuf_t* buf = (ipcbuf_t *) hdu->data_block;; 
        char** buffer = buf->buffer;
        int nbufs = ipcbuf_get_nbufs(buf);
        int bufsz = ipcbuf_get_bufsz(buf);

        // for testing, pretend trigger time is current time -14s
        // with a 20s transient
        time_t trigger_time = time (NULL)-1;
        //double trigger_len = 20;
        time_t tmin = trigger_time - 1;
        //time_t tmax = trigger_time + trigger_len + 8;
        time_t tmax = trigger_time;
        printf ("tmin = %ld tmax = %ld\n",tmin,tmax);

        // check to see whether we have exceeded the dump limit; if we have
        // a triggered dump, ignore the limit
        if (do_dump==1)
        {
          int dumps_in_window = 0;
          for (int idump=0; idump < num_dump_times; ++idump)
          {
            dumps_in_window += abs (trigger_time-dump_times[idump]) < dump_window;
          } 
          multilog (log, LOG_INFO, "Found %d seconds of dumps in the window.\n",
              dumps_in_window);
          if (dumps_in_window > max_dump_window)
          {
            multilog (log, LOG_INFO, "Too many dumps, skipping this trigger.\n");
            continue;
          }
        }

        for (int ibuf=0; ibuf < nbufs; ++ibuf)
        {
          // get time for frame at start of buffer
          vdif_header* vdhdr = (vdif_header*) buffer[ibuf];
          time_t utc_seconds = vdif_to_unixepoch (vdhdr);

          // TMP
          //
          /*
          char dada_utc[32];
          struct tm utc_time;
          gmtime_r (&utc_seconds, &utc_time);
          strftime (dada_utc, 64, DADA_TIMESTR, &utc_time);
          if (ibuf==0)
            fprintVDIFHeader(stderr, vdhdr, VDIFHeaderPrintLevelColumns);
          multilog (log, LOG_INFO, "buffer UTC %s\n", dada_utc);
          printf ("utc_seconds = %ld\n",utc_seconds);
          fprintVDIFHeader (stderr, vdhdr, VDIFHeaderPrintLevelShort);
          */
          //
          // end TMP

          // first condition -- within trigger time (TODO -- if we want
          // a voltage recording mode, could override this)
          int cond1 = (utc_seconds >= tmin) && (utc_seconds <= tmax);

          // second condition -- see if we have already dumped it
          int cond2 = 1;
          for (int idump=0; idump < num_dump_times; ++idump)
          {
            if (utc_seconds == dump_times[idump])
            {
              cond2 = 0;
              break;
            }
          }
          if (cond1 && cond2)
          {
            // dump this buffer
            bufs_to_write[nthreadios++] = buffer[ibuf];
            multilog (log, LOG_INFO, "dumping buffer %02d\n", ibuf);
            num_dump_times += num_dump_times < size_dump_times;
            if (idx_dump_times == size_dump_times)
              idx_dump_times = 0;
            dump_times[idx_dump_times++] = utc_seconds;
            voltage_packets_written += 2*25600;
          }  
        } // end loop over buffers

        // TODO -- replace this file name with appropriate format
        currt = time (NULL);
        gmtime_r (&currt,&tmpt);
        strftime (
            currt_string,sizeof(currt_string), "%Y%m%d_%H%M%S", &tmpt);
        *(currt_string+15) = 0;
        multilog (log, LOG_INFO, "GM time is %s\n", currt_string);

        // make new threadio_ts and pthreads
        threadios = malloc (sizeof (threadio_t*) * nthreadios);
        for (int iio=0; iio < nthreadios; ++iio)
        {
          threadios[iio] = malloc (sizeof (threadio_t));
          threadios[iio]->status = -1;
          threadios[iio]->buf = bufs_to_write[iio];
          threadios[iio]->bufsz = bufsz;
          threadios[iio]->ms_delay = iio > 1?iio*500:0;
          int sid = getVDIFStationID ((vdif_header*)bufs_to_write[iio]);
          snprintf (threadios[iio]->fname, 255,
              "%s/%s_ea%02d_buff%02d.vdif",
              EVENTDIR,currt_string,sid,iio);
          if (pthread_create (&threadios[iio]->tid, NULL, &buffer_dump, 
              (void*)threadios[iio]) != 0)
              multilog (log, LOG_ERR, "pthread_create failed\n");
          if (pthread_detach (threadios[iio]->tid) != 0)
              multilog (log, LOG_ERR, "pthread_detach failed\n");
        }

        // write out the observation document for this dump
        char dump_od_fname[256];
        snprintf (dump_od_fname, 255,
            "/home/vlite-master/mtk/events/%s.od", currt_string);
        FILE *dump_od_fp = fopen (dump_od_fname, "w");
        fprint_observation_document(dump_od_fp, &od);
        fclose (dump_od_fp);

        // TODO -- want to transfer antenna properties and write them out

        // and we're done
        multilog (log, LOG_INFO,
            "Launched %d threads for buffer dump.\n", nthreadios);

      } // end do_dump logic
    
    //if state is STARTED, poll the command listening socket and the VDIF raw data socket
    if (state == STATE_STARTED) {

      // this construct adds the two sockets to the FDs and then blocks
      // until input is available on one or the other; multiplexing
      FD_ZERO (&readfds);
      FD_SET (mc_control_sock, &readfds);
      FD_SET (mc_trigger_sock, &readfds);
      FD_SET (raw.svc, &readfds);
      if (select (maxsock+1,&readfds,NULL,NULL,&tv_500mus) < 0)
      {
        multilog (log, LOG_ERR, "[STATE_STARTED] Error calling select.");
        fflush (logfile_fp);
        exit (EXIT_FAILURE);
      }
      
      //if input is waiting on listening socket, read it
      if (FD_ISSET (mc_control_sock,&readfds)) {
        cmd = check_for_cmd (mc_control_sock, mc_control_buf, 32, logfile_fp);
      }

      // note to future self -- dump_time is not actually used below, I think
      // it's mostly just a shorthand for a triggered dump, so refactor to
      // make it more apparent!

      // check if we are enough packets removed from an automatic dump
      // request and, if so, execute it; wait 10s
      int do_dump = (dump_time && (packets_written > 25600*20));
      if (do_dump)
        dump_time = 0;

      // only trigger a "write voltage" dump every 10 seconds for overhead
      if (write_voltages && (packets_written > 25600*16) && ((packets_written-voltage_packet_counter)>(25600*4)))
      {
        do_dump = 1;
        voltage_packet_counter = packets_written;
        multilog (log, LOG_INFO, "Issuing a new 10-s dump for %s.\n",od.name);
      }


      if (cmd == CMD_EVENT)
      {
        do_dump += 1; // will be 1 for CMD_EVENT or 2 for triggered dump
        cmd = CMD_NONE;
        // CMD_EVENT overrides dump_time
        dump_time = 0;
      }

      if (do_dump)
      //if (0) // TMP -- disable dumps
      {
        
        // dump voltages to file
        
        // check to see if there is a previous dump ongoing
        int ready_to_write = 1;

        for (int iio=0; iio < nthreadios; ++iio)
        {
          if (threadios[iio]->status != 0)
          {
            // previous dump still happening
            multilog (log, LOG_INFO,
                "Previous I/O still ongoing, skipping this CMD_EVENT.");
            ready_to_write = 0;
            break;
          }
          if (threadios[iio]->status > 0)
          {
            // some problem with previous dump; skip new dumps for now
            multilog (log, LOG_ERR,
                "Previous I/O errored, skipping this CMD_EVENT.");
            ready_to_write = 0;
            break;
          }
        }

        if (!ready_to_write)
          continue;

        multilog (log, LOG_INFO, "Launching threads for buffer dump.\n");

        // free previous structs
        for (int iio=0; iio < nthreadios; ++iio)
          if (threadios[iio])
            free (threadios[iio]);
        if (threadios)
          free (threadios); threadios = NULL;
        nthreadios = 0;

        // determine which buffers to write
        ipcbuf_t* buf = (ipcbuf_t *) hdu->data_block;; 
        char** buffer = buf->buffer;
        int nbufs = ipcbuf_get_nbufs(buf);
        int bufsz = ipcbuf_get_bufsz(buf);

        // for testing, pretend trigger time is current time -14s
        // with a 20s transient
        time_t trigger_time = time (NULL)-1;
        //double trigger_len = 20;
        time_t tmin = trigger_time - 1;
        //time_t tmax = trigger_time + trigger_len + 8;
        time_t tmax = trigger_time;
        printf ("tmin = %ld tmax = %ld\n",tmin,tmax);
        char* bufs_to_write[32] = {NULL};

        // check to see whether we have exceeded the dump limit; if we have
        // a triggered dump, ignore the limit
        if (do_dump==1)
        {
          int dumps_in_window = 0;
          for (int idump=0; idump < num_dump_times; ++idump)
          {
            dumps_in_window += abs (trigger_time-dump_times[idump]) < dump_window;
          } 
          multilog (log, LOG_INFO, "Found %d seconds of dumps in the window.\n",
              dumps_in_window);
          if (dumps_in_window > max_dump_window)
          {
            multilog (log, LOG_INFO, "Too many dumps, skipping this trigger.\n");
            continue;
          }
        }

        for (int ibuf=0; ibuf < nbufs; ++ibuf)
        {
          // get time for frame at start of buffer
          vdif_header* vdhdr = (vdif_header*) buffer[ibuf];
          time_t utc_seconds = vdif_to_unixepoch (vdhdr);

          // TMP
          //
          /*
          char dada_utc[32];
          struct tm utc_time;
          gmtime_r (&utc_seconds, &utc_time);
          strftime (dada_utc, 64, DADA_TIMESTR, &utc_time);
          if (ibuf==0)
            fprintVDIFHeader(stderr, vdhdr, VDIFHeaderPrintLevelColumns);
          multilog (log, LOG_INFO, "buffer UTC %s\n", dada_utc);
          printf ("utc_seconds = %ld\n",utc_seconds);
          fprintVDIFHeader (stderr, vdhdr, VDIFHeaderPrintLevelShort);
          */
          //
          // end TMP

          // first condition -- within trigger time (TODO -- if we want
          // a voltage recording mode, could override this)
          int cond1 = (utc_seconds >= tmin) && (utc_seconds <= tmax);

          // second condition -- see if we have already dumped it
          int cond2 = 1;
          for (int idump=0; idump < num_dump_times; ++idump)
          {
            if (utc_seconds == dump_times[idump])
            {
              cond2 = 0;
              break;
            }
          }
          if (cond1 && cond2)
          {
            // dump this buffer
            bufs_to_write[nthreadios++] = buffer[ibuf];
            multilog (log, LOG_INFO, "dumping buffer %02d\n", ibuf);
            num_dump_times += num_dump_times < size_dump_times;
            if (idx_dump_times == size_dump_times)
              idx_dump_times = 0;
            dump_times[idx_dump_times++] = utc_seconds;
            voltage_packets_written += 2*25600;
          }  
        } // end loop over buffers

        // TODO -- replace this file name with appropriate format
        currt = time (NULL);
        gmtime_r (&currt,&tmpt);
        strftime (
            currt_string,sizeof(currt_string), "%Y%m%d_%H%M%S", &tmpt);
        *(currt_string+15) = 0;
        multilog (log, LOG_INFO, "GM time is %s\n", currt_string);

        // make new threadio_ts and pthreads
        threadios = malloc (sizeof (threadio_t*) * nthreadios);
        for (int iio=0; iio < nthreadios; ++iio)
        {
          threadios[iio] = malloc (sizeof (threadio_t));
          threadios[iio]->status = -1;
          threadios[iio]->buf = bufs_to_write[iio];
          threadios[iio]->bufsz = bufsz;
          threadios[iio]->ms_delay = iio > 1?iio*500:0;
          int sid = getVDIFStationID ((vdif_header*)bufs_to_write[iio]);
          snprintf (threadios[iio]->fname, 255,
              "%s/%s_ea%02d_buff%02d.vdif",
              EVENTDIR,currt_string,sid,iio);
          if (pthread_create (&threadios[iio]->tid, NULL, &buffer_dump, 
              (void*)threadios[iio]) != 0)
              multilog (log, LOG_ERR, "pthread_create failed\n");
          if (pthread_detach (threadios[iio]->tid) != 0)
              multilog (log, LOG_ERR, "pthread_detach failed\n");
        }

        // write out the observation document for this dump
        char dump_od_fname[256];
        snprintf (dump_od_fname, 255,
            "/home/vlite-master/mtk/events/%s.od", currt_string);
        FILE *dump_od_fp = fopen (dump_od_fname, "w");
        fprint_observation_document(dump_od_fp, &od);
        fclose (dump_od_fp);

        // TODO -- want to transfer antenna properties and write them out

        // and we're done
        multilog (log, LOG_INFO,
            "Launched %d threads for buffer dump.\n", nthreadios);

      } // end do_dump logic
      
      //CMD_STOP --> change state to STOPPED, close data block
      else if (cmd == CMD_STOP) {
        state = STATE_STOPPED;
        skip_frames = 0;
        if (dada_hdu_unlock_write (hdu) < 0) {
          multilog (log, LOG_ERR,
              "[STATE_STARTED->STOP]: unable to unlock psrdada HDU, exiting\n");
          exit_status = EXIT_FAILURE;
          break;
        }
        multilog (log, LOG_INFO, 
            "[STATE_STARTED->STOP] Wrote %d packets to psrdada buffer.\n",packets_written);
        packets_written = 0;
        write_voltages = 0;
        cmd = CMD_NONE;
        fflush (logfile_fp);
        continue;
      }

      //CMD_QUIT --> close data block, shutdown listening socket, return
      else if (cmd == CMD_QUIT) {
        multilog (log, LOG_INFO,
            "[STATE_STARTED->QUIT], exiting.\n");
        multilog (log, LOG_INFO,
            "dada_hdu_unlock_write result = %d.\n",
            dada_hdu_unlock_write (hdu));
        break;
      }

      else if (cmd == CMD_START) {
        multilog (log, LOG_INFO,
            "[STATE_STARTED->START] ignored CMD_START.\n");
        cmd = CMD_NONE;
      }

      //read a packet from the data socket and write it to the ring buffer
      if (FD_ISSET (raw.svc,&readfds)) {
        
        // This is a little kluge to reduce CPU utilization.
        // If we are in START_STARTED, read multiple packets before 
        // looping back to multiplex and check for commands
        for (int ipacket = 0; ipacket < 20; ++ipacket) {

          raw_bytes_read = recvfrom (raw.svc, buf, BUFSIZE, 0, 
              (struct sockaddr *)&(raw.rem_addr), &(raw.alen));

          if (raw_bytes_read == BUFSIZE) {

            // this makes sure we read 0.5s of data from the buffer; based
            // on the maximum requested raw socket size (2x16MB) this is
            // more than enough to clear out any old data from the buffer
            if (skip_frames <  25600) {
              skip_frames ++;
              continue;
            }

            if (write_header) {
              multilog (log, LOG_INFO, "Writing psrdada header.\n");
              write_psrdada_header (
                  hdu, (vdif_header *)(buf + UDP_HDR_SIZE), &od);
              write_header = 0;
            }

            ipcio_bytes_written = ipcio_write (
                hdu->data_block,buf+UDP_HDR_SIZE, VDIF_PKT_SIZE);

            if (ipcio_bytes_written != VDIF_PKT_SIZE) {
              multilog (log, LOG_ERR,
                  "Failed to write VDIF packet to psrdada buffer.\n");
              exit_status = EXIT_FAILURE;
              break;
            }
            else
              packets_written++;
          }
          else if (raw_bytes_read <= 0) {
            multilog (log, LOG_ERR,
                "Raw socket read failed: %d\n.", raw_bytes_read);
            fflush (logfile_fp);
            cmd = CMD_STOP;
            break; // break from multi-packet loop
          }
          else {
            multilog (log, LOG_ERR,
                "Received packet size: %d, ignoring.\n", raw_bytes_read);
            fflush (logfile_fp);
            cmd = CMD_STOP;
            break; // break from multi-packet loop
          }
        } // end multiple packet read
      } // end raw socket read logic
    } // end STATE_STARTED logic

