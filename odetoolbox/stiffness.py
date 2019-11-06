#
# stiffness.py
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

from __future__ import print_function

from inspect import getmembers
import logging
import math
import numpy as np
import numpy.random
import random
from .mixed_integrator import MixedIntegrator
from .mixed_integrator import ParametersIncompleteException
from .shapes import Shape
from .spike_generator import SpikeGenerator

# Make NumPy warnings errors. Without this, we can't catch overflow errors that can occur in the step() function, which might indicate a problem with the ODE, the grid resolution or the stiffness testing framework itself.
np.seterr(over='raise')

try:
    import matplotlib as mpl
    mpl.use('Agg')
    import matplotlib.pyplot as plt
    STIFFNESS_DEBUG_PLOT = True
except:
    STIFFNESS_DEBUG_PLOT = False

import sympy
import sympy.utilities.autowrap
import time

try:
    import pygsl.odeiv as odeiv
except ImportError as ie:
    print("Warning: PyGSL is not available. The stiffness test will be skipped.")
    print("Warning: " + str(ie), end="\n\n\n")
    raise


class StiffnessTester(object):

    def __init__(self, system_of_shapes, shapes, analytic_solver_dict=None, parameters={}, stimuli=[], random_seed=123, max_step_size=np.inf, integration_accuracy=1E-3, sim_time=100., alias_spikes=False):
        self.alias_spikes = alias_spikes
        self.max_step_size = max_step_size
        self.integration_accuracy = integration_accuracy
        self.sim_time = sim_time
        self._system_of_shapes = system_of_shapes
        self.symbolic_jacobian_ = self._system_of_shapes.get_jacobian_matrix()
        self.shapes = shapes
        self.system_of_shapes = system_of_shapes
        self.parameters = parameters
        self.parameters = { k : sympy.parsing.sympy_parser.parse_expr(v, global_dict=Shape._sympy_globals).n() for k, v in self.parameters.items() }
        self._locals = self.parameters.copy()
        self._stimuli = stimuli
        self.random_seed = random_seed

        self.analytic_solver_dict = analytic_solver_dict
        if not self.analytic_solver_dict is None:
            if not "parameters" in self.analytic_solver_dict.keys():
                self.analytic_solver_dict["parameters"] = {}
            self.analytic_solver_dict["parameters"].update(self.parameters)
        self.analytic_integrator = None


    @property
    def random_seed(self):
        return self._random_seed


    @random_seed.setter
    def random_seed(self, value):
        assert type(value) is int
        assert value >= 0
        self._random_seed = value


    def check_stiffness(self, raise_errors=False):
        """Perform stiffness testing.

        The idea is not to compare if the given implicit method or the explicit method is better suited for this small simulation, for instance by comparing runtimes, but to instead check for tendencies of stiffness. If we find that the average step size of the implicit evolution method is a lot larger than the average step size of the explicit method, then this ODE system could be stiff. Especially if it become significantly more stiff when a different step size is used or when parameters are changed, an implicit evolution scheme could become increasingly important.

        It is important to note here, that this analysis depends significantly on the parameters that are assigned for an ODE system. If these are changed significantly in magnitude, the result of the analysis can also change significantly.
        """
        try:
            step_min_exp, step_average_exp, runtime_exp = self.evaluate_integrator(odeiv.step_rk4, raise_errors=raise_errors)
            step_min_imp, step_average_imp, runtime_imp = self.evaluate_integrator(odeiv.step_bsimp, raise_errors=raise_errors)
        except ParametersIncompleteException:
            print("Stiffness test not possible because numerical values were not specified for all parameters.")
            return None

        #print("runtime (imp:exp): %f:%f" % (runtime_imp, runtime_exp))

        return self.draw_decision(step_min_imp, step_min_exp, step_average_imp, step_average_exp)


    def evaluate_integrator(self, integrator, h_min_lower_bound=5E-9, sym_receiving_spikes=[], raise_errors=True, debug=True):
        """
        This function computes the average step size and the minimal step size that a given integration method from GSL uses to evolve a certain system of ODEs during a certain simulation time, integration method from GSL and spike train for a given maximal stepsize.

        This function will reset the numpy random seed.

        :param max_step_size: The maximal stepsize for one evolution step in miliseconds
        :param integrator: A method from the GSL library for evolving ODEs, e.g. `odeiv.step_rk4`
        :param y: The 'state variables' in f(y)=y'
        :return: Average and minimal step size.
        """

        np.random.seed(self.random_seed)

        spike_times = SpikeGenerator.spike_times_from_json(self._stimuli, self.sim_time)


        #
        #  initialise and run mixed integrator
        #

        mixed_integrator = MixedIntegrator(
         integrator,
         self.system_of_shapes,
         self.shapes,
         analytic_solver_dict=self.analytic_solver_dict,
         parameters=self.parameters,
         spike_times=spike_times,
         random_seed=self.random_seed,
         max_step_size=self.max_step_size,
         integration_accuracy=self.integration_accuracy,
         sim_time=self.sim_time,
         alias_spikes=self.alias_spikes)
        h_min, h_avg, runtime = (lambda x: x[:3])(mixed_integrator.integrate_ode(
         h_min_lower_bound=1E-12, raise_errors=raise_errors, debug=debug))

        logging.info("For integrator = " + str(integrator) + ": h_min = " + str(h_min) + ", h_avg = " + str(h_avg) + ", runtime = " + str(runtime))

        return h_min, h_avg, runtime


    def draw_decision(self, step_min_imp, step_min_exp, step_average_imp, step_average_exp, avg_step_size_ratio=6):
        """Decide which is the best integrator to use for a certain system of ODEs

        1. If the minimal step size is close to machine precision for one of the methods but not for the other, this suggest that the other is more stable and should be used instead.

        2. If the ODE system is stiff the average step size of the implicit method tends to be larger. This indicates that the ODE system is possibly stiff (and that it could be even more stiff for minor changes in stepsize and parameters). 

        :param step_min_imp: data measured during solving
        :param step_min_exp: data measured during solving
        :param step_average_imp: data measured during solving
        :param step_average_exp: data measured during solving
        """

        machine_precision = np.finfo(float).eps

        if step_min_imp > 10. * machine_precision and step_min_exp < 10. * machine_precision:
            return "implicit"
        elif step_min_imp < 10. * machine_precision and step_min_exp > 10. * machine_precision:
            return "explicit"
        elif step_min_imp < 10. * machine_precision and step_min_exp < 10. * machine_precision:
            return "warning"

        if step_average_imp > avg_step_size_ratio * step_average_exp:
            return "implicit"
        else:
            return "explicit"
