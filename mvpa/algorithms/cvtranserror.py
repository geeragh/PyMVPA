# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the PyMVPA package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Cross-validate a classifier on a dataset"""

__docformat__ = 'restructuredtext'

import numpy as N

from mvpa.support.copy import deepcopy

from mvpa.measures.base import DatasetMeasure
from mvpa.datasets.base import Dataset
from mvpa.datasets.splitters import NoneSplitter
from mvpa.base import warning
from mvpa.misc.state import StateVariable, Harvestable
from mvpa.misc.transformers import GrandMean

if __debug__:
    from mvpa.base import debug


class CrossValidatedTransferError(DatasetMeasure, Harvestable):
    """Classifier cross-validation.

    This class provides a simple interface to cross-validate a classifier
    on datasets generated by a splitter from a single source dataset.

    Arbitrary performance/error values can be computed by specifying an error
    function (used to compute an error value for each cross-validation fold)
    and a combiner function that aggregates all computed error values across
    cross-validation folds.
    """

    results = StateVariable(enabled=False, doc=
       """Store individual results in the state""")
    splits = StateVariable(enabled=False, doc=
       """Store the actual splits of the data. Can be memory expensive""")
    transerrors = StateVariable(enabled=False, doc=
       """Store copies of transerrors at each step. If enabled -
       operates on clones of transerror, but for the last split original
       transerror is used""")
    confusion = StateVariable(enabled=False, doc=
       """Store total confusion matrix (if available)""")
    training_confusion = StateVariable(enabled=False, doc=
       """Store total training confusion matrix (if available)""")
    samples_error = StateVariable(enabled=False,
                        doc="Per sample errors.")


    def __init__(self,
                 transerror,
                 splitter=None,
                 expose_testdataset=False,
                 harvest_attribs=None,
                 copy_attribs='copy',
                 samples_idattr='origids',
                 **kwargs):
        """
        Parameters
        ----------
        transerror : TransferError instance
          Provides the classifier used for cross-validation.
        splitter : Splitter or None
          Used to split the dataset for cross-validation folds. By
          convention the first dataset in the tuple returned by the
          splitter is used to train the provided classifier. If the
          first element is 'None' no training is performed. The second
          dataset is used to generate predictions with the (trained)
          classifier. If `None` (default) an instance of
          :class:`~mvpa.datasets.splitters.NoneSplitter` is used.
        expose_testdataset : bool, optional
          In the proper pipeline, classifier must not know anything
          about testing data, but in some cases it might lead only
          to marginal harm, thus migth wanted to be enabled (provide
          testdataset for RFE to determine stopping point).
        harvest_attribs : list of str
          What attributes of call to store and return within
          harvested state variable
        copy_attribs : None or str, optional
          Force copying values of attributes on harvesting
        samples_idattr : str, optional
          What samples attribute to use to identify and store samples_errors
          state variable
        **kwargs
          All additional arguments are passed to the
          :class:`~mvpa.measures.base.DatasetMeasure` base class.
        """
        DatasetMeasure.__init__(self, **kwargs)
        Harvestable.__init__(self, harvest_attribs, copy_attribs)

        if splitter is None:
            self.__splitter = NoneSplitter()
        else:
            self.__splitter = splitter

        self.__transerror = transerror
        self.__expose_testdataset = expose_testdataset
        self.__samples_idattr = samples_idattr

