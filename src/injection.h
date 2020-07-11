#ifndef __INJECTION_H__
#define __INJECTION_H__
/*************
 * FRB Injection 
 * struct and definitions
 * ***********/
typedef struct {
  float amp;        // amplitude
  float dm;         // dispersion measure
  uint8_t wd;       // width in samples
} injection_t;

injection_t sample_inject = {0.5, 100, 4};

#define FCH1  384.0
#define BW    64.0
#define STATIONID 67

#define IFRB_PERIOD 10
#define DM_DELAY    4.15e-3*(0.320**-2-0.384**-2)
#define NFRBS       100
#define FRBPARFILE  ""

#endif //__INJECTION_H__
