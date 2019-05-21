# **************************************************************************
# *
# * Authors:     David Maluenda (dmaluenda@cnb.csic.es)
# *              Peter Horvath (phorvath@cnb.csic.es)
# *
# * Unidad de  Bioinformatica of Centro Nacional de Biotecnologia , CSIC
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

from pyworkflow.em.protocol import ProtParticlePicking
import pyworkflow.protocol.constants as cons
import pyworkflow.protocol.params as params
import pyworkflow.utils as pwutils

from sphire import Plugin
import sphire.convert as convert


class SphireProtCRYOLOTraining(ProtParticlePicking):
    """ Picks particles in a set of micrographs
    either manually or in a supervised mode.
    """
    _label = 'cryolo training'
    MODEL = 'model.h5'
    TRAIN = ['train_annotations', 'train_images']

    def __init__(self, **args):
        ProtParticlePicking.__init__(self, **args)

    # -------------------------- DEFINE param functions ------------------------
    def _defineParams(self, form):
        ProtParticlePicking._defineParams(self, form)
        form.addParam('inputCoordinates', params.PointerParam,
                      pointerClass='SetOfCoordinates',
                      label='Input coordinates', important=True,
                      help='Select the SetOfCoordinates to be used for training.')
        form.addParam('input_size', params.IntParam, default=1024,
                      label="Input size",
                      help="crYOLO extracts a patch and rescales to the given"
                           " input size and uses the resized patch for training.")
        form.addParam('boxSize', params.IntParam, default=100,
                      label='Box Size',
                      allowsPointers=True,
                      help='Box size in pixels. It should be the size of '
                           'the minimum particle enclosing square in pixel.')
        form.addParam('doFineTune', params.BooleanParam, default=True,
                      label='Fine-tune previous model?',
                      help='Since crYOLO 1.3 you can train a model for your '
                           'data by fine-tuning the general model.'
                           'The general model was trained on a lot of particles '
                           'with a variety of shapes and therefore learned a '
                           'very good set of generic features. ')
        form.addParam('useGenMod', params.BooleanParam,
                      default=True, condition="doFineTune",
                      label='Use general model?',
                      help="You might use a general network model that consists "
                           "of real, simulated, particle free datasets"
                      " on various grids with contaminations and skip training "
                           "completely or if you would like to "
                           "improve the results you can use the model from the "
                           "previous training step by answering no. The general"
                           " model can be found.")
        form.addParam('sphireTraining', params.PointerParam,
                      allowsNull=True,
                      condition="doFineTune and not useGenMod",
                      label="Cryolo training run",
                      pointerClass='SphireProtCRYOLOTraining',
                      help='Select the previous cryolo training run.')

        form.addParam('eFlagParam', params.IntParam, default=10,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Stop when not changed (times in a row)",
                      help="The training stops when the 'loss' metric on the "
                           "validation data does not improve 10 times in a row. "
                           "This is typically enough. In case want to give the "
                           "training more time to find the best model you might "
                           "increase this parameters to a higher value (e.g 15).")

        form.addParam('max_box_per_image',params.IntParam, default=600,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Maximum box per image",
                      help="Maximum number of particles in the image. Only for" 
                           "the memory handling. Keep the default value of 600 "
                           "or 1000. ")

        form.addParam('nb_epochVal', params.IntParam, default=50,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Maximum number of iterations",
                      help="Maximum number of epochs the network will train."
                           " Basically never reach this number, as crYOLO "
                           "stops training if it recognize that the validation "
                           "loss is not improving anymore.")

        form.addParam('learning_rates', params.FloatParam, default=1e-4,
                      expertLevel=cons.LEVEL_ADVANCED,
                      label="Learning rates",
                      help="If the number is too small convergence can be slow,"
                           " if it is.")

        form.addParam('lowPassFilter', params.BooleanParam,
                      expertLevel=cons.LEVEL_ADVANCED,
                      default=False,
                      label="Low-pass filter",
                      help="CrYOLO works on original micrographs but the results"
                           " will be probably improved by the application of a "
                           "reasonable low-pass filter.")

        form.addParam('absCutOffFreq', params.FloatParam, default=0.1,
                  expertLevel=cons.LEVEL_ADVANCED,
                  condition='lowPassFilter',
                  label="Absolute cut off frequency",
                  help="Specifies the absolute cut-off frequency for the "
                       "low-pass filter.")

        form.addHidden(params.GPU_LIST, params.StringParam, default='0',
                         expertLevel=cons.LEVEL_ADVANCED,
                         label="Choose GPU IDs",
                         help="GPU may have several cores. Set it to zero"
                             " if you do not know what we are talking about."
                             " First core index is 0, second 1 and so on."
                             " Motioncor2 can use multiple GPUs - in that case"
                             " set to i.e. *0 1 2*.")

        form.addParallelSection(threads=1, mpi=1)

    # --------------------------- INSERT steps functions ------------------------
    def _insertAllSteps(self):
        self._insertFunctionStep("convertInputStep")
        self._insertFunctionStep("createConfigStep")
        if self.doFineTune:
            self._insertFunctionStep("cryoloModelingStep", ' --fine_tune')
        else:
            self._insertFunctionStep("warmUpNetworkStep")
            self._insertFunctionStep("cryoloModelingStep")

    # --------------------------- STEPS functions ------------------------------
    def convertInputStep(self):
        """ Converts a set of coordinates to box files and binaries to mrc
        if needed. It generates 2 folders 1 for the box files and another for
        the mrc files. To be passed (the folders as params for cryolo
        """
        inputMics = self.inputMicrographs.get()
        coordSet = self.inputCoordinates.get()

        paths = []
        for d in self.TRAIN:
            paths.append(self._getWorkDir(d))
            pwutils.makePath(paths[-1])

        # call the write set of Coordinates passing the createMic function
        micList = [mic.clone() for mic in inputMics]
        convert.writeSetOfCoordinates(paths[0], coordSet, micList)
        convert.convertMicrographs(micList, paths[1])

    def createConfigStep(self):
        inputSize = self.input_size.get()
        boxSize = self.boxSize.get()
        maxBoxPerImage = self.max_box_per_image.get()
        absCutOfffreq = self.absCutOffFreq.get()

        model = {"architecture": "PhosaurusNet",
                 "input_size": inputSize,
                 "anchors": [boxSize, boxSize],
                 "max_box_per_image": maxBoxPerImage,
                 "num_patches": 1
                 }

        if self.lowPassFilter:
            model.update({"filter": [absCutOfffreq, "filtered"]})

        pretrainedModel = self.getInputModel() if self.doFineTune else self.MODEL

        train = {"train_image_folder": "%s/" % self.TRAIN[1],
                 "train_annot_folder": "%s/" % self.TRAIN[0],
                 "train_times": 10,
                 "pretrained_weights": pretrainedModel,
                 "batch_size": 6,
                 "learning_rate": self.learning_rates.get(),
                 "nb_epoch": self.nb_epochVal.get(),
                 "warmup_epochs": 0,
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

        jsonDict = {"model": model, "train": train, "valid": valid}

        with open(self._getWorkDir('config.json'), 'w') as fp:
            json.dump(jsonDict, fp, indent=4)

    def runCryoloTrain(self, w, extraArgs=''):
        params = "-c config.json"
        params += " -w %s " % w  # FIXME: Check this param
        params += " -g %(GPU)s"
        params += " -e %d" % self.eFlagParam
        params += extraArgs
        Plugin.runCryolo(self, 'cryolo_train.py', params,
                         cwd=self._getWorkDir())

    def warmUpNetworkStep(self):
        self.runCryoloTrain(3)

    def cryoloModelingStep(self, extraArgs=''):
        self.runCryoloTrain(0, extraArgs=extraArgs)
        pwutils.moveFile(self._getWorkDir(self.MODEL), self.getOutputModel())

    # --------------------------- INFO functions -------------------------------
    def _summary(self):
        summary = ['This protocol does not generate any output, '
                   'but it can be used as input in a picking protocol.'
                   '(Internally a model.h5 should be written. ']
        if self.doFineTune:
            summary.append('Fine-tunning input model: \n %s'
                           % self.getInputModel())
        return summary

    def _validate(self):
        validateMsgs = []

        if self.inputCoordinates.get() is None:
            validateMsgs.append("Please select a set of coordinates, obtained"
                                " from a previous picking run. Typically the "
                                "number of coordinates from 10 micrographs are "
                                "a good start.")

        return validateMsgs

    # -------------------------- UTILS functions ------------------------------
    def _getWorkDir(self, *paths):
        return self._getExtraPath(*paths)

    def getOutputModel(self):
        return self._getPath(self.MODEL)

    def getInputModel(self):
        if self.useGenMod:
            m = Plugin.getCryoloGeneralModel()
        else:
            m = self.particlePickingRun.getOutputModel()

        return os.path.abspath(m) if m else ''



