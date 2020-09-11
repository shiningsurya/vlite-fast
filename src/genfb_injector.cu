/* GENFB test for injection
 * To generate filterbank to write to PSRDADA buffer.
 - Defaults:
 - written to output dada buffer
 - kurtosis happens
 - pscrunching happens
 * 
 *
 */


// system support
#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <string.h>
#include <time.h>
#include <fcntl.h>

#include "vdifio.h"

// psrdada support
#include "dada_def.h"
#include "dada_hdu.h"
#include "ipcio.h"
#include "ascii_header.h"
#include "multilog.h"

// local support
#include "process_baseband.h"
#include "util.h"
#include "cuda_util.h"
#include "injection.h"

// from Julia's code
extern "C" {
#include "utils.h"
#include "def.h"
#include "executor.h"
#include "multicast.h"
}

// rt profiling
//#define RT_PROFILE 1

// fighting against decimation

static volatile int NBIT = 8;
static FILE* logfile_fp = NULL;
static FILE* fb_fp = NULL;
static multilog_t* mlog = NULL;
static dada_hdu_t* hdu_out = NULL;
static int mc_control_sock = 0;
static float EARLY = 0.0f;

static double UTCEPOCH = 831297600.0;
static double MJD      = 50208.5;

void usage ()
{
  fprintf (stdout,"Usage: genfb [options]\n"
      "-k hexadecimal shared memory key for output (default: 40)\n"
      "-o print logging messages to stdout (as well as logfile)\n"
      "-b reduce output to b bits (2, 4, and 8[def] are supported))\n"
      "-s seed for random number generator [long; default=42]\n"
      "-e seconds of whitenoise data before anything starts [default=3.0f]\n"
      "-E UTC start epoch of the observation[default=123456789, 29/11/1973]\n"
      "-m MJD of the start epoch[default matched to UTC]\n"
      "-f write filterbank [def=no]\n"
      "-g run on specified GPU\n");
  //"-m retain MUOS band\n"
  //	  ,(uint64_t)READER_SERVICE_PORT);
}

void cleanup (void)
{
  fprintf (stderr,"called cleanup! [GENFB]\n");
  fflush (stderr);
  if (fb_fp) fclose (fb_fp);
  fprintf (stderr,"h1\n");
  fflush (stderr);
  if (hdu_out != NULL)
  {
    dada_hdu_disconnect (hdu_out);
    dada_hdu_destroy (hdu_out);
  }
  fprintf (stderr,"h2\n");
  fflush (stderr);
  if (mc_control_sock > 0)
    shutdown (mc_control_sock, 2);
  fprintf (stderr,"h3\n");
  fflush (stderr);
  if (mlog) {
    multilog (mlog, LOG_INFO, "Completed shutdown [GENFB].\n");
    multilog_close (mlog);
  }
  fprintf (stderr,"h4\n");
  fflush (stderr);
  if (logfile_fp) fclose (logfile_fp);
  fprintf (stderr,"h5\n");
  fflush (stderr);
}

void exit_handler (void) {
  fprintf (stderr, "exit handler called\n");
  fflush (stderr);
  cleanup ();
}

void sigint_handler (int dummy) {
  cleanup ();
  exit (EXIT_SUCCESS);
}

/********************
  Header contains the following 
  which should be provided somehow
  - STATIONID int
  - BEAM int
  - RA  double
  - DEC double
  - NAME char[]
  - SCANSTART double
  - NCHANS int
  - BANDWIDTH double
  - CFREQ double
  - NPOL int
  - NBIT int
  - TSAMP double
  - UTC_START char[]
  - UNIXEPOCH double
 *******************/

