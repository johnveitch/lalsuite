#include <stdio.h>
#include <math.h>
#include "global.h"
#include "context.h"
#include "util.h"
#include "cmdline.h"
#include "dataset.h"

#define restrict

#include <lal/LALDatatypes.h>
#include <lal/AVFactories.h>
#include <lal/ComplexFFT.h>

#define XALLOC(var, call)	while((var=call)==NULL) { \
	fprintf(stderr, "*** Could not allocate " #var "=" #call "\n"); \
	condor_safe_sleep(10); \
	}

struct gengetopt_args_info args_info;

SPARSE_CONV *new_sparse_conv(void)
{
SPARSE_CONV *sc;

sc=do_alloc(1, sizeof(*sc));

sc->free=0;
sc->size=20;

sc->bin=do_alloc(sc->size, sizeof(*sc->bin));
sc->data=do_alloc(sc->size, sizeof(*sc->data));

return(sc);
}

void free_sparse_conv(SPARSE_CONV *sc)
{
free(sc->bin);
free(sc->data);
sc->bin=NULL;
sc->data=NULL;
free(sc);
}

LOOSE_CONTEXT * create_context(void)
{
LOOSE_CONTEXT *ctx;
int wing_step;
int day_samples=round(2.0*SIDEREAL_DAY/args_info.coherence_length_arg);

ctx=do_alloc(1, sizeof(*ctx));

ctx->timebase=max_gps()-min_gps();
ctx->first_gps=min_gps();
	
ctx->nsamples=1+ceil(2.0*ctx->timebase/args_info.coherence_length_arg);
wing_step=round(ctx->nsamples*args_info.coherence_length_arg/SIDEREAL_DAY);
ctx->nsamples=day_samples*floor(ctx->nsamples/day_samples);
ctx->nsamples=round235up_int(ctx->nsamples);

TODO("increase plan optimization level to 1")
fprintf(stderr, "Creating FFT plan of length %d\n", ctx->nsamples);
XALLOC(ctx->fft_plan, XLALCreateForwardCOMPLEX16FFTPlan(ctx->nsamples, 0));

XALLOC(ctx->plus_samples, XLALCreateCOMPLEX16Vector(ctx->nsamples));
XALLOC(ctx->cross_samples, XLALCreateCOMPLEX16Vector(ctx->nsamples));
XALLOC(ctx->plus_fft, XLALCreateCOMPLEX16Vector(ctx->nsamples));
XALLOC(ctx->cross_fft, XLALCreateCOMPLEX16Vector(ctx->nsamples));
XALLOC(ctx->plus_te_fft, XLALCreateCOMPLEX16Vector(ctx->nsamples));
XALLOC(ctx->cross_te_fft, XLALCreateCOMPLEX16Vector(ctx->nsamples));

/* Bessel coeffs */
ctx->te_sc=new_sparse_conv();
ctx->spindown_sc=new_sparse_conv();
ctx->ra_sc=new_sparse_conv();
ctx->dec_sc=new_sparse_conv();

/* Parameters */

ctx->n_freq_adj_filter=7;
ctx->n_fsteps=4;
ctx->half_window=1;

ctx->ra=0;
ctx->dec=0;
ctx->frequency=0;
ctx->spindown=0;
ctx->dInv=args_info.focus_dInv_arg;
ctx->fstep=0;

fprintf(stderr, "nsamples=%d day_samples=%d wing_step=%d half_window=%d\n", ctx->nsamples, day_samples, wing_step, ctx->half_window);

return(ctx);
}