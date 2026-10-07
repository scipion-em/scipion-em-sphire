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

        for item in newItems:
            itemId = item.getObjId()

            if itemId in self._knownMicIds:
                continue

            self._knownMicIds.add(itemId)
            micKey = getKeyFunc(item)

            if micKey in self.micDict:
                continue

            if micKey in scheduledMicNames:
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
        """Micrograph names represented by finished picking steps."""
        return self._collectStepArgKeys(PICKING_STEP_NAMES, keyType=str)

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

            for mic in newDone:
                self.micDict.pop(mic.getMicName(), None)
        elif not self.finished:
            if allDone:
                self._streamingSleepOnWait()

            return

        if self.finished:
            self._updateStreamState(streamMode)

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
        self._pickMicrographList([micrograph], args)

    def _pickMicrographList(self, micList, *args):
        if not micList:  # maybe in continue cases, need to properly check
            return
        try:
            workingDir = self._getTmpPath(self.getMicsWorkingDir(micList))
            self._pickMicrographsBatch(micList, workingDir, '%(GPU)s')
            # Move output files to extra folder
            # FIXME: I think this can be problematic with parallel process running
            # cryolo on different GPUs
            cboxFn = os.path.join(workingDir, "CBOX")
            pwutils.moveTree(cboxFn, self._getExtraPath())
        except FileNotFoundError:
            self.warning(
                f'File not found error:{cboxFn}. '
                f'Failed mics:{workingDir}'
            )
            raise
        except Exception as e:
            self.warning(
                f"Cryolo has failed for {workingDir} --> {str(e)}. "
                f"Failed mics:{workingDir}"
            )
            raise

    def _getMicCoordsFile(self, outputDir, mic):
        # Here CBOX output files are moved to extra, so not taking into
        # account outputDir here. Scoped by id for the same reason the
        # links are, with the unscoped name still honoured so a project
        # picked before this change keeps its coordinates on Continue.
        return self._itemScopedPath(mic, convert.getMicFn(mic, "cbox"))

    def readCoordsFromMics(self, outputDir, micDoneList, outputCoords):
        """This method read coordinates from a given list of micrographs.
        Return a dict with micIds and number of coordinates read for each one.
        """
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
                    self.warning(
                        f"ERROR: Cryolo has not a boxSize estimation yet "
                        f"--> {str(e)}\n"
                    )
                    raise RuntimeError(
                        "Could not determine box size while reading "
                        "crYOLO coordinates."
                    ) from e
                if self.boxSizeFactor.get() != 1:
                    boxSize = int(boxSize * self.boxSizeFactor.get())

            outputCoords.setBoxSize(boxSize)

        # Calculate if flip is needed
        # JMRT: Let's assume that all mics have same dims, so we avoid
        # to open the image file each time for checking this
        if not hasattr(self, 'yFlipHeight'):
            self.yFlipHeight = convert.getFlipYHeight(micDoneList[0].getFileName())

        # Create a reader to parse .cbox files
        # and a Coordinate object to add to output set
        reader = convert.CoordBoxReader(boxSize,
                                        yFlipHeight=self.yFlipHeight,
                                        boxSizeEstimated=self.boxSizeEstimated)
        coord = emobj.Coordinate()
        coord._cryoloScore = emobj.Float()

        processedMics = {}
        failedMicIds = []

        for mic in micDoneList:
            # A missing cbox is a genuine crYOLO failure signal for that
            # micrograph, not a legitimate zero-coordinate result - it
            # must not be silently swallowed. But letting it abort the
            # whole loop would also drop every other (good) micrograph
            # still pending in this batch, since the caller checkpoints
            # (classic) or persists (tasks) whatever this method leaves
            # behind. Isolate it per-micrograph instead and only raise
            # once, below, if the entire batch turned out unreadable.
            coordsFile = self._getMicCoordsFile(outputDir, mic)
            if not os.path.exists(coordsFile):
                self.error(
                    f"Missing crYOLO coordinate output for micrograph "
                    f"{mic.getObjId()}: {coordsFile}"
                )
                failedMicIds.append(mic.getObjId())
                continue

            count = 0
            if os.path.getsize(coordsFile):
                for x, y, z, score, _, _ in reader.iterCoords(coordsFile):
                    # Clean up objId to add as a new coordinate
                    coord.setObjId(None)
                    coord.setPosition(x, y)
                    coord.setMicrograph(mic)
                    coord._cryoloScore.set(score)
                    # Add it to the set
                    outputCoords.append(coord)
                    count += 1
            processedMics[mic.getObjId()] = count

        # Register box size
        self.createBoxSizeOutput(outputCoords)

        if failedMicIds and not processedMics:
            # Every micrograph in this batch was unreadable - treat it as
            # a systemic failure (e.g. crYOLO/model/GPU issue) and surface
            # it loudly, instead of silently completing an all-failed
            # batch as if it had produced zero coordinates.
            raise RuntimeError(
                "Missing crYOLO coordinate output for micrograph(s): %s"
                % ", ".join(str(micId) for micId in failedMicIds)
            )

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