// injection_t struct has start which is when the signal should begin. 
// start argument is when the data begins
// because we would want to have white noise preceding the trigger.
int write_psrdada_header (dada_hdu_t* hdu, char* fb_file)
{
  // update the time with the actual data start, since we have discarded
  // some data to reach a 1s boundary
  time_t epoch_seconds = UTCEPOCH;
  struct tm utc_time;
  gmtime_r (&epoch_seconds, &utc_time);
  char dada_utc[DADA_TIMESTR_LENGTH];
  strftime (dada_utc, DADA_TIMESTR_LENGTH, DADA_TIMESTR, &utc_time);

  // initialize observation parameters for filterbank
  // NB the data are upper sideband, so negative channel bandwidth
  double chbw = -BW / NCHAN;
  double tsamp = double(NFFT)/VLITE_RATE*NSCRUNCH*1e6; // NB in mus
  int nchan = CHANMAX-CHANMIN+1;
  double bw = nchan*chbw;
  double freq0 = FCH1;
  double freq = freq0 + 0.5*(CHANMIN+CHANMAX-1)*chbw;

  fprintf (stderr, "before lock\n");
  dadacheck (dada_hdu_lock_write (hdu));
  fprintf (stderr, "after lock\n");
  char* ascii_hdr = ipcbuf_get_next_write (hdu->header_block);
  fprintf (stderr, "after next write\n");
  // default options
  dadacheck (ascii_header_set (ascii_hdr, "STATIONID", "%d", STATIONID));
  dadacheck (ascii_header_set (ascii_hdr, "BEAM", "%d", STATIONID));
  dadacheck (ascii_header_set (ascii_hdr, "RA", "%lf", 0.0));
  dadacheck (ascii_header_set (ascii_hdr, "DEC", "%lf", 0.0));
  dadacheck (ascii_header_set (ascii_hdr, "NAME", "%s", "INJECTED"));
  dadacheck (ascii_header_set (ascii_hdr, "NCHAN", "%d", nchan) );
  dadacheck (ascii_header_set (ascii_hdr, "BANDWIDTH", "%lf", bw) );
  dadacheck (ascii_header_set (ascii_hdr, "CFREQ", "%lf", freq) );
  dadacheck (ascii_header_set (ascii_hdr, "NPOL", "%d", 1) );
  dadacheck (ascii_header_set (ascii_hdr, "NBIT", "%d", NBIT) );
  dadacheck (ascii_header_set (ascii_hdr, "TSAMP", "%lf", tsamp) );
  dadacheck (ascii_header_set (ascii_hdr, "UTC_START", "%s", dada_utc) );

  // changing options
  dadacheck (ascii_header_set (ascii_hdr, "SCANSTART", "%lf", UTCEPOCH));
  dadacheck (ascii_header_set (ascii_hdr, "UNIXEPOCH", "%lf", UTCEPOCH) );
  // also record the VDIF MJD info, this is useful for finding
  // transients in the baseband stream.
  dadacheck (ascii_header_set (ascii_hdr, "VDIF_MJD", "%d", MJD) );
  unsigned long imjd = (MJD - (int)MJD)*86400.0f;
  dadacheck (ascii_header_set (ascii_hdr, "VDIF_SEC", "%lu", imjd) );

  if (fb_file)
    dadacheck (ascii_header_set (ascii_hdr, "SIGPROC_FILE", "%s", fb_file) );
  multilog (hdu->log, LOG_INFO, "%s",ascii_hdr);
  ipcbuf_mark_filled (hdu->header_block, 4096);
  return 0;
}

void write_sigproc_header (FILE* output_fp)
{
  double chbw = -64./NCHAN;
  double tsamp = double(NFFT)/VLITE_RATE*NSCRUNCH;
  // write out a sigproc header
  send_string ("HEADER_START",output_fp);
  send_string ("source_name",output_fp);
  send_string ("INJECTED",output_fp);
  send_int ("barycentric",0,output_fp);
  send_int ("telescope_id",STATIONID,output_fp);
  send_double ("src_raj",0.0,output_fp);
  send_double ("src_dej",0.0,output_fp);
  send_int ("data_type",1,output_fp);
  //
  send_double ("fch1",384+(CHANMIN-0.5)*chbw,output_fp);
  send_double ("foff",chbw,output_fp);//negative foff, fch1 is highest freq
  send_int ("nchans",CHANMAX-CHANMIN+1,output_fp);
  send_int ("nbits",NBIT,output_fp);
  send_double ("tstart",MJD,output_fp);
  send_double ("tsamp",tsamp,output_fp);//[sec]
  send_int ("nifs",1,output_fp);
  send_string ("HEADER_END",output_fp);
}

void get_fbfile (char* fbfile, ssize_t fbfile_len)
{
  // Open up filterbank file using timestamp and antenna
  char currt_string[128];
  time_t epoch_seconds = UTCEPOCH;
  struct tm utc_time;
  gmtime_r (&epoch_seconds, &utc_time);
  strftime (currt_string,sizeof(currt_string), "%Y%m%d_%H%M%S", &utc_time);
  *(currt_string+15) = 0;
  if (CHANMIN < 2411)
    snprintf (fbfile,fbfile_len,"%s/%s_muos_ea%02d.fil",DATADIR,currt_string,STATIONID);
  else
    snprintf (fbfile,fbfile_len,"%s/%s_ea%02d.fil",DATADIR,currt_string,STATIONID);
}

