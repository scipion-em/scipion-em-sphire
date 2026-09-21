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
import json
import time
import tempfile
from datetime import datetime
from uuid import uuid4

from emtools.utils import Timer, Pretty, Process
from emtools.jobs import Pipeline
from emtools.pwx import BatchManager

import pyworkflow.protocol.constants as cons
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
        micsJson = self.getPath('micrographs.json')

        micIds = {}
        if os.path.exists(micsJson):
            try:
                with open(micsJson) as f:
                    storedProcessed = json.load(f).get('processed', {})
            except (OSError, json.JSONDecodeError) as e:
                self.warning(
                    f"Could not read streaming checkpoint {micsJson}: {e}. "
                    f"Recovering from persisted output coordinates."
                )
            else:
                micIds.update({
                    int(micId): count
                    for micId, count in storedProcessed.items()
                })

        if hasattr(self, 'outputCoordinates'):
            micAggr = self.outputCoordinates.aggregate(
                ["COUNT"], "_micId", ["_micId"])
            micIds.update({
                int(mic["_micId"]): mic['COUNT']
                for mic in micAggr
                if mic["_micId"] is not None
            })

        self._processedMics = micIds
        waitSecs = self.streamingSleepOnWait.get()
        batchSize = self.streamingBatchSize.get()
        self._inputMicsCount = inputMics.getSize()

        if batchSize == 0:
            batchGenerator = lambda: self._iterAvailableInputBatches(
                inputMics, micIds, waitSecs=waitSecs)
        else:
            micsIter = self._iterInputMicrographs(
                inputMics, micIds, waitSecs=waitSecs)
            batchMgr = BatchManager(batchSize, micsIter, self._getTmpPath())
            batchGenerator = batchMgr.generate

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

        outputErrors = []

        def _updateOutput(batch):
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

    def _iterAvailableInputBatches(self, inputMics, processedIds,
                                   waitSecs=60):
        """Yield one batch with all new items available in each Set refresh."""
        seenIds = {int(micId) for micId in processedIds}
        batchIndex = 0
        lastCheck = None

        while True:
            checkTime = datetime.now()
            if inputMics.hasChangedSince(lastCheck):
                inputMics.loadAllProperties()
                lastCheck = checkTime
                available = []
                currentCount = 0

                for mic in inputMics.iterItems():
                    currentCount += 1
                    micId = mic.getObjId()
                    if micId in seenIds:
                        continue

                    if micId is not None:
                        seenIds.add(micId)
                    available.append(mic.clone())

                self._inputMicsCount = currentCount

                if available:
                    batchIndex += 1
                    batchId = str(uuid4())
                    batchPath = os.path.join(self._getTmpPath(), batchId)

                    Process.system(f"rm -rf '{batchPath}'")
                    Process.system(f"mkdir '{batchPath}'")

                    for mic in available:
                        micFn = mic.getFileName()
                        os.symlink(
                            os.path.abspath(micFn),
                            os.path.join(batchPath, os.path.basename(micFn)),
                        )

                    yield {
                        'items': available,
                        'id': batchId,
                        'path': batchPath,
                        'index': batchIndex,
                    }

                if inputMics.isStreamClosed():
                    break

            if waitSecs:
                time.sleep(waitSecs)

    def _iterInputMicrographs(self, inputMics, processedIds,
                              waitSecs=60):
        """Yield new micrographs using only the generic Scipion Set API."""
        seenIds = {int(micId) for micId in processedIds}
        lastCheck = None

        if seenIds:
            self.info(f"Existing output: {len(seenIds)} micrographs")
        else:
            self.info("No output micrographs.")

        while True:
            checkTime = datetime.now()
            if inputMics.hasChangedSince(lastCheck):
                inputMics.loadAllProperties()
                lastCheck = checkTime
                currentCount = 0

                for mic in inputMics.iterItems():
                    currentCount += 1
                    micId = mic.getObjId()
                    if micId in seenIds:
                        continue

                    if micId is not None:
                        seenIds.add(micId)
                    yield mic.clone()

                self._inputMicsCount = currentCount

                if inputMics.isStreamClosed():
                    break

            if waitSecs:
                time.sleep(waitSecs)

        self.info(
            f"No more micrographs, stream closed. "
            f"Total: {self._inputMicsCount}"
        )

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
                self.warning(
                    f"Cryolo has failed for batch {batch['index']} "
                    f"({batch['path']}) --> {str(e)}. "
                    f"Skipping this batch."
                )
            self.info(f"BATCH: {batch['index']} Done picking...{t.getToc()}")
            return batch
        return _processBatch

    def _getMicCoordsFile(self, outputDir, mic):
        # Here CBOX output files are moved to extra, so not taking into account
        # outputDir here
        cboxFile = convert.getMicFn(mic, "cbox")
        return os.path.join(outputDir, 'CBOX', cboxFile)

    def _updateSummary(self, total):
        """ Update the summary variable based on total processed micrographs. """
        done = len(self._processedMics)
        per = done / total * 100 if total else 0.0
        self.summaryVar.set(f"Processed: *{done}* micrographs, "
                            f"out of {total} ({per:0.2f}%)")
        self._store(self.summaryVar)

        # Write the resume checkpoint atomically so an interrupted write
        # cannot destroy the last valid micrographs.json.
        micsJson = self.getPath('micrographs.json')
        fd, tmpJson = tempfile.mkstemp(
            prefix='micrographs.',
            suffix='.json.tmp',
            dir=os.path.dirname(micsJson),
            text=True,
        )
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump({'processed': self._processedMics}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmpJson, micsJson)
        except Exception:
            try:
                os.unlink(tmpJson)
            except FileNotFoundError:
                pass
            raise

    def _updateOutputCoords(self, batch):
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
            processed = {mic.getObjId(): 0 for mic in micList}
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
