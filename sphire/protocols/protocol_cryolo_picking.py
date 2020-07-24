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
import glob

import pwem
import pyworkflow.utils as pwutils
from pyworkflow import Config
from pyworkflow.object import Integer
import pyworkflow.protocol.params as params
import pyworkflow.protocol.constants as cons
from pwem.protocols import ProtParticlePickingAuto

from sphire import Plugin
import sphire.convert as convert
from sphire.constants import *


class SphireProtCRYOLOPicking(ProtParticlePickingAuto):
    """ Picks particles in a set of micrographs
    either manually or in a supervised mode.
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
                           "of\n   -cryo: real, simulated, particle free datasets on "
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
                      default=600,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Maximum box per image",
                      help="Maximum number of particles in the image. Only for "
                           "the memory handling. Keep the default value of "
                           "600 or 1000.")
        form.addHidden(params.USE_GPU, params.BooleanParam, default=True,
                       expertLevel=params.LEVEL_ADVANCED,
                       label="Use GPU (vs CPU)",
                       help="Set to true if you want to use GPU implementation ")
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

    # --------------------------- INSERT steps functions ----------------------
    def _insertInitialSteps(self):
        if self.inputModelFrom in [INPUT_MODEL_GENERAL,
                                   INPUT_MODEL_GENERAL_DENOISED]:
            model_chosen_str = '(GENERAL)'
        elif self.inputModelFrom == INPUT_MODEL_GENERAL_NS:
            model_chosen_str = '(GENERAL_NS)'
        else:
            model_chosen_str = '(CUSTOM)'

        self.summaryVar.set("Picking using %s model: \n%s" % (model_chosen_str,
                                                              self.getInputModel()))
        return [self._insertFunctionStep("createConfigStep")]

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
            model.update({"filter": [absCutOfffreq, "filtered"]})

        jsonDict = {"model": model}

        with open(self._getExtraPath('config.json'), 'w') as fp:
            json.dump(jsonDict, fp, indent=4)

    def _pickMicrograph(self, micrograph, *args):
        """This function picks from a given micrograph"""
        self._pickMicrographList([micrograph], args)

    def _pickMicrographList(self, micList, *args):
        def cleanAndMakePath(inDirectory):
            pwutils.cleanPath(inDirectory)
            pwutils.makePath(inDirectory)
        workingDir = self._getTmpPath(self.getMicsWorkingDir(micList))
        cleanAndMakePath(workingDir)

        # Create folder with linked mics
        convert.convertMicrographs(micList, workingDir)

        args = "-c %s" % self._getExtraPath('config.json')
        args += " -w %s" % self.getInputModel()
        args += " -i %s/" % workingDir
        args += " -o %s/" % workingDir
        args += " -t %0.3f" % self.conservPickVar
        args += " -g %(GPU)s"  # Add GPU that will be set by the executor
        args += " -nc %d" % self.numCpus.get()
        if self.lowPassFilter:
            args += ' --otf'

        Plugin.runCryolo(self, 'cryolo_predict.py', args, useCpu=not self.useGpu.get())

        # Move output files to a common location
        dirs2Move = [os.path.join(workingDir, dir) for dir in ['CBOX', 'DISTR']]
        outputDirs = [self.getOutpuCBOXtDir(), self.getOutputDISTRDir()]
        [cleanAndMakePath(dir) for dir in outputDirs]
        [self.runJob('mv', '%s/* %s/' % (indDir, outputDir))
         for indDir, outputDir in zip(dirs2Move, outputDirs) if os.path.exists(indDir)]

    def readCoordsFromMics(self, outputDir, micDoneList, outputCoords):
        """This method read coordinates from a given list of micrographs"""
        outDir = self.getOutpuCBOXtDir()
        boxSizeEstimated = False
        # Coordinates may have a boxSize (e. g. streaming case)
        boxSize = outputCoords.getBoxSize()
        if not boxSize:
            if self.boxSize.get():  # Box size can be provided by the user
                boxSize = self.boxSize.get()
            else:  # If not crYOLO estimates it
                boxSizeEstimated = True
                boxSize = self._getEstimatedBoxSize()
            outputCoords.setBoxSize(boxSize)

        # Calculate if flip is needed
        # JMRT: Let's assume that all mics have same dims, so we avoid
        # to open the image file each time for checking this
        yFlipHeight = convert.getFlipYHeight(micDoneList[0].getFileName())

        for mic in micDoneList:
            coordsFile = os.path.join(outDir, convert.getMicIdName(mic, '.cbox'))
            if os.path.exists(coordsFile):
                convert.readMicrographCoords(mic, outputCoords, coordsFile, boxSize,
                                             yFlipHeight=yFlipHeight,
                                             boxSizeEstimated=boxSizeEstimated)

    def createOutputStep(self):
        """ The output is just an Integer. Other protocols can use it in those
            IntParam if it has set allowsPointer=True
        """
        boxSize = Integer(self.outputCoordinates.getBoxSize())
        self._defineOutputs(boxsize=boxSize)

    # --------------------------- INFO functions ------------------------------
    def _summary(self):
        return [self.summaryVar.get()]

    def _validate(self):
        validateMsgs = []

        if (not self.useGpu.get() and os.system(Plugin.getCondaActivationCmd() +
                                                Plugin.getVar(CRYOLO_ENV_ACTIVATION_CPU))):
            validateMsgs.append("CPU implementation of crYOLO is not installed, "
                                "install 'cryoloCPU' or use the GPU implementation.")

        nprocs = max(self.numberOfMpi.get(), self.numberOfThreads.get())
        if nprocs < len(self.getGpuList()):
            validateMsgs.append("Multiple GPUs can not be used by a single process. "
                                "Make sure you specify more threads than GPUs.")

        modelPath = self.getInputModel()
        if not os.path.exists(modelPath):
            validateMsgs.append("Input model file '{}' does not exists.".format(modelPath))

            if self.inputModelFrom == INPUT_MODEL_GENERAL:
                validateMsgs.append(
                    "The general model for cryolo must be downloaded from Sphire "
                    "website and {} must contain "
                    "the '{}' parameter pointing to the downloaded file.".format(
                        Config.SCIPION_LOCAL_CONFIG, CRYOLO_GENMOD_VAR))

            elif self.inputModelFrom == INPUT_MODEL_GENERAL_DENOISED:
                validateMsgs.append(
                    "The general model for cryolo must be downloaded from Sphire "
                    "website and {} must contain "
                    "the '{}' parameter pointing to the downloaded file.".format(
                        Config.SCIPION_LOCAL_CONFIG, JANNI_GENMOD_VAR))

            elif self.inputModelFrom == INPUT_MODEL_GENERAL_NS:
                validateMsgs.append(
                    "The general model for cryolo (negative stain) must be downloaded from Sphire "
                    "website and {} must contain "
                    "the '{}' parameter pointing to the downloaded file.".format(
                        Config.SCIPION_LOCAL_CONFIG, CRYOLO_NS_GENMOD_VAR))
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
        elif self.inputModelFrom == INPUT_MODEL_GENERAL_DENOISED:
            m = Plugin.getCryoloGeneralNNModel()
        elif self.inputModelFrom == INPUT_MODEL_GENERAL_NS:
            m = Plugin.getCryoloGeneralNSModel()
        else:
            m = self.inputModel.get().getPath()

        return os.path.abspath(m) if m else ''

    def getOutpuCBOXtDir(self):
        return self._getTmpPath('outputCBOX')

    def getOutputDISTRDir(self):
        return self._getExtraPath('outputDISTR')

    def getMicsWorkingDir(self, micList):
        wd = 'micrographs_%s' % micList[0].strId()
        if len(micList) > 1:
            wd += '-%s' % micList[-1].strId()
        return wd

    def _getEstimatedBoxSize(self):
        sizeSummaryFilePattern = os.path.join(self.getOutputDISTRDir(),
                                              'size_distribution_summary*.txt')
        lineFilterPattern = 'mean,'
        boxSize = None
        try:
            distrSummaryFile = glob.glob(sizeSummaryFilePattern)[0]
            with open(distrSummaryFile) as f:
                for line in f:
                    if line.lower().startswith(lineFilterPattern):
                        boxSize = int(line.lower().replace(lineFilterPattern, ''))
                        break
            if not boxSize:
                raise ValueError

            return boxSize

        except IndexError:
            raise Exception('File not found:\n{}'.format(sizeSummaryFilePattern))
        except ValueError:
            raise Exception('Boxsize not found in file:\n{}'.format(f.name))
        except Exception as e:
            raise e
