# **************************************************************************
# *
# * crYOLO picking in streaming: a failed micrograph is left out and picked
# * again on Continue, a micrograph is published whole, and the run fails
# * only when every micrograph failed.
# *
# **************************************************************************

import json
import os
import tempfile
import unittest
from collections import OrderedDict
from unittest.mock import patch

import pwem.objects as emobj

import sphire.convert as convert
from sphire.protocols import protocol_cryolo_picking_tasks as tasks
from sphire.protocols.protocol_cryolo_picking import SphireProtCRYOLOPicking

from .test_streaming_regression import _Mic as _TasksMic, _Node, _TasksHarness


def _mic(objId):
    mic = emobj.Micrograph()
    mic.setObjId(objId)
    mic.setMicName("mic_%03d" % objId)
    mic.setFileName("/data/mic_%03d.mrc" % objId)
    return mic


class _StoredValue:
    def __init__(self, value):
        self._value = value

    def get(self, default=None):
        return self._value


class _PickStep:
    def __init__(self, micName, finished=True):
        self.funcName = _StoredValue("pickMicrographListStepOwn")
        self.argsStr = _StoredValue(json.dumps([[micName]]))
        self._finished = finished

    def isFinished(self):
        return self._finished


class _Picking(SphireProtCRYOLOPicking):
    def __init__(self, root):
        self._root = root
        os.makedirs(os.path.join(root, 'extra'), exist_ok=True)
        os.makedirs(os.path.join(root, 'tmp'), exist_ok=True)
        self.micDict = OrderedDict()
        self._pendingMics = OrderedDict()
        self._knownMicIds = set()
        self._prevSteps = []
        self._steps = []
        self.errors = []
        self.newItems = []

    def _getExtraPath(self, *paths):
        return os.path.join(self._root, 'extra', *paths)

    def _getTmpPath(self, *paths):
        return os.path.join(self._root, 'tmp', *paths)

    def _discoverNewInputItems(self, inputSet, watermarkAttr, knownIds):
        return self.newItems, False, False

    def error(self, message, redirectStandard=True):
        self.errors.append(message)

    def info(self, *args, **kwargs):
        pass