void check_buffer (dada_hdu_t* hdu, multilog_t* log)
{
  ipcbuf_t* buf = (ipcbuf_t*) hdu->data_block;
  uint64_t m_nbufs = ipcbuf_get_nbufs (buf);
  uint64_t m_full_bufs = ipcbuf_get_nfull (buf);
  if (m_full_bufs == (m_nbufs - 1))
  {
    fprintf (stderr,"failed buffer check\n");
    fflush (stderr);
    dadacheck (dada_hdu_unlock_write (hdu));
    multilog (mlog, LOG_ERR,
        "Only one free buffer left!  Aborting output.\n");
    exit (EXIT_FAILURE);
  }
}

void check_ipcio_write (dada_hdu_t* hdu, char* buf, size_t to_write, multilog_t* log)
{
  size_t written = ipcio_write (hdu->data_block,buf,to_write);
  if (written != to_write)
  {
    fprintf (stderr, "failed ipcio write\n"); 
    fflush (stderr);
    multilog (mlog, LOG_ERR, "Tried to write %lu bytes to psrdada buffer but only wrote %lu.", to_write, written);
    exit (EXIT_FAILURE);
  }
}

int main (int argc, char *argv[])
{
  // register SIGINT handling
  signal (SIGINT, sigint_handler);

  // register exit function
  atexit (exit_handler);

  int exit_status = EXIT_SUCCESS;
  key_t key_out = 0x40;
  int stdout_output = 0;
  int write_fb = 0;
  int npol = 1;
  int gpu_id = 0;
  size_t maxn = 0;
  long seed = 42;

  int arg = 0;
  while ((arg = getopt(argc, argv, "hk:of:b:s:e:g:E:m:")) != -1) {
    switch (arg) {

      case 'h':
        usage ();
        return 0;

      case 'k':
        if (sscanf (optarg, "%x", &key_out) != 1) {
          fprintf (stderr, "genfb: could not parse key from %s\n", optarg);
          return -1;
        }
        break;

      case 's':
        if (sscanf (optarg, "%li", &seed) != 1) {
          fprintf (stderr, "genfb: could not read seed from %s\n", optarg);
          return -1;
        }
        break;

      case 'o':
        stdout_output = 1;
        break;

      case 'f':
        if (sscanf (optarg, "%d", &write_fb) != 1) {
          fprintf (stderr, "genfb: could not parse write mode %s\n", optarg);
          return -1;
        }
        break;

      case 'b':
        if (sscanf (optarg, "%d", &NBIT) != 1) {
          fprintf (stderr, "genfb: could not parse number of bits %s\n", optarg);
          return -1;
        }
        if (!(NBIT==2 || NBIT==4 || NBIT==8)) {
          fprintf (stderr, "Unsupported NBIT!\n");
          return -1;
        }
        break;

      case 'e':
        if (sscanf (optarg, "%f", &EARLY) != 1) {
          fprintf (stderr, "genfb: could not parse early %s\n", optarg);
          return -1;
        }
        break;

      case 'g':
        if (sscanf (optarg, "%d", &gpu_id) != 1) {
          fprintf (stderr, "writer: could not parse GPU id %s\n", optarg);
          return -1;
        }
        if (!(gpu_id==0 || gpu_id==1)) {
          fprintf (stderr, "Unsupported GPU id!\n");
          return -1;
        }
        break;
      case 'E':
        if (sscanf (optarg, "%lf", &UTCEPOCH) != 1) {
          fprintf (stderr, "genfb: could not parse UTCEPOCH: %s\n", optarg);
          return -1;
        }

      case 'm':
        if (sscanf (optarg, "%lf", &MJD) != 1) {
          fprintf (stderr, "genfb: could not parse MJD: %s\n", optarg);
          return -1;
        }
    }

  }

  cudacheck (cudaSetDevice (gpu_id));
  printf ("Setting CUDA device to %d.\n",gpu_id);
  int nsms;
  cudaDeviceGetAttribute (&nsms,cudaDevAttrMultiProcessorCount,gpu_id);

  struct timespec ts_1ms = get_ms_ts (1);
  struct timespec ts_10s = get_ms_ts (10000);

#if RT_PROFILE
  cudaEvent_t rt_start, rt_stop; //,start_total,stop_total;
  cudaEventCreate (&rt_start);
  cudaEventCreate (&rt_stop);

  float measured_time=0;
  float read_time=0, proc_time=0, write_time=0, rt_elapsed=0;
#endif

#if PROFILE
  // support for measuring run times of parts
  cudaEvent_t start,stop;
  cudaEventCreate (&start);
  cudaEventCreate (&stop);
  float alloc_time=0, hdr_time=0, read_time=0, todev_time=0, 
        convert_time=0, kurtosis_time=0, fft_time=0, histo_time=0,
        normalize_time=0, tscrunch_time=0, pscrunch_time=0, 
        digitize_time=0, write_time=0, flush_time=0, misc_time=0,
        elapsed=0;
#endif
  // measure full run time time
  cudaEvent_t obs_start, obs_stop;
  cudaEventCreate (&obs_start);
  cudaEventCreate (&obs_stop);

  multilog_t* mlog = multilog_open ("genfb",0);
  if (stdout_output)
    multilog_add (mlog, stdout);

  // sanity checks on configuration parameters
  if (NKURTO != 250 && NKURTO != 500) {
    multilog (mlog, LOG_ERR, "Only NKURTO==250 or 500 supported.\n");
    exit (EXIT_FAILURE);
  }

  // connect to output buffer
  if (key_out) {
    hdu_out = dada_hdu_create (mlog);
    dada_hdu_set_key (hdu_out,key_out);
    if (dada_hdu_connect (hdu_out) != 0) {
      multilog (mlog, LOG_ERR, 
          "Unable to connect to outgoing PSRDADA buffer!\n");
      exit (EXIT_FAILURE);
    }
  }

#if PROFILE
  cudaEventRecord(start,0);
#endif

  // voltage samples in a chunk, 2*VLITE_RATE/SEG_PER_SEC (both pols)
  size_t samps_per_chunk = 2*VLITE_RATE/SEG_PER_SEC;
  // FFTs per processing chunk (2 per pol)
  int fft_per_chunk = 2*FFTS_PER_SEG;

  // Only one side fft
  cufftHandle plan;
  cufftcheck (cufftPlan1d (&plan,NFFT,CUFFT_R2C,fft_per_chunk));

  // memory for FFTs
  cufftReal* fft_in; cudacheck (
      cudaMalloc ((void**)&fft_in,sizeof(cufftReal)*samps_per_chunk) );
  cufftComplex* fft_out; cudacheck (
      cudaMalloc ((void**)&fft_out,sizeof(cufftComplex)*fft_per_chunk*NCHAN) );
  cufftReal* fft_in_kur; cudacheck ( 
      cudaMalloc ((void**)&fft_in_kur,sizeof(cufftReal)*samps_per_chunk) );

  // device memory for kurtosis statistics, uses NKURTO samples, both pols
  // NKURTO must be commensurate with samps_per_chunk/2, i.e. samples per
  // chunk in a pol
  size_t nkurto_per_chunk = samps_per_chunk / NKURTO;

  // extra factor of 2 to store both power and kurtosis statistics
  // storage for high time resolution and filterbank block ("fb") scales
  cufftReal *pow_dev(NULL), *kur_dev(NULL), 
            *pow_fb_dev(NULL), *kur_fb_dev(NULL);
  cudacheck (
      cudaMalloc ((void**)&pow_dev,2*sizeof(cufftReal)*nkurto_per_chunk) );
  cudacheck (
      cudaMalloc ((void**)&pow_fb_dev,2*sizeof(cufftReal)*fft_per_chunk) );
  kur_dev = pow_dev + nkurto_per_chunk;
  kur_fb_dev = pow_fb_dev + fft_per_chunk;

  // store D'Agostino statistic for thresholding
  // only using one per pol now, but keep memory size for both pols
  // to make life easier; the values are duplicated
  cufftReal* dag_dev=NULL;
  cudaMalloc ((void**)&dag_dev,sizeof(cufftReal)*nkurto_per_chunk);
  cufftReal* dag_fb_dev=NULL;
  cudaMalloc ((void**)&dag_fb_dev,sizeof(cufftReal)*fft_per_chunk);

  // store a set of to re-normalize voltages after applying kurtosis
  cufftReal* kur_weights_dev=NULL;
  cudaMalloc ((void**)&kur_weights_dev,sizeof(cufftReal)*fft_per_chunk);

  // NB, reduce by a further factor of 2 if pscrunching
  int polfac = 2;
  int scrunch = (fft_per_chunk*NCHAN)/(polfac*NSCRUNCH);
  cufftReal* fft_ave; cudacheck (
      cudaMalloc ((void**)&fft_ave,sizeof(cufftReal)*scrunch) );

  // error check that NBIT is commensurate with trimmed array size
  int trim = (fft_per_chunk*(CHANMAX-CHANMIN+1))/(polfac*NSCRUNCH);
  if (trim % (8/NBIT) != 0) {
    multilog (mlog, LOG_ERR, 
        "Selected channel and bit scheme is not commensurate!.\n");
    exit (EXIT_FAILURE);
  }

  // reduce array size by packing of samples into byte
  trim /= (8/NBIT);
  unsigned char* fft_trim_u_dev; cudacheck (
      cudaMalloc ((void**)&fft_trim_u_dev,trim) );
  unsigned char* fft_trim_u_hst;

  // memory for a 10s buffer of output filterbank data
  int output_buf_sec = 10;
  int output_buf_seg_size = trim;
  int output_buf_size = output_buf_seg_size*output_buf_sec*SEG_PER_SEC;
  unsigned char* output_buf_mem;
  cudacheck (cudaMallocHost ((void**)&output_buf_mem,output_buf_size) );
  unsigned char* output_buf_cur = output_buf_mem;

  // memory for running bandpass correction; 2 pol * NCHAN
  cufftReal* bp_dev; cudacheck (
      cudaMalloc ((void**)&bp_dev,sizeof(cufftReal)*NCHAN*2));
  cudacheck (cudaMemset (bp_dev, 0, sizeof(cufftReal)*NCHAN*2));

  // memory for FRB injection
  float* frb_delays_dev = NULL;
  cudacheck (cudaMalloc ((void**)&frb_delays_dev, sizeof(float)*NCHAN));

  // prepare RNG
  curandGenerator_t       cugen;
  curandcheck (
      curandCreateGenerator (&cugen, CURAND_RNG_PSEUDO_DEFAULT)
      );
  curandcheck (
      curandSetPseudoRandomGeneratorSeed (cugen, seed)
      );


#if PROFILE
  CUDA_PROFILE_STOP(start,stop,&alloc_time)
#endif

    // constants for bandpass normalization: tsamp/tsmooth, giving a time
    // constant of about tsmooth secs.
    double tsmooth = 1;
  double tsamp = double(NFFT)/VLITE_RATE*NSCRUNCH;
  float bp_scale = tsamp/tsmooth;

  /*
  // connect to control socket
  Connection conn;
  conn.sockoptval = 1; //release port immediately after closing connection
  if (port) {
  if (serve (port, &conn) < 0) {
  multilog (mlog, LOG_ERR,
  "Failed to create control socket on port %d.\n", port);
  exit (EXIT_FAILURE);
  }
  fcntl (conn.rqst, F_SETFL, O_NONBLOCK); // set up for polling
  }
  char cmd_buff[32];
   */

  // connect to multicast injection socket
#define MAX_INJECTIONS 1
  int mc_injection_sock = open_mc_socket (mc_injectgrp, MC_INJECT_PORT,
      (char*)"Injection Socket [GENFB]", NULL, mlog);
  int injection = 0;
  injection_t ip_par;

  int quit = 0;

  double integrated  = 0.0;
  int integrated_sec = 0;

  /******************************
   **
   All injections last for 10s.
   Two seconds of noise in the beginning.
   And 8s of dispersed signals. 
   All triggers should have toa as 
   (observation_i0 + EARLY (2) ) % 10
   ******************************/

  // This point start to loop over commands.
  // 1 obs --> 2 mins --> 15 frbs of 8seconds each
  // 30 obs --> 1 hr  --> 450 frbs
  for (int iobs = 0; iobs < 50; iobs++)
  {
    // update MJD and UTCEPOCH
    UTCEPOCH += integrated_sec;
    MJD += (integrated_sec/86400.0f);
    integrated = 0.0;
    integrated_sec = 0;
    
    // add buffer space 
    // this buffer is to separate the observations
    //UTCEPOCH += 8;
    //MJD += (8.0/86400.0f);

    // do the pleasantaries
    // since only one observation happening
    // Open up filterbank file at appropriate time
    char fbfile[256];
    get_fbfile (fbfile, 256);
    uint64_t fb_bytes_written = 0;
    FILE * fb_fp = NULL;
    if (write_fb) {
      fb_fp = myopen (fbfile, "wb", true, trim);
      multilog (mlog, LOG_INFO,
          "Writing filterbank to %s.\n",fbfile);
    }

#if PROFILE
    cudaEventRecord(start,0);
#endif

    if (key_out) {
      write_psrdada_header (hdu_out, fbfile);
      fprintf (stderr, "write psrdada header\n");
    }

    // write out a sigproc header
    if (write_fb)
      write_sigproc_header (fb_fp);

#if PROFILE
    CUDA_PROFILE_STOP(start,stop,&hdr_time);
#endif
    if (quit)
      break;


    // 15 frbs
    // 8s per frb
    // one observation is two minute
    // LCM (24, 60) is 120
    // 24 <- heimdall good gulp
    // 60 seconds in a minute
    for (int ifrb = 0; ifrb < 15; ifrb++) {
      // check for injection par
      // begin only if received
      int nbytes = 0;
      while (true) {
        nbytes = MultiCastReceive (mc_injection_sock, (char*)&ip_par,
            sizeof(injection_t), 0);
        multilog (mlog, LOG_INFO, "Received %d bytes.\n", nbytes);
        // to avoid a lot of IO
        if (nbytes < 0) {
          sleep (5);
          continue;
        }
        else {
          break;
        }
        // we only work with one injection
      }

      multilog (mlog, LOG_INFO, 
          "Received injection request with DM=%3.2f, Width[units]=%d" 
          " Amplitude=%5.2ef\n",
          ip_par.dm, ip_par.wd, ip_par.amp);

      // beginning new observation
      cudaEventRecord(obs_start,0);

      set_frb_delays <<< NCHAN/NTHREAD+1, NTHREAD >>> (frb_delays_dev, ip_par.dm);
      cudacheck (cudaGetLastError () );

      /*
         float* frb_delays_hst = NULL;
         cudacheck (cudaMallocHost ((void**)&frb_delays_hst, sizeof(float)*NCHAN));
         cudacheck (cudaMemcpy (

         frb_delays_hst,frb_delays_dev,sizeof(float)*NCHAN,
         cudaMemcpyDeviceToHost) );
         for (int ichan=0; ichan < 6250; ichan += 100)
         fprintf (stdout, "frb_delay %d = %.6f\n", ichan, frb_delays_hst[ichan]);
       */

#if RT_PROFILE
      cudaEventRecord(rt_start,0);
      measured_time = 0;
#endif 

      int SECS = 8;

      for (int isec = 0; isec < SECS; isec++) // loop over segments
      {
        // We have a 10s buffer on host
        // which we cycle through.
        if ( (integrated_sec % output_buf_sec) == 0 )
          output_buf_cur = output_buf_mem;
        // do dispatch -- break into chunks to fit in GPU memory; this is
        // currently 100 milliseconds
        for (int iseg = 0; iseg < SEG_PER_SEC; iseg++)
        {

          ////// FILL WITH WHITE NOISE   //////
#if PROFILE
          cudaEventRecord (start,0);
#endif 

          cudacheck (cudaGetLastError () );

          // fill fft_in with samps_per_chunk white noise
          curandcheck (
              curandGenerateNormal (
                cugen, fft_in, samps_per_chunk,
                0.0f, 33.818f
                )
              );

#if PROFILE
          CUDA_PROFILE_STOP(start,stop,&elapsed)
            convert_time += elapsed;
#endif

          ////// CALCULATE KURTOSIS STATISTICS //////
#if PROFILE
          cudaEventRecord (start,0);
#endif

          // calculate high time resolution kurtosis (250 or 500 samples)
          kurtosis <<<nkurto_per_chunk, 256>>> (
              fft_in,pow_dev,kur_dev);
          cudacheck (cudaGetLastError () );

          // compute the thresholding statistic
          // NB now modified to combine polarizations
          compute_dagostino <<<nsms*32,NTHREAD>>> (
              kur_dev,dag_dev,nkurto_per_chunk/2);
          cudacheck (cudaGetLastError () );

          // calculate coarser kurtosis (for entire filterbank sample, e.g. 12500 samples)
          // NB this relies on results of previous D'Agostino calculation
          block_kurtosis <<<fft_per_chunk/8,256>>> (
              pow_dev,kur_dev,dag_dev,pow_fb_dev,kur_fb_dev);
          cudacheck (cudaGetLastError () );
          // NB now modified to combine polarizations
          compute_dagostino2 <<<nsms*32,NTHREAD>>> (
              kur_fb_dev,dag_fb_dev,fft_per_chunk/2);
          cudacheck (cudaGetLastError () );

          cudacheck (cudaMemset (
                kur_weights_dev,0,sizeof(cufftReal)*fft_per_chunk) );
          // (1) NB that fft_in_kur==fft_in if not writing both streams
          // (2) original implementation had a block for each pol; keeping
          //     that, but two blocks now access the same Dagostino entry
          //if (integrated >= 0.1)
          apply_kurtosis <<<nkurto_per_chunk, 256>>> (
              fft_in,fft_in_kur,dag_dev,dag_fb_dev,kur_weights_dev);
          cudacheck (cudaGetLastError () );

#if PROFILE
          CUDA_PROFILE_STOP(start,stop,&elapsed)
            kurtosis_time += elapsed;
#endif

          ////// PERFORM FFTs //////
#if PROFILE
          cudaEventRecord (start,0);
#endif 
          cufftcheck (cufftExecR2C (plan,fft_in_kur,fft_out) );
#if PROFILE
          CUDA_PROFILE_STOP(start,stop,&elapsed)
            fft_time += elapsed;
#endif

          ////// INJECT FRB AS REQUESTED //////
          if (1)
          {
            // NB that inject_frb_now is only reset every 1s, so we also use
            // it to keep track of how many segments have elapsed since the
            // FRB time, since this loop is over 100ms chunks which will be
            // < dispersed FRB width, typically

            int since_frb = ( ( isec *SEG_PER_SEC ) + iseg-1 )*FFTS_PER_SEG;
            inject_frb <<< NCHAN/NTHREAD+1,NTHREAD >>> (fft_out, 
                frb_delays_dev, since_frb,
                ip_par.wd, ip_par.amp
                );
            cudacheck ( cudaGetLastError () );
          }

          ////// NORMALIZE BANDPASS //////
#if PROFILE
          cudaEventRecord(start,0);
#endif 
          detect_and_normalize3 <<<(NCHAN*2)/NTHREAD+1,NTHREAD>>> (
              fft_out,kur_weights_dev,bp_dev,bp_scale);
          cudacheck ( cudaGetLastError () );
#if PROFILE
          CUDA_PROFILE_STOP(start,stop,&elapsed)
            normalize_time += elapsed;
#endif

          ////// ADD POLARIZATIONS //////
#if PROFILE
          cudaEventRecord (start,0);
#endif 
          maxn = (fft_per_chunk*NCHAN)/polfac;
          pscrunch_weights <<<nsms*32,NTHREAD>>> (
              fft_out,kur_weights_dev,maxn);
          cudacheck ( cudaGetLastError () );
#if PROFILE
          CUDA_PROFILE_STOP(start,stop,&elapsed)
            pscrunch_time += elapsed;
#endif

          ////// AVERAGE TIME DOMAIN //////
#if PROFILE
          cudaEventRecord( start,0);
#endif 
          maxn /= NSCRUNCH;
          tscrunch <<<nsms*32,NTHREAD>>> (fft_out,fft_ave,maxn);
          cudacheck ( cudaGetLastError () );
#if PROFILE
          CUDA_PROFILE_STOP(start,stop,&elapsed)
            tscrunch_time += elapsed;
#endif

          ////// TRIM CHANNELS AND DIGITIZE //////
#if PROFILE
          cudaEventRecord (start,0);
#endif 
          maxn = (CHANMAX-CHANMIN+1)*(maxn/NCHAN)/(8/NBIT);
          switch (NBIT)
          {
            case 2:
              sel_and_dig_2b <<<nsms*32,NTHREAD>>> (
                  fft_ave,fft_trim_u_dev,maxn, npol);
              break;
            case 4:
              sel_and_dig_4b <<<nsms*32,NTHREAD>>> (
                  fft_ave,fft_trim_u_dev,maxn, npol);
              break;
            case 8:
              sel_and_dig_8b <<<nsms*32,NTHREAD>>> (
                  fft_ave,fft_trim_u_dev,maxn, npol);
              break;
            default:
              sel_and_dig_8b <<<nsms*32,NTHREAD>>> (
                  fft_ave,fft_trim_u_dev,maxn, npol);
              break;
          }
          cudacheck ( cudaGetLastError () );
#if PROFILE
          CUDA_PROFILE_STOP(start,stop,&elapsed)
            digitize_time += elapsed;
#endif

#if PROFILE
          cudaEventRecord (start,0);
#endif 

          // copy filterbanked data back to host; use big buffer to avoid
          // a second copy; NB that if we are only recording a single RFI
          // excision mode, the _kur buffer points to same place.  And if we
          // are recording both, then we output the kurtosis.  So we can
          // just always record the kurtosis to the output buffer, and if
          // we are recording both, copy the second to the small buffer
          fft_trim_u_hst = output_buf_cur;
          cudacheck (cudaMemcpy (
                fft_trim_u_hst,fft_trim_u_dev,maxn,cudaMemcpyDeviceToHost) );
          output_buf_cur += output_buf_seg_size; 
          cudacheck (cudaGetLastError () );

#if PROFILE
          CUDA_PROFILE_STOP(start,stop,&elapsed)
            misc_time += elapsed;
#endif

          // finally, push the filterbanked time samples onto psrdada buffer
          // and/or write out to sigproc

#if PROFILE
          cudaEventRecord (start,0);
#endif 

          char* outbuff = (char*)fft_trim_u_hst;
          // check_buffer (hdu_out, mlog);
          if (key_out) {
            check_ipcio_write (hdu_out, outbuff, maxn, mlog);
          }

          // TODO -- tune this I/O.  The buffer size is set to 8192, but
          // according to fstat the nfs wants a block size of 1048576! Each
          // 100ms of data is 65536 with the current parameters.  So optimally
          // we would buffer in memory for the full 1 second before a write.
          // However, a simple improvement will be reducing the write calls by
          // a factor of 8 by either changing the buffer size or using the

          // TODO -- add error checking for these writes
          if (write_fb) {
            fwrite (fft_trim_u_hst,1,maxn,fb_fp);
            fb_bytes_written += maxn;
          }

#if PROFILE
          CUDA_PROFILE_STOP(start,stop,&elapsed)
            write_time += elapsed;
#endif

          integrated += 1./double(SEG_PER_SEC);

        } // end loop over segments

        cudacheck (cudaGetLastError () );

        // sleep for 1.0
        sleep (1);

        integrated_sec += 1;
      } // end loop over seconds
    } // end loop over frb

    cudacheck ( cudaGetLastError () );
    if (key_out) {
      fprintf (stderr, "genfb: before dada_hdu_unlock_write\n");
      dadacheck (dada_hdu_unlock_write (hdu_out));
      fprintf (stderr, "genfb: after dada_hdu_unlock_write\n");
    }
    fflush (stderr);

#if PROFILE
    cudaEventRecord(start,0);
#endif 

    // close files
    if (write_fb) {
      if (fb_fp) {fclose (fb_fp); fb_fp = NULL;}
      uint64_t samps_written = (fb_bytes_written*(8/NBIT))/(CHANMAX-CHANMIN+1);
      multilog (mlog, LOG_INFO, "Wrote %.2f MB (%.2f s) to %s\n",
          fb_bytes_written*1e-6,samps_written*tsamp,fbfile);
    }

    float obs_time;
    CUDA_PROFILE_STOP (obs_start,obs_stop,&obs_time);
    multilog (mlog, LOG_INFO, "Proc Time...%.3f\n", obs_time*1e-3);

#if PROFILE
    CUDA_PROFILE_STOP(start,stop,&flush_time)
      float sub_time = hdr_time + read_time + todev_time + 
      histo_time + convert_time + kurtosis_time + fft_time + 
      normalize_time + pscrunch_time + tscrunch_time + digitize_time + 
      write_time + flush_time + misc_time;
    multilog (mlog, LOG_INFO, "Alloc Time..%.3f\n", alloc_time*1e-3);
    multilog (mlog, LOG_INFO, "Histogram...%.3f\n", histo_time*1e-3);
    multilog (mlog, LOG_INFO, "Convert.....%.3f\n", convert_time*1e-3);
    multilog (mlog, LOG_INFO, "Kurtosis....%.3f\n", kurtosis_time*1e-3);
    multilog (mlog, LOG_INFO, "FFT.........%.3f\n", fft_time*1e-3);
    multilog (mlog, LOG_INFO, "Normalize...%.3f\n", normalize_time*1e-3);
    multilog (mlog, LOG_INFO, "Pscrunch....%.3f\n", pscrunch_time*1e-3);
    multilog (mlog, LOG_INFO, "Tscrunch....%.3f\n", tscrunch_time*1e-3);
    multilog (mlog, LOG_INFO, "Digitize....%.3f\n", digitize_time*1e-3);
    multilog (mlog, LOG_INFO, "Write.......%.3f\n", write_time*1e-3);
    multilog (mlog, LOG_INFO, "Flush.......%.3f\n", flush_time*1e-3);
    multilog (mlog, LOG_INFO, "Misc........%.3f\n", misc_time*1e-3);
    multilog (mlog, LOG_INFO, "Sum of subs.%.3f\n", sub_time*1e-3);

    // reset values for next loop
    hdr_time=read_time=todev_time=convert_time=kurtosis_time=fft_time=0;
    histo_time=normalize_time=tscrunch_time=pscrunch_time=digitize_time=0;
    write_time=flush_time=misc_time=elapsed=0;

#endif

    // sleep for 3 seconds after every observation
    sleep (3);

  } // end loop over observations

  // ffts
  if (fft_in) cudaFree (fft_in);
  if (fft_in_kur) cudaFree (fft_in_kur);
  if (fft_out) cudaFree (fft_out);
  // kur
  if (pow_dev) cudaFree (pow_dev);
  if (kur_dev) cudaFree (kur_dev);
  if (dag_dev) cudaFree (dag_dev);
  if (dag_fb_dev) cudaFree (dag_fb_dev);
  if (kur_weights_dev) cudaFree (kur_weights_dev);
  // pscrunch
  if (fft_ave) cudaFree (fft_ave);
  // digitized
  if (fft_trim_u_dev) cudaFree (fft_trim_u_dev);
  if (fft_trim_u_hst) cudaFreeHost (fft_trim_u_hst);
  if (output_buf_mem ) cudaFreeHost (output_buf_mem );
  // bandpass
  if (bp_dev) cudaFree (bp_dev);
  // frb delays
  if (frb_delays_dev) cudaFree (frb_delays_dev);
  // RNG
  curandDestroyGenerator (cugen);

  return exit_status;

}