# TODO: put back in ASAP
#    def __repr__(self):
#        """String summary over the object
#        """
#        return """CrossValidatedTransferError /
# splitter: %s
# classifier: %s
# errorfx: %s
# combiner: %s""" % (indentDoc(self.__splitter), indentDoc(self.__clf),
#                      indentDoc(self.__errorfx), indentDoc(self.__combiner))


    def _call(self, dataset):
        """Perform cross-validation on a dataset.

        'dataset' is passed to the splitter instance and serves as the source
        dataset to generate split for the single cross-validation folds.
        """
        # store the results of the splitprocessor
        results = []
        self.states.splits = []

        # local bindings
        states = self.states
        clf = self.__transerror.clf
        expose_testdataset = self.__expose_testdataset

        # what states to enable in terr
        terr_enable = []
        for state_var in ['confusion', 'training_confusion', 'samples_error']:
            if states.is_enabled(state_var):
                terr_enable += [state_var]

        # charge states with initial values
        summaryClass = clf.__summary_class__
        clf_hastestdataset = hasattr(clf, 'testdataset')

        self.states.confusion = summaryClass()
        self.states.training_confusion = summaryClass()
        self.states.transerrors = []
        if states.is_enabled('samples_error'):
            dataset.init_origids('samples',
                                 attr=self.__samples_idattr, mode='existing')
            self.states.samples_error = dict(
                [(id_, []) for id_ in dataset.sa[self.__samples_idattr].value])

        # enable requested states in child TransferError instance (restored
        # again below)
        if len(terr_enable):
            self.__transerror.states.change_temporarily(
                enable_states=terr_enable)

        # We better ensure that underlying classifier is not trained if we
        # are going to deepcopy transerror
        if states.is_enabled("transerrors"):
            self.__transerror.untrain()

        # collect sum info about the split that where made for the resulting
        # dataset
        splitinfo = []

        # splitter
        for split in self.__splitter(dataset):
            splitinfo.append(
                "%s->%s"
                % (','.join([str(c)
                    for c in split[0].sa[self.__splitter.splitattr].unique]),
                   ','.join([str(c)
                    for c in split[1].sa[self.__splitter.splitattr].unique])))

            # only train classifier if splitter provides something in first
            # element of tuple -- the is the behavior of TransferError
            if states.is_enabled("splits"):
                self.states.splits.append(split)

            if states.is_enabled("transerrors"):
                # copy first and then train, as some classifiers cannot be copied
                # when already trained, e.g. SWIG'ed stuff
                lastsplit = None
                for ds in split:
                    if ds is not None:
                        lastsplit = ds.a.lastsplit
                        break
                if lastsplit:
                    # only if we could deduce that it was last split
                    # use the 'mother' transerror
                    transerror = self.__transerror
                else:
                    # otherwise -- deep copy
                    transerror = deepcopy(self.__transerror)
            else:
                transerror = self.__transerror

            # assign testing dataset if given classifier can digest it
            if clf_hastestdataset and expose_testdataset:
                transerror.clf.testdataset = split[1]

            # run the beast
            result = transerror(split[1], split[0])

            # unbind the testdataset from the classifier
            if clf_hastestdataset and expose_testdataset:
                transerror.clf.testdataset = None

            # next line is important for 'self._harvest' call
            self._harvest(locals())

            # XXX Look below -- may be we should have not auto added .?
            #     then transerrors also could be deprecated
            if states.is_enabled("transerrors"):
                self.states.transerrors.append(transerror)

            # XXX: could be merged with next for loop using a utility class
            # that can add dict elements into a list
            if states.is_enabled("samples_error"):
                for k, v in \
                  transerror.states.samples_error.iteritems():
                    self.states.samples_error[k].append(v)

            # pull in child states
            for state_var in ['confusion', 'training_confusion']:
                if states.is_enabled(state_var):
                    states[state_var].value.__iadd__(
                        transerror.states[state_var].value)

            if __debug__:
                debug("CROSSC", "Split #%d: result %s" \
                      % (len(results), `result`))
            results.append(result)

        # Since we could have operated with a copy -- bind the last used one back
        self.__transerror = transerror

        # put states of child TransferError back into original config
        if len(terr_enable):
            self.__transerror.states.reset_changed_temporarily()

        self.states.results = results
        """Store state variable if it is enabled"""
        results = Dataset(results, sa={'cv_fold': splitinfo})
        return results


    splitter = property(fget=lambda self:self.__splitter,
                        doc="Access to the Splitter instance.")
    transerror = property(fget=lambda self:self.__transerror,
                        doc="Access to the TransferError instance.")
