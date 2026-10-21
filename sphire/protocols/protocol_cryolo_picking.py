# **************************************************************************
# *
# * Authors:    David Maluenda (dmaluenda@cnb.csic.es) [1]
# *             Peter Horvath (phorvath@cnb.csic.es) [1]
# *             J.M. De la Rosa Trevin (delarosatrevin@scilifelab.se) [2]
# *
# * [1] Unidad de  Bioinformatica of Centro Nacional de Biotecnologia , CSIC
# * [2] SciLifeLab, Stockholm University
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
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'scipion@cnb.csic.es'
# *
# **************************************************************************

import os
import threading
import time
from collections import OrderedDict
from datetime import datetime

import pyworkflow.utils as pwutils
from pyworkflow.object import Integer
import pyworkflow.protocol.params as params
import pyworkflow.protocol.constants as cons
from pwem.protocols import ProtParticlePickingAuto
import pwem.objects as emobj

from .. import Plugin
from ..constants import INPUT_MODEL_GENERAL_DENOISED
from .protocol_base import ProtCryoloBase
from .protocol_streaming_base import SphireStreamingBase
import sphire.convert as convert

# Module level: these helpers are called unbound on light test harnesses.
PICKING_STEP_NAMES = ('pickMicrographStepOwn', 'pickMicrographListStepOwn')
# The micrographs whose picking failed, as a durable list in extra/: a
# micrograph with no coordinates is otherwise indistinguishable from one
# without particles, and Continue picks the listed ones again.
FAILED_PICKING_LIST = 'FAILED_all.TXT'
_failedListLock = threading.Lock()


