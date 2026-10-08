# **************************************************************************
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 3 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'scipion@cnb.csic.es'
# *
# **************************************************************************
"""crYOLO is handed a folder of micrographs and names its output after
each input file.

A Set can hold /data/sessionA/mic001.mrc and /data/sessionB/mic001.mrc
at once: different micrographs, one basename. Linked into one folder
under that basename, crYOLO sees a single image, and both micrographs
read their coordinates back from the same .cbox afterwards.

Only the single-particle path is scoped here. The tomography protocols
share the conversion helper and must keep behaving exactly as before.
"""
import os
import shutil
import tempfile
import unittest

from sphire import convert
from sphire.protocols.protocol_cryolo_picking import SphireProtCRYOLOPicking
from sphire.protocols.protocol_cryolo_picking_tasks import (
    SphireProtCRYOLOPickingTasks,
)


class _Mic:
    def __init__(self, objId, fileName):
        self._objId = objId
        self._fileName = fileName

    def getObjId(self):
        return self._objId

    def getFileName(self):
        return self._fileName


SAME_BASENAME_A = '/data/sessionA/mic001.mrc'
SAME_BASENAME_B = '/data/sessionB/mic001.mrc'


class _CboxHarness:
    """Exercises the real .cbox path helper of each picking protocol."""

    def __init__(self, protocolClass, extraDir):
        self._protocolClass = protocolClass
        self._extraDir = extraDir
        self._itemScopedPath = SphireProtCRYOLOPicking._itemScopedPath.__get__(
            self)

    def _getExtraPath(self, *paths):
        return os.path.join(self._extraDir, *paths)

    def cboxFor(self, mic):
        return self._protocolClass._getMicCoordsFile(
            self, self._extraDir, mic)


class TestTwoMicrographsNeverShareACbox(unittest.TestCase):

    def setUp(self):
        self.extraDir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.extraDir, True)

    def _harness(self, protocolClass):
        return _CboxHarness(protocolClass, self.extraDir)

    def testPickingKeepsTheTwoApart(self):
        harness = self._harness(SphireProtCRYOLOPicking)

        self.assertNotEqual(
            harness.cboxFor(_Mic(1, SAME_BASENAME_A)),
            harness.cboxFor(_Mic(2, SAME_BASENAME_B)),
            "Both micrographs read their coordinates from the same "
            "file, so one of them gets the other's particles.",
        )

    def testPickingTasksKeepsTheTwoApart(self):
        harness = self._harness(SphireProtCRYOLOPickingTasks)

        self.assertNotEqual(
            harness.cboxFor(_Mic(1, SAME_BASENAME_A)),
            harness.cboxFor(_Mic(2, SAME_BASENAME_B)),
        )

    def testThePathIsStableForTheSameMicrograph(self):
        """Resume re-derives it and has to land on the same file."""
        harness = self._harness(SphireProtCRYOLOPicking)

        self.assertEqual(
            harness.cboxFor(_Mic(7, SAME_BASENAME_A)),
            harness.cboxFor(_Mic(7, SAME_BASENAME_A)),
        )

    def testACboxFromAnOlderRunIsStillFound(self):
        """Continuing a project written before the names were scoped."""
        harness = self._harness(SphireProtCRYOLOPicking)
        legacy = os.path.join(self.extraDir, 'mic001.cbox')
        with open(legacy, 'w') as handle:
            handle.write('legacy')

        self.assertEqual(
            harness.cboxFor(_Mic(1, SAME_BASENAME_A)),
            legacy,
            "Coordinates an earlier run already picked must still be the "
            "ones this run reads.",
        )


class TestTheLinkFolderKeepsMicrographsApart(unittest.TestCase):
    """convertMicrographs links every micrograph of a batch into one
    folder, which is what crYOLO is pointed at."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.micDir = os.path.join(self.root, 'batch')
        os.makedirs(self.micDir)

    def _realMic(self, objId, name):
        session = os.path.join(self.root, 'session%d' % objId)
        os.makedirs(session, exist_ok=True)
        path = os.path.join(session, name)
        with open(path, 'w') as handle:
            handle.write('micrograph')
        return _Mic(objId, path)

    def testTwoMicrographsWithOneBasenameBothReachCryolo(self):
        mics = [self._realMic(1, 'mic001.mrc'), self._realMic(2, 'mic001.mrc')]

        convert.convertMicrographs(mics, self.micDir,
                                   nameFunc=convert.getScopedMicFn)

        self.assertEqual(
            len(os.listdir(self.micDir)),
            2,
            "One link overwrote the other, so crYOLO only ever sees one "
            "of the two micrographs.",
        )

    def testTheTomographyBehaviourIsUnchanged(self):
        """The tomography protocols share this helper and must not move."""
        mics = [self._realMic(1, 'tomo001.mrc')]

        convert.convertMicrographs(mics, self.micDir)

        self.assertEqual(
            os.listdir(self.micDir),
            ['tomo001.mrc'],
            "Without an explicit namer the helper must keep naming "
            "exactly as it always did.",
        )


if __name__ == '__main__':
    unittest.main()


class _BatchHarness:
    """Drives the tasks protocol's own batching over a fake stream."""

    _streamingMustStop = lambda self: False
    _createBatch = SphireProtCRYOLOPickingTasks._createBatch
    _iterInputBatches = SphireProtCRYOLOPickingTasks._iterInputBatches

    def __init__(self, tmpDir, mics, batchSize):
        self._tmpDir = tmpDir
        self._mics = mics
        self._batchSize = batchSize
        self._outputErrors = []

    def _getTmpPath(self, *parts):
        return os.path.join(self._tmpDir, *parts)

    def _pollNewMicrographs(self, inputMics, processedIds, waitSecs=0):
        yield list(self._mics)

    def batches(self):
        return list(self._iterInputBatches(None, set(),
                                           batchSize=self._batchSize,
                                           waitSecs=0))


