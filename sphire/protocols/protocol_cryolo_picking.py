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

import pyworkflow.utils as pwutils
from pyworkflow.object import Integer
import pyworkflow.protocol.params as params
import pyworkflow.protocol.constants as cons
from pwem.protocols import ProtParticlePickingAuto
import pwem.objects as emobj

from .. import Plugin
from ..constants import INPUT_MODEL_GENERAL_DENOISED
from .protocol_base import ProtCryoloBase
import sphire.convert as convert


class SphireProtCRYOLOPicking(ProtCryoloBase, ProtParticlePickingAuto):
    """
    Picks particles in a set of micrographs with crYOLO.

    AI Generated:

    crYOLO Particle Picking (SphireProtCRYOLOPicking) - User Manual
        Overview

        The crYOLO Particle Picking protocol performs automated particle
        detection on cryo-EM micrographs using deep learning models trained
        to recognize particle locations with high sensitivity and speed.
        The protocol is intended to streamline the particle selection stage
        in single-particle cryo-EM workflows, reducing the amount of manual
        intervention required while maintaining reproducibility across large
        datasets.

        In practical biological workflows, this protocol is commonly used
        after motion correction and CTF estimation, once micrographs are
        ready for particle extraction. Automated particle picking becomes
        particularly important in modern cryo-EM projects where datasets
        may contain tens or hundreds of thousands of micrographs. By using
        pretrained or custom-trained models, the protocol enables rapid
        identification of candidate particles suitable for downstream
        classification and reconstruction.

        Inputs and General Workflow

        The protocol requires a set of input micrographs together with a
        compatible crYOLO model. The model may represent a general-purpose
        detector or a model trained specifically for a given biological
        specimen. In most workflows, custom-trained models provide higher
        precision when the particle morphology differs substantially from
        standard cryo-EM datasets.

        During execution, the protocol analyzes each micrograph and produces
        a set of particle coordinates representing the predicted particle
        centers. These coordinates can then be used directly for particle
        extraction and subsequent image processing steps.

        The protocol supports both standard and streaming-oriented workflows.
        In conventional processing, all micrographs are analyzed as a batch.
        In streaming scenarios, newly arriving micrographs can be processed
        progressively as data acquisition continues. This capability is
        especially valuable in high-throughput cryo-EM facilities where
        users may wish to monitor particle quality and data consistency in
        near real time.

        Confidence Thresholds and Particle Selection

        One of the most biologically relevant parameters is the prediction
        confidence threshold. This value determines how permissive the
        particle selection will be. Lower thresholds generally increase the
        number of detected particles but may also introduce more false
        positives such as ice contamination, carbon edges, or background
        artifacts. Higher thresholds improve precision but may miss weak or
        low-contrast particles.

        In practice, users often begin with moderate thresholds and visually
        inspect the results before optimizing the settings. The ideal balance
        depends strongly on particle size, contrast, ice thickness, and the
        biological heterogeneity of the sample.

        Box Size Estimation and Interpretation

        The protocol can determine particle box dimensions automatically or
        use values provided by the user. Accurate box sizing is biologically
        important because it directly influences downstream particle
        extraction and classification quality. Boxes that are too small may
        truncate structural features, whereas excessively large boxes
        introduce unnecessary background noise and increase computational
        cost.

        In many practical cases, automated estimation provides a useful
        starting point, particularly for exploratory analyses or newly
        collected datasets. Nevertheless, experienced users may prefer to
        refine the box dimensions manually to better match the expected
        particle diameter and structural context.

        GPU and High-Throughput Processing

        The protocol is designed to benefit from GPU acceleration, allowing
        rapid analysis of large cryo-EM datasets. This is particularly
        important in facility environments and modern automated acquisition
        pipelines where thousands of micrographs may be generated during a
        single collection session.

        Parallel execution significantly reduces turnaround time and enables
        faster experimental decisions. For example, users can evaluate
        particle distribution, ice quality, and preferred orientations early
        during data collection rather than waiting until the end of the
        acquisition process.

        Streaming and Incremental Processing

        The protocol supports incremental processing workflows in which
        micrographs are analyzed continuously as they become available. This
        approach is highly valuable for microscope sessions that operate in
        streaming mode because it allows immediate feedback regarding sample
        quality and particle abundance.

        From a biological perspective, rapid access to picking statistics
        helps users identify problematic acquisition conditions such as low
        particle concentration, aggregation, contamination, or preferred
        orientation bias before large amounts of unusable data are collected.

        Outputs and Their Interpretation

        The primary output of the protocol is a set of particle coordinates
        associated with the analyzed micrographs. Each coordinate corresponds
        to a predicted particle location and may include an associated
        confidence score reflecting the reliability of the prediction.

        These outputs form the basis for subsequent cryo-EM processing steps,
        including particle extraction, two-dimensional classification,
        three-dimensional reconstruction, and refinement. The quality of the
        particle coordinates strongly influences all downstream analyses,
        making visual validation an essential part of routine workflows.

        Practical Recommendations

        For most biological projects, it is advisable to begin with a
        well-validated pretrained model whenever the specimen resembles
        previously characterized particles. When dealing with uncommon
        complexes, filamentous assemblies, membrane proteins, or highly
        heterogeneous particles, custom model training usually provides
        superior performance.

        Visual inspection remains essential even when automated picking
        performs well. Users should verify that the detected particles match
        the expected biological structures and that contamination or ice
        features are not systematically selected.

        If the protocol detects too many false positives, increasing the
        confidence threshold or refining the training dataset is usually
        effective. Conversely, if many valid particles are missed, reducing
        the threshold or retraining the model with more representative
        examples may improve sensitivity.

        Final Perspective

        Automated particle picking has become one of the foundational stages
        of modern cryo-EM image analysis. By combining deep learning with
        scalable high-throughput processing, this protocol enables rapid and
        reproducible particle detection across diverse biological datasets.
        Careful model selection, threshold optimization, and visual
        validation are the most important factors for obtaining reliable
        particle coordinates suitable for high-resolution structural studies.
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

        form.addParallelSection(threads=1, mpi=1)

        self._defineStreamingParams(form)
        # Default batch size --> 16
        form.getParam('streamingBatchSize').setDefault(16)

    # --------------------------- INSERT steps functions ----------------------
    def _insertInitialSteps(self):
        stepId = self._insertFunctionStep(self.createConfigStep,
                                          self.inputMicrographs.get(),
                                          needsGPU=False)
        return stepId

    # --------------------------- STEPS functions -----------------------------
    def _pickMicrographsBatch(self, micList, workingDir, gpuId, clean=True):
        if clean:
            pwutils.cleanPath(workingDir)
            pwutils.makePath(workingDir)

        # Create folder with linked mics
        convert.convertMicrographs(micList, workingDir)

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
            self.warning(f'File not found error:{cboxFn}. Skipping the following mics:{workingDir}')
        except Exception as e:
            self.warning(f"Cryolo has failed for {workingDir} --> {str(e)}. Skipping the following mics:{workingDir}")

    def _getMicCoordsFile(self, outputDir, mic):
        # Here CBOX output files are moved to extra, so not taking into account
        # outputDir here
        cboxFile = convert.getMicFn(mic, "cbox")
        return self._getExtraPath(cboxFile)

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
                    self.warning(f"ERROR: Cryolo has not a boxSize estimation yet --> {str(e)}\n")
                    return
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

        for mic in micDoneList:
            coordsFile = self._getMicCoordsFile(outputDir, mic)
            count = 0
            if os.path.exists(coordsFile) and os.path.getsize(coordsFile):
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
