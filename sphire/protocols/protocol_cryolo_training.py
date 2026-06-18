# **************************************************************************
# *
# * Authors:     David Maluenda (dmaluenda@cnb.csic.es)
# *              Peter Horvath (phorvath@cnb.csic.es)
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

from pwem.protocols import ProtParticlePicking
import pyworkflow.protocol.params as params
import pyworkflow.utils as pwutils
from pyworkflow.object import Integer

from .. import Plugin
from ..objects import CryoloModel
from .protocol_base import ProtCryoloBase
import sphire.convert as convert


class SphireProtCRYOLOTraining(ProtCryoloBase, ProtParticlePicking):
    """
    Trains a crYOLO deep learning model for automated particle picking in cryo-EM
    micrographs using a curated set of particle coordinates provided by the user.

    AI Generated:

    crYOLO Training (SphireProtCRYOLOTraining) - User Manual
        Overview

        The crYOLO training protocol creates a customized deep learning model capable
        of automatically identifying particles in cryo-EM micrographs. Its primary
        objective is to adapt particle picking performance to the specific appearance,
        imaging conditions, and biological characteristics of a user dataset. By
        learning from manually curated or previously validated particle coordinates,
        the resulting model becomes specialized for the structures and acquisition
        conditions present in the experiment.

        In practical cryo-EM workflows, particle picking is one of the most critical
        early processing stages because it strongly influences downstream classification,
        reconstruction quality, and final biological interpretation. A well trained
        model can dramatically reduce manual intervention while increasing consistency
        and throughput in large cryo-EM datasets.

        Inputs and General Workflow

        The protocol requires a set of micrographs together with corresponding particle
        coordinates that represent correct particle locations. These coordinates usually
        originate from manual picking, template matching, or a previously validated
        picking workflow. Even relatively small training datasets can be effective when
        the annotations are accurate and representative of the biological sample.

        During training, the protocol prepares the experimental images and associated
        particle annotations so the neural network can learn the visual appearance of
        the target particles. The resulting model can later be applied to new
        micrographs acquired under similar experimental conditions.

        Biological users should ensure that the training coordinates reflect the true
        structural diversity of the dataset. If the annotations contain strong bias,
        contamination, damaged particles, or preferential orientations, the trained
        model may reproduce these limitations during automated picking.

        Training Strategies

        The protocol supports both training from scratch and fine tuning of an existing
        crYOLO model. Training from scratch is generally appropriate when working with
        novel samples, unusual imaging conditions, or particle types that differ
        substantially from existing pretrained models. This strategy may require more
        training examples and additional optimization but provides maximum flexibility.

        Fine tuning is often preferred when a previously trained model already resembles
        the current dataset. In these situations, the model can adapt more rapidly and
        frequently achieves reliable picking performance with fewer annotated
        micrographs. This is particularly useful for iterative cryo-EM projects,
        related protein families, or repeated data collection campaigns performed under
        similar microscope conditions.

        Training Parameters and Convergence

        Several parameters influence how the neural network learns from the training
        data. The learning rate controls how quickly the model adapts during training.
        Excessively large values may lead to unstable learning, while very small values
        can slow convergence significantly.

        The batch size determines how many micrographs are processed simultaneously
        during optimization. Larger batch sizes may improve computational efficiency
        when sufficient GPU memory is available, whereas smaller values are often more
        stable on limited hardware resources.

        The protocol also incorporates an early stopping strategy that monitors training
        convergence. This prevents unnecessary overtraining once the model performance
        no longer improves on validation data. From a biological perspective, avoiding
        overfitting is essential because a model that memorizes the training images too
        closely may fail to generalize to new micrographs.

        GPU Requirements and Computational Considerations

        crYOLO training relies heavily on GPU acceleration. Training time depends on
        the number of micrographs, particle complexity, image size, and available GPU
        resources. Modern GPUs substantially reduce execution time and allow more
        efficient optimization of deep learning models.

        Users should monitor training quality carefully rather than relying exclusively
        on computational metrics. Visual inspection of picked particles on independent
        micrographs remains one of the most reliable ways to evaluate biological
        relevance and practical usability.

        Output Interpretation

        The protocol produces a trained crYOLO model that can be directly applied for
        automated particle picking in future workflows. The model encapsulates the
        learned visual representation of the particles and associated imaging
        conditions.

        A successful model should identify particles consistently across different
        micrographs while minimizing false positives originating from contamination,
        carbon edges, ice artifacts, or background noise. Biological interpretation of
        downstream reconstructions depends strongly on the quality of this selection
        step.

        Practical Recommendations

        For most cryo-EM projects, it is advisable to begin with a small but carefully
        curated set of high quality particle annotations. Correct annotations are more
        important than large quantities of inconsistent training data. Including a
        representative range of defocus conditions, particle orientations, and ice
        qualities usually improves model robustness.

        Fine tuning existing models is often an efficient starting point for related
        datasets, while completely new biological systems may benefit from dedicated
        training from scratch. Users should periodically validate the picking results
        visually and refine the training dataset if systematic picking errors appear.

        Final Perspective

        Deep learning based particle picking has become an essential component of
        modern cryo-EM workflows because it enables rapid, scalable, and reproducible
        particle detection. Careful preparation of training annotations, thoughtful
        parameter selection, and continuous biological validation are the key elements
        for obtaining reliable automated picking models that support high quality
        structural analysis.
    """
    _label = 'cryolo training'
    MODEL = 'model.h5'
    TRAIN = ['train_annotations', 'train_images']
    _IS_TRAIN = True

    # -------------------------- DEFINE param functions -----------------------
    def _defineTrainParams(self, form):
        ProtCryoloBase._defineParams(self, form)

        form.addSection(label="Training")
        form.addParam('eFlagParam', params.IntParam, default=10,
                      label="Early stop patience",
                      help="The training stops when the 'loss' metric on the "
                           "validation data does not improve 10 times in a row. "
                           "This is typically enough. In case want to give the "
                           "training more time to find the best model you might "
                           "increase this parameters to a higher value (e.g 15).")
        form.addParam('nb_epochVal', params.IntParam, default=200,
                      label="Maximum number of iterations",
                      help="Maximum number of epochs the network will train. "
                           "Basically never reach this number, as crYOLO "
                           "stops training if it recognize that the validation "
                           "loss is not improving anymore.")
        form.addParam('learning_rates', params.FloatParam, default=1e-4,
                      label="Learning rates",
                      help="If the number is too small convergence can be slow.")
        form.addParam('batchSize', params.IntParam, default=4,
                      label="Batch size",
                      help="The number of images crYOLO process in parallel "
                           "during training.")

        form.addParallelSection(threads=1, mpi=0)

        # Default box size --> 100
        form.getParam('boxSize').default = Integer(100)

    def _defineParams(self, form):
        ProtParticlePicking._defineParams(self, form)
        form.addParam('inputCoordinates', params.PointerParam,
                      pointerClass='SetOfCoordinates',
                      label='Input coordinates', important=True,
                      help="Please select a set of coordinates, obtained "
                           "from a previous picking run. Typically the "
                           "coordinates from ~ 10 micrographs is "
                           "a good start.")
        self._defineTrainParams(form)

    # --------------------------- INSERT steps functions ----------------------
    def _insertAllSteps(self):
        self._insertFunctionStep(self.convertInputStep, needsGPU=False)
        self._insertFunctionStep(self.createConfigStep,
                                 self.getInputMicrographs(),
                                 needsGPU=False)

        if self.doFineTune:
            self._insertFunctionStep(self.cryoloTrainingStep,
                                     ' --fine_tune -lft 2',
                                     needsGPU=True)
        else:
            self._insertFunctionStep(self.cryoloTrainingStep, needsGPU=True)

        self._insertFunctionStep(self.createOutputStep, needsGPU=False)

    # --------------------------- STEPS functions -----------------------------
    def convertInputStep(self):
        """ Converts a set of coordinates to box files and binaries to mrc.
        It generates 2 folders: one for the box files and another for
        the mrc files.
        """
        inputMics = self.getInputMicrographs()
        coordSet = self.inputCoordinates.get()

        paths = []
        for d in self.TRAIN:
            paths.append(self._getExtraPath(d))
            pwutils.makePath(paths[-1])

        micList = [mic.clone() for mic in inputMics]
        convert.writeSetOfCoordinates(paths[0], coordSet, micList)
        convert.convertMicrographs(micList, paths[1])

    def cryoloTrainingStep(self, extraArgs=''):
        params = " -c config.json"
        params += " -w %d" % (0 if self.doFineTune else 5)
        params += " -g %(GPU)s"
        params += " -nc %d" % self.numCpus.get()
        params += " -e %d" % self.eFlagParam
        if self.lowPassFilter:
            params += " --cleanup"
        params += extraArgs

        Plugin.runCryolo(self, 'cryolo_train.py', params,
                         cwd=self._getExtraPath())

        pwutils.moveFile(self._getExtraPath(self.MODEL),
                         self.getOutputModelPath())

    def createOutputStep(self):
        """ Register the output model. """
        self._defineOutputs(outputModel=CryoloModel(self.getOutputModelPath()))

    # --------------------------- INFO functions ------------------------------
    def _summary(self):
        summary = []

        if self.doFineTune:
            summary.append(f"Fine-tuning using "
                           f"{self.getEnumText('inputModelFrom')} model: "
                           f"{self.getInputModel()}")
        else:
            summary.append("Training a new model from scratch")

        return summary

    def _methods(self):
        methods = []

        return methods

    # -------------------------- UTILS functions ------------------------------
    def getOutputModelPath(self):
        return self._getPath(self.MODEL)
