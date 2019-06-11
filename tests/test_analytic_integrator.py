#
# test_integration.py
#
# This file is part of the NEST ODE toolbox.
#
# Copyright (C) 2017 The NEST Initiative
#
# The NEST ODE toolbox is free software: you can redistribute it
# and/or modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 2 of
# the License, or (at your option) any later version.
#
# The NEST ODE toolbox is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty
# of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with NEST.  If not, see <http://www.gnu.org/licenses/>.
#

INTEGRATION_TEST_DEBUG_PLOTS = True

import json
import os
import unittest
import sympy
import numpy as np

#np.seterr(under="warn")
if INTEGRATION_TEST_DEBUG_PLOTS:
    import matplotlib as mpl
    mpl.use('Agg')
    import matplotlib.pyplot as plt

from .context import odetoolbox
from odetoolbox.analytic_integrator import AnalyticIntegrator

from math import e
from sympy import exp, sympify

import scipy
import scipy.special
import scipy.linalg
from scipy.integrate import solve_ivp
from odetoolbox.spike_generator import SpikeGenerator

try:
    import pygsl.odeiv as odeiv
except ImportError as ie:
    print("Warning: PyGSL is not available. The integration test will be skipped.")
    print("Warning: " + str(ie))


def open_json(fname):
    absfname = os.path.join(os.path.abspath(os.path.dirname(__file__)), fname)
    with open(absfname) as infile:
        indict = json.load(infile)
    return indict


class TestAnalyticIntegrator(unittest.TestCase):
    '''Numerical comparison between ode-toolbox calculated propagators, hand-calculated propagators expressed in Python, and numerical integration, for the iaf_cond_alpha neuron.

    Definition of alpha function:

        g'' = -g / tau^2 - 2*g' / tau

    Let z1 = g
        z2 = g'

    Then z1' = z2
         z2' = -z1 / tau^2 - 2*z2 / tau

    Or equivalently

        Z' = S * Z

    with

        S = [ 0         1      ]
            [ -1/tau^2  -2/tau ]

    Exact solution: let

        P = exp[h * S]

          = [ (h/tau_syn + 1) * np.exp(-h/tau_syn)      h*np.exp(-h/tau_syn)                ]
            [ -h*np.exp(-h/tau_syn)/tau_syn**2          (-h/tau_syn + 1)*np.exp(-h/tau_syn) ]

    Then

        z(t + h) = P * z(t)


    '''

    def test_integration_iaf_psc_alpha(self):
        
        debug = True

        h = 1E-3    # [s]
        T = 100E-3    # [s]


        #
        #   timeseries using ode-toolbox generated propagators
        #

        indict = open_json("test_analytic_integrator.json")
        solver_dict = odetoolbox.analysis(indict)
        print("Got solver_dict from ode-toolbox: ")
        print(json.dumps(solver_dict, indent=2))
        assert len(solver_dict) == 1
        solver_dict = solver_dict[0]
        assert solver_dict["solver"] == "analytical"

        ODE_INITIAL_VALUES = { "I" : 0., "I__d" : 0. }

        _parms = {"Tau" : 2E-3,    # [s]
                  "e" : sympy.exp(1) }

        if not "parameters" in solver_dict.keys():
            solver_dict["parameters"] = {}
        solver_dict["parameters"].update(_parms)

        spike_times = SpikeGenerator.spike_times_from_json(indict["stimuli"], T)

        N = int(np.ceil(T / h) + 1)
        timevec = np.linspace(0., T, N)
        state = { True: {}, False: {} }
        for use_caching in [False, True]:
            state[use_caching] = { sym : [] for sym in solver_dict["state_variables"] }
            state[use_caching]["timevec"] = []
            analytic_integrator = AnalyticIntegrator(solver_dict, spike_times, enable_caching=use_caching)
            analytic_integrator.set_initial_values(ODE_INITIAL_VALUES)
            analytic_integrator.reset()
            for step, t in enumerate(timevec):
                print("Step " + str(step) + " of " + str(N))
                state_ = analytic_integrator.get_value(t)
                state[use_caching]["timevec"].append(t)
                for sym, val in state_.items():
                    state[use_caching][sym].append(val)

        for use_caching in [False, True]:
            for k, v in state[use_caching].items():
                state[use_caching][k] = np.array(v)

        if INTEGRATION_TEST_DEBUG_PLOTS:
            fig, ax = plt.subplots(2, sharex=True)

            ax[0].plot(1E3 * timevec, state[True]["I"], linewidth=2, linestyle=":", marker="o", label="I (caching)")
            ax[0].plot(1E3 * timevec, state[False]["I"], linewidth=2, linestyle=":", marker="o", label="I")
            ax[1].plot(1E3 * timevec, state[True]["I__d"], linewidth=2, linestyle=":", marker="o", label="I' (caching)")
            ax[1].plot(1E3 * timevec, state[False]["I__d"], linewidth=2, linestyle=":", marker="o", label="I'")

            for _ax in ax:
                _ax.legend()
                _ax.grid(True)
                #_ax.set_xlim(49., 55.)

            ax[-1].set_xlabel("Time [ms]")

            #plt.show()
            fn = "/tmp/remotefs2/test_analytic_integrator.png"
            print("Saving to " + fn)
            plt.savefig(fn, dpi=600)

        np.testing.assert_allclose(state[True]["timevec"], timevec)
        np.testing.assert_allclose(state[True]["timevec"], state[False]["timevec"])
        for sym, val in state_.items():
            np.testing.assert_allclose(state[True][sym], state[False][sym])
