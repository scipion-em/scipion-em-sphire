# **************************************************************************
# *
# * Authors: Yunior C. Fonseca Reyna    (cfonseca@cnb.csic.es)
# *
# *
# * Unidad de  Bioinformatica of Centro Nacional de Biotecnologia , CSIC
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
import glob
import json

from pkg_resources import parse_version

import pyworkflow.utils as pwutils
from pyworkflow import BETA, Config
from pyworkflow.object import Boolean
import pyworkflow.protocol.params as params
import pyworkflow.protocol.constants as cons

from sphire import Plugin
import sphire.convert as convert
from sphire.constants import *
from tomo.objects import SetOfCoordinates3D
from tomo.protocols import ProtTomoPicking
import tomo.constants as tomoConst


class SphireProtCRYOLOTomoPicking(ProtTomoPicking):
    """ Picks particles in a set of micrographs
    either manually or in a supervised mode.
    """
    _label = 'cryolo tomo picking'
    boxSizeEstimated = Boolean(False)
    _devStatus = BETA
    _possibleOutputs = {'output3DCoordinates': SetOfCoordinates3D}
    _protCompatibility = [V1_8_0]

    def __init__(self, **kwargs):
        ProtTomoPicking.__init__(self, **kwargs)

    # --------------------------- DEFINE param functions ----------------------
    def _defineParams(self, form):
        ProtTomoPicking._defineParams(self, form)

        form.addParam('boxSize', params.IntParam,
                      default=50,
                      label='Box Size',
                      allowsPointers=True,
                      help='Box size in pixels. It should be the size of '
                           'the minimum particle enclosing square in pixel. '
                           'If introduced value is zero, it is estimated.')
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
                      help='Confidence threshold. Have to be between 0 and 1.'
                           'The higher, the more conservative')
        form.addParam('lowPassFilter', params.BooleanParam,
                      default=False,
                      label="Low-pass filter",
                      help="Noise filter applied before training/picking")
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
        form.addParam('max_box_per_image', params.IntParam,
                      default=600,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Maximum box per image",
                      help="Maximum number of particles in the image. Only for "
                           "the memory handling. Keep the default value of "
                           "600 or 1000.")
        form.addParam("batchSize", params.IntParam, default=1,
                      expertLevel=params.LEVEL_ADVANCED,
                      label="Batch size",
                      help="The number of images crYOLO process in parallel")

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

    def _insertAllSteps(self):
        if self.inputModelFrom in [INPUT_MODEL_GENERAL,
                                   INPUT_MODEL_GENERAL_DENOISED]:
            model_chosen_str = '(GENERAL)'
        elif self.inputModelFrom == INPUT_MODEL_GENERAL_NS:
            model_chosen_str = '(GENERAL_NS)'
        else:
            model_chosen_str = '(CUSTOM)'

        self.summaryVar.set("Picking using %s model: \n%s" % (model_chosen_str,
                                                              self.getInputModel()))

        self._insertFunctionStep(self.createConfigStep)
        self._insertFunctionStep(self.pickTomogramsStep)
        self._insertFunctionStep(self.createOutputStep)

    # -------------------------- STEPS functions ------------------------------

    def createConfigStep(self):
        inputSize = convert.roundInputSize(self.input_size.get())
        maxBoxPerImage = self.max_box_per_image.get()
        absCutOfffreq = self.absCutOffFreq.get()
        model = {
            "architecture": "PhosaurusNet",
            "input_size": inputSize,
            "max_box_per_image": maxBoxPerImage,
            "norm": "STANDARD"
        }
        boxSize = self.boxSize.get()
        model.update({"anchors": [boxSize, boxSize]})
        if self.lowPassFilter:
            model.update({"filter": [absCutOfffreq, self._getTmpPath("filtered_tmp")]})
        other = {
            "log_path": self._getExtraPath("logs")
        }

        jsonDict = {"model": model, "other": other}

        with open(self._getExtraPath('config.json'), 'w') as fp:
            json.dump(jsonDict, fp, indent=4)

    def pickTomogramsStep(self):
        """This function picks from a given set of Tomograms"""

        tomogramsList = self.inputTomograms.get()

        def cleanAndMakePath(inDirectory):
            pwutils.cleanPath(inDirectory)
            pwutils.makePath(inDirectory)

        tomogramsDir = self._getTmpPath("tomograms")
        outputDir = self._getExtraPath()
        cleanAndMakePath(tomogramsDir)

        # Create folder with linked tomograms
        for tomogram in tomogramsList:
            convert.convertTomograms([tomogram], tomogramsDir)
        args = "-c %s" % self._getExtraPath('config.json')
        args += " -w %s" % self.getInputModel()
        args += " -i %s/" % tomogramsDir
        args += " -o %s/" % outputDir
        args += " -t %0.3f" % self.conservPickVar
        args += " -g %(GPU)s"  # Add GPU that will be set by the executor
        args += " -nc %d" % self.numCpus.get()
        args += " --tomogram"
        Plugin.runCryolo(self, 'cryolo_predict.py', args,
                         useCpu=not self.useGpu.get())

    def createOutputStep(self):
        setOfTomograms = self.inputTomograms.get()
        outputPath = self._getExtraPath("CBOX_3D")
        suffix = self._getOutputSuffix(SetOfCoordinates3D)
        coord3DSetDict = {}
        setOfCoord3D = self._createSetOfCoordinates3D(setOfTomograms, suffix)
        setOfCoord3D.setName("tomoCoord")
        setOfCoord3D.setPrecedents(setOfTomograms)
        setOfCoord3D.setSamplingRate(setOfTomograms.getSamplingRate())
        setOfCoord3D.setBoxSize(self.boxSize.get())

        for tomogram in setOfTomograms.iterItems():
            outFile = '%s%05d%s' % (pwutils.removeBaseExt(tomogram.getFileName()),
                                    tomogram.getObjId(), '.cbox')
            pattern = os.path.join(outputPath, outFile)
            files = glob.glob(pattern)

            if not files or not os.path.isfile(files[0]):
                continue

            coord3DSetDict[tomogram.getObjId()] = setOfCoord3D

            # Populate Set of 3D Coordinates with 3D Coordinates
            filePath = os.path.join(outputPath, outFile)
            tomogramClone = tomogram.clone()
            tomogramClone.copyInfo(tomogram)
            convert.readSetOfCoordinates3D(tomogramClone, coord3DSetDict, filePath,
                                           self.boxSize.get(),
                                           origin=tomoConst.BOTTOM_LEFT_CORNER)
            name = self.OUTPUT_PREFIX + suffix
            args = {}
            args[name] = setOfCoord3D
            self._defineOutputs(**args)
            self._defineSourceRelation(setOfTomograms, setOfCoord3D)

            # Update Outputs
            for index, coord3DSet in coord3DSetDict.items():
                self._updateOutputSet(name, coord3DSet,
                                      state=coord3DSet.STREAM_CLOSED)

    def _validate(self):
        validateMsgs = []
        cryoloVersion = self.getCryoloVersion(defaultVersion=V1_8_0)
        if not [version for version in self._protCompatibility if parse_version(cryoloVersion) >= parse_version(version)]:
            validateMsgs.append("The protocol is not compatible with the "
                                "crYOLO version %s" % cryoloVersion)

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

    def getCryoloVersion(self, defaultVersion=V_UNKNOWN):
        """ Get cryolo version"""
        _cryoloVersion = defaultVersion
        try:
            # TODO We need an adecuated way to check the activated version
            envName = Plugin.getVar(CRYOLO_ENV_ACTIVATION).split(' ')[-1]
            if '-' in envName:
                _cryoloVersion = envName.split('-')[-1]
            else:
                print("Warning: It seems you have an installed crYOLO outside "
                      "Scipion. We can not detect crYOLO's version. We assume it "
                      "is %s " % _cryoloVersion)
        except Exception:
            print("Couldn't get crYOLO's version. Please review your config (%s)" % Plugin.getUrl())
        return _cryoloVersion.rstrip('\n')




