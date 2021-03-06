# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the PyMVPA package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helper to map and validate samples' origids into indices"""

import numpy as np

class SamplesLookup(object):
    """Map to translate sample origids into unique indices.
    """

    def __init__(self, ds):
        """
        Parameters
        ----------
        ds : Dataset
            Dataset for which to create the map
        """
        
        # TODO: Generate origids and magic_id in Dataset!!
        # They are simply added here for development convenience, but they
        # should be removed.  We should also consider how exactly to calculate
        # the magic ids and sample ids as this is not necessarily the fastest/
        # most robust method --SG
        try:
            sample_ids = ds.sa.origids
        except AttributeError:
            # origids not yet generated
            if __debug__:
                Warning("Generating dataset origids in SamplesLookup")
            ds.sa.update({'origids':np.arange(ds.nsamples)})
            sample_ids = ds.sa.origids
        
        try:
            self._orig_ds_id = ds.a.magic_id
        except AttributeError:
            ds.a.update({'magic_id':hash(ds)})
            self._orig_ds_id = ds.a.magic_id
            if __debug__:
                Warning("Generating dataset magic_id in SamplesLookup")
                
        self._map = dict(zip(sample_ids,
                             range(len(sample_ids))))

    def __call__(self, ds):
        """
        .. note:
           Will raise KeyError if lookup for sample_ids fails, or ds has not 
           been mapped at all
           """
        if (not 'magic_id' in ds.a) or ds.a.magic_id != self._orig_ds_id:
            raise KeyError, 'This dataset is not indexed by this SamplesLookup'
        _map = self._map
        return np.array([_map[i] for i in ds.sa.origids])

