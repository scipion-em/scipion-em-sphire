# **************************************************************************
# *
# * Authors:     Grigory Sharov (gsharov@mrc-lmb.cam.ac.uk) [1]
# *
# * [1] MRC Laboratory of Molecular Biology (MRC-LMB)
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

import pyworkflow.protocol.params as params
import pyworkflow.protocol.constants as cons
from pwem.protocols import EMProtocol

from .. import Plugin
from ..constants import *
import sphire.convert as convert


class ProtCryoloBase(EMProtocol):
    """ Base class for crYOLO picking protocols. """
    _label = None
    _IS_TRAIN = False

    def __init__(self, **args):
        EMProtocol.__init__(self, **args)

    def _defineParams(self, form):
        if self._IS_TRAIN:
            form.addParam('doFineTune', params.BooleanParam, default=True,
                          label='Fine-tune previous model?',
                          help='Since crYOLO 1.3 you can train a model for your '
                               'data by fine-tuning the general model.'
                               'The general model was trained on a lot of particles '
                               'with a variety of shapes and therefore learned a '
                               'very good set of generic features.')
            form.addParam('inputModelFrom', params.EnumParam,
                          default=INPUT_MODEL_GENERAL,
                          choices=['general', 'other'],
                          condition="doFineTune",
                          display=params.EnumParam.DISPLAY_HLIST,
                          label='Use previous model: ',
                          help="You might use a general network model that consists "
                               "of real, simulated, particle free datasets on "
                               "various grids with contamination and skip training "
                               "completely or if you would like to "
                               "improve the results you can use the model from a "
                               "previous training step or an imported one.")
            form.addParam('inputModel', params.PointerParam,
                          allowsNull=True,
                          condition=("doFineTune and inputModelFrom!=%d"
                                     % INPUT_MODEL_GENERAL),
                          label="Input model",
                          pointerClass='CryoloModel',
                          help='Select an existing crYOLO trained model.')
        else:
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
                      default=10.0,
                      condition='lowPassFilter',
                      label="Cut-off resolution (A)",
                      help="Specifies the absolute cut-off resolution for the "
                           "low-pass filter. Recommended value sampling/0.3")
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

        if not self._IS_TRAIN:
            form.addHidden(params.USE_GPU, params.BooleanParam, default=True,
                           expertLevel=params.LEVEL_ADVANCED,
                           label="Use GPU?",
                           help="Set to True if you want to use GPU implementation.")
        form.addHidden(params.GPU_LIST, params.StringParam, default='0',
                       expertLevel=cons.LEVEL_ADVANCED,
                       label="Choose GPU IDs",
                       help="GPU may have several cores. Set it to zero"
                            " if you do not know what we are talking about."
                            " First core index is 0, second 1 and so on."
                            " crYOLO can use multiple GPUs - in that case"
                            " set to i.e. *0 1 2*.")

    # --------------------------- STEPS functions -----------------------------
    def createConfigStep(self, inputData):
        inputSize = convert.roundInputSize(self.input_size.get())
        maxBoxPerImage = self.max_box_per_image.get()
        sampling = inputData.getSamplingRate()
        nyquist = 2*sampling
        if nyquist >= self.absCutOffFreq.get():
            absCutOfffreq = 0.5
        else:
            absCutOfffreq = sampling/self.absCutOffFreq.get()
        model = {
            "architecture": "PhosaurusNet",
            "input_size": inputSize,
            "max_box_per_image": maxBoxPerImage,
            "norm": "STANDARD"
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

        if self._IS_TRAIN:
            pretrainedModel = self.getInputModel() if self.doFineTune else ""

            train = {"train_image_folder": f"{self.TRAIN[1]}/",
                     "train_annot_folder": f"{self.TRAIN[0]}/",
                     "train_times": 10,
                     "pretrained_weights": pretrainedModel,
                     "batch_size": self.batchSize.get(),
                     "learning_rate": self.learning_rates.get(),
                     "nb_epoch": self.nb_epochVal.get(),
                     "object_scale": 5.0,
                     "no_object_scale": 1.0,
                     "coord_scale": 1.0,
                     "class_scale": 1.0,
                     "log_path": "logs/",
                     "saved_weights_name": self.MODEL,
                     "debug": True
                     }

            valid = {"valid_image_folder": "",
                     "valid_annot_folder": "",
                     "valid_times": 1
                     }

            jsonDict.update({"train": train, "valid": valid})

        with open(self._getExtraPath('config.json'), 'w') as fp:
            json.dump(jsonDict, fp, indent=4)

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

        if self._IS_TRAIN and not self.doFineTune:
            # no models to validate
            return validateMsgs

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

        if (not self._IS_TRAIN and
                self.inputModelFrom == INPUT_MODEL_GENERAL_DENOISED and
                self.usingCpu()):
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

    def usingCpu(self):
        if self._IS_TRAIN:
            return False
        else:
            return not self.useGpu.get()

    def getInputModel(self):
        if self._IS_TRAIN:
            if self.inputModelFrom == INPUT_MODEL_GENERAL:
                m = Plugin.getModelFn(CRYOLO_GENMOD_VAR)
            else:
                m = os.path.abspath(self.inputModel.get().getPath())
        else:
            if self.inputModelFrom == INPUT_MODEL_GENERAL:
                m = Plugin.getModelFn(CRYOLO_GENMOD_VAR)
            elif self.inputModelFrom == INPUT_MODEL_GENERAL_DENOISED:
                m = Plugin.getModelFn(CRYOLO_GENMOD_NN_VAR)
            elif self.inputModelFrom == INPUT_MODEL_GENERAL_NS:
                m = Plugin.getModelFn(CRYOLO_NS_GENMOD_VAR)
            else:
                m = os.path.abspath(self.inputModel.get().getPath())
        return m

    def getEstimatedBoxSize(self, path):
        sizeSummaryFilePattern = os.path.join(path,
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
