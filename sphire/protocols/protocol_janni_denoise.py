# **************************************************************************
# *
# * Authors:     Jorge Jiménez (jjimenez@cnb.csic.es)
# *
# * Biocomputing Unit of Centro Nacional de Biotecnologia, (CNB-CSIC)
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
from os.path import basename, exists
import logging
logger = logging.getLogger(__name__)


from pyworkflow.protocol import params, ValidationException
from pyworkflow.utils import moveTree, createLink, Message
from pwem.protocols import ProtMicrographs

from .. import Plugin
from ..constants import JANNI_GENMOD_VAR, JANNI_GENMOD


class SphireProtJanniDenoising(ProtMicrographs):
    """
    Denoises cryo-EM micrographs using the JANNI deep learning framework in order to
    improve image quality before downstream particle picking, classification, or
    reconstruction steps.

    AI Generated:

    JANNI Micrograph Denoising (SphireProtJanniDenoising) - User Manual
        Overview

        The JANNI denoising protocol applies deep learning based image restoration to
        cryo-EM micrographs. Its primary objective is to reduce background noise while
        preserving biologically meaningful structural information, allowing users to
        obtain cleaner images for subsequent cryo-EM processing tasks. Denoising is
        particularly useful in challenging datasets acquired at low dose conditions,
        with thick ice, poor contrast, or difficult imaging environments where particle
        visibility becomes limited.

        In practical cryo-EM workflows, denoising often improves visualization of
        particles and increases the robustness of automated particle picking methods.
        Biological users commonly employ this protocol before particle detection,
        especially when working with small proteins, flexible assemblies, membrane
        proteins, or heterogeneous samples where weak signal can complicate analysis.

        Inputs and General Workflow

        The protocol requires a set of input micrographs that will be processed with a
        pretrained JANNI model. The denoising procedure generates a corresponding set
        of restored micrographs while preserving the original acquisition metadata and
        organizational structure needed for downstream processing.

        Since denoising modifies the appearance of the raw experimental images, users
        should interpret the results carefully. The protocol is intended to enhance
        visibility and improve computational processing, not to generate new biological
        information. Structural features that are absent in the original data cannot be
        reliably reconstructed through denoising alone.

        GPU Requirements and Performance

        JANNI performs denoising using GPU acceleration. The protocol is optimized for
        execution on a single GPU device, providing efficient processing for large
        cryo-EM datasets. GPU memory availability strongly influences processing speed
        and the ability to handle large micrographs.

        In facility or high throughput environments, denoising can substantially reduce
        the manual effort required during particle selection and dataset inspection.
        However, users working with extremely large datasets should monitor hardware
        usage carefully and verify that the selected computational resources are
        sufficient for stable execution.

        Biological Interpretation of Denoised Micrographs

        Denoised micrographs are generally easier to inspect visually and may reveal
        particle boundaries more clearly than the original images. This is especially
        beneficial when particles are embedded in noisy vitreous ice or when contrast
        transfer effects obscure structural features.

        Nevertheless, denoising should not replace rigorous validation using the
        original experimental data. Biological interpretation, resolution assessment,
        and publication quality reconstructions should always consider whether image
        restoration could introduce biases or suppress weak structural variability.
        Users are encouraged to compare denoised and non-denoised workflows whenever
        possible.

        Output Interpretation

        The protocol produces a new set of denoised micrographs suitable for downstream
        cryo-EM analysis pipelines. These outputs can be directly used for particle
        picking, visual inspection, or additional preprocessing steps.

        In some cases, individual micrographs may fail during processing due to GPU
        limitations, corrupted input data, or unexpected image properties. The protocol
        reports incomplete processing situations so users can identify problematic
        images and evaluate whether reprocessing or dataset curation is necessary.

        Practical Recommendations

        For most biological applications, denoising is best used as an auxiliary
        enhancement step rather than a replacement for careful data acquisition and
        preprocessing. Users should visually inspect representative outputs to ensure
        that particle shapes, membrane boundaries, filament organization, or other
        relevant biological features remain realistic after restoration.

        Denoising is particularly effective before automated particle picking,
        especially for low contrast datasets. However, overly aggressive interpretation
        of restored images should be avoided, particularly in cases involving flexible
        complexes, rare conformational states, or weak densities close to the noise
        level.

        Final Perspective

        Deep learning based denoising provides a practical way to improve the usability
        of cryo-EM micrographs while reducing the impact of experimental noise. When
        used carefully and validated against the original data, it can simplify
        downstream processing and improve the efficiency of cryo-EM workflows without
        compromising biological interpretation.
    """
    _label = 'janni denoising'

    def __init__(self, **kwargs):
        ProtMicrographs.__init__(self, **kwargs)
        self._some_mics_failed = None

    # -------------------------- DEFINE param functions -----------------------
    def _defineParams(self, form):
        form.addSection(label=Message.LABEL_INPUT)
        form.addHidden(params.GPU_LIST, params.StringParam,
                       default='0',
                       label="Choose GPU ID",
                       help="JANNI works on a single GPU.")
        form.addParam('inputMicrographs',
                      params.PointerParam,
                      pointerClass='SetOfMicrographs',
                      label='Input micrographs')

    # --------------------------- STEPS functions -----------------------------
    def _insertAllSteps(self):
        self._insertFunctionStep(self.denoisingStep, needsGPU=True)
        self._insertFunctionStep(self.createOutputStep, needsGPU=False)

    def denoisingStep(self):
        input_mics = self.inputMicrographs.get()
        # Create links to the movies desired to denoise in tmp folder
        # janni only accepts directories
        for mic in input_mics:
            micName = mic.getFileName()
            createLink(micName, self._getTmpPath(basename(micName)))

        args = [
            f"denoise -g {self.gpuList.get()}",
            f"{self._getTmpPath()}/",
            f"{self._getTmpPath()}/",
            f"{self.getInputModel()}"
        ]
        Plugin.runCryolo(self, 'janni_denoise.py', " ".join(args))

        # Move the output to the extra folder
        moveTree(self._getTmpPath("tmp"), self._getExtraPath())

    def createOutputStep(self):
        in_mics = self.inputMicrographs.get()
        out_mics = self._createSetOfMicrographs()
        out_mics.copyInfo(in_mics)

        n_failed_mics = 0
        for mic in in_mics:
            current_out_mic = self._getExtraPath(basename(mic.getFileName()))
            if exists(current_out_mic):
                mic.setFileName(current_out_mic)
                out_mics.append(mic)
            else:
                n_failed_mics += 1
                logger.error(f"Failed to process the micrograph: {mic.getFileName()}")

        # Check if the output list is empty
        if n_failed_mics > 0:
            n_mics_in = len(in_mics)
            if n_failed_mics == n_mics_in:
                raise ValidationException("No output micrographs were generated.")
            else:
                self._some_mics_failed = (f"{n_failed_mics} of {n_mics_in} micrographs "
                                          "weren't correctly processed. "
                                          "Please check the log for more details")

        self._defineOutputs(outputMicrographs=out_mics)
        self._defineTransformRelation(self.inputMicrographs, out_mics)

    # --------------------------- INFO functions ------------------------------
    def _summary(self):
        summary = []

        if self.isFinished():
            summary.append(f"Denoising using model: {self.getInputModel()}")
            summary.append(f"Micrographs processed: {self.outputMicrographs.getSize()}")
            summary.append(self._some_mics_failed)

        return summary

    def _validate(self):
        validateMsgs = []
        modelPath = self.getInputModel()

        if len(self.getGpuList()) > 1:
            validateMsgs.append("Multiple GPUs cannot be used by JANNI.")

        if not os.path.exists(modelPath):
            validateMsgs.append(f"Input model file {modelPath} does not exist."
                                f"Check your config or scipion installb {JANNI_GENMOD}")

        return validateMsgs

    def _citations(self):
        return ['thorsten_wagner_2019_3378300']

    # -------------------------- UTILS functions ------------------------------
    def getInputModel(self):
        return Plugin.getModelFn(JANNI_GENMOD_VAR)
