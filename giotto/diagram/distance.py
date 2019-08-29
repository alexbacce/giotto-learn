# Authors: Guillaume Tauzin <guillaume.tauzin@epfl.ch>
#          Umberto Lupo <u.lupo@l2f.ch>
# License: TBD

import math as m
import numpy as np
import sklearn as sk
from sklearn.utils.validation import check_X_y, check_array, check_is_fitted
from sklearn.base import BaseEstimator, TransformerMixin
from functools import partial
import itertools

from ._metrics import _parallel_pairwise, implemented_metric_recipes
from ._utils import _sample, _pad


class DiagramDistance(BaseEstimator, TransformerMixin):
    """Transformer for calculating distances between collections of persistence diagrams.
    In the case in which diagrams in the collection have been consistently partitioned
    into one or more subdiagrams (e.g. according to homology dimension), the distance
    between any two diagrams is a *p*-norm of a vector of distances between
    respective subdiagrams of the same kind.

    Parameters
    ----------
    metric : 'bottleneck' | 'wasserstein' | 'landscape' | 'betti', optional, default: 'bottleneck'
        Which notion of distance between (sub)diagrams to use:

        - ``'bottleneck'`` and ``'wasserstein'`` refer to the identically named
           perfect-matching--based notions of distance.
        - ``'landscape'`` refers to a family of possible (:math:`L^p`-like) distances
           between "persistence landscapes" obtained from persistence (sub)diagrams.
        - ``'betti'`` refers to a family of possible (:math:`L^p`-like) distances
           between "Betti curves" obtained from persistence (sub)diagrams. A Betti
           curve simply records the evolution in the number of independent topological
           holes (technically, the number of linearly independent homology classes)
           as can be read from a persistence (sub)diagram.

    metric_params : dict, optional, default: {'n_samples': 200}
        Additional keyword arguments for the metric function:

        - If ``metric == 'bottleneck'`` the available arguments are ``order`` (default = ``np.inf``)
          and ``delta`` (default = ``0.0``).
        - If ``metric == 'wasserstein'`` the only argument is ``order`` (default = ``1``)
          and ``delta`` (default = ``0.0``).
        - If ``metric == 'landscape'`` the available arguments are ``order``
          (default = ``2``), ``n_samples`` (default = ``200``) and ``n_layers``
          (default = ``1``).
        - If ``metric == 'betti'`` the available arguments are ``order`` (default = ``2``)
           and ``n_samples`` (default = ``200``).

    n_jobs : int or None, optional, default: None
        The number of jobs to use for the computation. ``None`` means 1 unless in
        a :obj:`joblib.parallel_backend` context. ``-1`` means using all processors.

    """
    def __init__(self, metric='bottleneck', metric_params={'n_samples': 200, 'delta': 0.0}, n_jobs=None):
        self.metric = metric
        self.metric_params = metric_params
        self.n_jobs = n_jobs

    def get_params(self, deep=True):
        """Get parameters for this estimator.

        Parameters
        ----------
        deep : boolean, optional, default: True
            Behaviour not yet implemented.

        Returns
        -------
        params : mapping of string to any
            Parameter names mapped to their values.
        """
        return {'metric': self.metric, 'metric_params': self.metric_params, 'n_jobs': self.n_jobs}

    @staticmethod
    def _validate_params():
        pass

    def fit(self, X, y=None):
        """Fit the estimator and return it.

        Parameters
        ----------
        X : dict of int: ndarray
            Input data. Dictionary whose keys are typically non-negative integers representing
            homology dimensions, and whose values are ndarrays of shape (n_samples, M, 2)
            whose each entries along axis 0 are persistence diagrams.

        y : None
            There is no need of a target in a transformer, yet the pipeline API
            requires this parameter.

        Returns
        -------
        self : object
            Returns self.

        """
        self._validate_params()

        if 'n_samples' in self.metric_params:
            self._n_samples = self.metric_params['n_samples']
        else:
            self._n_samples = None

        self._X = X

        if self.metric in ['landscape', 'betti']:
            self.metric_params['sampling'] = _sample(self._X, self._n_samples)

        self._is_fitted = True
        return self

    def transform(self, X, y=None):
        """Computes the distance matrix between the diagrams in X, according to
        the choice of ``metric`` and ``metric_params``.

        Parameters
        ----------
        X : dict of int: ndarray
            Input data. Dictionary whose keys are typically non-negative integers representing
            homology dimensions, and whose values are ndarrays of shape (n_samples, M, 2)
            whose each entries along axis 0 are persistence diagrams.

        y : None
            There is no need of a target in a transformer, yet the pipeline API
            requires this parameter.

        Returns
        -------
        X_transformed : ndarray, shape (n_samples, n_samples)
            Distance matrix between diagrams in X.

        """
        check_is_fitted(self, ['_is_fitted'])
        n_diagrams_X = next(iter(X.values())).shape[0]

        metric_params = self.metric_params.copy()

        if 'n_samples' in metric_params:
            metric_params.pop('n_samples')

        is_same = np.all([np.array_equal(X[dimension], self._X[dimension]) for dimension in X.keys()])
        if is_same:
            # Only calculate metric for upper triangle
            iterator = list(itertools.combinations(range(n_diagrams_X), 2))
            X_transformed = _parallel_pairwise(X, X, self.metric, metric_params, iterator, self.n_jobs)
            X_transformed = X_transformed + X_transformed.T
        else:
            max_betti_numbers = {dimension: max(self._X[dimension].shape[1], X[dimension].shape[1]) for dimension in self._X.keys()}
            self._X = _pad(self._X, max_betti_numbers)
            X = _pad(X, max_betti_numbers)
            Y = {dimension: np.vstack([self._X[dimension], X[dimension]]) for dimension in self._X.keys()}
            n_diagrams_Y = next(iter(Y.values())).shape[0]

            # Calculate all cells
            iterator = tuple(itertools.product(range(n_diagrams_Y), range(n_diagrams_X)))
            X_transformed = _parallel_pairwise(Y, X, self.metric, metric_params, iterator, self.n_jobs)

        return X_transformed