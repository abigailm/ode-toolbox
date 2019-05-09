#
# system_of_shapes.py
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

import json

from sympy import diff, exp, Matrix, simplify, sqrt, Symbol, sympify
from sympy.parsing.sympy_parser import parse_expr
from sympy.matrices import zeros
import sympy
import sympy.matrices
import numpy
import numpy as np

class SystemOfShapes(object):
    """    """

    def __init__(self, x, A, C, shapes):
        assert x.shape[0] == A.shape[0] == A.shape[1] == C.shape[0]
        self.x_ = x
        self.A_ = A
        self.C_ = C
        self.shapes_ = shapes


    def get_dependency_edges(self):

        E = []
        
        for i, sym1 in enumerate(self.x_):
            for j, sym2 in enumerate(self.x_):
                if not sympy.simplify(self.A_[j, i]) == sympy.parsing.sympy_parser.parse_expr("0"):
                    E.append((sym2, sym1))
                    #E.append((str(sym2).replace("__d", "'"), str(sym1).replace("__d", "'")))
                else:
                    if not sympy.simplify(sympy.diff(self.C_[j], sym1)) == sympy.parsing.sympy_parser.parse_expr("0"):
                        E.append((sym2, sym1))
                        #E.append((str(sym2).replace("__d", "'"), str(sym1).replace("__d", "'")))

        return E
    

    def get_lin_cc_symbols(self, E):
        """retrieve the variable symbols of those shapes than are linear and constant coefficient. In the case of a higher-order shape, will return all the variable symbols with "__d" suffixes up to the order of the shape."""
        
        #
        # initial pass: is a node linear and constant coefficient by itself?
        #
        
        node_is_lin = {}
        for shape in self.shapes_:
            if shape.is_lin_const_coeff(self.shapes_):
                _node_is_lin = True
            else:
                _node_is_lin = False
            all_shape_symbols = [ sympy.Symbol(str(shape.symbol) + "__d" * i) for i in range(shape.order) ]
            for sym in all_shape_symbols:
                node_is_lin[sym] = _node_is_lin

        return node_is_lin

    def propagate_lin_cc_judgements(self, node_is_lin, E):
        """propagate: if a node depends on a node that is not linear and constant coefficient, it cannot be linear and constant coefficient"""
        
        queue = [ sym for sym, is_lin_cc in node_is_lin.items() if not is_lin_cc ]
        while len(queue) > 0:

            n = queue.pop(0)

            if not node_is_lin[n]:
                # mark dependent neighbours as also not lin_cc
                dependent_neighbours = [ n1 for (n1, n2) in E if n2 == n ]    # nodes that depend on n
                for n_neigh in dependent_neighbours:
                    if node_is_lin[n_neigh]:
                        print("\t\tMarking dependent node " + str(n_neigh))
                        node_is_lin[n_neigh] = False
                        queue.append(n_neigh)

        return node_is_lin

    def get_sub_system(self, symbols):
        """Return a new instance which discards all symbols and equations except for those in `symbols`. This is probably only sensible when the elements in `symbols` do not dependend on any of the other symbols that will be thrown away.
        """

        idx = [ i for i, sym in enumerate(self.x_) if sym in symbols ]
        
        x_sub = self.x_[idx, :]
        A_sub = self.A_[idx, :][:, idx]
        C_sub = self.C_[idx, :]
        
        shapes_sub = [shape for shape in self.shapes_ if shape.symbol in symbols]
        
        return SystemOfShapes(x_sub, A_sub, C_sub, shapes_sub)


    def compute_propagator(self, output_timestep_symbol_name="__h"):
        """
        """

        #from IPython import embed;embed()

        #
        #   generate the propagator matrix
        #

        P = sympy.simplify(sympy.exp(self.A_ * sympy.Symbol(output_timestep_symbol_name)))
        

        #
        #   generate symbols for each nonzero entry of the propagator matrix
        #

        P_sym = sympy.zeros(*P.shape)   # each entry in the propagator matrix is assigned its own symbol
        P_expr = {}     # the expression corresponding to each propagator symbol
        update_expr = {}    # keys are str(variable symbol), values are str(expressions) that evaluate to the new value of the corresponding key
        for row in range(P_sym.shape[0]):
            update_expr_terms = []
            for col in range(P_sym.shape[1]):
                if sympy.simplify(P[row, col]) != sympy.sympify(0):
                    #sym_str = "__P_{}__{}_{}".format(self.x_[row], row, col)
                    sym_str = "__P__{}__{}".format(str(self.x_[row]), str(self.x_[col]))
                    P_sym[row, col] = parse_expr(sym_str)
                    P_expr[sym_str] = str(P[row, col])
                    update_expr_terms.append(sym_str + " * " + str(self.x_[col]))
            update_expr[str(self.x_[row])] = " + ".join(update_expr_terms)
            
                    

        all_variable_symbols = [ str(sym) for sym in self.x_ ]
        
        #for i, sym1 in enumerate(all_variable_symbols):
            #update_expr_terms = []
            #for j, sym2 in enumerate(all_variable_symbols):
                #if sympy.simplify(P[i, j]) != sympy.sympify(0):
                    #update_expr_terms.append("

        solver_dict = {"propagators" : P_expr,
                       "update_expressions" : update_expr,
                       "shape_state_variables" : all_variable_symbols }
        import pdb;pdb.set_trace()

        return solver_dict

    @classmethod
    def from_shapes(cls, shapes):
        """Construct the global system matrix including all shapes.
        
        Global dynamics
        
        .. math::
        
            x' = Ax + C

        where :math:`x` and :math:`C` are column vectors of length :math:`N` and :math:`A` is an :math:`N \times N` matrix.        
        """
        
        N = np.sum([shape.order for shape in shapes]).__index__()
        x = sympy.zeros(N, 1)
        A = sympy.zeros(N, N)
        C = sympy.zeros(N, 1)

        i = 0
        for shape in shapes:
            for j in range(shape.order):
                x[i] = shape.state_variables[j]
                i += 1
        
        i = 0
        for shape in shapes:
            #print("Shape: " + str(shape.symbol))
            shape_expr = shape.diff_rhs_derivatives
            derivative_symbols = [ Symbol(str(shape.symbol) + "__d" * order) for order in range(shape.order) ]
            for derivative_factor, derivative_symbol in zip(shape.derivative_factors, derivative_symbols):
                shape_expr = shape_expr + derivative_factor * derivative_symbol
            #print("\t expr =  " + str(shape_expr))

            highest_diff_sym_idx = [k for k, el in enumerate(x) if el == Symbol(str(shape.symbol) + "__d" * (shape.order - 1))][0]
            for j in range(N):
                A[highest_diff_sym_idx, j] = diff(shape_expr, x[j])
            
            # for higher-order shapes: mark subsequent derivatives x_i' = x_(i+1)
            for order in range(shape.order - 1):
                _idx = [k for k, el in enumerate(x) if el == Symbol(str(shape.symbol) + "__d" * (order + 1))][0]
                #print("\t\tThe symbol " + str(Symbol(str(shape.symbol) + "__d" * (order ))) + " is at position " + str(_idx) + " in vector " + str(x) + ", writing in row " + str(_idx))
                A[i + (shape.order - order - 1), _idx] = 1.     # the highest derivative is at row `i`, the next highest is below, and so on, until you reach the variable symbol without any "__d" suffixes

            i += shape.order
 
        i = 0
        for shape in shapes:
            print("Shape: " + str(shape.symbol))
            shape_expr = shape.diff_rhs_derivatives

            highest_diff_sym_idx = [k for k, el in enumerate(x) if el == Symbol(str(shape.symbol) + "__d" * (shape.order - 1))][0]
            for j in range(N):
                shape_expr = simplify(shape_expr - diff(shape_expr, x[j]) * x[j])

            C[highest_diff_sym_idx] = shape_expr

            i += shape.order
 
        return SystemOfShapes(x, A, C, shapes)