class SphireProtCRYOLOPicking(SphireStreamingBase, ProtCryoloBase,
                              ProtParticlePickingAuto):
    """ Picks particles in a set of micrographs with crYOLO.
    """
    _label = 'cryolo picking'
    stepsExecutionMode = cons.STEPS_PARALLEL

    # --------------------------- DEFINE param functions ----------------------
    def _defineParams(self, form):
        ProtParticlePickingAuto._defineParams(self, form)
        ProtCryoloBase._defineParams(self, form)

        form.addParam('boxSizeFactor', params.FloatParam,
                      default=1.,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Adjust estimated box size by",
                      help="Value to multiply crYOLO estimated box size to be "
                           "registered with the SetOfCoordinates. It is usually "
                           "very tight.")

        form.addParallelSection(threads=3, mpi=1)

        self._defineStreamingParams(form)
        # Default batch size --> 16
        form.getParam('streamingBatchSize').setDefault(16)

    def _loadSet(self, inputSet, SetClass, getKeyFunc):
        """Discover the micrographs added since the last poll.

        Only ids above the watermark are queried and only those items are
        hydrated, so a poll costs what just arrived instead of everything
        the stream has produced. Micrographs no batch has taken yet stay
        in _pendingMics and are offered again next time, since the
        watermark will never look back at them.
        """
        newItems, producerClosed, terminalConsistent = (
            self._discoverNewInputItems(inputSet, '_lastInputId',
                                        self._knownMicIds))

        gapIds = getattr(self, '_resumeGapIds', None)

        if gapIds:
            newItems = (self._loadLogicalSetItemsByIds(inputSet, gapIds)
                        + newItems)
            self._resumeGapIds = set()

        scheduledMicNames = self._getScheduledPickingMicNames()
        failedMicIds = self._failedPickingMicIds()

        for item in newItems:
            itemId = item.getObjId()

            if itemId in self._knownMicIds:
                continue

            self._knownMicIds.add(itemId)
            micKey = getKeyFunc(item)

            if micKey in self.micDict:
                continue

            if micKey in scheduledMicNames and itemId in failedMicIds:
                # Its earlier picking failed: it is picked again, and only
                # the step of this run says when that is done.
                self.__dict__.setdefault('_retriedMicNames', set()).add(micKey)
            elif micKey in scheduledMicNames:
                # Already has a step from an earlier run: it only needs
                # publishing, so it must not be scheduled a second time.
                self.micDict[micKey] = item
                continue

            self._pendingMics[micKey] = item

        return OrderedDict(self._pendingMics), producerClosed and terminalConsistent

    def _checkNewInput(self):
        # Refresh logical input state directly. Do not gate
        # discovery on storage filenames or filesystem mtimes.
        micDict, self.streamClosed = self._loadInputList()
        newMics = list(micDict.values())

        if newMics:
            self._insertNewMicsSteps(newMics)

            # pwem only takes whole batches; whatever it left out has to be
            # offered again, because discovery will not find it twice.
            for mic in newMics:
                if mic.getMicName() in self.micDict:
                    self._pendingMics.pop(mic.getMicName(), None)

            self.updateSteps()

    # --------------------------- INSERT steps functions ----------------------
    def _insertAllSteps(self):
        """Insert the config step and then the resumable generator.

        createConfigStep has to be scheduled here, not from inside the
        generator: every picking step takes it as a prerequisite, and a
        step inserted by a running step cannot be one the executor has
        already planned around - the picking steps would wait on it
        forever and the generator would poll with nothing to publish.
        """
        configStepId = self._insertFunctionStep(self.createConfigStep,
                                                self.inputMicrographs.get(),
                                                needsGPU=False)

        self._insertFunctionStep(self.resumableStepGeneratorStep,
                                 str(datetime.now()),
                                 prerequisites=[configStepId],
                                 needsGPU=False)

    def resumableStepGeneratorStep(self, timestamp):
        """Run the generator as a unique step on every resume."""
        self.stepsGeneratorStep()

    def stepsGeneratorStep(self):
        """Discover, pick and publish micrographs incrementally."""
        self.micDict = OrderedDict()
        self._pendingMics = OrderedDict()
        self._knownMicIds = set()
        self.streamClosed = False
        self.finished = False
        self.initialIds = self._insertInitialSteps()

        self._restoreProcessedMicsFromPersistentState()

        while not self.finished:
            # A failed step makes the executor stop and then join every
            # thread, this generator included: keep polling and the run
            # hangs for good with nothing left to do.
            if self._streamingMustStop():
                break

            self._checkNewInput()
            self._checkNewOutput()

            if self.finished:
                break

            sleepOnWait = self._getStreamingSleepOnWait()

            if sleepOnWait > 0:
                self._streamingSleepOnWait()
            else:
                time.sleep(1)

    def _stepsCheck(self):
        """Persist steps created by the generator without legacy polling."""
        if getattr(self, '_newSteps', False):
            self.updateSteps()

    def _insertInitialSteps(self):
        """The config step already ran before the generator started."""
        return []

    # ----------------------- completion tracking -----------------------------
    def _insertNewMicsSteps(self, inputMics):
        """Schedule picking through hooks this protocol fully owns.

        pwem's own step functions decide completion with DONE marker files;
        the local ones leave that to the persisted step graph instead.
        """
        return self._insertNewMics(inputMics,
                                   lambda mic: mic.getMicName(),
                                   self._insertPickMicrographStepOwn,
                                   self._insertPickMicrographListStepOwn,
                                   *self._getPickArgs())

    def _insertPickMicrographStepOwn(self, mic, prerequisites, *args):
        return self._insertFunctionStep('pickMicrographStepOwn',
                                        mic.getMicName(), *args,
                                        prerequisites=prerequisites)

    def _insertPickMicrographListStepOwn(self, micList, prerequisites, *args):
        micNameList = [mic.getMicName() for mic in micList]
        return self._insertFunctionStep('pickMicrographListStepOwn',
                                        micNameList, *args,
                                        prerequisites=prerequisites)

    def pickMicrographStepOwn(self, micName, *args):
        """Pick one micrograph, with no DONE sidecar to write."""
        self.pickMicrographListStepOwn([micName], *args)

    def pickMicrographListStepOwn(self, micNameList, *args):
        """Pick a batch, leaving completion to the persisted step status."""
        micList = [self.micDict[micName] for micName in micNameList
                   if micName in self.micDict]

        if not micList:
            return

        self.info("Picking micrographs: %s"
                  % [mic.getObjId() for mic in micList])
        self._pickMicrographList(micList, *args)

    def _getScheduledPickingMicNames(self):
        """Micrograph names represented by persisted picking steps."""
        return self._collectStepArgKeys(PICKING_STEP_NAMES,
                                        onlyFinished=False, keyType=str)

    def _getFinishedPickingMicNames(self):
        """Micrograph names represented by finished picking steps.

        A micrograph picked again in this run (it failed before) only
        counts once its new step has finished: its old step finished too.
        """
        finished = self._collectStepArgKeys(PICKING_STEP_NAMES, keyType=str)
        retried = getattr(self, '_retriedMicNames', None)

        if retried:
            finishedNow = self._collectStepArgKeys(
                PICKING_STEP_NAMES, keyType=str, includePrevious=False)
            finished = {name for name in finished
                        if name not in retried or name in finishedNow}

        return finished

    def _hasActiveStreamingWork(self):
        """Micrographs scheduled or waiting for a batch, not yet published."""
        return bool(getattr(self, 'micDict', None)
                    or getattr(self, '_pendingMics', None))

    def _getPublishedPickingMicIds(self):
        """Micrograph ids already represented in the output coordinates.

        This is an id query on the output, not a walk over it, and it only
        runs once per execution.
        """
        micIds = self._getOutputUniqueValues(
            getattr(self, 'outputCoordinates', None), '_micId')

        return set() if micIds is None else micIds

    def _restoreProcessedMicsFromPersistentState(self):
        """Place the watermark past what a previous run already picked.

        Coordinates carry the id of their micrograph, so the output Set
        says which micrographs were picked, and the step graph covers the
        ones that produced no coordinate at all. Anything below the
        watermark that was never handled comes back as a gap.
        """
        self._lastInputId = getattr(self, '_lastInputId', 0)

        pickedMicIds = self._getPublishedPickingMicIds()

        if not pickedMicIds:
            return

        watermark, gapIds = self._resumeWatermarkWithGaps(
            self.getInputMicrographs(), pickedMicIds)

        self._lastInputId = max(self._lastInputId, watermark)
        self._knownMicIds.update(pickedMicIds)
        self._resumeGapIds = gapIds

    def _checkNewOutput(self):
        """Publish finished picking steps without DONE sidecars."""
        if getattr(self, 'finished', False):
            return

        finishedNames = self._getFinishedPickingMicNames()

        # micDict holds what has been scheduled and not published yet, so
        # only that has to be looked at - never every micrograph seen.
        newDone = [mic for micName, mic in self.micDict.items()
                   if micName in finishedNames]

        allDone = (len(newDone) == len(self.micDict)
                   and not self._pendingMics)

        self.finished = self.streamClosed and allDone
        streamMode = (emobj.Set.STREAM_CLOSED if self.finished
                      else emobj.Set.STREAM_OPEN)

        if newDone:
            self._updateOutputCoordSet(newDone, streamMode)
            self.__dict__.setdefault('_handledPickingMicIds', set()).update(
                mic.getObjId() for mic in newDone)

            for mic in newDone:
                self.micDict.pop(mic.getMicName(), None)
        elif not self.finished:
            if allDone:
                self._streamingSleepOnWait()

            return

        if self.finished:
            self._updateStreamState(streamMode)
            self._failIfEveryMicrographFailed()

    def _failIfEveryMicrographFailed(self):
        """A failed micrograph is left out; the run fails only when that
        happened to every micrograph."""
        handled = getattr(self, '_handledPickingMicIds', set())
        output = getattr(self, 'outputCoordinates', None)

        if (handled and handled <= self._failedPickingMicIds()
                and (output is None or output.getSize() == 0)):
            raise Exception("crYOLO picking failed for every one of the %d "
                            "micrographs; see the errors above. Continue "
                            "picks them again." % len(handled))

    # ------------------------- failed micrographs ------------------------
    def _failedPickingMicIds(self):
        """Ids of the micrographs whose picking failed, from extra/."""
        cached = getattr(self, '_failedPickingMicIdsCache', None)

        if cached is None:
            cached = set()
            path = self._getExtraPath(FAILED_PICKING_LIST)

            if os.path.exists(path):
                with open(path) as handle:
                    cached = {int(line) for line in handle if line.strip()}

            self._failedPickingMicIdsCache = cached

        return set(cached)

    def _writeFailedPicking(self, micIds):
        with open(self._getExtraPath(FAILED_PICKING_LIST), 'w') as handle:
            handle.writelines('%d\n' % micId for micId in sorted(micIds))

        self._failedPickingMicIdsCache = set(micIds)

    def _recordFailedPicking(self, micIds):
        with _failedListLock:
            failed = self._failedPickingMicIds()

            if not set(micIds) <= failed:
                self._writeFailedPicking(failed | set(micIds))

    def _forgetFailedPicking(self, micIds):
        """Picked well now: no longer listed as failed."""
        with _failedListLock:
            failed = self._failedPickingMicIds()

            if failed & set(micIds):
                self._writeFailedPicking(failed - set(micIds))

    # -------------------------- INFO functions -------------------------------
    def _validateStreamingThreads(self):
        """The generator holds one thread for the whole run.

        One more is reserved by the step executor, so fewer than three
        leaves nothing to actually pick with.
        """
        inputMics = self.getInputMicrographs()

        if (inputMics is not None and inputMics.isStreamOpen()
                and self.numberOfThreads.get() < 3):
            return ['crYOLO streaming picking requires at least 3 threads.']

        return []

    def _validate(self):
        errors = ProtCryoloBase._validate(self)
        errors.extend(self._validateStreamingThreads())

        return errors

    # --------------------------- STEPS functions -----------------------------
    def _pickMicrographsBatch(self, micList, workingDir, gpuId, clean=True):
        if clean:
            pwutils.cleanPath(workingDir)
            pwutils.makePath(workingDir)

        # Create folder with linked mics. The names are scoped by id:
        # two micrographs whose files share a basename would otherwise
        # become a single link, and crYOLO would only ever see one.
        convert.convertMicrographs(micList, workingDir,
                                   nameFunc=convert.getScopedMicFn)

        configJson = os.path.abspath(self._getExtraPath('config.json'))
        args = " -c %s" % configJson
        args += " -w %s" % self.getInputModel()
        args += " -i ./ -o ./ "
        args += " -t %0.3f" % self.conservPickVar
        args += " -nc %d" % self.numCpus

        if not self.usingCpu():
            args += " -g %s " % gpuId

        if self.lowPassFilter or self.inputModelFrom == INPUT_MODEL_GENERAL_DENOISED:
            args += ' --cleanup'

        Plugin.runCryolo(self, 'cryolo_predict.py', args,
                         cwd=workingDir,
                         useCpu=self.usingCpu())

    def _pickMicrograph(self, micrograph, *args):
        """This function picks from a given micrograph"""
        self._pickMicrographList([micrograph], *args)

    def _pickMicrographList(self, micList, *args):
        """Pick a batch; a micrograph crYOLO gives no output for fails alone.

        A failure is not raised: the step would fail and take the whole
        run down with it. Its micrographs are left out of the output
        instead, and Continue picks them again.
        """
        if not micList:  # maybe in continue cases, need to properly check
            return

        workingDir = self._getTmpPath(self.getMicsWorkingDir(micList))

        try:
            self._pickMicrographsBatch(micList, workingDir, '%(GPU)s')
        except Exception as e:
            self.error(f"crYOLO has failed for micrographs "
                       f"{[mic.getObjId() for mic in micList]} --> {e}")

        # Each micrograph's own output is moved on its own, so a missing
        # one is known for what it is, not hidden by the others.
        for mic in micList:
            cboxName = convert.getScopedMicFn(mic, 'cbox')
            source = os.path.join(workingDir, 'CBOX', cboxName)
            target = self._getExtraPath(cboxName)

            if os.path.exists(source):
                pwutils.moveFile(source, target)
            else:
                # An older output of a failed attempt must not stand in
                # for this one.
                pwutils.cleanPath(target)
                self.error(f"Missing crYOLO output for micrograph "
                           f"{mic.getObjId()}: {source}")
                self._recordFailedPicking([mic.getObjId()])

    def _getMicCoordsFile(self, outputDir, mic):
        # Here CBOX output files are moved to extra, so not taking into
        # account outputDir here. Scoped by id for the same reason the
        # links are, with the unscoped name still honoured so a project
        # picked before this change keeps its coordinates on Continue.
        return self._itemScopedPath(mic, convert.getMicFn(mic, "cbox"))

    def readCoordsFromMics(self, outputDir, micDoneList, outputCoords):
        """This method read coordinates from a given list of micrographs.
        Return a dict with micIds and number of coordinates read for each one.

        A micrograph with no output, or one that cannot be read whole, is
        recorded as failed and left out, coordinates and all: the others
        are still read.
        """
        readable = []

        for mic in micDoneList:
            coordsFile = self._getMicCoordsFile(outputDir, mic)

            if os.path.exists(coordsFile):
                readable.append((mic, coordsFile))
            else:
                self.error(
                    f"Missing crYOLO coordinate output for micrograph "
                    f"{mic.getObjId()}: {coordsFile}"
                )
                self._recordFailedPicking([mic.getObjId()])

        if not readable:
            return {}

        # Coordinates may have a boxSize (e.g. streaming case)
        boxSize = outputCoords.getBoxSize()
        if not boxSize:
            if self.boxSize.get():  # Box size can be provided by the user
                boxSize = self.boxSize.get()
            else:  # If not crYOLO estimates it
                if outputDir:
                    outputPath = os.path.join(outputDir, 'DISTR')
                else:
                    outputPath = self._getTmpPath('micrographs_*/DISTR')
                try:
                    boxSize = self.getEstimatedBoxSize(outputPath)
                except Exception as e:
                    self.error(
                        f"Could not determine the box size while reading "
                        f"crYOLO coordinates --> {str(e)}"
                    )
                    self._recordFailedPicking(
                        [mic.getObjId() for mic, _ in readable])
                    return {}
                if self.boxSizeFactor.get() != 1:
                    boxSize = int(boxSize * self.boxSizeFactor.get())

            outputCoords.setBoxSize(boxSize)

        # Calculate if flip is needed
        # JMRT: Let's assume that all mics have same dims, so we avoid
        # to open the image file each time for checking this
        if not hasattr(self, 'yFlipHeight'):
            self.yFlipHeight = convert.getFlipYHeight(readable[0][0].getFileName())

        # Create a reader to parse .cbox files
        # and a Coordinate object to add to output set
        reader = convert.CoordBoxReader(boxSize,
                                        yFlipHeight=self.yFlipHeight,
                                        boxSizeEstimated=self.boxSizeEstimated)
        coord = emobj.Coordinate()
        coord._cryoloScore = emobj.Float()

        processedMics = {}

        for mic, coordsFile in readable:
            # A micrograph is published whole or not at all: its rows are
            # all read before any of them reaches the output.
            try:
                rows = (list(reader.iterCoords(coordsFile))
                        if os.path.getsize(coordsFile) else [])
            except Exception as e:
                self.error(f"Could not read the crYOLO coordinates of "
                           f"micrograph {mic.getObjId()}: {e}")
                self._recordFailedPicking([mic.getObjId()])
                continue

            for x, y, z, score, _, _ in rows:
                # Clean up objId to add as a new coordinate
                coord.setObjId(None)
                coord.setPosition(x, y)
                coord.setMicrograph(mic)
                coord._cryoloScore.set(score)
                # Add it to the set
                outputCoords.append(coord)

            processedMics[mic.getObjId()] = len(rows)

        self._forgetFailedPicking(processedMics)

        # Register box size
        self.createBoxSizeOutput(outputCoords)

        return processedMics

    def createBoxSizeOutput(self, coordSet):
        """ Output box size as an Integer. Other protocols can use it as
            IntParam with allowsPointer=True.
        """
        if not hasattr(self, "boxsize"):
            boxSize = Integer(coordSet.getBoxSize())
            self._defineOutputs(boxsize=boxSize)

    # -------------------------- UTILS functions ------------------------------
    def getMicsWorkingDir(self, micList):
        wd = 'micrographs_%s' % micList[0].strId()
        if len(micList) > 1:
            wd += '-%s' % micList[-1].strId()
        return wd
