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
from sphire.protocols.protocol_cryolo_picking import SphireProtCRYOLOPicking


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


    def testTasksSummaryKeepsPreviousCheckpointIfJsonWriteFails(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _TasksHarness(tmp)
            protocol._processedMics = {1: 4, 2: 0}
            checkpoint = protocol.getPath("micrographs.json")

            with open(checkpoint, "w") as handle:
                json.dump({"processed": {"1": 4}}, handle)

            def _failingDump(payload, handle):
                handle.write('{"processed": ')
                handle.flush()
                raise RuntimeError("simulated crash while writing checkpoint")

            with patch.object(tasks.json, "dump", _failingDump):
                with self.assertRaises(RuntimeError):
                    tasks.SphireProtCRYOLOPickingTasks._updateSummary(
                        protocol,
                        2,
                    )

            with open(checkpoint) as handle:
                persisted = json.load(handle)

            self.assertEqual(
                {"processed": {"1": 4}},
                persisted,
                "A failed checkpoint rewrite must leave the previous valid "
                "micrographs.json untouched for Resume.",
            )


    def testTasksPickProcessorToleratesFailedBatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _TasksHarness(tmp)
            warnings = []
            protocol.warning = warnings.append

            def _failPicking(*args, **kwargs):
                raise RuntimeError("simulated crYOLO batch failure")

            protocol._pickMicrographsBatch = _failPicking

            batch = {
                "index": 1,
                "items": [_Mic(1)],
                "path": tmp,
            }

            processor = tasks.SphireProtCRYOLOPickingTasks._getPickProcessor(
                protocol,
                "0",
            )
            result = processor(batch)

            self.assertIs(
                batch,
                result,
                "A failed crYOLO batch must be returned downstream so the "
                "stream can checkpoint it and continue with later batches.",
            )
            self.assertTrue(
                warnings,
                "A tolerated crYOLO batch failure must still be reported.",
            )


    def testTasksOutputUpdateDoesNotCheckpointUnreadableCoords(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _TasksHarness(tmp)
            protocol._processedMics = {}
            protocol._inputMicsCount = 1

            class _AppendableOutput(_OutputCoordinates):
                def enableAppend(self):
                    pass

            class _BatchMic(_Mic):
                def strId(self):
                    return str(self.getObjId())

            protocol.outputCoordinates = _AppendableOutput()
            protocol.readCoordsFromMics = lambda *args, **kwargs: None

            def _updateOutputSet(name, output, streamMode):
                output.setStreamState(streamMode)
                setattr(protocol, name, output)

            protocol._updateOutputSet = _updateOutputSet

            batch = {
                "index": 1,
                "items": [_BatchMic(1)],
                "path": tmp,
            }

            with self.assertRaisesRegex(
                RuntimeError,
                "coordinates",
            ):
                tasks.SphireProtCRYOLOPickingTasks._updateOutputCoords(
                    protocol,
                    batch,
                )

            self.assertEqual(
                {},
                protocol._processedMics,
                "Unreadable coordinates must not be checkpointed as a "
                "successful zero-coordinate result.",
            )


    def testTasksStreamingDoesNotMissChangeDuringRefresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            class _Clock:
                current = 0

                @classmethod
                def now(cls):
                    return cls.current

            class _RacyStreamingMics(_StreamingMics):
                def __init__(self):
                    self.items = [_Mic(1)]
                    self.snapshot = []
                    self.reloads = 0
                    self.changeTime = 5
                    self.closed = False

                def hasChangedSince(self, lastCheck):
                    if lastCheck is None:
                        return True
                    if self.changeTime > lastCheck:
                        return True
                    raise AssertionError(
                        "The polling checkpoint advanced past an unseen "
                        "Set change."
                    )

                def loadAllProperties(self):
                    self.reloads += 1
                    self.snapshot = list(self.items)

                    if self.reloads == 1:
                        # Simulate a new item committed after this refresh took
                        # its snapshot but before the poll checkpoint is saved.
                        self.items.append(_Mic(2))
                        _Clock.current = 10
                    else:
                        self.closed = True

                def iterItems(self):
                    return iter(self.snapshot)

                def isStreamClosed(self):
                    return self.closed

                def getSize(self):
                    return len(self.items)

            protocol = _TasksHarness(tmp)
            inputMics = _RacyStreamingMics()

            with patch.object(tasks, "datetime", _Clock):
                yielded = list(
                    protocol._iterInputMicrographs(
                        inputMics,
                        {},
                        waitSecs=0,
                    )
                )

            self.assertEqual(
                [1, 2],
                [mic.getObjId() for mic in yielded],
                "A Set change that lands during a refresh must be detected "
                "on the next poll instead of being skipped forever.",
            )


    def testTasksResumeRecoversFromCorruptCheckpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _TasksHarness(tmp)
            protocol.mics.items = [_Mic(1), _Mic(2), _Mic(3)]
            warnings = []
            protocol.warning = warnings.append

            class _PersistedCoordinates(_OutputCoordinates):
                def aggregate(self, *args, **kwargs):
                    return [{"_micId": 2, "COUNT": 15}]

            protocol.outputCoordinates = _PersistedCoordinates()

            with open(protocol.getPath("micrographs.json"), "w") as handle:
                handle.write('{"processed": ')

            with patch.object(tasks, "BatchManager", _BatchManager),                  patch.object(tasks, "Pipeline", _Pipeline):
                tasks.SphireProtCRYOLOPickingTasks.pickAllMicrogaphsStep(
                    protocol
                )

            self.assertEqual(
                [1, 3],
                _BatchManager.seenIds,
                "Resume must recover persisted coordinate-producing "
                "micrographs even when the legacy JSON checkpoint is corrupt.",
            )
            self.assertTrue(
                warnings,
                "Recovering from a corrupt checkpoint must emit a warning.",
            )


    def testTasksPropagatesOutputPersistenceFailure(self):
        with tempfile.TemporaryDirectory() as tmp:
            micFile = os.path.join(tmp, "mic_1.mrc")
            with open(micFile, "w") as handle:
                handle.write("test")

            class _FileMic(_Mic):
                def getFileName(self):
                    return micFile

                def clone(self):
                    return _FileMic(self.objId)

            protocol = _TasksHarness(tmp)
            protocol.mics.items = [_FileMic(1)]
            protocol.streamingBatchSize = _Value(0)
            protocol.getGpuList = lambda: ["0"]
            protocol._getPickProcessor = lambda gpu: (lambda batch: batch)

            def _failOutputUpdate(batch):
                raise RuntimeError("simulated output persistence failure")

            protocol._updateOutputCoords = _failOutputUpdate

            with self.assertRaisesRegex(
                RuntimeError,
                "simulated output persistence failure",
            ):
                tasks.SphireProtCRYOLOPickingTasks.pickAllMicrogaphsStep(
                    protocol
                )

    def testTasksFailedPickingBatchIsNotCheckpointedAsProcessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _TasksHarness(tmp)
            protocol._processedMics = {}
            protocol._inputMicsCount = 1
            protocol.warning = lambda *args, **kwargs: None

            def _failPicking(*args, **kwargs):
                raise RuntimeError("simulated crYOLO batch failure")

            protocol._pickMicrographsBatch = _failPicking

            def _mustNotReadFailedBatch(*args, **kwargs):
                raise AssertionError(
                    "A failed picking batch must not be read as a "
                    "successful zero-coordinate result."
                )

            protocol.readCoordsFromMics = _mustNotReadFailedBatch

            batch = {
                "index": 1,
                "items": [_Mic(1)],
                "path": tmp,
            }

            processor = tasks.SphireProtCRYOLOPickingTasks._getPickProcessor(
                protocol,
                "0",
            )
            failedBatch = processor(batch)

            tasks.SphireProtCRYOLOPickingTasks._updateOutputCoords(
                protocol,
                failedBatch,
            )

            self.assertTrue(
                failedBatch.get("failed", False),
                "A crYOLO execution failure must remain attached to the "
                "batch while later batches continue through the pipeline.",
            )
            self.assertEqual(
                {},
                protocol._processedMics,
                "A failed crYOLO batch must not be checkpointed as processed; "
                "Resume must be able to retry those micrographs.",
            )





class TestSphireStreamingFailedBatchCompletionRegression(unittest.TestCase):
    def testTasksFailedPickingBatchFailsProtocolAfterPipelineDrains(self):
        with tempfile.TemporaryDirectory() as tmp:
            class _PipelineWithFailedBatch:
                def __init__(self):
                    self.processors = []

                def addGenerator(self, generator):
                    return _Node()

                def addProcessor(self, inputQueue, processor, outputQueue=None):
                    self.processors.append(processor)
                    return _Node()

                def run(self):
                    batch = {
                        "index": 1,
                        "items": [_Mic(1)],
                        "path": tmp,
                    }
                    for processor in self.processors:
                        batch = processor(batch)

            protocol = _TasksHarness(tmp)
            protocol.mics.items = [_Mic(1)]
            protocol.getGpuList = lambda: ["0"]
            protocol.warning = lambda *args, **kwargs: None

            def _failPicking(*args, **kwargs):
                raise RuntimeError("simulated crYOLO batch failure")

            protocol._pickMicrographsBatch = _failPicking
            protocol._getPickProcessor = lambda gpu: (
                tasks.SphireProtCRYOLOPickingTasks._getPickProcessor(
                    protocol,
                    gpu,
                )
            )
            protocol._updateOutputCoords = lambda batch: (
                tasks.SphireProtCRYOLOPickingTasks._updateOutputCoords(
                    protocol,
                    batch,
                )
            )

            with patch.object(tasks, "BatchManager", _BatchManager), \
                    patch.object(tasks, "Pipeline", _PipelineWithFailedBatch):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "crYOLO.*batch",
                ):
                    tasks.SphireProtCRYOLOPickingTasks.pickAllMicrogaphsStep(
                        protocol
                    )

            self.assertEqual(
                {},
                protocol._processedMics,
                "A failed batch must remain absent from the resume checkpoint.",
            )
            self.assertNotEqual(
                emobj.Set.STREAM_CLOSED,
                protocol.outputCoordinates.state,
                "The output stream must not be closed after a failed batch.",
            )

if __name__ == "__main__":
    unittest.main()

class _ClassicMic(_Mic):
    def __init__(self, objId, fileName):
        super().__init__(objId)
        self.fileName = fileName

    def getMicName(self):
        return "mic_%03d" % self.objId

    def getFileName(self):
        return self.fileName

    def strId(self):
        return str(self.objId)


class _ClassicPickingFailureHarness(SphireProtCRYOLOPicking):
    def __init__(self, tmpDir):
        self.tmpDir = tmpDir
        mic = _ClassicMic(1, os.path.join(tmpDir, "mic_1.mrc"))
        self.micDict = {mic.getMicName(): mic}
        self.warnings = []

    def isContinued(self):
        return False

    def _getMicDone(self, mic):
        return os.path.join(
            self.tmpDir,
            "DONE",
            "mic_%06d.TXT" % mic.getObjId(),
        )

    def _getTmpPath(self, *parts):
        return os.path.join(self.tmpDir, *parts)

    def _getExtraPath(self, *parts):
        return os.path.join(self.tmpDir, "extra", *parts)

    def _pickMicrographsBatch(self, *args, **kwargs):
        raise RuntimeError("simulated crYOLO picking failure")

    def warning(self, message):
        self.warnings.append(message)

    def info(self, *args, **kwargs):
        pass


class TestSphireClassicStreamingFailureResumeRegression(unittest.TestCase):
    def testClassicPickingFailureDoesNotCreateDoneMarker(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _ClassicPickingFailureHarness(tmp)
            mic = protocol.micDict["mic_001"]
            doneFile = protocol._getMicDone(mic)

            with self.assertRaisesRegex(
                RuntimeError,
                "simulated crYOLO picking failure",
            ):
                protocol.pickMicrographListStep(["mic_001"])

            self.assertFalse(
                os.path.exists(doneFile),
                "A failed crYOLO batch must not be marked DONE; Continue "
                "must be able to retry it.",
            )
            self.assertTrue(
                protocol.warnings,
                "The picking failure should still be reported as a warning.",
            )

class _ClassicNoStorageMicSet:
    def getFileName(self):
        raise AssertionError(
            "Classic crYOLO streaming must not depend on a storage filename."
        )


class _ClassicLogicalInputHarness(SphireProtCRYOLOPicking):
    def __init__(self):
        self._mics = _ClassicNoStorageMicSet()
        self.micDict = {}
        self.streamClosed = False
        self.loadCalls = 0

    def getInputMicrographs(self):
        return self._mics

    def _loadInputList(self):
        self.loadCalls += 1
        return {}, False

    def _getFirstJoinStep(self):
        return None

    def debug(self, *args, **kwargs):
        pass

    def updateSteps(self):
        raise AssertionError("No new micrographs should have been scheduled.")


class TestSphireClassicBackendIndependentInputCheck(unittest.TestCase):
    def testClassicCheckNewInputDoesNotDependOnStorageMtime(self):
        protocol = _ClassicLogicalInputHarness()

        protocol._checkNewInput()

        self.assertEqual(
            1,
            protocol.loadCalls,
            "Classic crYOLO streaming must refresh the logical Set directly "
            "instead of gating discovery on SQLite/file modification times.",
        )

class _ClassicLogicalMic:
    def __init__(self, objId, name):
        self._objId = objId
        self._name = name

    def getObjId(self):
        return self._objId

    def getMicName(self):
        return self._name

    def clone(self):
        return _ClassicLogicalMic(self._objId, self._name)


class _ClassicLogicalMicSet:
    def __init__(self, items, closed=False):
        self._items = list(items)
        self._closed = closed
        self.loadCalls = 0

    def getFileName(self):
        raise AssertionError(
            "Classic crYOLO streaming Sets must not be reopened from "
            "storage filenames."
        )

    def loadAllProperties(self):
        self.loadCalls += 1

    def iterItems(self):
        return iter(self._items)

    def isStreamClosed(self):
        return self._closed


class _ClassicLogicalLoadHarness(SphireProtCRYOLOPicking):
    def __init__(self):
        self.micDict = {}
        self._mics = _ClassicLogicalMicSet(
            [_ClassicLogicalMic(7, "mic_007")],
            closed=True,
        )

    def getInputMicrographs(self):
        return self._mics

    def debug(self, *args, **kwargs):
        pass


class TestSphireClassicLogicalSetLoading(unittest.TestCase):
    def testClassicLoadInputListUsesLogicalSet(self):
        protocol = _ClassicLogicalLoadHarness()

        newMics, closed = protocol._loadInputList()

        self.assertEqual(["mic_007"], list(newMics.keys()))
        self.assertEqual(1, protocol._mics.loadCalls)
        self.assertTrue(closed)

class _ClassicNoBoxOutput:
    def getBoxSize(self):
        return 0


class _ClassicUnreadableCoordsHarness(SphireProtCRYOLOPicking):
    def __init__(self):
        self.boxSize = _Value(0)
        self.warnings = []

    def getEstimatedBoxSize(self, outputPath):
        raise RuntimeError("box size is not available yet")

    def _getTmpPath(self, *parts):
        return os.path.join("/tmp", *parts)

    def warning(self, message):
        self.warnings.append(message)


class TestSphireClassicUnreadableCoordinatesRegression(unittest.TestCase):
    def testClassicUnreadableCoordinatesRaiseInsteadOfCompleting(self):
        protocol = _ClassicUnreadableCoordsHarness()
        outputCoords = _ClassicNoBoxOutput()

        with self.assertRaisesRegex(
            RuntimeError,
            "box size|coordinates",
        ):
            protocol.readCoordsFromMics(
                None,
                [_Mic(1)],
                outputCoords,
            )

        self.assertTrue(
            protocol.warnings,
            "The coordinate-read failure should still be reported.",
        )

class TestSphireTasksCheckpointPersistenceReconciliation(unittest.TestCase):
    def testTasksDoesNotTrustUnpersistedPositiveCheckpointCount(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _TasksHarness(tmp)
            protocol.mics.items = [_Mic(1), _Mic(2)]

            class _NoPersistedCoordinates(_OutputCoordinates):
                def aggregate(self, *args, **kwargs):
                    return []

            protocol.outputCoordinates = _NoPersistedCoordinates()

            with open(protocol.getPath("micrographs.json"), "w") as handle:
                json.dump({"processed": {"1": 15}}, handle)

            with patch.object(tasks, "BatchManager", _BatchManager),                     patch.object(tasks, "Pipeline", _Pipeline):
                tasks.SphireProtCRYOLOPickingTasks.pickAllMicrogaphsStep(
                    protocol
                )

            self.assertEqual(
                [1, 2],
                _BatchManager.seenIds,
                "A positive coordinate count from the JSON checkpoint must "
                "not hide a micrograph whose coordinates are absent from the "
                "persisted output Set. Resume must retry it.",
            )

    def testTasksKeepsZeroCoordinateCheckpointWithoutPersistedRows(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _TasksHarness(tmp)
            protocol.mics.items = [_Mic(1), _Mic(2)]

            class _NoPersistedCoordinates(_OutputCoordinates):
                def aggregate(self, *args, **kwargs):
                    return []

            protocol.outputCoordinates = _NoPersistedCoordinates()

            with open(protocol.getPath("micrographs.json"), "w") as handle:
                json.dump({"processed": {"1": 0}}, handle)

            with patch.object(tasks, "BatchManager", _BatchManager),                     patch.object(tasks, "Pipeline", _Pipeline):
                tasks.SphireProtCRYOLOPickingTasks.pickAllMicrogaphsStep(
                    protocol
                )

            self.assertEqual(
                [2],
                _BatchManager.seenIds,
                "A zero-coordinate micrograph has no persisted coordinate "
                "rows, so its valid zero-count checkpoint must still be "
                "honoured on Resume.",
            )

class _ClassicFixedBoxOutput:
    def getBoxSize(self):
        return 50

    def append(self, coord):
        raise AssertionError(
            "These tests should not append coordinates."
        )


class _ClassicCboxPresenceHarness(SphireProtCRYOLOPicking):
    def __init__(self, coordsFile):
        self.coordsFile = coordsFile
        self.boxSize = _Value(50)
        self.yFlipHeight = 100

    def _getMicCoordsFile(self, outputDir, mic):
        return self.coordsFile

    def createBoxSizeOutput(self, coordSet):
        pass


class TestSphireClassicCboxPresenceRegression(unittest.TestCase):
    def testClassicMissingCboxIsNotTreatedAsZeroCoordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            protocol = _ClassicCboxPresenceHarness(
                os.path.join(tmp, "missing.cbox")
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "cbox|coordinate|output",
            ):
                protocol.readCoordsFromMics(
                    tmp,
                    [_Mic(1)],
                    _ClassicFixedBoxOutput(),
                )

    def testClassicEmptyCboxRemainsValidZeroCoordinateResult(self):
        with tempfile.TemporaryDirectory() as tmp:
            emptyCbox = os.path.join(tmp, "empty.cbox")
            open(emptyCbox, "w").close()

            protocol = _ClassicCboxPresenceHarness(emptyCbox)

            processed = protocol.readCoordsFromMics(
                tmp,
                [_Mic(1)],
                _ClassicFixedBoxOutput(),
            )

            self.assertEqual(
                {1: 0},
                processed,
                "An existing empty cbox is a valid zero-coordinate result "
                "and must remain checkpointable.",
            )
