# **************************************************************************
# *
# * Authors:    J.M. De la Rosa Trevin (delarosatrevin@gmail.com)
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
# **************************************************************************

import os
import time
from uuid import uuid4

from emtools.utils import Timer, Pretty, Process
from emtools.jobs import Pipeline

import pyworkflow.protocol.constants as cons
import pyworkflow.utils as pwutils
import pwem.objects as emobj

import sphire.convert as convert
from .protocol_cryolo_picking import SphireProtCRYOLOPicking


class SphireProtCRYOLOPickingTasks(SphireProtCRYOLOPicking):
    """ Picks particles in a set of micrographs with crYOLO.
    """
    _label = 'cryolo picking tasks'
    stepsExecutionMode = cons.STEPS_SERIAL

    def __init__(self, **args):
        SphireProtCRYOLOPicking.__init__(self, **args)
        # Disable parallelization options just take into account GPUs
        self.numberOfMpi.set(0)
        self.numberOfThreads.set(0)
        self.allowMpi = False
        self.allowThreads = False
        # Read by the input generator to know when to stop feeding the
        # GPU; it exists from construction so no caller can miss it.
        self._outputErrors = []

    # We are not using the steps mechanism for parallelism from Scipion
    def _stepsCheck(self):
        pass

    @classmethod
    def worksInStreaming(cls):
        return True

    # --------------------------- DEFINE param functions ----------------------
    def _defineParams(self, form):
        SphireProtCRYOLOPicking._defineParams(self, form)

        # Override some defaults from base class
        form.getParam('numberOfMpi').setDefault(0)
        # Default batch size --> 16
        form.getParam('streamingBatchSize').setDefault(16)
        # Make default 1 minute for sleeping when no new input movies
        form.getParam('streamingSleepOnWait').setDefault(60)

    # --------------------------- INSERT steps functions ----------------------
    def _insertAllSteps(self):
        self._insertFunctionStep(self.createConfigStep,
                                 self.getInputMicrographs(),
                                 needsGPU=False)
        self._insertFunctionStep(self.pickAllMicrogaphsStep, needsGPU=True)

    # --------------------------- STEPS functions -----------------------------
    def pickAllMicrogaphsStep(self):
        self.info(f">>> {Pretty.now()}: ----------------- "
                  f"Start processing movies----------- ")
        self._firstTimeOutput = True
        inputMics = self.getInputMicrographs()

        self._processedMics = self._restoreProcessedMics(inputMics)
        waitSecs = self.streamingSleepOnWait.get()
        batchSize = self.streamingBatchSize.get()
        self._inputMicsCount = inputMics.getSize()

        batchGenerator = lambda: self._iterInputBatches(
            inputMics, self._processedMics, batchSize=batchSize,
            waitSecs=waitSecs)

        mc = Pipeline()
        g = mc.addGenerator(batchGenerator)
        gpus = self.getGpuList()
        outputQueue = None
        self.info(f">>> GPUS: {gpus}, processed micrographs: {len(self._processedMics)}")
        self._updateSummary(inputMics.getSize())

        for gpu in gpus:
            p = mc.addProcessor(g.outputQueue, self._getPickProcessor(gpu),
                                outputQueue=outputQueue)
            outputQueue = p.outputQueue

        # Kept on the protocol so the input generator can see it: it has
        # to stop feeding the GPU once the output is lost.
        self._outputErrors = []
        outputErrors = self._outputErrors
        failedBatches = []

        def _updateOutput(batch):
            if batch.get('failed', False):
                failedBatches.append(batch)
                return batch

            if outputErrors:
                return batch

            try:
                return self._updateOutputCoords(batch)
            except Exception as e:
                outputErrors.append(e)
                return batch

        mc.addProcessor(outputQueue, _updateOutput)
        mc.run()

        if outputErrors:
            raise outputErrors[0]

        if failedBatches:
            raise RuntimeError(
                "crYOLO failed for one or more streaming batches."
            )

        outputName = 'outputCoordinates'
        outputCoords = getattr(self, outputName, None)

        if outputCoords is None:
            micSetPtr = self.getInputMicrographsPointer()
            outputCoords = self._createSetOfCoordinates(micSetPtr)
            self._updateOutputSet(
                outputName, outputCoords, emobj.Set.STREAM_CLOSED)
            self._defineSourceRelation(micSetPtr, outputCoords)
        else:
            outputCoords.setStreamState(emobj.Set.STREAM_CLOSED)
            self._store(outputCoords)

    def _getPersistedMicCoordsFile(self, mic):
        """Where a micrograph's crYOLO output is kept once read.

        The batch directory lives under tmp and is cleaned, so the .cbox
        is moved next to the other outputs to survive a Continue.
        """
        return self._itemScopedPath(mic, convert.getMicFn(mic, "cbox"))

    def _persistBatchCoordsFiles(self, batch):
        """Keep each micrograph's .cbox after its coordinates were read.

        This runs on the single output thread, never on the parallel GPU
        processors, so moving files here cannot race.
        """
        for mic in batch['items']:
            source = self._getMicCoordsFile(batch['path'], mic)

            if not os.path.exists(source):
                continue

            try:
                pwutils.moveFile(source, self._getPersistedMicCoordsFile(mic))
            except Exception as e:
                self.warning(f"Could not keep crYOLO output for micrograph "
                             f"{mic.getObjId()}: {e}")

    def _restoreProcessedMics(self, inputMics):
        """Work out what a previous run already picked, with no checkpoint.

        The output coordinates answer this for every micrograph that
        produced at least one coordinate, as an aggregate query rather
        than a walk. A micrograph picked with zero coordinates leaves no
        row behind, so its own .cbox file - crYOLO's real output for it,
        not a marker this protocol invented - is what says it was done.
        Only the ids the output does not account for are checked that way.
        """
        processed = {}

        if hasattr(self, 'outputCoordinates'):
            micAggr = self.outputCoordinates.aggregate(
                ["COUNT"], "_micId", ["_micId"])
            processed.update({
                int(mic["_micId"]): mic['COUNT']
                for mic in micAggr
                if mic["_micId"] is not None
            })

        cboxNames = self._listPersistedCoordsFiles()

        if not cboxNames:
            return processed

        # Zero-coordinate micrographs can only be recognised by name, so
        # this walks the input once per execution - never per poll - and
        # only compares names already in memory.
        for mic in inputMics.iterItems():
            if mic.getObjId() in processed:
                continue

            persisted = self._getPersistedMicCoordsFile(mic)

            if os.path.basename(persisted) in cboxNames:
                processed[mic.getObjId()] = 0

        return processed

    def _listPersistedCoordsFiles(self):
        """Names of the .cbox files kept from previous runs."""
        try:
            return {name for name in os.listdir(self._getExtraPath())
                    if name.endswith('.cbox')}
        except OSError:
            return set()

    def _pollNewMicrographs(self, inputMics, processedIds, waitSecs=60):
        """Yield each poll's newly arrived micrographs, until the stream ends.

        Discovery is by id watermark, so a poll queries and hydrates what
        just arrived rather than walking everything the stream has already
        produced. It also means no filesystem mtime decides whether the
        input changed - the Set itself answers that.
        """
        processedIds = {int(micId) for micId in processedIds}
        watermark, gapIds = self._resumeWatermarkWithGaps(inputMics,
                                                          processedIds)
        self._lastInputId = watermark
        knownIds = set(processedIds)

        while True:
            # Picking is GPU work and this generator is what feeds it.
            # Once the output can no longer be written, or the run has
            # been aborted, every further batch is picked and thrown
            # away - and the error would only surface when the producer
            # finally closes, hours later on a long acquisition.
            if self._streamingMustStop() or getattr(self, '_outputErrors', None):
                break

            newMics, producerClosed, terminalConsistent = (
                self._discoverNewInputItems(inputMics, '_lastInputId',
                                            knownIds))

            if gapIds:
                newMics = (self._loadLogicalSetItemsByIds(inputMics, gapIds)
                           + newMics)
                gapIds = set()

            available = []

            for mic in newMics:
                micId = mic.getObjId()

                if micId in knownIds:
                    continue

                if micId is not None:
                    knownIds.add(micId)

                available.append(mic)

            self._inputMicsCount = inputMics.getSize()

            if available:
                yield available

            if producerClosed and terminalConsistent:
                break

            if waitSecs:
                time.sleep(waitSecs)

    def _createBatch(self, items, batchIndex):
        """Build the folder of links crYOLO is pointed at.

        The links are named by id: two micrographs whose files share a
        basename cannot both be linked under it, and the second symlink
        would take down the thread that feeds every GPU.
        """
        batchId = str(uuid4())
        batchPath = os.path.join(self._getTmpPath(), batchId)

        Process.system(f"rm -rf '{batchPath}'")
        Process.system(f"mkdir '{batchPath}'")

        for mic in items:
            os.symlink(
                os.path.abspath(mic.getFileName()),
                os.path.join(batchPath, convert.getScopedMicFn(
                    mic, pwutils.getExt(mic.getFileName()).lstrip('.'))),
            )

        return {
            'items': items,
            'id': batchId,
            'path': batchPath,
            'index': batchIndex,
        }

    def _iterInputBatches(self, inputMics, processedIds, batchSize=0,
                          waitSecs=60):
        """Yield batches of newly arrived micrographs.

        ``batchSize`` 0 means one batch per Set refresh, with whatever
        turned up in it; any other value cuts fixed-size batches and
        still picks the trailing partial one when the stream ends.

        This replaces emtools' BatchManager, which named its links after
        the micrograph basename alone and so could not take two
        micrographs whose files differ only in their directory.
        """
        batchIndex = 0
        pending = []

        for available in self._pollNewMicrographs(inputMics, processedIds,
                                                  waitSecs=waitSecs):
            if not batchSize:
                batchIndex += 1
                yield self._createBatch(available, batchIndex)
                continue

            pending.extend(available)

            while len(pending) >= batchSize:
                batchIndex += 1
                yield self._createBatch(pending[:batchSize], batchIndex)
                pending = pending[batchSize:]

        if pending:
            batchIndex += 1
            yield self._createBatch(pending, batchIndex)

    def _getPickProcessor(self, gpu):
        def _processBatch(batch):
            self.info(f"Processing batch: {batch['index']}")
            t = Timer()
            self.info(f"BATCH: {batch['index']} Start picking...")
            try:
                self._pickMicrographsBatch(
                    batch['items'],
                    batch['path'],
                    gpu,
                    clean=False,
                )
            except Exception as e:
                batch['failed'] = True
                self.warning(
                    f"Cryolo has failed for batch {batch['index']} "
                    f"({batch['path']}) --> {str(e)}. "
                    f"Skipping this batch."
                )
            self.info(f"BATCH: {batch['index']} Done picking...{t.getToc()}")
            return batch
        return _processBatch

    def _getMicCoordsFile(self, outputDir, mic):
        # Here CBOX output files are moved to extra, so not taking into
        # account outputDir here. Scoped by id: two micrographs whose
        # files share a basename would otherwise read their coordinates
        # from one and the same file.
        return self._itemScopedPath(
            mic, convert.getMicFn(mic, "cbox"),
            pathFunc=lambda name: os.path.join(outputDir, 'CBOX', name))

    def _updateSummary(self, total):
        """ Update the summary variable based on total processed micrographs. """
        done = len(self._processedMics)
        per = done / total * 100 if total else 0.0
        self.summaryVar.set(f"Processed: *{done}* micrographs, "
                            f"out of {total} ({per:0.2f}%)")
        self._store(self.summaryVar)

    def _updateOutputCoords(self, batch):
        if batch.get('failed', False):
            return batch

        outputName = 'outputCoordinates'
        outputCoords = getattr(self, outputName, None)

        # If there are not outputCoordinates yet, it means that is the first
        # time we are updating output coordinates, so we need to first create
        # the output set
        firstTime = outputCoords is None

        if firstTime:
            micSetPtr = self.getInputMicrographsPointer()
            outputCoords = self._createSetOfCoordinates(micSetPtr)
        else:
            outputCoords.enableAppend()

        micList = batch['items']
        self.info(f"BATCH: {batch['index']} Reading coords")
        self.info("Reading coordinates from mics: %s" %
                  ','.join([mic.strId() for mic in micList]))
        processed = self.readCoordsFromMics(batch['path'], micList, outputCoords)
        if processed is None:
            raise RuntimeError(
                "Could not read coordinates for streaming batch."
            )
        self._persistBatchCoordsFiles(batch)
        self._updateOutputSet(outputName, outputCoords, emobj.Set.STREAM_OPEN)
        self._processedMics.update(processed)
        self._updateSummary(self._inputMicsCount)

        if firstTime:
            self._defineSourceRelation(self.getInputMicrographsPointer(),
                                       outputCoords)
        return batch

    def _validate(self):
        validateMsgs = []  # fixme: SphireProtCRYOLOPicking._validate(self)

        if not validateMsgs:
            pass

        return validateMsgs

    def _summary(self):
        summary = []

        summary.append(f"Picking using {self.getEnumText('inputModelFrom')} model: "
                       f"{self.getInputModel()}")

        if self.summaryVar.get():
            summary.append(self.summaryVar.get())

        return summary