class TestBatchedPickingKeepsMicrographsApart(unittest.TestCase):
    """Batches are folders of links handed to crYOLO.

    Two micrographs whose files share a basename cannot both be linked
    under that basename: the link simply fails, and with it the thread
    feeding every GPU.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def _realMic(self, objId, name):
        session = os.path.join(self.root, 'session%d' % objId)
        os.makedirs(session, exist_ok=True)
        path = os.path.join(session, name)
        with open(path, 'w') as handle:
            handle.write('micrograph')
        return _Mic(objId, path)

    def testASharedBasenameDoesNotBreakTheBatch(self):
        mics = [self._realMic(1, 'mic001.mrc'), self._realMic(2, 'mic001.mrc')]
        harness = _BatchHarness(self.root, mics, batchSize=16)

        batches = harness.batches()

        self.assertEqual(len(batches), 1)
        self.assertEqual(
            len(os.listdir(batches[0]['path'])),
            2,
            "Both micrographs have to reach crYOLO; naming the links "
            "after the basename alone loses one of them.",
        )

    def testBatchesAreCutAtTheRequestedSize(self):
        mics = [self._realMic(i, 'mic%03d.mrc' % i) for i in range(1, 6)]
        harness = _BatchHarness(self.root, mics, batchSize=2)

        batches = harness.batches()

        self.assertEqual([len(b['items']) for b in batches], [2, 2, 1],
                         "A trailing partial batch must still be picked.")

    def testBatchSizeZeroTakesWhateverArrived(self):
        mics = [self._realMic(i, 'mic%03d.mrc' % i) for i in range(1, 4)]
        harness = _BatchHarness(self.root, mics, batchSize=0)

        batches = harness.batches()

        self.assertEqual([len(b['items']) for b in batches], [3])

    def testEveryBatchCarriesTheKeysThePipelineReads(self):
        mics = [self._realMic(1, 'mic001.mrc')]
        harness = _BatchHarness(self.root, mics, batchSize=0)

        batch = harness.batches()[0]

        for key in ('items', 'id', 'path', 'index'):
            self.assertIn(key, batch)


class _PickBatchHarness:
    """Drives the non-tasks picking protocol's batch preparation."""

    _pickMicrographsBatch = SphireProtCRYOLOPicking._pickMicrographsBatch

    def __init__(self):
        self.conservPickVar = 0.3
        self.numCpus = 1
        self.lowPassFilter = False
        self.inputModelFrom = None
        self.ranIn = None

    def _getExtraPath(self, *parts):
        return os.path.join('/tmp', *parts)

    def getInputModel(self):
        return 'model.h5'

    def usingCpu(self):
        return True


class TestPickingLinksEveryMicrographForCryolo(unittest.TestCase):
    """The picking protocol builds crYOLO's input folder itself.

    It is the call site, not the conversion helper, that decides whether
    the links are scoped - so that is what this pins down.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)

    def _realMic(self, objId, name):
        session = os.path.join(self.root, 'session%d' % objId)
        os.makedirs(session, exist_ok=True)
        path = os.path.join(session, name)
        with open(path, 'w') as handle:
            handle.write('micrograph')
        return _Mic(objId, path)

    def testBothMicrographsAreLinkedForCryolo(self):
        from sphire import Plugin

        workingDir = os.path.join(self.root, 'work')
        mics = [self._realMic(1, 'mic001.mrc'), self._realMic(2, 'mic001.mrc')]
        harness = _PickBatchHarness()

        original = Plugin.runCryolo
        Plugin.runCryolo = lambda *a, **k: None
        try:
            harness._pickMicrographsBatch(mics, workingDir, '0')
        finally:
            Plugin.runCryolo = original

        self.assertEqual(
            len(os.listdir(workingDir)),
            2,
            "crYOLO is pointed at this folder: naming the links after the "
            "basename alone leaves one micrograph out of the run.",
        )
