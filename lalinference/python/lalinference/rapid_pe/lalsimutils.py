# Copyright (C) 2012  Evan Ochsner, R. O'Shaughnessy
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
A collection of useful data analysis routines built from the SWIG wrappings of LAL and LALSimulation.
"""
import sys
import copy
import types
from math import cos, sin, sqrt

import numpy as np
from scipy import interpolate
from scipy import signal

from glue.ligolw import lsctables, utils, ligolw # check all are needed
lsctables.use_in(ligolw.LIGOLWContentHandler)
from glue.lal import Cache

import lal
import lalsimulation as lalsim
import lalinspiral
import lalmetaio

import pylal
from pylal import frutils
from pylal import series

__author__ = "Evan Ochsner <evano@gravity.phys.uwm.edu>, R. O'Shaughnessy"

TOL_DF = 1.e-6 # Tolerence for two deltaF's to agree

#
# Class to hold arguments of ChooseWaveform functions
#
class ChooseWaveformParams:
    """
    Class containing all the arguments needed for SimInspiralChooseTD/FDWaveform
    plus parameters theta, phi, psi, radec to go from h+, hx to h(t)

    if radec==True: (theta,phi) = (DEC,RA) and strain will be computed using
            XLALSimDetectorStrainREAL8TimeSeries
    if radec==False: then strain will be computed using a simple routine 
            that assumes (theta,phi) are spherical coord. 
            in a frame centered at the detector
    """
    def __init__(self, phiref=0., deltaT=1./4096., m1=10.*lal.MSUN_SI,
            m2=10.*lal.MSUN_SI, s1x=0., s1y=0., s1z=0.,
            s2x=0., s2y=0., s2z=0., fmin=40., fref=0., dist=1.e6*lal.PC_SI,
            incl=0., lambda1=0., lambda2=0., waveFlags=None, nonGRparams=None,
            ampO=0, phaseO=7, approx=lalsim.TaylorT4, 
            theta=0., phi=0., psi=0., tref=0., radec=False, detector="H1",
            deltaF=None, fmax=0., # for use w/ FD approximants
            taper=lalsim.SIM_INSPIRAL_TAPER_NONE # for use w/TD approximants
            ):
        self.phiref = phiref
        self.deltaT = deltaT
        self.m1 = m1
        self.m2 = m2
        self.s1x = s1x
        self.s1y = s1y
        self.s1z = s1z
        self.s2x = s2x
        self.s2y = s2y
        self.s2z = s2z
        self.fmin = fmin
        self.fref = fref
        self.dist = dist
        self.incl = incl
        self.lambda1 = lambda1
        self.lambda2 = lambda2
        self.waveFlags = waveFlags
        self.nonGRparams = nonGRparams
        self.ampO = ampO
        self.phaseO = phaseO
        self.approx = approx
        self.theta = theta     # DEC.  DEC =0 on the equator; the south pole has DEC = - pi/2
        self.phi = phi         # RA.   
        self.psi = psi
        self.tref = tref
        self.radec = radec
        self.detector = "H1"
        self.deltaF=deltaF
        self.fmax=fmax
        self.taper = taper

    def copy(self):
        """
        Create a deep copy, so copy and original can be changed separately
        """
        return copy.deepcopy(self)

    def print_params(self):
        """
        Print all key-value pairs belonging in the class instance
        """
        print "This ChooseWaveformParams has the following parameter values:"
        print "m1 =", self.m1 / lal.MSUN_SI, "(Msun)"
        print "m2 =", self.m2 / lal.MSUN_SI, "(Msun)"
        print "s1x =", self.s1x
        print "s1y =", self.s1y
        print "s1z =", self.s1z
        print "s2x =", self.s2x
        print "s2y =", self.s2y
        print "s2z =", self.s2z
        print "lambda1 =", self.lambda1
        print "lambda2 =", self.lambda2
        print "inclination =", self.incl
        print "distance =", self.dist / 1.e+6 / lal.PC_SI, "(Mpc)"
        print "reference orbital phase =", self.phiref
        print "time of coalescence =", float(self.tref)
        print "detector is:", self.detector
        if self.radec==False:
            print "Sky position relative to overhead detector is:"
            print "zenith angle =", self.theta, "(radians)"
            print "azimuth angle =", self.phi, "(radians)"
        if self.radec==True:
            print "Sky position relative to geocenter is:"
            print "declination =", self.theta, "(radians)"
            print "right ascension =", self.phi, "(radians)"
        print "polarization angle =", self.psi
        print "starting frequency is =", self.fmin
        print "reference frequency is =", self.fref
        print "Max frequency is =", self.fmax
        print "time step =", self.deltaT, "(s) <==>", 1./self.deltaT,\
                "(Hz) sample rate"
        print "freq. bin size is =", self.deltaF, "(Hz)"
        print "approximant is =", lalsim.GetStringFromApproximant(self.approx)
        print "phase order =", self.phaseO
        print "amplitude order =", self.ampO
        print "waveFlags struct is", self.waveFlags
        print "nonGRparams struct is", self.nonGRparams
        if self.taper==lalsim.SIM_INSPIRAL_TAPER_NONE:
            print "Tapering is set to SIM_INSPIRAL_TAPER_NONE"
        elif self.taper==lalsim.SIM_INSPIRAL_TAPER_START:
            print "Tapering is set to SIM_INSPIRAL_TAPER_START"
        elif self.taper==lalsim.SIM_INSPIRAL_TAPER_END:
            print "Tapering is set to SIM_INSPIRAL_TAPER_END"
        elif self.taper==lalsim.SIM_INSPIRAL_TAPER_STARTEND:
            print "Tapering is set to SIM_INSPIRAL_TAPER_STARTEND"
        else:
            print "Warning! Invalid value for taper:", self.taper

    def copy_sim_inspiral(self, row):
        """
        Fill this ChooseWaveformParams with the fields of a
        row of a SWIG wrapped lalmetaio.SimInspiral table

        NB: SimInspiral table does not contain deltaT, deltaF, fref, fmax,
        lambda1, lambda2, waveFlags, nonGRparams, or detector fields, but
        ChooseWaveformParams does have these fields.
        This function will not alter these fields, so their values will
        be whatever values the instance previously had.
        """
        self.phiref = row.coa_phase
        self.m1 = row.mass1 * lal.MSUN_SI
        self.m2 = row.mass2 * lal.MSUN_SI
        self.s1x = row.spin1x
        self.s1y = row.spin1y
        self.s1z = row.spin1z
        self.s2x = row.spin2x
        self.s2y = row.spin2y
        self.s2z = row.spin2z
        self.fmin = row.f_lower
        self.dist = row.distance * lal.PC_SI * 1.e6
        self.incl = row.inclination
        self.ampO = row.amp_order
        self.phaseO = lalsim.GetOrderFromString(row.waveform)
        self.approx = lalsim.GetApproximantFromString(row.waveform)
        self.theta = row.latitude # Declination
        self.phi = row.longitude # Right ascension
        self.radec = True # Flag to interpret (theta,phi) as (DEC,RA)
        self.psi = row.polarization
        self.tref = row.geocent_end_time + 1e-9*row.geocent_end_time_ns
        self.taper = lalsim.GetTaperFromString(row.taper)

    def copy_lsctables_sim_inspiral(self, row):
        """
        Fill this ChooseWaveformParams with the fields of a
        row of an lsctables.SimInspiral table
        (i.e. SimInspiral table in the format as read from a file)

        NB: SimInspiral table does not contain deltaT, deltaF, fref, fmax,
        lambda1, lambda2, waveFlags, nonGRparams, or detector fields, but
        ChooseWaveformParams does have these fields.
        This function will not alter these fields, so their values will
        be whatever values the instance previously had.

        Adapted from code by Chris Pankow
        """
        # Convert from lsctables.SimInspiral --> lalmetaio.SimInspiral
        swigrow = lalmetaio.SimInspiralTable()
        for simattr in lsctables.SimInspiralTable.validcolumns.keys():
            if simattr in ["waveform", "source", "numrel_data", "taper"]:
                # unicode -> char* doesn't work
                setattr(swigrow, simattr, str(getattr(row, simattr)))
            else:
                setattr(swigrow, simattr, getattr(row, simattr))
        # Call the function to read lalmetaio.SimInspiral format
        self.copy_sim_inspiral(swigrow)

def xml_to_ChooseWaveformParams_array(fname, minrow=None, maxrow=None,
        deltaT=1./4096., fref=0., lambda1=0., lambda2=0., waveFlags=None,
        nonGRparams=None, detector="H1", deltaF=None, fmax=0.):
    """
    Function to read an xml file 'fname' containing a SimInspiralTable,
    convert rows of the SimInspiralTable into ChooseWaveformParams instances
    and return an array of the ChooseWaveformParam instances

    Can optionally give 'minrow' and 'maxrow' to convert only rows
    in the range (starting from zero) [minrow, maxrow). If these arguments
    are not given, this function will convert the whole SimInspiral table.

    The rest of the optional arguments are the fields in ChooseWaveformParams
    that are not present in SimInspiral tables. Any of these arguments not given
    values will use the standard default values of ChooseWaveformParams.
    """
    xmldoc = utils.load_filename(fname, contenthandler=ligolw.LIGOLWContentHandler)
    try:
        # Read SimInspiralTable from the xml file, set row bounds
        sim_insp = lsctables.SimInspiralTable.get_table(xmldoc)
        length = len(sim_insp)
        if not minrow and not maxrow:
            minrow = 0
            maxrow = length
        else:
            assert minrow >= 0
            assert minrow <= maxrow
            assert maxrow <= length
        rng = range(minrow,maxrow)
        # Create a ChooseWaveformParams for each requested row
        Ps = [ChooseWaveformParams(deltaT=deltaT, fref=fref, lambda1=lambda1,
            lambda2=lambda2, waveFlags=waveFlags, nonGRparams=nonGRparams,
            detector=detector, deltaF=deltaF, fmax=fmax) for i in rng]
        # Copy the information from requested rows to the ChooseWaveformParams
        [Ps[i-minrow].copy_lsctables_sim_inspiral(sim_insp[i]) for i in rng]
    except ValueError:
        print >>sys.stderr, "No SimInspiral table found in xml file"
    return Ps


#
# Classes for computing inner products of waveforms
#
class InnerProduct(object):
    """
    Base class for inner products
    """
    def __init__(self, fLow=10., fMax=None, fNyq=2048., deltaF=1./8.,
            psd=lalsim.SimNoisePSDaLIGOZeroDetHighPower, analyticPSD_Q=True,
            inv_spec_trunc_Q=False, T_spec=0.):
        self.fLow = fLow # min limit of integration
        self.fMax = fMax # max limit of integration
        self.fNyq = fNyq # max freq. in arrays whose IP will be computed
        self.deltaF = deltaF
        self.deltaT = 1./2./self.fNyq
        self.len1side = int(fNyq/deltaF)+1 # length of Hermitian arrays
        self.len2side = 2*(self.len1side-1) # length of non-Hermitian arrays
        self.weights = np.zeros(self.len1side)
        self.weights2side = np.zeros(self.len2side)
        if self.fMax is None:
            self.fMax = self.fNyq
        assert self.fMax <= self.fNyq
        self.minIdx = int(round(self.fLow/deltaF))
        self.maxIdx = int(round(self.fMax/deltaF))
        # Fill 1-sided (Herm.) weights from psd
        if analyticPSD_Q is True:
            for i in range(self.minIdx,self.maxIdx): # set weights = 1/Sn(f)
                self.weights[i] = 1./psd(i*deltaF)
        elif analyticPSD_Q is False:
            if isinstance(psd, lal.REAL8FrequencySeries):
                assert psd.f0 == 0. # don't want heterodyned psd
                assert abs(psd.deltaF - self.deltaF) <= TOL_DF
                fPSD = (psd.data.length - 1) * psd.deltaF # -1 b/c start at f=0
                assert self.fMax <= fPSD
                for i in range(self.minIdx,self.maxIdx):
                    if psd.data.data[i] != 0.:
                        self.weights[i] = 1./psd.data.data[i]
            else: # if we get here psd must be an array
                fPSD = (len(psd) - 1) * self.deltaF # -1 b/c start at f=0
                assert self.fMax <= fPSD
                for i in range(self.minIdx,self.maxIdx):
                    if psd[i] != 0.:
                        self.weights[i] = 1./psd[i]
        else:
            raise ValueError("analyticPSD_Q must be either True or False")

        # Do inverse spectrum truncation if requested
        if inv_spec_trunc_Q is True and T_spec is not 0.:
            N_spec = int(T_spec / self.deltaT ) # number of non-zero TD pts
            # Ensure you will have some uncorrupted region in IP time series
            assert N_spec < self.len2side / 2
            # Create workspace arrays
            WFD = lal.CreateCOMPLEX16FrequencySeries('FD root inv. spec.',
                    lal.LIGOTimeGPS(0.), 0., self.deltaF,
                    lal.DimensionlessUnit, self.len1side)
            WTD = lal.CreateREAL8TimeSeries('TD root inv. spec.',
                    lal.LIGOTimeGPS(0.), 0., self.deltaT,
                    lal.DimensionlessUnit, self.len2side)
            fwdplan = lal.CreateForwardREAL8FFTPlan(self.len2side, 0)
            revplan = lal.CreateReverseREAL8FFTPlan(self.len2side, 0)
            WFD.data.data[:] = np.sqrt(self.weights) # W_FD is 1/sqrt(S_n(f))
            WFD.data.data[0] = WFD.data.data[-1] = 0. # zero 0, f_Nyq bins
            lal.REAL8FreqTimeFFT(WTD, WFD, revplan) # IFFT to TD
            for i in xrange(N_spec/2, self.len2side - N_spec/2):
                WTD.data.data[i] = 0. # Zero all but T_spec/2 ends of W_TD
            lal.REAL8TimeFreqFFT(WFD, WTD, fwdplan) # FFT back to FD
            WFD.data.data[0] = WFD.data.data[-1] = 0. # zero 0, f_Nyq bins
            # Square to get trunc. inv. PSD
            self.weights = np.abs(WFD.data.data*WFD.data.data)

        # Create 2-sided (non-Herm.) weights from 1-sided (Herm.) weights
        # They should be packed monotonically, e.g.
        # W(-N/2 df), ..., W(-df) W(0), W(df), ..., W( (N/2-1) df)
        # In particular,freqs = +-i*df are in N/2+-i bins of array
        self.weights2side[:len(self.weights)] = self.weights[::-1]
        self.weights2side[len(self.weights)-1:] = self.weights[0:-1]

    def ip(self, h1, h2):
        """
        Compute inner product between two COMPLEX16Frequency Series
        """
        raise Exception("This is the base InnerProduct class! Use a subclass")

    def norm(self, h):
        """
        Compute norm of a COMPLEX16Frequency Series
        """
        raise Exception("This is the base InnerProduct class! Use a subclass")


class RealIP(InnerProduct):
    """
    Real-valued inner product. self.ip(h1,h2) computes

             fNyq
    4 Re int      h1(f) h2*(f) / Sn(f) df
             fLow

    And similarly for self.norm(h1)

    DOES NOT maximize over time or phase
    """
    def ip(self, h1, h2):
        """
        Compute inner product between two COMPLEX16Frequency Series
        """
        assert h1.data.length == self.len1side
        assert h2.data.length == self.len1side
        assert abs(h1.deltaF-h2.deltaF) <= TOL_DF\
                and abs(h1.deltaF-self.deltaF) <= TOL_DF
        val = np.sum(np.conj(h1.data.data)*h2.data.data*self.weights)
        val = 4. * self.deltaF * np.real(val)
        return val

    def norm(self, h):
        """
        Compute norm of a COMPLEX16Frequency Series
        """
        assert h.data.length == self.len1side
        assert abs(h.deltaF-self.deltaF) <= TOL_DF
        val = np.sum(np.conj(h.data.data)*h.data.data*self.weights)
        val = np.sqrt( 4. * self.deltaF * np.abs(val) )
        return val


class HermitianComplexIP(InnerProduct):
    """
    Complex-valued inner product. self.ip(h1,h2) computes

          fNyq
    4 int      h1(f) h2*(f) / Sn(f) df
          fLow

    And similarly for self.norm(h1)

    N.B. Assumes h1, h2 are Hermitian - i.e. they store only positive freqs.
         with negative freqs. given by h(-f) = h*(f)
    DOES NOT maximize over time or phase
    """
    def ip(self, h1, h2):
        """
        Compute inner product between two COMPLEX16Frequency Series
        """
        assert h1.data.length == self.len1side
        assert h2.data.length == self.len1side
        assert abs(h1.deltaF-h2.deltaF) <= TOL_DF\
                and abs(h1.deltaF-self.deltaF) <= TOL_DF
        val = np.sum(np.conj(h1.data.data)*h2.data.data*self.weights)
        val *= 4. * self.deltaF
        return val

    def norm(self, h):
        """
        Compute norm of a COMPLEX16Frequency Series
        """
        assert h.data.length == self.len1side
        assert abs(h.deltaF-self.deltaF) <= TOL_DF
        val = np.sum(np.conj(h.data.data)*h.data.data*self.weights)
        val = np.sqrt( 4. * self.deltaF * np.abs(val) )
        return val


class ComplexIP(InnerProduct):
    """
    Complex-valued inner product. self.ip(h1,h2) computes

          fNyq
    2 int      h1(f) h2*(f) / Sn(f) df
          -fNyq

    And similarly for self.norm(h1)

    N.B. DOES NOT assume h1, h2 are Hermitian - they should contain negative
         and positive freqs. packed as
    [ -N/2 * df, ..., -df, 0, df, ..., (N/2-1) * df ]
    DOES NOT maximize over time or phase
    """
    def ip(self, h1, h2):
        """
        Compute inner product between two COMPLEX16Frequency Series
        """
        assert h1.data.length==h2.data.length==self.len2side
        assert abs(h1.deltaF-h2.deltaF) <= TOL_DF\
                and abs(h1.deltaF-self.deltaF) <= TOL_DF
        val = 0.
        val = np.sum( np.conj(h1.data.data)*h2.data.data*self.weights2side )
        val *= 2. * self.deltaF
        return val

    def norm(self, h):
        """
        Compute norm of a COMPLEX16Frequency Series
        """
        assert h.data.length==self.len2side
        assert abs(h.deltaF-self.deltaF) <= TOL_DF
        length = h.data.length
        val = 0.
        val = np.sum( np.conj(h.data.data)*h.data.data*self.weights2side )
        val = np.sqrt( 2. * self.deltaF * np.abs(val) )
        return val

class Overlap(InnerProduct):
    """
    Inner product maximized over time and phase. self.ip(h1,h2) computes:

                  fNyq
    max 4 Abs int      h1*(f,tc) h2(f) / Sn(f) df
     tc           fLow

    h1, h2 must be COMPLEX16FrequencySeries defined in [0, fNyq]
    (with the negative frequencies implicitly given by Hermitianity)

    If self.full_output==False: returns
        The maximized (real-valued, > 0) overlap
    If self.full_output==True: returns
        The maximized overlap
        The entire COMPLEX16TimeSeries of overlaps for each possible time shift
        The index of the above time series at which the maximum occurs
        The phase rotation which maximizes the real-valued overlap
    """
    def __init__(self, fLow=10., fMax=None, fNyq=2048., deltaF=1./8.,
            psd=lalsim.SimNoisePSDaLIGOZeroDetHighPower, analyticPSD_Q=True,
            inv_spec_trunc_Q=False, T_spec=0., full_output=False):
        super(Overlap, self).__init__(fLow, fMax, fNyq, deltaF, psd,
                analyticPSD_Q, inv_spec_trunc_Q, T_spec) # Call base constructor
        self.full_output = full_output
        self.deltaT = 1./self.deltaF/self.len2side
        self.revplan = lal.CreateReverseCOMPLEX16FFTPlan(self.len2side, 0)
        self.intgd = lal.CreateCOMPLEX16FrequencySeries("SNR integrand", 
                lal.LIGOTimeGPS(0.), 0., self.deltaF, lal.HertzUnit,
                self.len2side)
        self.ovlp = lal.CreateCOMPLEX16TimeSeries("Complex overlap", 
                lal.LIGOTimeGPS(0.), 0., self.deltaT, lal.DimensionlessUnit,
                self.len2side)

    def ip(self, h1, h2):
        """
        Compute inner product between two Hermitian COMPLEX16Frequency Series
        """
        assert h1.data.length==h2.data.length==self.len1side
        assert abs(h1.deltaF-h2.deltaF) <= TOL_DF\
                and abs(h1.deltaF-self.deltaF) <= TOL_DF
        # Tabulate the SNR integrand
        # Set negative freqs. of integrand to zero
        self.intgd.data.data[:self.len1side] = np.zeros(self.len1side)
        # Fill positive freqs with inner product integrand
        temp = 4.*np.conj(h1.data.data) * h2.data.data * self.weights
        self.intgd.data.data[self.len1side-1:] = temp[:-1]
        # Reverse FFT to get overlap for all possible reference times
        lal.COMPLEX16FreqTimeFFT(self.ovlp, self.intgd, self.revplan)
        rhoSeries = np.abs(self.ovlp.data.data)
        rho = rhoSeries.max()
        if self.full_output==False:
            # Return overlap maximized over time, phase
            return rho
        else:
            # Return max overlap, full overlap time series and other info
            rhoIdx = rhoSeries.argmax()
            rhoPhase = np.angle(self.ovlp.data.data[rhoIdx])
            # N.B. Copy rho(t) to a new TimeSeries, so we don't return a
            # reference to the TimeSeries belonging to the class (self.ovlp),
            # which will be overwritten if its ip() method is called again later
            rhoTS = lal.CreateCOMPLEX16TimeSeries("Complex overlap",
                lal.LIGOTimeGPS(0.), 0., self.deltaT, lal.DimensionlessUnit,
                self.len2side)
            rhoTS.data.data[:] = self.ovlp.data.data[:]
            return rho, rhoTS, rhoIdx, rhoPhase

    def norm(self, h):
        """
        Compute norm of a COMPLEX16Frequency Series
        """
        assert h.data.length == self.len1side
        assert abs(h.deltaF-self.deltaF) <= TOL_DF
        val = 0.
        val = np.sum( np.conj(h.data.data)*h.data.data *self.weights)
        val = np.sqrt( 4. * self.deltaF * np.abs(val) )
        return val

    def wrap_times(self):
        """
        Return a vector of wrap-around time offsets, i.e.
        [ 0, dt, 2 dt, ..., N dt, -(N-1) dt, -(N-1) dt, ..., -2 dt, -dt ]

        This is useful in conjunction with the 'full_output' option to plot
        the overlap vs timeshift. e.g. do:

        IP = Overlap(full_output=True)
        t = IP.wrap_times()
        rho, ovlp, rhoIdx, rhoPhase = IP.ip(h1, h2)
        plot(t, abs(ovlp))
        """
        tShift = np.arange(self.len2side) * self.deltaT
        for i in range(self.len1side,self.len2side):
            tShift[i] -= self.len2side * self.deltaT
        return tShift

class ComplexOverlap(InnerProduct):
    """
    Inner product maximized over time and polarization angle. 
    This inner product does not assume Hermitianity and is therefore
    valid for waveforms that are complex in the TD, e.g. h+(t) + 1j hx(t).
    self.IP(h1,h2) computes:

                  fNyq
    max 2 Abs int      h1*(f,tc) h2(f) / Sn(f) df
     tc          -fNyq

    h1, h2 must be COMPLEX16FrequencySeries defined in [-fNyq, fNyq-deltaF]
    At least one of which should be non-Hermitian for the maximization
    over phase to work properly.

    If self.full_output==False: returns
        The maximized overlap
    If self.full_output==True: returns
        The maximized overlap
        The entire COMPLEX16TimeSeries of overlaps for each possible time shift
        The index of the above time series at which the maximum occurs
        The phase rotation which maximizes the real-valued overlap
    """
    def __init__(self, fLow=10., fMax=None, fNyq=2048., deltaF=1./8.,
            psd=lalsim.SimNoisePSDaLIGOZeroDetHighPower, analyticPSD_Q=True,
            inv_spec_trunc_Q=False, T_spec=0., full_output=False):
        super(ComplexOverlap, self).__init__(fLow, fMax, fNyq, deltaF, psd,
                analyticPSD_Q, inv_spec_trunc_Q, T_spec) # Call base constructor
        self.full_output=full_output
        self.deltaT = 1./self.deltaF/self.len2side
        # Create FFT plan and workspace vectors
        self.revplan=lal.CreateReverseCOMPLEX16FFTPlan(self.len2side, 0)
        self.intgd = lal.CreateCOMPLEX16FrequencySeries("SNR integrand", 
                lal.LIGOTimeGPS(0.), 0., self.deltaF,
                lal.HertzUnit, self.len2side)
        self.ovlp = lal.CreateCOMPLEX16TimeSeries("Complex overlap", 
                lal.LIGOTimeGPS(0.), 0., self.deltaT, lal.DimensionlessUnit,
                self.len2side)

    def ip(self, h1, h2):
        """
        Compute inner product between two non-Hermitian COMPLEX16FrequencySeries
        """
        assert h1.data.length==h2.data.length==self.len2side
        assert abs(h1.deltaF-h2.deltaF) <= TOL_DF\
                and abs(h1.deltaF-self.deltaF) <= TOL_DF
        # Tabulate the SNR integrand
        self.intgd.data.data = 2*np.conj(h1.data.data)\
                *h2.data.data*self.weights2side
        # Reverse FFT to get overlap for all possible reference times
        lal.COMPLEX16FreqTimeFFT(self.ovlp, self.intgd, self.revplan)
        rhoSeries = np.abs(self.ovlp.data.data)
        rho = rhoSeries.max()
        if self.full_output==False:
            # Return overlap maximized over time, phase
            return rho
        else:
            # Return max overlap, full overlap time series and other info
            rhoIdx = rhoSeries.argmax()
            rhoPhase = np.angle(self.ovlp.data.data[rhoIdx])
            # N.B. Copy rho(t) to a new TimeSeries, so we don't return a
            # reference to the TimeSeries belonging to the class (self.ovlp),
            # which will be overwritten if its ip() method is called again later
            rhoTS = lal.CreateCOMPLEX16TimeSeries("Complex overlap",
                lal.LIGOTimeGPS(0.), 0., self.deltaT, lal.DimensionlessUnit,
                self.len2side)
            rhoTS.data.data[:] = self.ovlp.data.data[:]
            return rho, rhoTS, rhoIdx, rhoPhase

    def norm(self, h):
        """
        Compute norm of a non-Hermitian COMPLEX16FrequencySeries
        """
        assert h.data.length==self.len2side
        assert abs(h.deltaF-self.deltaF) <= TOL_DF
        val = np.sum( np.conj(h.data.data)*h.data.data *self.weights2side)
        val = np.sqrt( 2. * self.deltaF * np.abs(val) )
        return val

    def wrap_times(self):
        """
        Return a vector of wrap-around time offsets, i.e.
        [ 0, dt, 2 dt, ..., N dt, -(N-1) dt, -(N-1) dt, ..., -2 dt, -dt ]

        This is useful in conjunction with the 'full_output' option to plot
        the overlap vs timeshift. e.g. do:

        IP = ComplexOverlap(full_output=True)
        t = IP.wrap_times()
        rho, ovlp, rhoIdx, rhoPhase = IP.ip(h1, h2)
        plot(t, abs(ovlp))
        """
        tShift = np.arange(self.len2side) * self.deltaT
        for i in range(self.len1side,self.len2side):
            tShift[i] -= self.len2side * self.deltaT
        return tShift


#
# Antenna pattern functions
#
def Fplus(theta, phi, psi):
    """
    Antenna pattern as a function of polar coordinates measured from
    directly overhead a right angle interferometer and polarization angle
    """
    return 0.5*(1. + cos(theta)*cos(theta))*cos(2.*phi)*cos(2.*psi)\
            - cos(theta)*sin(2.*phi)*sin(2.*psi)

def Fcross(theta, phi, psi):
    """
    Antenna pattern as a function of polar coordinates measured from
    directly overhead a right angle interferometer and polarization angle
    """
    return 0.5*(1. + cos(theta)*cos(theta))*cos(2.*phi)*sin(2.*psi)\
            + cos(theta)*sin(2.*phi)*cos(2.*psi)

#
# Mass parameter conversion functions - note they assume m1 >= m2
#
def mass1(Mc, eta):
    """Compute larger component mass from Mc, eta"""
    return 0.5*Mc*eta**(-3./5.)*(1. + sqrt(1 - 4.*eta))

def mass2(Mc, eta):
    """Compute smaller component mass from Mc, eta"""
    return 0.5*Mc*eta**(-3./5.)*(1. - sqrt(1 - 4.*eta))

def mchirp(m1, m2):
    """Compute chirp mass from component masses"""
    return (m1*m2)**(3./5.)*(m1+m2)**(-1./5.)

def symRatio(m1, m2):
    """Compute symmetric mass ratio from component masses"""
    return m1*m2/(m1+m2)/(m1+m2)

def m1m2(Mc, eta):
    """Compute component masses from Mc, eta. Returns m1 >= m2"""
    m1 = 0.5*Mc*eta**(-3./5.)*(1. + sqrt(1 - 4.*eta))
    m2 = 0.5*Mc*eta**(-3./5.)*(1. - sqrt(1 - 4.*eta))
    return m1, m2

def Mceta(m1, m2):
    """Compute chirp mass and symmetric mass ratio from component masses"""
    Mc = (m1*m2)**(3./5.)*(m1+m2)**(-1./5.)
    eta = m1*m2/(m1+m2)/(m1+m2)
    return Mc, eta

#
# Other utility functions
#
def unwind_phase(phase,thresh=5.):
    """
    Unwind an array of values of a periodic variable so that it does not jump
    discontinuously when it hits the periodic boundary, but changes smoothly
    outside the periodic range.

    Note: 'thresh', which determines if a discontinuous jump occurs, should be
    somewhat less than the periodic interval. Empirically, 5 is usually a safe
    value of thresh for a variable with period 2 pi.
    """
    cnt = 0 # count number of times phase wraps around branch cut
    length = len(phase)
    unwound = np.zeros(length)
    unwound[0] = phase[0]
    for i in range(1,length):
        if phase[i-1] - phase[i] > thresh: # phase wrapped forward
            cnt += 1
        elif phase[i] - phase[i-1] > thresh: # phase wrapped backward
            cnt += 1
        unwound[i] = phase[i] + cnt * 2. * np.pi
    return unwound

def nextPow2(length):
    """
    Find next power of 2 <= length
    """
    return int(2**np.ceil(np.log2(length)))

def findDeltaF(P):
    """
    Given ChooseWaveformParams P, generate the TD waveform,
    round the length to the next power of 2,
    and find the frequency bin size corresponding to this length.
    This is useful b/c deltaF is needed to define an inner product
    which is needed for norm_hoft and norm_hoff functions
    """
    h = hoft(P)
    return 1./(nextPow2(h.data.length) * P.deltaT)

def estimateWaveformDuration(P):
    """
    Input:  P
    Output:estimated duration (in s) based on Newtonian inspiral from P.fmin to infinite frequency
    """
    fM  = P.fmin*(P.m1+P.m2)*lal.G_SI / lal.C_SI**3
    eta = symRatio(P.m1,P.m2)
    Msec = (P.m1+P.m2)*lal.G_SI / lal.C_SI**3
    return Msec*5./256. / eta* np.power((lal.PI*fM),-8./3.)
    

def sanitize_eta(eta, tol=1.e-10, exception='error'):
    """
    If 'eta' is slightly outside the physically allowed range for
    symmetric mass ratio, push it back in. If 'eta' is further
    outside the physically allowed range, throw an error
    or return a special value.
    Explicitly:
        - If 'eta' is in [tol, 0.25], return eta.
        - If 'eta' is in [0, tol], return tol.
        - If 'eta' in is (0.25, 0.25+tol], return 0.25
        - If 'eta' < 0 OR eta > 0.25+tol,
            - if exception=='error' raise a ValueError
            - if exception is anything else, return exception
    """
    MIN = 0.
    MAX = 0.25
    if eta < MIN or eta > MAX+tol:
        if exception=='error':
            raise ValueError("Value of eta outside the physicaly-allowed range of symmetric mass ratio.")
        else:
            return exception
    elif eta < tol:
        return tol
    elif eta > MAX:
        return MAX
    else:
        return eta

#
# Utilities using Overlap based classes to calculate physical quantities
#
def single_ifo_snr(data, psd, fNyq, fmin=None, fmax=None):
    """
    Calculate single IFO SNR using inner product class.
    """
    assert data.deltaF == psd.deltaF
    IP = ComplexIP(fLow=fmin, fNyq=fNyq, deltaF=psd.deltaF, psd=psd, fMax=fmax, analyticPSD_Q=isinstance(psd, types.FunctionType))
    return IP.norm(data)

#
# Functions to generate waveforms
#
def hoft(P, Fp=None, Fc=None):
    """
    Generate a TD waveform from ChooseWaveformParams P
    You may pass in antenna patterns Fp, Fc. If none are provided, they will
    be computed from the information in ChooseWaveformParams.

    Returns a REAL8TimeSeries object
    """
    hp, hc = lalsim.SimInspiralChooseTDWaveform(P.phiref, P.deltaT, P.m1, P.m2, 
            P.s1x, P.s1y, P.s1z, P.s2x, P.s2y, P.s2z, P.fmin, P.fref, P.dist, 
            P.incl, P.lambda1, P.lambda2, P.waveFlags, P.nonGRparams,
            P.ampO, P.phaseO, P.approx)

    if Fp!=None and Fc!=None:
        hp.data.data *= Fp
        hc.data.data *= Fc
        hp = lal.AddREAL8TimeSeries(hp, hc)
        ht = hp
    elif P.radec==False:
        fp = Fplus(P.theta, P.phi, P.psi)
        fc = Fcross(P.theta, P.phi, P.psi)
        hp.data.data *= fp
        hc.data.data *= fc
        hp = lal.AddREAL8TimeSeries(hp, hc)
        ht = hp
    else:
        hp.epoch = hp.epoch + P.tref
        hc.epoch = hc.epoch + P.tref
        ht = lalsim.SimDetectorStrainREAL8TimeSeries(hp, hc, 
                P.phi, P.theta, P.psi, 
                lalsim.DetectorPrefixToLALDetector(str(P.detector)))
    if P.taper != lalsim.SIM_INSPIRAL_TAPER_NONE: # Taper if requested
        lalsim.SimInspiralREAL8WaveTaper(ht.data, P.taper)
    if P.deltaF is not None:
        TDlen = int(1./P.deltaF * 1./P.deltaT)
        assert TDlen >= ht.data.length
        ht = lal.ResizeREAL8TimeSeries(ht, 0, TDlen)
    return ht

def hoff(P, Fp=None, Fc=None, fwdplan=None):
    """
    Generate a FD waveform from ChooseWaveformParams P.
    Will return a COMPLEX16FrequencySeries object.

    If P.approx is a FD approximant, hoff_FD is called.
    This path calls SimInspiralChooseFDWaveform
        fwdplan must be None for FD approximants.

    If P.approx is a TD approximant, hoff_TD is called.
    This path calls ChooseTDWaveform and performs an FFT.
        The TD waveform will be zero-padded so it's Fourier transform has
        frequency bins of size P.deltaT.
        If P.deltaF == None, the TD waveform will be zero-padded
        to the next power of 2.
    """
    # For FD approximants, use the ChooseFDWaveform path = hoff_FD
    if lalsim.SimInspiralImplementedFDApproximants(P.approx)==1:
        # Raise exception if unused arguments were specified
        if fwdplan is not None:
            raise ValueError('FFT plan fwdplan given with FD approximant.\nFD approximants cannot use this.')
        hf = hoff_FD(P, Fp, Fc)

    # For TD approximants, do ChooseTDWaveform + FFT path = hoff_TD
    else:
        hf = hoff_TD(P, Fp, Fc, fwdplan)

    return hf

def hoff_TD(P, Fp=None, Fc=None, fwdplan=None):
    """
    Generate a FD waveform from ChooseWaveformParams P
    by creating a TD waveform, zero-padding and
    then Fourier transforming with FFTW3 forward FFT plan fwdplan

    If P.deltaF==None, just pad up to next power of 2
    If P.deltaF = 1/X, will generate a TD waveform, zero-pad to length X seconds
        and then FFT. Will throw an error if waveform is longer than X seconds

    If you do not provide a forward FFT plan, one will be created.
    If you are calling this function many times, you may to create it
    once beforehand and pass it in, e.g.:
    fwdplan=lal.CreateForwardREAL8FFTPlan(TDlen,0)

    You may pass in antenna patterns Fp, Fc. If none are provided, they will
    be computed from the information in ChooseWaveformParams

    Returns a COMPLEX16FrequencySeries object
    """
    ht = hoft(P, Fp, Fc)

    if P.deltaF == None: # h(t) was not zero-padded, so do it now
        TDlen = nextPow2(ht.data.length)
        ht = lal.ResizeREAL8TimeSeries(ht, 0, TDlen)
    else: # Check zero-padding was done to expected length
        TDlen = int(1./P.deltaF * 1./P.deltaT)
        assert TDlen == ht.data.length
    
    if fwdplan==None:
        fwdplan=lal.CreateForwardREAL8FFTPlan(TDlen,0)
    FDlen = TDlen/2+1
    hf = lal.CreateCOMPLEX16FrequencySeries("Template h(f)", 
            ht.epoch, ht.f0, 1./ht.deltaT/TDlen, lal.HertzUnit,
            FDlen)
    lal.REAL8TimeFreqFFT(hf, ht, fwdplan)
    return hf

def hoff_FD(P, Fp=None, Fc=None):
    """
    Generate a FD waveform for a FD approximant.
    Note that P.deltaF (which is None by default) must be set
    """
    if P.deltaF is None:
        raise ValueError('None given for freq. bin size P.deltaF')

    hptilde, hctilde = lalsim.SimInspiralChooseFDWaveform(P.phiref, P.deltaF,
            P.m1, P.m2, P.s1x, P.s1y, P.s1z, P.s2x, P.s2y, P.s2z, P.fmin,
            P.fmax, P.fref, P.dist, P.incl, P.lambda1, P.lambda2, P.waveFlags,
            P.nonGRparams, P.ampO, P.phaseO, P.approx)
    if Fp is not None and Fc is not None:
        hptilde.data.data *= Fp
        hctilde.data.data *= Fc
        hptilde = lal.AddCOMPLEX16FrequencySeries(hptilde, hctilde)
        htilde = hptilde
    elif P.radec==False:
        fp = Fplus(P.theta, P.phi, P.psi)
        fc = Fcross(P.theta, P.phi, P.psi)
        hptilde.data.data *= fp
        hctilde.data.data *= fc
        hptilde = lal.AddCOMPLEX16FrequencySeries(hptilde, hctilde)
        htilde = hptilde
    else:
        raise ValueError('Must use P.radec=False for FD approximant (for now)')
    # N.B. TaylorF2(RedSpin)(Tidal)  stop filling the output array at ISCO.
    # The Hermitian inner product classes now expect the arrays to be a
    # power of two plus one. Therefore, we zero-pad the output
    # so it will work with lalsimutils inner products
    FDlen = int(1./P.deltaF/P.deltaT/2.+1)
    if htilde.data.length != FDlen:
        htilde = lal.ResizeCOMPLEX16FrequencySeries(htilde, 0, FDlen)
    return htilde

def norm_hoff(P, IP, Fp=None, Fc=None, fwdplan=None):
    """
    Generate a normalized FD waveform from ChooseWaveformParams P.
    Will return a COMPLEX16FrequencySeries object.

    If P.approx is a FD approximant, norm_hoff_FD is called.
    This path calls SimInspiralChooseFDWaveform
        fwdplan must be None for FD approximants.

    If P.approx is a TD approximant, norm_hoff_TD is called.
    This path calls ChooseTDWaveform and performs an FFT.
        The TD waveform will be zero-padded so it's Fourier transform has
        frequency bins of size P.deltaT.
        If P.deltaF == None, the TD waveform will be zero-padded
        to the next power of 2.
    """
    # For FD approximants, use the ChooseFDWaveform path = hoff_FD
    if lalsim.SimInspiralImplementedFDApproximants(P.approx)==1:
        # Raise exception if unused arguments were specified
        if fwdplan is not None:
            raise ValueError('FFT plan fwdplan given with FD approximant.\nFD approximants cannot use this.')
        hf = norm_hoff_FD(P, IP, Fp, Fc)

    # For TD approximants, do ChooseTDWaveform + FFT path = hoff_TD
    else:
        hf = norm_hoff_TD(P, IP, Fp, Fc, fwdplan)

    return hf

def norm_hoff_TD(P, IP, Fp=None, Fc=None, fwdplan=None):
    """
    Generate a waveform from ChooseWaveformParams P normalized according
    to inner product IP by creating a TD waveform, zero-padding and
    then Fourier transforming with FFTW3 forward FFT plan fwdplan.
    Returns a COMPLEX16FrequencySeries object.

    If P.deltaF==None, just pad up to next power of 2
    If P.deltaF = 1/X, will generate a TD waveform, zero-pad to length X seconds
        and then FFT. Will throw an error if waveform is longer than X seconds

    If you do not provide a forward FFT plan, one will be created.
    If you are calling this function many times, you may to create it
    once beforehand and pass it in, e.g.:
    fwdplan=lal.CreateForwardREAL8FFTPlan(TDlen,0)

    You may pass in antenna patterns Fp, Fc. If none are provided, they will
    be computed from the information in ChooseWaveformParams.

    N.B. IP and the waveform generated from P must have the same deltaF and 
        the waveform must extend to at least the highest frequency of IP's PSD.
    """
    hf = hoff_TD(P, Fp, Fc, fwdplan)
    norm = IP.norm(hf)
    hf.data.data /= norm
    return hf

def norm_hoff_FD(P, IP, Fp=None, Fc=None):
    """
    Generate a FD waveform for a FD approximant normalized according to IP.
    Note that P.deltaF (which is None by default) must be set.
    IP and the waveform generated from P must have the same deltaF and 
        the waveform must extend to at least the highest frequency of IP's PSD.
    """
    if P.deltaF is None:
        raise ValueError('None given for freq. bin size P.deltaF')

    htilde = hoff_FD(P, Fp, Fc)
    norm = IP.norm(htilde)
    htilde.data.data /= norm
    return htilde

def non_herm_hoff(P):
    """
    Generate a FD waveform with two-sided spectrum. i.e. not assuming
    the Hermitian symmetry applies
    """
    htR = hoft(P) # Generate real-valued TD waveform
    if P.deltaF == None: # h(t) was not zero-padded, so do it now
        TDlen = nextPow2(htR.data.length)
        htR = lal.ResizeREAL8TimeSeries(htR, 0, TDlen)
    else: # Check zero-padding was done to expected length
        TDlen = int(1./P.deltaF * 1./P.deltaT)
        assert TDlen == htR.data.length
    fwdplan=lal.CreateForwardCOMPLEX16FFTPlan(htR.data.length,0)
    htC = lal.CreateCOMPLEX16TimeSeries("hoft", htR.epoch, htR.f0,
            htR.deltaT, htR.sampleUnits, htR.data.length)
    # copy h(t) into a COMPLEX16 array which happens to be purely real
    for i in range(htR.data.length):
        htC.data.data[i] = htR.data.data[i]
    hf = lal.CreateCOMPLEX16FrequencySeries("Template h(f)",
            htR.epoch, htR.f0, 1./htR.deltaT/htR.data.length, lal.HertzUnit,
            htR.data.length)
    lal.COMPLEX16TimeFreqFFT(hf, htC, fwdplan)
    return hf



def hlmoft(P, Lmax=2, Fp=None, Fc=None):
    """
    Generate the TD h_lm -2-spin-weighted spherical harmonic modes of a GW
    with parameters P. Returns a SphHarmTimeSeries, a linked-list of modes with
    a COMPLEX16TimeSeries and indices l and m for each node.

    The linked list will contain all modes with l <= Lmax
    and all values of m for these l.
    """
    assert Lmax >= 2
    hlms = lalsim.SimInspiralChooseTDModes(P.phiref, P.deltaT, P.m1, P.m2,
            P.fmin, P.fref, P.dist, P.lambda1, P.lambda2, P.waveFlags,
            P.nonGRparams, P.ampO, P.phaseO, Lmax, P.approx)
    # FIXME: Add ability to taper
    # COMMENT: Add ability to generate hlmoft at a nonzero GPS time directly.
    #      USUALLY we will use the hlms in template-generation mode, so will want the event at zero GPS time

    if P.deltaF is not None:
        TDlen = int(1./P.deltaF * 1./P.deltaT)
        hxx = lalsim.SphHarmTimeSeriesGetMode(hlms, 2, 2)
        assert TDlen >= hxx.data.length
        hlms = lalsim.ResizeSphHarmTimeSeries(hlms, 0, TDlen)


    return hlms

def hlmoff(P, Lmax=2, Fp=None, Fc=None):
    """
    Generate the FD h_lm -2-spin-weighted spherical harmonic modes of a GW
    with parameters P. Returns a SphHarmTimeSeries, a linked-list of modes with
    a COMPLEX16TimeSeries and indices l and m for each node.

    The linked list will contain all modes with l <= Lmax
    and all values of m for these l.
    """

    hlms = hlmoft(P, Lmax, Fp, Fc)
    hxx = lalsim.SphHarmTimeSeriesGetMode(hlms, 2, 2)
    if P.deltaF == None: # h_lm(t) was not zero-padded, so do it now
        TDlen = nextPow2(hxx.data.length)
        hlms = lalsim.ResizeSphHarmTimeSeries(hlms, 0, TDlen)
    else: # Check zero-padding was done to expected length
        TDlen = int(1./P.deltaF * 1./P.deltaT)
        assert TDlen == hxx.data.length

    # FFT the hlms
    Hlms = lalsim.SphHarmFrequencySeriesFromSphHarmTimeSeries(hlms)

    return Hlms

def conj_hlmoff(P, Lmax=2, Fp=None, Fc=None):
    hlms = hlmoft(P, Lmax, Fp, Fc)
    hxx = lalsim.SphHarmTimeSeriesGetMode(hlms, 2, 2)
    if P.deltaF == None: # h_lm(t) was not zero-padded, so do it now
        TDlen = nextPow2(hxx.data.length)
        hlms = lalsim.ResizeSphHarmTimeSeries(hlms, 0, TDlen)
    else: # Check zero-padding was done to expected length
        TDlen = int(1./P.deltaF * 1./P.deltaT)
        assert TDlen == hxx.data.length

    # Conjugate each mode before taking FFT
    for l in range(2, Lmax+1):
        for m in range(-l, l+1):
            hxx = lalsim.SphHarmTimeSeriesGetMode(hlms, l, m)
            hxx.data.data = np.conj(hxx.data.data)
    # FFT the hlms
    Hlms = lalsim.SphHarmFrequencySeriesFromSphHarmTimeSeries(hlms)

    return Hlms

def SphHarmTimeSeries_to_dict(hlms, Lmax):
    """
    Convert a SphHarmTimeSeries SWIG-wrapped linked list into a dictionary.

    The keys are tuples of integers of the form (l,m)
    and a key-value pair will be created for each (l,m) with
    2 <= l <= Lmax, |m| <= l for which
    lalsimulation.SphHarmTimeSeriesGetMode(hlms, l, m)
    returns a non-null pointer.
    """
    hlm_dict = {}
    for l in range(2, Lmax+1):
        for m in range(-l, l+1):
            hxx = lalsim.SphHarmTimeSeriesGetMode(hlms, l, m)
            if hxx is not None:
                hlm_dict[(l,m)] = hxx

    return hlm_dict

def SphHarmFrequencySeries_to_dict(hlms, Lmax):
    """
    Convert a SphHarmFrequencySeries SWIG-wrapped linked list into a dictionary.

    The keys are tuples of integers of the form (l,m)
    and a key-value pair will be created for each (l,m) with
    2 <= l <= Lmax, |m| <= l for which
    lalsimulation.SphHarmFrequencySeriesGetMode(hlms, l, m)
    returns a non-null pointer.
    """
    hlm_dict = {}
    for l in range(2, Lmax+1):
        for m in range(-l, l+1):
            hxx = lalsim.SphHarmFrequencySeriesGetMode(hlms, l, m)
            if hxx is not None:
                hlm_dict[(l,m)] = hxx

    return hlm_dict

def complex_hoft(P, sgn=-1):
    """
    Generate a complex TD waveform from ChooseWaveformParams P
    Returns h(t) = h+(t) + 1j sgn hx(t)
    where sgn = -1 (default) or 1

    Returns a COMPLEX16TimeSeries object
    """
    assert sgn == 1 or sgn == -1
    hp, hc = lalsim.SimInspiralChooseTDWaveform(P.phiref, P.deltaT, P.m1, P.m2, 
            P.s1x, P.s1y, P.s1z, P.s2x, P.s2y, P.s2z, P.fmin, P.fref, P.dist, 
            P.incl, P.lambda1, P.lambda2, P.waveFlags, P.nonGRparams,
            P.ampO, P.phaseO, P.approx)
    if P.taper != lalsim.SIM_INSPIRAL_TAPER_NONE: # Taper if requested
        lalsim.SimInspiralREAL8WaveTaper(hp.data, P.taper)
        lalsim.SimInspiralREAL8WaveTaper(hc.data, P.taper)
    if P.deltaF is not None:
        TDlen = int(1./P.deltaF * 1./P.deltaT)
        assert TDlen >= hp.data.length
        hp = lal.ResizeREAL8TimeSeries(hp, 0, TDlen)
        hc = lal.ResizeREAL8TimeSeries(hc, 0, TDlen)

    ht = lal.CreateCOMPLEX16TimeSeries("Complex h(t)", hp.epoch, hp.f0, 
            hp.deltaT, lal.DimensionlessUnit, hp.data.length)
    ht.epoch = ht.epoch + P.tref
    ht.data.data = hp.data.data + 1j * sgn * hc.data.data
    return ht

def complex_hoff(P, sgn=-1, fwdplan=None):
    """
    CURRENTLY ONLY WORKS WITH TD APPROXIMANTS

    Generate a (non-Hermitian) FD waveform from ChooseWaveformParams P
    by creating a complex TD waveform of the form

    h(t) = h+(t) + 1j sgn hx(t)    where sgn = -1 (default) or 1

    If P.deltaF==None, just pad up to next power of 2
    If P.deltaF = 1/X, will generate a TD waveform, zero-pad to length X seconds
        and then FFT. Will throw an error if waveform is longer than X seconds

    If you do not provide a forward FFT plan, one will be created.
    If you are calling this function many times, it is best to create it
    once beforehand and pass it in, e.g.:
    fwdplan=lal.CreateForwardCOMPLEX16FFTPlan(TDlen,0)

    Returns a COMPLEX16FrequencySeries object
    """
    ht = complex_hoft(P, sgn)

    if P.deltaF == None: # h(t) was not zero-padded, so do it now
        TDlen = nextPow2(ht.data.length)
        ht = lal.ResizeCOMPLEX16TimeSeries(ht, 0, TDlen)
    else: # Check zero-padding was done to expected length
        TDlen = int(1./P.deltaF * 1./P.deltaT)
        assert TDlen == ht.data.length

    if fwdplan==None:
        fwdplan=lal.CreateForwardCOMPLEX16FFTPlan(TDlen,0)

    FDlen = TDlen/2+1
    hf = lal.CreateCOMPLEX16FrequencySeries("Template h(f)", 
            ht.epoch, ht.f0, 1./ht.deltaT/TDlen, lal.HertzUnit,
            TDlen)
    lal.COMPLEX16TimeFreqFFT(hf, ht, fwdplan)
    return hf

def complex_norm_hoff(P, IP, sgn=-1, fwdplan=None):
    """
    CURRENTLY ONLY WORKS WITH TD APPROXIMANTS

    Generate a (non-Hermitian) FD waveform from ChooseWaveformParams P
    by creating a complex TD waveform of the form

    h(t) = h+(t) + 1j sgn hx(t)    where sgn = -1 (default) or 1

    If P.deltaF==None, just pad up to next power of 2
    If P.deltaF = 1/X, will generate a TD waveform, zero-pad to length X seconds
        and then FFT. Will throw an error if waveform is longer than X seconds

    If you do not provide a forward FFT plan, one will be created.
    If you are calling this function many times, it is best to create it
    once beforehand and pass it in, e.g.:
    fwdplan=lal.CreateForwardCOMPLEX16FFTPlan(TDlen,0)

    Returns a COMPLEX16FrequencySeries object
    """
    htilde = complex_hoff(P, sgn, fwdplan)
    norm = IP.norm(htilde)
    htilde.data.data /= norm
    return htilde

def frame_data_to_hoft(fname, channel, start=None, stop=None, window_shape=0.,
        verbose=True):
    """
    Function to read in data in the frame format and convert it to 
    a REAL8TimeSeries. fname is the path to a LIGO cache file.

    Applies a Tukey window to the data with shape parameter 'window_shape'.
    N.B. if window_shape=0, the window is the identity function
         if window_shape=1, the window becomes a Hann window
         if 0<window_shape<1, the data will transition from zero to full
            strength over that fraction of each end of the data segment.
    """
    if verbose:
        print " ++ Loading from cache ", fname, channel
    with open(fname) as cfile:
        cachef = Cache.fromfile(cfile)
    for i in range(len(cachef))[::-1]:
        # FIXME: HACKHACKHACK
        if cachef[i].observatory != channel[0]:
            del cachef[i]
    if verbose:
        print cachef.to_segmentlistdict()
    fcache = frutils.FrameCache(cachef)
    # FIXME: Horrible, horrible hack -- will only work if all requested channels
    # span the cache *exactly*
    if start is None:
        start = cachef.to_segmentlistdict()[channel[0]][0][0]
    if stop is None:
        stop = cachef.to_segmentlistdict()[channel[0]][-1][-1]
    
    ht = fcache.fetch(channel, start, stop)
        
    tmp = lal.CreateREAL8TimeSeries("h(t)", 
            lal.LIGOTimeGPS(float(ht.metadata.segments[0][0])),
            0., ht.metadata.dt, lal.DimensionlessUnit, len(ht))
    print   "  ++ Frame data sampling rate ", 1./tmp.deltaT, " and epoch ", string_gps_pretty_print(tmp.epoch)
    tmp.data.data[:] = ht
    # Window the data - N.B. default is identity (no windowing)
    hoft_window = lal.CreateTukeyREAL8Window(tmp.data.length, window_shape)
    tmp.data.data *= hoft_window.data.data

    return tmp

def frame_data_to_hoff(fname, channel, start=None, stop=None, TDlen=0,
        window_shape=0., verbose=True):
    """
    Function to read in data in the frame format
    and convert it to a COMPLEX16FrequencySeries holding
    h(f) = FFT[ h(t) ]

    Before the FFT, applies a Tukey window with shape parameter 'window_shape'.
    N.B. if window_shape=0, the window is the identity function
         if window_shape=1, the window becomes a Hann window
         if 0<window_shape<1, the data will transition from zero to full
            strength over that fraction of each end of the data segment.

    If TDlen == -1, do not zero-pad the TD waveform before FFTing
    If TDlen == 0 (default), zero-pad the TD waveform to the next power of 2
    If TDlen == N, zero-pad the TD waveform to length N before FFTing
    """
    ht = frame_data_to_hoft(fname, channel, start, stop, window_shape, verbose)

    tmplen = ht.data.length
    if TDlen == -1:
        TDlen = tmplen
    elif TDlen==0:
        TDlen = nextPow2(tmplen)
    else:
        assert TDlen >= tmplen

    ht = lal.ResizeREAL8TimeSeries(ht, 0, TDlen)
    for i in range(tmplen,TDlen):
        ht.data.data[i] = 0.

    fwdplan=lal.CreateForwardREAL8FFTPlan(TDlen,0)
    hf = lal.CreateCOMPLEX16FrequencySeries("h(f)", 
            ht.epoch, ht.f0, 1./deltaT/TDlen, lal.HertzUnit,
            TDlen/2+1)
    lal.REAL8TimeFreqFFT(hf, ht, fwdplan)
    return hf


def frame_data_to_non_herm_hoff(fname, channel, start=None, stop=None, TDlen=0,
        window_shape=0., verbose=True):
    """
    Function to read in data in the frame format
    and convert it to a COMPLEX16FrequencySeries 
    h(f) = FFT[ h(t) ]
    Create complex FD data that does not assume Hermitianity - i.e.
    contains positive and negative freq. content

    Before the FFT, applies a Tukey window with shape parameter 'window_shape'.
    N.B. if window_shape=0, the window is the identity function
         if window_shape=1, the window becomes a Hann window
         if 0<window_shape<1, the data will transition from zero to full
            strength over that fraction of each end of the data segment.

    If TDlen == -1, do not zero-pad the TD waveform before FFTing
    If TDlen == 0 (default), zero-pad the TD waveform to the next power of 2
    If TDlen == N, zero-pad the TD waveform to length N before FFTing
    """
    ht = frame_data_to_hoft(fname, channel, start, stop, window_shape, verbose)

    tmplen = ht.data.length
    if TDlen == -1:
        TDlen = tmplen
    elif TDlen==0:
        TDlen = nextPow2(tmplen)
    else:
        assert TDlen >= tmplen

    ht = lal.ResizeREAL8TimeSeries(ht, 0, TDlen)
    hoftC = lal.CreateCOMPLEX16TimeSeries("h(t)", ht.epoch, ht.f0,
            ht.deltaT, ht.sampleUnits, TDlen)
    # copy h(t) into a COMPLEX16 array which happens to be purely real
    hoftC.data.data = ht.data.data + 0j
    FDlen = TDlen
    fwdplan=lal.CreateForwardCOMPLEX16FFTPlan(TDlen,0)
    hf = lal.CreateCOMPLEX16FrequencySeries("Template h(f)",
            ht.epoch, ht.f0, 1./ht.deltaT/TDlen, lal.HertzUnit,
            FDlen)
    lal.COMPLEX16TimeFreqFFT(hf, hoftC, fwdplan)
    if verbose:
        print " ++ Loaded data h(f) of length n= ", hf.data.length, " (= ", len(hf.data.data)*ht.deltaT, "s) at sampling rate ", 1./ht.deltaT    
    return hf


def string_gps_pretty_print(tgps):
    """
    Return a string with nice formatting displaying the value of a LIGOTimeGPS
    """
    return "%d.%d" % (tgps.gpsSeconds, tgps.gpsNanoSeconds)

def pylal_psd_to_swig_psd(raw_pylal_psd):
    """
    pylal_psd_to_swig_psd
    Why do I do a conversion? I am having trouble returning modified PSDs
    """
    data = raw_pylal_psd.data
    df = raw_pylal_psd.deltaF
    psdNew = lal.CreateREAL8FrequencySeries("PSD", lal.LIGOTimeGPS(0.), 0., df ,lal.HertzUnit, len(data))
    for i in range(len(data)):
        psdNew.data.data[i] = data[i]   # don't mix memory management between pylal and swig
    return psdNew

def get_psd_series_from_xmldoc(fname, inst):
    return series.read_psd_xmldoc(utils.load_filename(fname, contenthandler=series.LIGOLWContentHandler))[inst]  # return value is pylal wrapping of the data type; index data by a.data[k]

def get_intp_psd_series_from_xmldoc(fname, inst):
    psd = get_psd_series_from_xmldoc(fname, inst)
    return intp_psd_series(psd)

def resample_psd_series(psd, df=None, fmin=None, fmax=None):
    # handle pylal REAL8FrequencySeries
    if isinstance(psd, pylal.xlal.datatypes.real8frequencyseries.REAL8FrequencySeries):
        psd_fmin, psd_fmax, psd_df, data = psd.f0, psd.f0 + psd.deltaF*len(psd.data), psd.deltaF, psd.data
    # handle SWIG REAL8FrequencySeries
    elif isinstance(psd, lal.REAL8FrequencySeries):
        psd_fmin, psd_fmax, psd_df, data = psd.f0, psd.f0 + psd.deltaF*len(psd.data.data), psd.deltaF, psd.data.data
    # die horribly
    else:
        raise ValueError("resample_psd_series: Don't know how to handle %s." % type(psd))
    fmin = fmin or psd_fmin
    fmax = fmax or psd_fmax
    df = df or psd_df

    f = np.arange(psd_fmin, psd_fmax, psd_df)
    ifunc = interpolate.interp1d(f, data, fill_value=float("inf"), bounds_error=False)
    psd_intp = np.zeros(np.ceil((fmax - fmin) / df))
    newf = np.arange(fmin, psd_fmax, df)
    psd_intp = ifunc(newf)
    psd_intp[psd_intp == 0.0] = float("inf")

    tmpepoch = lal.LIGOTimeGPS(float(psd.epoch))
    # FIXME: Reenable when we figure out generic error
    """
    tmpunit = lal.Unit()
    lal.ParseUnitString(tmpunit, str(psd.sampleUnits))
    """
    tmpunit = lal.SecondUnit
    new_psd = lal.CreateREAL8FrequencySeries(epoch = tmpepoch, deltaF=df,
            f0 = fmin, sampleUnits = tmpunit, name = psd.name,
            length=len(psd_intp))
    new_psd.data.data = psd_intp
    return new_psd