class TestFailedMicrographsArePickedAgain(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def _continued(self):
        """Both micrographs had a finished step; only 2 failed."""
        protocol = _Picking(self._tmp.name)
        protocol._prevSteps = [_PickStep("mic_001"), _PickStep("mic_002")]
        protocol._recordFailedPicking([2])
        protocol._failedPickingMicIdsCache = None
        protocol.newItems = [_mic(1), _mic(2)]
        return protocol

    def test_AFailedMicrographGetsANewStep(self):
        protocol = self._continued()

        protocol._loadSet(None, None, lambda mic: mic.getMicName())

        self.assertEqual(["mic_001"], list(protocol.micDict))
        self.assertEqual(["mic_002"], list(protocol._pendingMics))

    def test_ItsOldFinishedStepDoesNotPublishIt(self):
        # Published before its new step ran, it would be read as failed
        # once more and never published after picking well.
        protocol = self._continued()
        protocol._loadSet(None, None, lambda mic: mic.getMicName())

        self.assertEqual({"mic_001"}, protocol._getFinishedPickingMicNames())

        protocol._steps.append(_PickStep("mic_002"))

        self.assertEqual({"mic_001", "mic_002"},
                         protocol._getFinishedPickingMicNames())

    def test_AMicrographWithoutOutputIsRecordedAndTheOthersKept(self):
        protocol = _Picking(self._tmp.name)
        good, bad = _mic(1), _mic(2)
        # An output left by an earlier, failed attempt.
        stale = protocol._getExtraPath(convert.getScopedMicFn(bad, 'cbox'))
        open(stale, 'w').close()

        def pick(micList, workingDir, gpuId, clean=True):
            os.makedirs(os.path.join(workingDir, 'CBOX'))
            open(os.path.join(workingDir, 'CBOX',
                              convert.getScopedMicFn(good, 'cbox')), 'w').close()

        protocol._pickMicrographsBatch = pick
        protocol._pickMicrographList([good, bad])

        self.assertTrue(os.path.exists(
            protocol._getExtraPath(convert.getScopedMicFn(good, 'cbox'))))
        self.assertFalse(os.path.exists(stale))
        self.assertEqual({2}, protocol._failedPickingMicIds())

    def test_ACrashOfCryoloDoesNotFailTheStep(self):
        protocol = _Picking(self._tmp.name)

        def crash(*args, **kwargs):
            raise RuntimeError("GPU out of memory")

        protocol._pickMicrographsBatch = crash
        protocol._pickMicrographList([_mic(1), _mic(2)])

        self.assertEqual({1, 2}, protocol._failedPickingMicIds())
        self.assertTrue(protocol.errors)


class _HalfReadable:
    """A .cbox reader that breaks after the first row."""

    def __init__(self, *args, **kwargs):
        pass

    def iterCoords(self, fileName):
        yield 10, 20, 0, 0.9, None, None
        raise ValueError("truncated cbox")


class _Coords:
    def __init__(self):
        self.items = []

    def getBoxSize(self):
        return 64

    def append(self, coord):
        self.items.append(coord.clone())


class TestAMicrographIsPublishedWhole(unittest.TestCase):
    def test_ACboxThatBreaksHalfWayPublishesNothingOfIt(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _Picking(tmp)
            protocol.yFlipHeight = None
            protocol.boxSize = _StoredValue(64)
            protocol.createBoxSizeOutput = lambda coordSet: None
            cbox = protocol._getExtraPath(convert.getScopedMicFn(_mic(1), 'cbox'))

            with open(cbox, 'w') as handle:
                handle.write("not empty")

            coords = _Coords()

            with patch.object(convert, 'CoordBoxReader', _HalfReadable):
                processed = protocol.readCoordsFromMics(None, [_mic(1)], coords)

        self.assertEqual({}, processed)
        self.assertEqual([], coords.items)
        self.assertEqual({1}, protocol._failedPickingMicIds())

    def test_AMicrographReadWellIsNoLongerFailed(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _Picking(tmp)
            protocol.yFlipHeight = None
            protocol.boxSize = _StoredValue(64)
            protocol.createBoxSizeOutput = lambda coordSet: None
            protocol._recordFailedPicking([1])
            open(protocol._getExtraPath(
                convert.getScopedMicFn(_mic(1), 'cbox')), 'w').close()

            processed = protocol.readCoordsFromMics(None, [_mic(1)], _Coords())

        self.assertEqual({1: 0}, processed)
        self.assertEqual(set(), protocol._failedPickingMicIds())


class _Closing(_Picking):
    def __init__(self, root, failed):
        super().__init__(root)
        self.streamClosed = True
        self.micDict = OrderedDict([("mic_001", _mic(1))])
        self._steps = [_PickStep("mic_001")]
        self._failed = failed

    def _updateOutputCoordSet(self, micList, streamMode):
        if self._failed:
            self._recordFailedPicking([mic.getObjId() for mic in micList])

    def _updateStreamState(self, streamMode):
        pass


class TestPickingFailsOnlyWhenEveryMicrographFailed(unittest.TestCase):
    def test_EveryMicrographFailedFailsTheRun(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _Closing(tmp, failed=True)

            with self.assertRaisesRegex(Exception, "failed for every"):
                protocol._checkNewOutput()

    def test_AMicrographWithoutParticlesIsNoFailure(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _Closing(tmp, failed=False)

            protocol._checkNewOutput()

        self.assertTrue(protocol.finished)


class _BatchesPipeline:
    """Runs the given batches through every processor, in order."""

    def __init__(self, batches):
        self._batches = batches
        self.processors = []

    def addGenerator(self, generator):
        return _Node()

    def addProcessor(self, inputQueue, processor, outputQueue=None):
        self.processors.append(processor)
        return _Node()

    def run(self):
        for batch in self._batches:
            for processor in self.processors:
                batch = processor(batch)


class TestTasksFailOnlyWhenEveryMicrographFailed(unittest.TestCase):
    def _run(self, tmp, goodBatch):
        protocol = _TasksHarness(tmp)
        protocol.getGpuList = lambda: ["0"]
        protocol.warning = lambda *args, **kwargs: None

        def pickProcessor(gpu):
            def process(batch):
                batch['failed'] = batch['index'] == 1
                return batch
            return process

        def updateOutput(batch):
            protocol._processedMics.update(
                {mic.getObjId(): 3 for mic in batch['items']})
            return batch

        protocol._getPickProcessor = pickProcessor
        protocol._updateOutputCoords = updateOutput
        batches = [{"index": 1, "items": [_TasksMic(1)], "path": tmp}]

        if goodBatch:
            batches.append({"index": 2, "items": [_TasksMic(2)], "path": tmp})

        with patch.object(tasks, "Pipeline", lambda: _BatchesPipeline(batches)):
            tasks.SphireProtCRYOLOPickingTasks.pickAllMicrogaphsStep(protocol)

        return protocol

    def test_OneFailedBatchAmongGoodOnesEndsTheRunWell(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = self._run(tmp, goodBatch=True)

        self.assertEqual(emobj.Set.STREAM_CLOSED,
                         protocol.outputCoordinates.state)
        self.assertEqual({1}, protocol._failedPickingMicIds())
        self.assertEqual({2: 3}, protocol._processedMics)

    def test_EveryBatchFailedFailsTheRun(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "every micrograph"):
                self._run(tmp, goodBatch=False)

    def test_AMicrographWhoseCboxCouldNotBeReadIsPickedAgain(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _TasksHarness(tmp)
            protocol.outputCoordinates = None
            del protocol.outputCoordinates
            mic = _TasksMic(7)
            open(protocol._getPersistedMicCoordsFile(mic), 'w').close()
            protocol._recordFailedPicking([7])

            processed = tasks.SphireProtCRYOLOPickingTasks._restoreProcessedMics(
                protocol, protocol.mics)

        self.assertEqual({}, processed)


if __name__ == '__main__':
    unittest.main()
