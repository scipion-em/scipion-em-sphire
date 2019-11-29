# **************************************************************************
# *
# * Authors:    David Maluenda (dmaluenda@cnb.csic.es) [1]
# *             Peter Horvath [1]
# *             J.M. De la Rosa Trevin (delarosatrevin@scilifelab.se) [2]
# *
# *
# * [1] Unidad de  Bioinformatica of Centro Nacional de Biotecnologia , CSIC
# * [2] SciLifeLab, Stockholm University
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 2 of the License, or
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
import json

import pyworkflow.utils as pwutils
from pyworkflow import Config
from pyworkflow.object import Integer
import pyworkflow.protocol.params as params
import pyworkflow.protocol.constants as cons
from pwem.protocols import ProtParticlePickingAuto

from sphire import Plugin
import sphire.convert as convert
from sphire.constants import CRYOLO_GENMOD_VAR, CRYOLO_NS_GENMOD_VAR, INPUT_MODEL_GENERAL, \
    INPUT_MODEL_GENERAL_NS, INPUT_MODEL_OTHER


class SphireProtCRYOLOPicking(ProtParticlePickingAuto):
    """ Picks particles in a set of micrographs
    either manually or in a supervised mode.
    """
    _label = 'cryolo picking'

    def __init__(self, **args):
        ProtParticlePickingAuto.__init__(self, **args)
        self.stepsExecutionMode = cons.STEPS_PARALLEL

    # --------------------------- DEFINE param functions ------------------------
    def _defineParams(self, form):
        ProtParticlePickingAuto._defineParams(self, form)

        form.addParam('inputModelFrom', params.EnumParam,
                      default=INPUT_MODEL_GENERAL,
                      choices=['general cryoem', 'other', 'general neg stain'],
                      display=params.EnumParam.DISPLAY_HLIST,
                      label='Picking model: ',
                      help="You might use a general network model that consists "
                           "of\n   -cryo-em: real, simulated, particle free datasets on "
                           "various grids with contamination\n   -negative stain: trained with"
                           "negative stain images\nand skip training "
                           "completely,\nor,\nif you would like to "
                           "improve the results you can use the model from a "
                           "previous training step or an imported one.")
        form.addParam('inputModel', params.PointerParam,
                      allowsNull=True,
                      condition="inputModelFrom==%d" % INPUT_MODEL_OTHER,
                      label="Input model",
                      pointerClass='CryoloModel',
                      help='Select an existing crYOLO trained model.')
        form.addParam('conservPickVar', params.FloatParam, default=0.3,
                      label="Confidence threshold",
                      help='If you want to pick less conservatively or more '
                           'conservatively you might want to change the threshold '
                           'from the default of 0.3 to a less conservative value '
                           'like 0.2 or more conservative value like 0.4.')
        form.addParam('lowPassFilter', params.BooleanParam,
                      default=False,
                      label="Low-pass filter",
                      help="CrYOLO works on original micrographs but the "
                           "results will be probably improved by the application"
                           " of a reasonable low-pass filter.")
        form.addParam('absCutOffFreq', params.FloatParam,
                      default=0.1,
                      condition='lowPassFilter',
                      label="Absolute cut off frequency",
                      help="Specifies the absolute cut-off frequency for the "
                           "low-pass filter.")
        form.addParam('input_size', params.IntParam,
                      default=1024,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Input size",
                      help="This is the size to which the input is rescaled "
                           "before passed through the network."
                           "For example the default value would be 1024x1024.")
        form.addParam('boxSize', params.IntParam,
                      default=100,
                      label='Box Size',
                      allowsPointers=True,
                      help='Box size in pixels. It should be the size of '
                           'the minimum particle enclosing square in pixel.')
        form.addParam('max_box_per_image', params.IntParam,
                      default=600,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Maximum box per image",
                      help="Maximum number of particles in the image. Only for "
                           "the memory handling. Keep the default value of "
                           "600 or 1000.")
        form.addParam('num_patches', params.IntParam,
                      default=1,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label='Number of Patches',
                      help='If specified the patch mode will be used. A value '
                           'of "2" means, that 2x2 patches will be used.')
        form.addHidden(params.GPU_LIST, params.StringParam, default='0',
                       expertLevel=cons.LEVEL_ADVANCED,
                       label="Choose GPU IDs",
                       help="GPU may have several cores. Set it to zero"
                            " if you do not know what we are talking about."
                            " First core index is 0, second 1 and so on."
                            " crYOLO can use multiple GPUs - in that case"
                            " set to i.e. *0 1 2*.")

        form.addParallelSection(threads=1, mpi=1)

        self._defineStreamingParams(form)
        # Default batch size --> 16
        form.getParam('streamingBatchSize').default = Integer(16)

    # --------------------------- INSERT steps functions -----------------------
    def _insertInitialSteps(self):
        if self.inputModelFrom == INPUT_MODEL_GENERAL:
            model_chosen_str = '(GENERAL)'
        elif self.inputModelFrom == INPUT_MODEL_GENERAL_NS:
            model_chosen_str = '(GENERAL_NS)'
        else:
            model_chosen_str = '(CUSTOM)'

        self.summaryVar.set("Picking using %s model: \n%s" % (model_chosen_str, self.getInputModel()))
        return [self._insertFunctionStep("createConfigStep")]

    # --------------------------- STEPS functions ------------------------------
    def createConfigStep(self):
        inputSize = convert.roundInputSize(self.input_size.get())
        boxSize = self.boxSize.get()
        maxBoxPerImage = self.max_box_per_image.get()
        numPatches = self.num_patches.get()
        absCutOfffreq = self.absCutOffFreq.get()

        model = {
            "architecture": "PhosaurusNet",
            "input_size": inputSize,
            "anchors": [boxSize, boxSize],
            "max_box_per_image": maxBoxPerImage,
            "num_patches": numPatches
        }
        if self.lowPassFilter:
            model.update({"filter": [absCutOfffreq, "filtered"]})

        jsonDict = {"model": model}

        with open(self._getExtraPath('config.json'), 'w') as fp:
            json.dump(jsonDict, fp, indent=4)

        # Create a temporary folder to store all coordinates files
        outDir = self.getOutputDir()
        pwutils.cleanPath(outDir)
        pwutils.makePath(outDir)

    def _pickMicrograph(self, micrograph, *args):
        """This function picks from a given micrograph"""
        self._pickMicrographList([micrograph], args)

    def _pickMicrographList(self, micList, *args):
        workingDir = self._getTmpPath(self.getMicsWorkingDir(micList))
        pwutils.cleanPath(workingDir)
        pwutils.makePath(workingDir)

        # Create folder with linked mics
        convert.convertMicrographs(micList, workingDir)

        args = "-c %s " % self._getExtraPath('config.json')
        args += " -w %s " % self.getInputModel()
        args += " -i %s/" % workingDir
        args += " -o %s/" % workingDir
        args += " -t %0.3f" % self.conservPickVar
        args += " -g %(GPU)s "  # Add GPU that will be set by the executor
        if self.lowPassFilter:
            args += ' --otf'

        Plugin.runCryolo(self, 'cryolo_predict.py', args)

        # Move output files to a common location
        outputCoordsDir = os.path.join(workingDir, 'CBOX')
        if os.path.exists(outputCoordsDir):
            self.runJob('mv', '%s/* %s/'
                        % (outputCoordsDir, self.getOutputDir()))
        # pwutils.cleanPath(workingDir)

    def readCoordsFromMics(self, outputDir, micDoneList, outputCoords):
        """This method read coordinates from a given list of micrographs"""
        outDir = self.getOutputDir()
        boxSize = self.boxSize.get()
        # Calculate if flip is needed
        # JMRT: Let's assume that all mics have same dims, so we avoid
        # to open the image file each time for checking this
        yFlipHeight = convert.getFlipYHeight(micDoneList[0].getFileName())

        for mic in micDoneList:
            coordsFile = os.path.join(outDir, convert.getMicIdName(mic, '.cbox'))
            if os.path.exists(coordsFile):
                convert.readMicrographCoords(mic, outputCoords, coordsFile, boxSize,
                                             yFlipHeight=yFlipHeight)
        outputCoords.setBoxSize(boxSize)

    def createOutputStep(self):
        pass

    # --------------------------- INFO functions -------------------------------
    def _summary(self):
        return [self.summaryVar.get()]

    def _validate(self):
        validateMsgs = []

        modelPath = self.getInputModel()
        if not os.path.exists(modelPath):
            validateMsgs.append("Input model file '%s' does not exists."
                                % modelPath)
            if self.inputModelFrom == INPUT_MODEL_GENERAL:
                validateMsgs.append(
                    "The general model for cryolo must be download from Sphire "
                    "website and %s must contain "
                    "the '%s' parameter pointing to the downloaded file."
                    % Config.SCIPION_LOCAL_CONFIG, CRYOLO_GENMOD_VAR)
            elif self.inputModelFrom == INPUT_MODEL_GENERAL_NS:
                validateMsgs.append(
                    "The general model for cryolo (negative stain) must be download from Sphire "
                    "website and %s must contain "
                    "the '%s' parameter pointing to the downloaded file."
                    % Config.SCIPION_LOCAL_CONFIG, CRYOLO_NS_GENMOD_VAR)
            else:
                validateMsgs.append(
                    "Input model path seems to be wrong. If you have moved the "
                    "project of location, restore the link to the place where "
                    "you have the correct model or use the general model for "
                    "picking. ")
        return validateMsgs

    def _citations(self):
        cites = ['Wagner2019']
        return cites

    # -------------------------- UTILS functions ------------------------------
    def getInputModel(self):
        if self.inputModelFrom == INPUT_MODEL_GENERAL:
            m = Plugin.getCryoloGeneralModel()
        elif self.inputModelFrom == INPUT_MODEL_GENERAL_NS:
            m = Plugin.getCryoloGeneralNSModel()
        else:
            m = self.inputModel.get().getPath()

        return os.path.abspath(m) if m else ''

    def getOutputDir(self):
        return self._getTmpPath('outputCBOX')

    def getMicsWorkingDir(self, micList):
        wd = 'micrographs_%s' % micList[0].strId()
        if len(micList) > 1:
            wd += '-%s' % micList[-1].strId()
        return wd




