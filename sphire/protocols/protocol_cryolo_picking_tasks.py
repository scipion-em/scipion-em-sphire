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

from emtools.utils import Timer, Pretty, Process
from emtools.jobs import Pipeline
from emtools.pwx import SetMonitor, BatchManager

import pyworkflow.protocol.constants as cons
import pwem.objects as emobj

import sphire.convert as convert
from .protocol_cryolo_picking import SphireProtCRYOLOPicking


class SphireProtCRYOLOPickingTasks(SphireProtCRYOLOPicking):
    """
    Picks particles in a set of micrographs with crYOLO.

    AI Generated:

    CRYOLO Streaming Particle Picking (SphireProtCRYOLOPickingTasks) — User Manual
        Overview

        The CRYOLO Streaming Particle Picking protocol performs automated
        particle detection on cryo-electron microscopy micrographs using
        a streaming-oriented workflow optimized for continuous data
        acquisition environments. Its main purpose is to identify particle
        coordinates in newly acquired micrographs as they become available,
        enabling near real-time processing during microscope sessions or
        large-scale facility operations.

        In modern cryo-EM facilities, datasets are often generated
        continuously over many hours or days. Manual monitoring and
        particle selection rapidly become impractical at this scale. This
        protocol addresses that challenge by combining automated deep
        learning particle detection with streaming execution strategies
        capable of processing incoming data incrementally and efficiently.

        For biological users, this approach allows rapid feedback about
        sample quality, particle distribution, contamination levels, ice
        thickness, and acquisition consistency while data collection is
        still ongoing. Early detection of problems can significantly
        reduce wasted microscope time and improve the overall quality of
        the final dataset.

        Inputs and Streaming Workflow

        The protocol requires a set of input micrographs together with a
        trained CRYOLO model appropriate for the biological specimen under
        study. As new micrographs appear during acquisition, the protocol
        automatically detects and processes them without requiring manual
        intervention.

        Unlike conventional batch-oriented workflows, streaming execution
        continuously monitors the acquisition source and updates the output
        coordinate set progressively. This behavior is especially valuable
        in automated cryo-EM pipelines where particle picking must keep
        pace with microscope throughput.

        The protocol maintains tracking of already processed micrographs
        to avoid redundant analysis and ensure stable long-running
        operation. This enables reliable processing even during extended
        acquisition sessions involving thousands of micrographs.

        GPU Utilization and Parallel Processing

        The protocol is optimized for GPU-based execution and can
        distribute particle picking tasks across multiple graphics
        processors. This substantially accelerates throughput and allows
        large streaming datasets to be analyzed in near real time.

        From a practical perspective, efficient GPU utilization becomes
        particularly important in high-throughput cryo-EM facilities where
        data generation rates may exceed the processing capacity of
        traditional serial workflows. By processing multiple batches
        concurrently, the protocol minimizes delays between acquisition and
        particle detection.

        Biological users should nevertheless ensure that GPU resources are
        balanced appropriately with storage bandwidth and acquisition
        speed. Extremely large datasets or unstable storage systems may
        otherwise introduce processing bottlenecks.

        Batch-Based Streaming Strategy

        Incoming micrographs are processed in batches to improve execution
        efficiency and reduce computational overhead. Batch-oriented
        processing allows the protocol to optimize GPU usage while
        maintaining responsiveness to newly arriving data.

        Smaller batch sizes may improve responsiveness during acquisition,
        especially when rapid quality feedback is desired. Larger batches
        generally improve computational efficiency but may introduce slight
        delays before results become visible.

        In practice, the optimal configuration depends on microscope
        throughput, available hardware resources, and the biological goals
        of the experiment. High-throughput screening sessions often favor
        larger batches, whereas interactive optimization during sample
        preparation may benefit from smaller and faster updates.

        Coordinate Generation and Interpretation

        The protocol generates particle coordinate sets associated with
        the input micrographs. These coordinates can be used directly for
        particle extraction, downstream classification, or structural
        reconstruction workflows.

        Because coordinates are produced progressively during streaming,
        users can begin evaluating particle quality and dataset integrity
        before the full acquisition has completed. This early feedback is
        often extremely valuable when optimizing vitrification conditions,
        microscope alignment, or acquisition parameters.

        Biological interpretation should still include careful visual
        inspection of representative micrographs. Even highly accurate
        neural network models may occasionally produce false positives,
        particularly in contaminated regions, crystalline ice, carbon
        edges, or low-contrast micrographs.

        Monitoring and Incremental Updates

        A major advantage of the streaming workflow is its ability to
        provide continuously updated progress information during data
        acquisition. Users can monitor how many micrographs have already
        been processed and evaluate whether particle detection remains
        stable throughout the session.

        This capability is particularly useful in long automated
        collection sessions where sample quality may drift over time due
        to beam-induced contamination, ice changes, charging effects, or
        microscope instability. Incremental monitoring allows corrective
        actions before an entire dataset becomes compromised.

        Practical Recommendations

        For most cryo-EM acquisition sessions, it is advisable to begin
        with a previously validated CRYOLO model trained on similar
        specimens and imaging conditions. Early inspection of the first
        processed micrographs helps confirm that particle detection is
        functioning as expected.

        Users should balance streaming batch sizes according to their
        hardware capabilities and acquisition priorities. Facilities
        emphasizing throughput may prioritize efficiency, whereas users
        optimizing new biological samples may prefer more frequent
        incremental updates.

        Periodic manual inspection of automatically picked coordinates
        remains strongly recommended, especially during the early stages
        of data collection or when working with difficult specimens,
        heterogeneous complexes, or low-contrast particles.

        Final Perspective

        Streaming particle picking represents an important step toward
        fully automated cryo-EM acquisition and processing pipelines. By
        integrating deep learning particle detection with continuous data
        monitoring, this protocol enables rapid biological feedback,
        improves operational efficiency, and helps maximize the value of
        expensive microscope acquisition time.
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
        # We can retrieve all picked micrographs from the output set, because
        # 0 particles micrographs will be missing. We will store a json file
        # with information of processed movies, if does not exist, will load
        # mics from the output set
        if os.path.exists(micsJson):
            with open(micsJson) as f:
                micsIds = json.load(f)['processed']
        elif hasattr(self, 'outputCoordinates'):
            # Check now which of these mics have particles
            micAggr = self.outputCoordinates.aggregate(
                ["COUNT"], "_micId", ["_micId"])
            micIds = {mic["_micId"]: mic['COUNT'] for mic in micAggr}
        else:
            micIds = {}

        blacklist = [mic.clone() for mic in inputMics if mic.getObjId() in micIds]
        micsMonitor = SetMonitor(emobj.SetOfMicrographs,
                                 self.getInputMicrographs().getFileName(),
                                 blacklist=blacklist)

        self._processedMics = micIds
        waitSecs = self.streamingSleepOnWait.get()
        self.micsMonitor = micsMonitor
        micsIter = micsMonitor.iterProtocolInput(self, 'micrographs', waitSecs=waitSecs)
        batchMgr = BatchManager(self.streamingBatchSize.get(), micsIter,
                                self._getTmpPath())

        mc = Pipeline()
        g = mc.addGenerator(batchMgr.generate)
        gpus = self.getGpuList()
        outputQueue = None
        self.info(f">>> GPUS: {gpus}, processed micrographs: {len(self._processedMics)}")
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
        done = len(self._processedMics)
        per = done / total * 100
        self.summaryVar.set(f"Processed: *{done}* micrographs, "
                            f"out of {total} ({per:0.2f}%)")
        self._store(self.summaryVar)

        # Write JSON file with processed micrographs
        micsJson = self.getPath('micrographs.json')
        with open(micsJson, 'w') as f:
            json.dump({'processed': self._processedMics}, f)

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
        self._updateOutputSet(outputName, outputCoords, emobj.Set.STREAM_OPEN)
        self._processedMics.update(processed)
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
