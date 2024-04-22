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

from emtools.utils import Timer, Pipeline, Pretty,Process
from emtools.pwx import SetMonitor, BatchManager

import pyworkflow.protocol.constants as cons
import pwem.objects as emobj

import sphire.convert as convert
from .protocol_cryolo_picking import SphireProtCRYOLOPicking


class SphireProtCRYOLOPickingTasks(SphireProtCRYOLOPicking):
    """ Picks particles in a set of micrographs with crYOLO.
    """
    _label = 'cryolo picking tasks'

    def __init__(self, **args):
        SphireProtCRYOLOPicking.__init__(self, **args)
        self.stepsExecutionMode = cons.STEPS_SERIAL
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
        self._insertFunctionStep(self.createConfigStep, self.getInputMicrographs())
        self._insertFunctionStep(self.pickAllMicrogaphsStep)

    # --------------------------- STEPS functions -----------------------------
    def pickAllMicrogaphsStep(self):
        self.info(f">>> {Pretty.now()}: ----------------- "
                  f"Start processing movies----------- ")
        self._firstTimeOutput = True
        inputMics = self.getInputMicrographs()
        micsJson = self.getPath('micrographs.json')
        # We can retrieve all picked micrographs from the output set, because
        # 0 particles micrographs will be missing. We will store a json file
        # with information of processed movies, if does not exist, will load
        # mics from the output set
        if os.path.exists(micsJson):
            with open(micsJson) as f:
                micsIds = json.load(f)['processed']
        elif hasattr(self, 'outputCoordinates'):
            # Check now which of these mics have related particles

            micAggr = self.outputCoordinates.aggregate(
                ["COUNT"], "_micId", ["_micId"])
            micIds = {mic["_micId"] for mic in micAggr}

        blacklist = [mic.clone() for mic in inputMics if mic.getObjId() in micIds]
        micsMonitor = SetMonitor(emobj.SetOfMicrographs,
                                 self.getInputMicrographs().getFileName(),
                                 blacklist=blacklist)

        self._processedMics = len(blacklist)
        waitSecs = self.streamingSleepOnWait.get()
        self.micsMonitor = micsMonitor
        micsIter = micsMonitor.iterProtocolInput(self, 'micrographs', waitSecs=waitSecs)
        batchMgr = BatchManager(self.streamingBatchSize.get(), micsIter,
                                self._getTmpPath())

        mc = Pipeline()
        g = mc.addGenerator(batchMgr.generate)
        gpus = self.getGpuList()
        outputQueue = None
        self.info(f">>> GPUS: {gpus}, processed micrographs: {self._processedMics}")
        self._updateSummary(inputMics.getSize())

        for gpu in gpus:
            p = mc.addProcessor(g.outputQueue, self._getPickProcessor(gpu),
                                outputQueue=outputQueue)
            outputQueue = p.outputQueue

        mc.addProcessor(outputQueue, self._updateOutputCoords)
        mc.run()
        # Mark the output as closed
        self.outputCoordinates.setStreamState(emobj.Set.STREAM_CLOSED)
        self._store(self.outputCoordinates)

    def _getPickProcessor(self, gpu):
        def _processBatch(batch):
            self.info(f"Processing batch: {batch['index']}")
            t = Timer()
            self.info(f"BATCH: {batch['index']} Start picking...")
            self._pickMicrographsBatch(batch['items'], batch['path'], gpu,
                                       clean=False)
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
        per = round(self._processedMics / total * 100)
        self.summaryVar.set(f"Processed: *{self._processedMics}* micrographs, "
                            f"out of {total} ({per}%)")
        self._store(self.summaryVar)

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
        self.readCoordsFromMics(batch['path'], micList, outputCoords)
        self._updateOutputSet(outputName, outputCoords, emobj.Set.STREAM_OPEN)
        self._processedMics += len(micList)
        self._updateSummary(self.micsMonitor.inputCount)

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
