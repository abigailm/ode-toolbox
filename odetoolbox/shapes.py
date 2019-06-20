#
# shapes.py
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

import functools
import numpy as np
import re
import sympy


def is_sympy_type(var):
    return isinstance(var, tuple(sympy.core.all_classes))


class Shape(object):
    """Canonical representation of a shape function.

    Description
    -----------

    This class provides a canonical representation of a shape function independently of the way in which the user specified the shape. It assumes a differential equation of the general form (where bracketed superscript :math:`\cdot^{(n)}` indicates the n-th derivative with respect to time):

    .. math::

        x^{(n)} = N + \sum_{i=0}^{n-1} c_i x^{(i)}

    Any constant or nonlinear part is here contained in the term N.

    In the input and output, derivatives are indicated by adding one prime (single quotation mark) for each derivative order. For example, in the expression

    .. code::

        x''' = c0*x + c1*x' + c2*x'' + x*y + x**2

    the `symbol` of the ODE would be `x` (i.e. without any qualifiers), `order` would be 3, `derivative_factors` would contain the linear part in the form of the list `[c0, c1, c2]`, and the nonlinear part is stored in `diff_rhs_derivatives`.

    """

    # a minimal subset of sympy classes and functions to avoid "from sympy import *"
    _sympy_globals = {"Symbol" : sympy.Symbol,
                     "Integer" : sympy.Integer,
                     "Float" : sympy.Float,
                     "Function" : sympy.Function,
                     "Pow" : sympy.Pow,
                     "power" : sympy.power,
                     "exp" : sympy.exp,
                     "log" : sympy.log,
                     "sin" : sympy.sin,
                     "cos" : sympy.cos,
                     "tan" : sympy.tan,
                     "asin" : sympy.asin,
                     "sinh" : sympy.sinh,
                     "asinh" : sympy.asinh,
                     "acos" : sympy.acos,
                     "cosh" : sympy.cosh,
                     "acosh" : sympy.acosh,
                     "tanh" : sympy.tanh,
                     "atanh" : sympy.atanh,
                     "e" : sympy.exp(1),
                     "E" : sympy.exp(1),
                     "t" : sympy.Symbol("t")
                     }


    def __init__(self, symbol, order, initial_values, derivative_factors, diff_rhs_derivatives=sympy.Float(0.), lower_bound=None, upper_bound=None, debug=False):
        """Perform type and consistency checks and assign arguments to member variables.


        Parameters
        ----------

        symbol : SymPy expression
            Symbolic name of the shape without additional qualifiers like prime symbols or similar.
        order : int
            Order of the ODE representing the shape.
        initial_values : dict of SymPy expressions
            Initial values of the ODE representing the shape. The dict contains `order` many key-value pairs: one for each derivative that occurs in the ODE. The keys are strings created by concatenating the variable symbol with as many single quotation marks (') as the derivation order. The values are SymPy expressions.
        derivative_factors : list of SymPy expressions
            The factors for the derivatives that occur in the ODE. This list has to contain `order` many values, i.e. one for each derivative that occurs in the ODE. The values have to be in ascending order, i.e. a0 df_d0, iv_d1, ... for the derivatives d0, d1, ...
        diff_rhs_derivatives : 
        """
        assert type(symbol) is sympy.Symbol, "symbol is not a SymPy symbol: \"%r\"" % symbol
        self.symbol = symbol

        assert not str(symbol) in Shape._sympy_globals.keys(), "The symbol name " + str(symbol) + " clashes with a predefined symbol by the same name"

        assert type(order) is int, "order is not an integer: \"%d\"" % order
        self.order = order

        assert len(initial_values) == order, "length of initial_values != order"
        for iv_name, iv in initial_values.items():
            assert is_sympy_type(iv), "initial value for %s is not a SymPy expression: \"%r\"" % (iv_name, iv)
        self.initial_values = initial_values

        assert len(derivative_factors) == order, "length of derivative_factors != order"
        for df in derivative_factors:
            assert is_sympy_type(df), "derivative factor is not a SymPy expression: \"%r\"" % iv
        self.derivative_factors = derivative_factors

        # Compute the state variables for ODE the shape satisfies
        self.state_variables = []
        for i in range(self.order):
            if i > 0:
                self.state_variables.insert(0, sympy.Symbol("{}{}".format(str(symbol), "__d" * i)))
            else:
                self.state_variables.insert(0, symbol)

        self.diff_rhs_derivatives = sympy.simplify(diff_rhs_derivatives)

        self.lower_bound = lower_bound
        if not self.lower_bound is None:
            self.lower_bound = sympy.simplify(self.lower_bound)

        self.upper_bound = upper_bound
        if not self.upper_bound is None:
            self.upper_bound = sympy.simplify(self.upper_bound)

        #if debug:
        if True:
            print("Created Shape with symbol " + str(self.symbol) + ", derivative_factors = " + str(self.derivative_factors) + ", diff_rhs_derivatives = " + str(self.diff_rhs_derivatives))


    def __str__(self):
        s = "Shape \"" + str(self.symbol) + "\" of order " + str(self.order)
        return s


    def get_initial_value(self, sym):
        """get the initial value corresponding to the symbol

        Parameters
        ----------
        sym : str
            string representation of a sympy symbol, e.g. `"V_m'"`
        """
        assert type(sym) is str
        if not sym in self.initial_values:
            return None
        return self.initial_values[sym]


    def get_all_variable_symbols(self, differential_order_str="'"):
        """Get all variable symbols for this shape

        Return
        ------
        all_symbols : list of sympy.Symbol
        """
        all_symbols = []
        for order in range(self.order):
            all_symbols.append(sympy.Symbol(str(self.symbol) + differential_order_str * order))
        return all_symbols


    def is_lin_const_coeff(self, shapes=[]):
        """
        Returns
        -------
        lin_const_coeff : bool
            True if and only if the shape is linear and constant coefficient in all known variable symbols in `shapes`
        """
        if not self in shapes:
            shapes = shapes + [self]

        all_symbols = []
        for shape in shapes:
            all_symbols.extend(shape.get_all_variable_symbols(differential_order_str="__d"))

        all_symbols = list(set(all_symbols))	# filter for unique symbols
        for sym in all_symbols:
            for df in self.derivative_factors:
                expr = sympy.diff(df, sym)
                if not sympy.sympify(expr).is_zero:
                    # the expression "sym * self.symbol" appears on right-hand side of this shape's definition
                    return False

            expr = sympy.diff(self.diff_rhs_derivatives, sym)
            if not sympy.sympify(expr).is_zero:
                # the variable symbol `sym` appears on right-hand side of this expression. Check to see if it appears as a linear term by checking whether taking its derivative again, with respect to any known variable, yields 0
                for sym_ in all_symbols:
                    if not sympy.sympify(sympy.diff(expr, sym_)).is_zero:
                        return False

        return True


    @classmethod
    def from_json(cls, indict, all_variable_symbols=[], time_symbol=sympy.Symbol("t"), _debug=False):
        """Create a shape object from a JSON input dictionary
        """

        if not "expression" in indict:
            raise Exception("No `expression` keyword found in input")

        if not indict["expression"].count("=") == 1:
            raise Exception("Expecting exactly one \"=\" symbol in defining expression: \"" + str(indict["expression"]) + "\"")

        lhs, rhs = indict["expression"].split("=")
        lhs_ = re.findall("\S+", lhs)
        if not len(lhs_) == 1:
            raise Exception("Error while parsing expression \"" + indict["expression"] + "\"")
        lhs = lhs_[0]
        rhs = rhs.strip()

        symbol_match = re.search("[a-zA-Z_][a-zA-Z0-9_]*", lhs)
        if symbol_match is None:
            raise Exception("Error while parsing symbol name in \"" + lhs + "\"")
        symbol = symbol_match.group()
        order = len(re.findall("'", lhs))

        initial_values = {}
        if not "initial_value" in indict.keys() \
         and not "initial_values" in indict.keys() \
         and order > 0:
            raise Exception("No initial values specified for order " + str(order) + " equation with variable symbol \"" + symbol + "\"")

        if "initial_value" in indict.keys() \
         and "initial_values" in indict.keys():
            raise Exception("`initial_value` and `initial_values` cannot be specified simultaneously for equation with variable symbol \"" + symbol + "\"")

        if "initial_value" in indict.keys():
            if not order == 1:
                raise Exception("Single initial value specified for equation that is not first order in equation with variable symbol \"" + symbol + "\"")
            initial_values[symbol] = indict["initial_value"]

        if "initial_values" in indict.keys():
            if not len(indict["initial_values"]) == order:
                raise Exception("Wrong number of initial values specified for order " + str(order) + " equation with variable symbol \"" + symbol + "\"")

            for iv_lhs, iv_rhs in indict["initial_values"].items():
                symbol_match = re.search("[a-zA-Z_][a-zA-Z0-9_]*", iv_lhs)
                if symbol_match is None:
                    raise Exception("Error trying to parse initial value variable symbol from string \"" + iv_lhs + "\"")
                iv_symbol = symbol_match.group()
                if not iv_symbol == symbol:
                    raise Exception("Initial value variable symbol \"" + iv_symbol + "\" does not match equation variable symbol \"" + symbol + "\"")
                iv_order = len(re.findall("'", iv_lhs))
                initial_values[iv_symbol + iv_order * "'"] = iv_rhs

        lower_bound = None
        if "lower_bound" in indict.keys():
            lower_bound = indict["lower_bound"]

        upper_bound = None
        if "upper_bound" in indict.keys():
            upper_bound = indict["upper_bound"]

        if order == 0:
            return Shape.from_function(symbol, rhs)
        else:
            return Shape.from_ode(symbol, rhs, initial_values, all_variable_symbols=all_variable_symbols, lower_bound=lower_bound, upper_bound=upper_bound)


    def reconstitute_expr(self, derivative_symbol="__d"):
        expr = self.diff_rhs_derivatives
        derivative_symbols = [ sympy.Symbol(str(self.symbol) + derivative_symbol * order) for order in range(self.order) ]
        for derivative_factor, derivative_symbol in zip(self.derivative_factors, derivative_symbols):
            expr += derivative_factor * derivative_symbol
        return expr


    @staticmethod
    def split_lin_nonlin(expr, x):
        """const_terms = [term for term in expr.args if not term.free_symbols]
        const_term = functools.reduce(lambda x, y: x + y, const_terms)
        C[highest_diff_sym_idx] += const_term"""

        assert all([is_sympy_type(sym) for sym in x])

        lin_factors = []

        print("* Splitting expr = " + str(expr))
        expr = expr.expand()
        print("                 = " + str(expr))
        print("  with known symbols = " + str(x))
        for j, sym in enumerate(x):
            # check if there is a linear part in `sym`
            print("\t* Symbol " + str(sym))
            if expr.is_Add:
                terms = expr.args
            else:
                terms = [expr]
            # a term is linear in `sym` if `term/sym` contains only free symbols that are not in all_known_symbols, i.e. if the sets are disjoint
            linear_terms = [term for term in terms if (term / sym).free_symbols.isdisjoint(x)]
            print("\t  linear_terms = " + str(linear_terms))
            #all_linear_terms.append(linear_term)
            if linear_terms:
                linear_factors = [term / sym for term in linear_terms]
                linear_factor = functools.reduce(lambda x, y: x + y, linear_factors)
                linear_terms = [term for term in linear_terms]
                linear_term = functools.reduce(lambda x, y: x + y, linear_terms)
            else:
                linear_factor = sympy.Float(0)
                linear_term = sympy.Float(0)

            print("\t  linear_term = " + str(linear_term))
            lin_factors.append(linear_factor)
            print("\t   Old expr = " + str(expr))
            expr = expr - linear_term
            print("\t   New expr = " + str(expr))

        lin_factors = np.array(lin_factors)
        nonlin_term = expr
        assert len(lin_factors) == len(x)
        print("\t--> lin_factors = " + str(lin_factors))
        print("\t--> nonlin_term = " + str(nonlin_term))

        return lin_factors, nonlin_term

        """for j, sym1 in enumerate(x):
            #diff_expr = sympy.simplify(sympy.diff(shape_expr, sym1))
            diff_expr = sympy.diff(shape_expr, sym1)
            print("\tdiff wrt " + str(sym1) + " = " + str(diff_expr))
            for sym2 in x:
                print("\t\tsym2 = " + str(sym2))
                diff_wrt_sym2 = sympy.diff(diff_expr, sym2)
                #print("\t\tdiff_wrt_sym2 = " + str(diff_wrt_sym2))
                if not diff_wrt_sym2.is_zero:
                    # nonlinear term containing sym1
                    C[highest_diff_sym_idx] += sym1 * sym2 * diff_wrt_sym2
                    shape_expr -= sym1 * sym2 * diff_wrt_sym2
                    diff_expr -= sym2 * diff_wrt_sym2
                    #shape_expr = sympy.simplify(shape_expr)
                    #diff_expr = sympy.simplify(diff_expr)
                A[highest_diff_sym_idx, j] = diff_expr
                print("\t\t---> new diff_expr = " + str(diff_expr))
                print("\t\t---> new shape_expr = " + str(shape_expr))"""


    @classmethod
    def from_function(cls, symbol, definition, max_t=100, max_order=4, all_variable_symbols=[], time_symbol=sympy.Symbol("t"), debug=False):
        """Create a Shape object given a function of time.

        The goal of the algorithm is to calculate the factors of the ODE,
        assuming they exist. It uses a matrix whose entries correspond to
        the evaluation of derivatives of the shape function at certain
        points `t` in time.

        The idea is to create a system of equations by substituting
        natural numbers into the homogeneous linear ODE with variable
        derivative factors order many times for varying natural numbers
        and solving for derivative factors. Once we have derivative
        factors, the ODE is uniquely defined. This is assuming that shape
        satisfies an ODE of this order, which we check after determining
        the factors.

        In the function, the symbol `t` is assumed to stand for the
        current time.

        The algorithm used in this function is described in full detail
        together with the mathematical foundations in the following
        publication:

            Inga Blundell, Dimitri Plotnikov, Jochen Martin Eppler,
            Abigail Morrison (2018) Automatically selecting an optimal
            integration scheme for systems of differential equations in
            neuron models. Front. Neuroinf. doi:10.3389/fninf.2018.00050.

        Parameters
        ----------
        symbol : string
            The symbol of the shape (e.g. "alpha", "I", "exp")
        definition : string
            The definition of the shape (e.g. "(e/tau_syn_in) * t *
            exp(-t/tau_syn_in)")

        Returns
        -------
        shape : Shape
            The canonical representation of the postsynaptic shape

        Examples
        --------
        >>> Shape("I_in", "(e/tau_syn_in) * t * exp(-t/tau_syn_in)")
        """

        all_variable_symbols_dict = { str(el) : el for el in all_variable_symbols }

        # The symbol and the definition of the shape function were given as
        # strings. We have to transform them to SymPy symbols for using
        # them in symbolic calculations.
        symbol = sympy.Symbol(symbol)
        definition = sympy.parsing.sympy_parser.parse_expr(definition, global_dict=Shape._sympy_globals, local_dict=all_variable_symbols_dict)  # minimal global_dict to make no assumptions (e.g. "beta" could otherwise be recognised as a function instead of as a parameter symbol))

        # `derivatives` is a list of all derivatives of `shape` up to the order we are checking, starting at 0.
        derivatives = [definition, sympy.diff(definition, time_symbol)]

        #
        #   we first check if the shape satisfies satisfies a linear homogeneous ODE of order 1.
        #

        order = 1
        if debug:
            print("\nProcessing shape " + str(symbol) + ", defining expression = " + str(definition))


        #
        #   to avoid a division by zero below, we have to find a `t` so that the shape function is not zero at this `t`.
        #

        t_val = None
        for t_ in range(1, max_t):
            if not definition.subs(time_symbol, t_).is_zero:
                t_val = t_
                break

        if debug > 1:
            print("Found t: " + str(t_val))

        if t_val is None:

            #
            # it is very unlikely that the shape obeys a linear homogeneous ODE of order 1 and we still did not find a suitable `t_val`. This would mean that the function evaluates to zero at `t_` = 1, ..., `max_t`, which usually hints at an error in the specification of the function.
            #

            msg = "Cannot find t for which shape function is unequal to zero"
            raise Exception(msg)


        #
        #   first handle the case for an ODE of order 1, i.e. of the form I' = a0 * I
        #

        if debug > 1:
            print("\tFinding ode for order 1...")

        derivative_factors = [(1 / derivatives[0] * derivatives[1]).subs(time_symbol, t_val)]
        diff_rhs_lhs = derivatives[1] - derivative_factors[0] * derivatives[0]
        found_ode = sympy.simplify(diff_rhs_lhs).is_zero

        # If `shape` does not satisfy a linear homogeneous ODE of order 1,
        # we try to find one of higher order in a loop. The loop runs
        # while no linear homogeneous ODE was found and the maximum
        # order to check for was not yet reached.
        while not found_ode and order < max_order:
            # Set the potential order for the iteration
            order += 1

            if debug > 1:
                print("\tFinding ode for order " + str(order) + "...")

            # Add the next higher derivative to the list
            derivatives.append(sympy.diff(derivatives[-1], time_symbol))

            # `X` is an `order`x`order` matrix that will be assigned
            # the derivatives up to `order`-1 of some natural numbers
            # as rows (differing in each row)
            X = sympy.zeros(order)

            # `Y` is a vector of length `order` that will be assigned the derivatives of `order` of the natural number in the corresponding row of `X`
            Y = sympy.zeros(order, 1)

            # It is possible that by choosing certain natural numbers,
            # the system of equations will not be solvable, i.e. `X`
            # is not invertible. This is unlikely but we check for
            # invertibility of `X` for varying sets of natural
            # numbers.
            if debug > 1:
                print("\tFinding invertibility...")
            invertible = False
            for t_ in range(1, max_t):
                for i in range(order):
                    substitute = i + t_
                    Y[i] = derivatives[order].subs(time_symbol, substitute)
                    for j in range(order):
                        X[i, j] = derivatives[j].subs(time_symbol, substitute)

                if sympy.det(X) != 0:
                    invertible = True
                    break

            #
            #   If we failed to find an invertible `X`, it is very unlikely that the shape function obeys a linear homogeneous ODE of order `order` and we go on checking the next potential order.
            #

            if not invertible:
                continue


            #
            #   calculate `derivative_factors`
            #

            if debug > 1:
                print("\tinv()...")
            derivative_factors = sympy.simplify(X.inv() * Y)


            #
            #   fill in the obtained expressions for the derivative_factors and check whether they satisfy the definition of the shape
            #

            diff_rhs_lhs = 0
            if debug > 1:
                print("\tchecking whether shape definition is satisfied...")
            for k in range(order):
                diff_rhs_lhs -= derivative_factors[k] * derivatives[k]
            diff_rhs_lhs += derivatives[order]

            if debug > 1:
                print("\tsimplify...")
            if len(str(diff_rhs_lhs)) < 1000 and sympy.simplify(diff_rhs_lhs).is_zero:
                found_ode = True
                break

        if not found_ode:
            msg = "Shape does not satisfy any ODE of order <= " + str(max_order)
            raise Exception(msg)

        derivative_factors = [sympy.simplify(df) for df in derivative_factors]


        #
        #    calculate the initial values of the found ODE
        #

        initial_values = { str(symbol) + derivative_order * '\'' : x.subs(time_symbol, 0) for derivative_order, x in enumerate(derivatives[:-1]) }

        return cls(symbol, order, initial_values, derivative_factors)


    @classmethod
    def from_ode(cls, symbol, definition, initial_values, all_variable_symbols=[], lower_bound=None, upper_bound=None, debug=False, **kwargs):
        """Create a Shape object given an ODE and initial values.

        Note that shapes are only aware of their own state variables: if an equation for x depends on another state variable of another shape y, then y will appear in the nonlinear part of x.


        Parameters
        ----------
        symbol : string
            The symbol (variable name) of the ODE
        definition : string
            The definition of the ODE
        initial_values : dict
            A dictionary mapping initial values to expressions.


        Examples
        --------
        Shape.from_ode("alpha",
                       "-1/tau**2 * shape_alpha -2/tau * shape_alpha'",
                       {"alpha" : "0", "alpha'" : "e/tau", "0"]})
        """

        assert type(symbol) is str

        all_variable_symbols_dict = { str(el) : el for el in all_variable_symbols }

        order = len(initial_values)

        def _initial_values_sanity_checks():
            assert type(initial_values) is dict, "Initial values should be specified as a dictionary"
            _order_from_definition = 1
            _re_search = re.compile(symbol + "'+").findall(definition)

            for match in _re_search:
                __re_search = re.compile("'+").search(match)
                _order = 0
                if not __re_search is None:
                    _order = len(__re_search.group())
                _order_from_definition = max(_order + 1, _order_from_definition)

            assert _order_from_definition == order, "Wrong number of initial values specified, expected " + str(_order_from_definition) + ", got " + str(order)

            initial_val_specified = [False] * order
            for k, v in initial_values.items():
                if not k[0:len(symbol)] == symbol:
                    raise Exception("In definition for " + str(symbol) + ": Initial value specified for unknown variable symbol \"" + k + "\"")
                _order = 0
                _re_search = re.compile("'+").search(k)
                if not _re_search is None:
                    _order = len(_re_search.group())
                    if _order >= order:
                        raise Exception("In defintion of initial value for variable \"" + k + "\": differential order (" + str(_order) + ") exceeds that of overall equation order (" + str(order) + ")")
                    initial_val_specified[_order] = True
                else:
                    # _order == 0
                    if initial_val_specified[_order]:
                        raise Exception("Initial value for zero-th order specified more than once")
                    initial_val_specified[_order] = True

            if not all(initial_val_specified):
                raise Exception("Initial value not specified for all differential orders")

        _initial_values_sanity_checks()

        symbol = sympy.Symbol(symbol)
        definition = sympy.parsing.sympy_parser.parse_expr(definition.replace("'", "__d"), global_dict=Shape._sympy_globals, local_dict=all_variable_symbols_dict)  # minimal global_dict to make no assumptions (e.g. "beta" could otherwise be recognised as a function instead of as a parameter symbol)
        initial_values = { k : sympy.parsing.sympy_parser.parse_expr(v, global_dict=Shape._sympy_globals, local_dict=all_variable_symbols_dict) for k, v in initial_values.items() }

        derivative_symbols = [ sympy.Symbol(str(symbol)+"__d"*i) for i in range(order) ]
        if not symbol in all_variable_symbols:
            all_variable_symbols.extend(derivative_symbols)
        all_variable_symbols = [ sympy.Symbol(str(sym_name).replace("'", "__d")) for sym_name in all_variable_symbols ]

        """# the purely linear part of the shape goes into `derivative_factors`
        derivative_factors = []
        expr = definition.copy()    # part of the defining expression yet to process
        linear_part = sympy.Float(0.)
        nonlinear_part = sympy.Float(0.)


        #
        #   for each defined symbol in this shape...
        #

        if debug:
            print("\nProcessing shape " + str(symbol) + ", defining expression = " + str(definition))
        for sym1 in derivative_symbols:

            #
            #   grab the defining expression and separate into linear and nonlinear part
            #

            diff_expr = sympy.diff(expr, sym1)
            for sym2 in all_variable_symbols:
                diff_wrt_sym2 = sympy.diff(diff_expr, sym2)
                if not diff_wrt_sym2.is_zero:
                    # if does not appear as zero -> nonlinear
                    nonlinear_part += sym1 * sym2 * diff_wrt_sym2
                    diff_expr -= sym2 * diff_wrt_sym2

            # whatever remains of `diff_expr` after nonlinear terms have been subtracted away must be the linear portion
            new_linear_part_term = sym1 * diff_expr
            linear_part += new_linear_part_term

            #nonlinear_part = sympy.simplify(expr - linear_part)

            linear_part = sympy.simplify(linear_part)
            nonlinear_part = sympy.simplify(nonlinear_part)

            #
            #   check if this symbol appears as a linear constant coefficient term in the definition (e.g. "42/e * x" for sym1 = "x") by checking if differentiating again with respect to all known variable symbols yields zero
            #

            #sym1_appears_as_lin_const_coeff = True
            #diff_expr = sympy.diff(expr, sym1)
            #print("diff_expr = " + str(diff_expr))
            #for sym2 in all_variable_symbols:
                #print("\tsym2 = " + str(sym2))
                #print("\tsympy.diff(diff_expr, sym2) = " + str(sympy.diff(diff_expr, sym2)))
                #if not sympy.diff(diff_expr, sym2).is_zero:
                    #diff_expr -= sym2 * sympy.diff(diff_expr, sym2)
                    #nonlinear_part += sym2 * sympy.diff(diff_expr, sym2)
                    ##sym1_appears_as_lin_const_coeff = False
                    ##break
            #print("\t\t----> " + str(sym1_appears_as_lin_const_coeff))


            #
            #   if linear, put into `derivative_factors`; leave all nonlinear terms for `diff_rhs_derivatives`
            #

            derivative_factors.append(sympy.diff(linear_part, sym1))
            #expr -= nonlinear_part
            #print("Subtracting new_linear_part_term = " + str(new_linear_part_term) + " from expr = " + str(expr) + " to yield " + str(sympy.simplify(expr - linear_part)))
            expr -= new_linear_part_term
            expr = sympy.simplify(expr)
        #print("final expr = " + str(expr))

        #
        #   the nonlinear and non-homogeneous parts are in `diff_rhs_derivatives`
        #

        diff_rhs_derivatives = expr

            #diff_expr = sympy.diff(expr, derivative_symbol)
            #if diff(diff_expr, derivative_symbol).is_zero:
                ## the equation is nonlinear in this `derivative_symbol`; do not put this term into `derivative_factors` but leave it for `diff_rhs_derivatives`
                #derivative_factors.append(sympy.Float(0.))
            #else:
                #derivative_factors.append(diff_expr)
                #expr -= expr * derivative_symbol
                #expr = sympy.simplify(expr)

        #diff_rhs_derivatives = sympy.simplify(definition)
        #for derivative_factor, derivative_symbol in zip(derivative_factors, derivative_symbols):
            #diff_rhs_derivatives -= derivative_factor * derivative_symbol
            #diff_rhs_derivatives = sympy.simplify(diff_rhs_derivatives)

        print("In creating shape " + str(symbol))
        print(str(definition))"""

        derivative_factors, diff_rhs_derivatives = Shape.split_lin_nonlin(definition, all_variable_symbols)
        local_symbols_idx = [ all_variable_symbols.index(sym) for sym in derivative_symbols ]
        local_derivative_factors = [ derivative_factors[i] for i in range(len(all_variable_symbols)) if i in local_symbols_idx ]
        nonlocal_derivative_terms = [ derivative_factors[i] * all_variable_symbols[i] for i in range(len(all_variable_symbols)) if i not in local_symbols_idx ]
        if nonlocal_derivative_terms:
            diff_rhs_derivatives = diff_rhs_derivatives + functools.reduce(lambda x, y: x + y, nonlocal_derivative_terms)


        if str(symbol) == "I_shape_gap1":
            import pdb;pdb.set_trace()
        #derivative_factors, diff_rhs_derivatives = Shape.split_lin_nonlin(definition, derivative_symbols)

        return cls(symbol, order, initial_values, local_derivative_factors, diff_rhs_derivatives, lower_bound, upper_bound)

