# **************************************************************************
# *
# * Regression tests for SPHIRE streaming/resume behaviour.
# *
# **************************************************************************

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import pwem.objects as emobj

from sphire.protocols import protocol_cryolo_picking_tasks as tasks


class _Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _Summary:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class _Mic:
    def __init__(self, objId):
        self.objId = objId

    def getObjId(self):
        return self.objId

    def clone(self):
        return _Mic(self.objId)


class _StreamingMics:
    def __init__(self):
        self.reloads = 0
        self.items = [_Mic(7)]

    def getFileName(self):
        raise AssertionError(
            "Streaming must not depend on a persistence filename as the "
            "logical source of truth."
        )

    def hasChangedSince(self, lastCheck):
        return True

    def loadAllProperties(self):
        self.reloads += 1

    def iterItems(self):
        return iter(self.items)

    def isStreamClosed(self):
        return True

    def getSize(self):
        return len(self.items)

    def __iter__(self):
        return self.iterItems()


class _OutputCoordinates:
    def __init__(self):
        self.state = None

    def aggregate(self, *args, **kwargs):
        return []

    def setStreamState(self, state):
        self.state = state


class _BatchManager:
    seenIds = []

    def __init__(self, batchSize, micsIter, workingPath):
        type(self).seenIds = [mic.getObjId() for mic in micsIter]

    def generate(self):
        return iter(())


class _Node:
    outputQueue = object()


class _Pipeline:
    def addGenerator(self, generator):
        return _Node()

    def addProcessor(self, inputQueue, processor, outputQueue=None):
        return _Node()

    def run(self):
        pass


class _TasksHarness:
    def __init__(self, tmpDir):
        self.tmpDir = tmpDir
        self.mics = _StreamingMics()
        self.outputCoordinates = _OutputCoordinates()
        self.streamingSleepOnWait = _Value(0)
        self.streamingBatchSize = _Value(16)
        self.summaryVar = _Summary()

    def getInputMicrographs(self):
        return self.mics

    def getPath(self, *parts):
        return os.path.join(self.tmpDir, *parts)

    def _getTmpPath(self):
        return self.tmpDir

    def getGpuList(self):
        return []

    def info(self, *args, **kwargs):
        pass

    def _store(self, *args, **kwargs):
        pass

    def _updateSummary(self, total):
        pass

    def _updateOutputCoords(self, batch):
        return batch

    def _iterInputMicrographs(self, *args, **kwargs):
        method = getattr(
            tasks.SphireProtCRYOLOPickingTasks,
            "_iterInputMicrographs",
        )
        return method(self, *args, **kwargs)

    def _iterAvailableInputBatches(self, *args, **kwargs):
        method = getattr(
            tasks.SphireProtCRYOLOPickingTasks,
            "_iterAvailableInputBatches",
        )
        return method(self, *args, **kwargs)


class TestSphireStreamingRegression(unittest.TestCase):
    def testTasksStreamingUsesLogicalSetApi(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _TasksHarness(tmp)

            with patch.object(tasks, "BatchManager", _BatchManager),                  patch.object(tasks, "Pipeline", _Pipeline):
                tasks.SphireProtCRYOLOPickingTasks.pickAllMicrogaphsStep(
                    protocol
                )

            self.assertEqual([7], _BatchManager.seenIds)
            self.assertGreaterEqual(protocol.mics.reloads, 1)
            self.assertEqual(
                emobj.Set.STREAM_CLOSED,
                protocol.outputCoordinates.state,
            )

    def testTasksResumeReconcilesStaleJsonWithPersistedCoordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _TasksHarness(tmp)
            protocol.mics.items = [_Mic(1), _Mic(2), _Mic(3)]

            class _PersistedCoordinates(_OutputCoordinates):
                def aggregate(self, *args, **kwargs):
                    return [{"_micId": 2, "COUNT": 15}]

            protocol.outputCoordinates = _PersistedCoordinates()

            with open(protocol.getPath("micrographs.json"), "w") as handle:
                json.dump({"processed": {"1": 0}}, handle)

            with patch.object(tasks, "BatchManager", _BatchManager),                  patch.object(tasks, "Pipeline", _Pipeline):
                tasks.SphireProtCRYOLOPickingTasks.pickAllMicrogaphsStep(
                    protocol
                )

            self.assertEqual([3], _BatchManager.seenIds)

    def testTasksSummaryHandlesEmptyOpenStream(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _TasksHarness(tmp)
            protocol._processedMics = {}

            tasks.SphireProtCRYOLOPickingTasks._updateSummary(protocol, 0)

            self.assertIn("0.00%", protocol.summaryVar.value)

    def testTasksEmptyClosedStreamCreatesClosedOutput(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _TasksHarness(tmp)
            protocol.mics.items = []
            del protocol.outputCoordinates

            created = _OutputCoordinates()
            protocol.getInputMicrographsPointer = lambda: object()
            protocol._createSetOfCoordinates = lambda pointer: created
            protocol._defineSourceRelation = lambda *args, **kwargs: None

            def _updateOutputSet(name, output, streamMode):
                output.setStreamState(streamMode)
                setattr(protocol, name, output)

            protocol._updateOutputSet = _updateOutputSet

            with patch.object(tasks, "BatchManager", _BatchManager),                  patch.object(tasks, "Pipeline", _Pipeline):
                tasks.SphireProtCRYOLOPickingTasks.pickAllMicrogaphsStep(
                    protocol
                )

            self.assertIs(created, protocol.outputCoordinates)
            self.assertEqual(
                emobj.Set.STREAM_CLOSED,
                protocol.outputCoordinates.state,
            )

    def testTasksBatchZeroFlushesCurrentlyAvailableMicrographs(self):
        with tempfile.TemporaryDirectory() as tmp:
            micFiles = []
            for index in range(1, 4):
                micFile = os.path.join(tmp, f"mic_{index}.mrc")
                with open(micFile, "w") as handle:
                    handle.write("test")
                micFiles.append(micFile)

            class _FileMic(_Mic):
                def __init__(self, objId, fileName):
                    super().__init__(objId)
                    self.fileName = fileName

                def getFileName(self):
                    return self.fileName

                def clone(self):
                    return _FileMic(self.objId, self.fileName)

            class _PollingStreamingMics(_StreamingMics):
                def __init__(self):
                    self.reloads = 0
                    self.items = [
                        _FileMic(1, micFiles[0]),
                        _FileMic(2, micFiles[1]),
                    ]
                    self.closed = False

                def loadAllProperties(self):
                    self.reloads += 1
                    if self.reloads >= 2 and not self.closed:
                        self.items.append(_FileMic(3, micFiles[2]))
                        self.closed = True

                def isStreamClosed(self):
                    return self.closed

            class _CollectingPipeline:
                batches = []

                def addGenerator(self, generator):
                    generated = list(generator())
                    type(self).batches = [
                        [mic.getObjId() for mic in batch["items"]]
                        for batch in generated
                    ]
                    return _Node()

                def addProcessor(self, inputQueue, processor, outputQueue=None):
                    return _Node()

                def run(self):
                    pass

            protocol = _TasksHarness(tmp)
            protocol.mics = _PollingStreamingMics()
            protocol.streamingBatchSize = _Value(0)

            with patch.object(tasks, "Pipeline", _CollectingPipeline):
                tasks.SphireProtCRYOLOPickingTasks.pickAllMicrogaphsStep(
                    protocol
                )

            self.assertEqual(
                [[1, 2], [3]],
                _CollectingPipeline.batches,
            )


if __name__ == "__main__":
    unittest.main()
