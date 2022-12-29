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
from ..constants import JANNI_GENMOD_VAR


class SphireProtJanniDenoising(ProtMicrographs):
    """ Protocol to denoise a set of micrographs. """
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
        self._insertFunctionStep(self.denoisingStep)
        self._insertFunctionStep(self.createOutputStep)

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
            validateMsgs.append(f"Input model file {modelPath} does not exist.")

        return validateMsgs

    def _citations(self):
        return ['thorsten_wagner_2019_3378300']

    # -------------------------- UTILS functions ------------------------------
    def getInputModel(self):
        return Plugin.getModelFn(JANNI_GENMOD_VAR)
