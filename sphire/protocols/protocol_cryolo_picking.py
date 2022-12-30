# **************************************************************************
# *
# * Authors:    David Maluenda (dmaluenda@cnb.csic.es) [1]
# *             Peter Horvath (phorvath@cnb.csic.es) [1]
# *             J.M. De la Rosa Trevin (delarosatrevin@scilifelab.se) [2]
# *
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

import json
from glob import glob
import os

import pyworkflow.utils as pwutils
from pyworkflow.object import Integer
import pyworkflow.protocol.params as params
import pyworkflow.protocol.constants as cons
from pwem.protocols import ProtParticlePickingAuto
import pwem.objects as emobj

from .. import Plugin
from ..constants import *
import sphire.convert as convert


class SphireProtCRYOLOPicking(ProtParticlePickingAuto):
    """ Picks particles in a set of micrographs with crYOLO.
    """
    _label = 'cryolo picking'

    def __init__(self, **args):
        ProtParticlePickingAuto.__init__(self, **args)
        self.stepsExecutionMode = cons.STEPS_PARALLEL

    # --------------------------- DEFINE param functions ----------------------
    def _defineParams(self, form):
        ProtParticlePickingAuto._defineParams(self, form)

        form.addParam('inputModelFrom', params.EnumParam,
                      default=INPUT_MODEL_GENERAL,
                      choices=['general cryo (low-pass filtered)',
                               'general cryo (denoised)',
                               'other', 'general neg stain'],
                      display=params.EnumParam.DISPLAY_COMBO,
                      label='Picking model: ',
                      help="You might use a general network model that consists "
                           "of\n\t-cryo: real, simulated, particle free datasets on "
                           "various grids with contamination\n\t-negative stain: trained with"
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
                      label="Cut-off frequency",
                      help="Specifies the absolute cut-off frequency for the "
                           "low-pass filter.")
        form.addParam('numCpus', params.IntParam, default=4,
                      label="Number of CPUs",
                      help="*Important!* This is different from number of threads "
                           "above as threads are used for GPU parallelization. "
                           "Provide here the number of CPU cores for each cryolo "
                           "process.")
        form.addParam('input_size', params.IntParam,
                      default=1024,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Input size",
                      help="This is the size to which the input is rescaled "
                           "before passed through the network."
                           "For example the default value would be 1024x1024.")
        form.addParam('boxSize', params.IntParam,
                      default=0,
                      label='Box Size (optional)',
                      allowsPointers=True,
                      help='Box size in pixels. It should be the size of '
                           'the minimum particle enclosing square in pixel. '
                           'If introduced value is zero, it is estimated.')
        form.addParam('max_box_per_image', params.IntParam,
                      default=700,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Maximum box per image",
                      help="Maximum number of particles in the image. Only for "
                           "the memory handling. Keep the default value of 700.")
        form.addHidden(params.USE_GPU, params.BooleanParam, default=True,
                       expertLevel=params.LEVEL_ADVANCED,
                       label="Use GPU?",
                       help="Set to True if you want to use GPU implementation ")
        form.addHidden(params.GPU_LIST, params.StringParam, default='0',
                       expertLevel=cons.LEVEL_ADVANCED,
                       label="Choose GPU IDs",
                       help="GPU may have several cores. Set it to zero"
                            " if you do not know what we are talking about."
                            " First core index is 0, second 1 and so on."
                            " crYOLO can use multiple GPUs - in that case"
                            " set to i.e. *0 1 2*.")

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
        form.getParam('streamingBatchSize').default = Integer(16)

    # --------------------------- INSERT steps functions ----------------------
    def _insertInitialSteps(self):
        return self._insertFunctionStep(self.createConfigStep)

    # --------------------------- STEPS functions -----------------------------
    def createConfigStep(self):
        inputSize = convert.roundInputSize(self.input_size.get())
        maxBoxPerImage = self.max_box_per_image.get()
        absCutOfffreq = self.absCutOffFreq.get()
        model = {
            "architecture": "PhosaurusNet",
            "input_size": inputSize,
            "max_box_per_image": maxBoxPerImage,
        }
        boxSize = self.boxSize.get()
        if boxSize:
            model.update({"anchors": [boxSize, boxSize]})
        if self.lowPassFilter:
            model.update({"filter": [absCutOfffreq, self._getTmpPath("filtered")]})
        elif self.inputModelFrom == INPUT_MODEL_GENERAL_DENOISED:
            model.update({"filter": [
                Plugin.getModelFn(JANNI_GENMOD_VAR),
                24,
                3,
                self._getTmpPath("filtered")
            ]})

        jsonDict = {"model": model}

        with open(self._getExtraPath('config.json'), 'w') as fp:
            json.dump(jsonDict, fp, indent=4)

    def _pickMicrograph(self, micrograph, *args):
        """This function picks from a given micrograph"""
        self._pickMicrographList([micrograph], args)

    def _pickMicrographList(self, micList, *args):
        if not micList:  # maybe in continue cases, need to properly check
            return

        workingDir = self._getTmpPath(self.getMicsWorkingDir(micList))
        pwutils.cleanPath(workingDir)
        pwutils.makePath(workingDir)

        # Create folder with linked mics
        convert.convertMicrographs(micList, workingDir)

        args = " -c %s" % self._getExtraPath('config.json')
        args += " -w %s" % self.getInputModel()
        args += " -i %s/" % workingDir
        args += " -o %s/" % workingDir
        args += " -t %0.3f" % self.conservPickVar
        if not self.usingCpu():
            args += " -g %(GPU)s"  # Add GPU that will be set by the executor
        args += " -nc %d" % self.numCpus.get()
        if self.lowPassFilter or self.inputModelFrom == INPUT_MODEL_GENERAL_DENOISED:
            args += ' --cleanup'

        Plugin.runCryolo(self, 'cryolo_predict.py', args, useCpu=self.usingCpu())

        # Move output files to extra folder
        pwutils.moveTree(os.path.join(workingDir, "CBOX"), self._getExtraPath())

    def readCoordsFromMics(self, outputDir, micDoneList, outputCoords):
        """This method read coordinates from a given list of micrographs"""
        # Coordinates may have a boxSize (e.g. streaming case)
        boxSize = outputCoords.getBoxSize()
        if not boxSize:
            if self.boxSize.get():  # Box size can be provided by the user
                boxSize = self.boxSize.get()
            else:  # If not crYOLO estimates it
                boxSize = self._getEstimatedBoxSize()

                if self.boxSizeFactor.get() != 1:
                    boxSize = int(boxSize * self.boxSizeFactor.get())

            outputCoords.setBoxSize(boxSize)

        # Calculate if flip is needed
        # JMRT: Let's assume that all mics have same dims, so we avoid
        # to open the image file each time for checking this
        yFlipHeight = convert.getFlipYHeight(micDoneList[0].getFileName())

        # Create a reader to parse .cbox files
        # and a Coordinate object to add to output set
        reader = convert.CoordBoxReader(boxSize,
                                        yFlipHeight=yFlipHeight,
                                        boxSizeEstimated=self.boxSizeEstimated)
        coord = emobj.Coordinate()
        coord._cryoloScore = emobj.Float()

        for mic in micDoneList:
            cboxFile = convert.getMicIdName(mic, suffix='.cbox')
            coordsFile = self._getExtraPath(cboxFile)
            if os.path.exists(coordsFile):
                for x, y, score in reader.iterCoords(coordsFile):
                    # Clean up objId to add as a new coordinate
                    coord.setObjId(None)
                    coord.setPosition(x, y)
                    coord.setMicrograph(mic)
                    coord._cryoloScore.set(score)
                    # Add it to the set
                    outputCoords.append(coord)

        # Register box size
        self.createBoxSizeOutput(outputCoords)

    def createBoxSizeOutput(self, coordSet):
        """ Output box size as an Integer. Other protocols can use it as
            IntParam with allowsPointer=True.
        """
        if not hasattr(self, "boxsize"):
            boxSize = Integer(coordSet.getBoxSize())
            self._defineOutputs(boxsize=boxSize)

    # --------------------------- INFO functions ------------------------------
    def _summary(self):
        summary = []

        summary.append(f"Picking using {self.getEnumText('inputModelFrom')} model: "
                       f"{self.getInputModel()}")

        return summary

    def _validate(self):
        validateMsgs = []

        if self.lowPassFilter and self.inputModelFrom == INPUT_MODEL_GENERAL_DENOISED:
            validateMsgs.append("Lowpass cannot be used with the JANNI-denoised model")

        if self.usingCpu():
            if os.system(Plugin.getCondaActivationCmd() + Plugin.getVar(CRYOLO_ENV_ACTIVATION_CPU)):
                validateMsgs.append("CPU implementation of crYOLO is not installed, "
                                    "install 'cryoloCPU' or use the GPU implementation.")

        else:
            if self.numberOfThreads.get() < len(self.getGpuList()):
                validateMsgs.append("Multiple GPUs can not be used by a single process. "
                                    "Make sure you specify more threads than GPUs.")

        modelPath = self.getInputModel()
        modelNames = {
            INPUT_MODEL_GENERAL: CRYOLO_GENMOD,
            INPUT_MODEL_GENERAL_DENOISED: CRYOLO_GENMOD,
            INPUT_MODEL_OTHER: None,
            INPUT_MODEL_GENERAL_NS: CRYOLO_NS_GENMOD
        }

        if not os.path.exists(modelPath):
            validateMsgs.append(f"Input model file {modelPath} does not exist.")
            modelName = modelNames[self.inputModelFrom.get()]
            if modelName is not None:
                validateMsgs.append(f"Check your config or run scipion installb {modelName}")

        if self.inputModelFrom == INPUT_MODEL_GENERAL_DENOISED:
            # extra model for janni is required
            janniModel = Plugin.getModelFn(JANNI_GENMOD_VAR)
            if not os.path.exists(janniModel):
                validateMsgs.append(f"Input model file {janniModel} does not exist."
                                    f"Check your config or run scipion installb {JANNI_GENMOD}")

        return validateMsgs

    def _warnings(self):
        warnings = []

        if self.inputModelFrom == INPUT_MODEL_GENERAL_DENOISED and self.usingCpu():
            warnings.append("Picking with JANNI-denoised model is quite slow "
                            "on CPU - about 10 seconds per micrograph")

        return warnings

    def _citations(self):
        return ['Wagner2019']

    # -------------------------- UTILS functions ------------------------------
    @property
    def boxSizeEstimated(self):
        # Only when boxSize == 0 it is estimated by cryolo
        return self.boxSize.get() == 0

    def getInputModel(self):
        if self.inputModelFrom == INPUT_MODEL_GENERAL:
            m = Plugin.getModelFn(CRYOLO_GENMOD_VAR)
        elif self.inputModelFrom == INPUT_MODEL_GENERAL_DENOISED:
            m = Plugin.getModelFn(CRYOLO_GENMOD_NN_VAR)
        elif self.inputModelFrom == INPUT_MODEL_GENERAL_NS:
            m = Plugin.getModelFn(CRYOLO_NS_GENMOD_VAR)
        else:
            m = os.path.abspath(self.inputModel.get().getPath())

        return m

    def getMicsWorkingDir(self, micList):
        wd = 'micrographs_%s' % micList[0].strId()
        if len(micList) > 1:
            wd += '-%s' % micList[-1].strId()
        return wd

    def usingCpu(self):
        return not self.useGpu.get()

    def _getEstimatedBoxSize(self):
        sizeSummaryFilePattern = self._getTmpPath('micrographs_*/DISTR',
                                                  'size_distribution_summary*.txt')
        boxSize = None
        try:
            distrSummaryFile = glob(sizeSummaryFilePattern)[0]
            with open(distrSummaryFile) as f:
                for line in f:
                    if line.startswith("MEAN,"):
                        boxSize = int(line.split(",")[-1])
                        break
            if not boxSize:
                raise ValueError

            return boxSize

        except IndexError:
            raise Exception(f'File not found:\n{sizeSummaryFilePattern}')
        except ValueError:
            raise Exception(f'Boxsize not found in file:\n{f.name}')
        except Exception as e:
            raise e
