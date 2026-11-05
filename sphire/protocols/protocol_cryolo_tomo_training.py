# **************************************************************************
# *
# * Authors: Yunior C. Fonseca Reyna (cfonseca@cnb.csic.es)
# *
# * Unidad de Bioinformatica of Centro Nacional de Biotecnologia, CSIC
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

import pyworkflow.protocol.params as params
import pyworkflow.utils as pwutils

from . import SphireProtCRYOLOTraining
import sphire.convert as convert


class SphireProtCRYOLOTomoTraining(SphireProtCRYOLOTraining):
    """
    Trains a crYOLO deep learning model for particle detection in cryo-electron tomography datasets using annotated 3D coordinates and tomograms.

    AI Generated:

    crYOLO Tomogram Training (SphireProtCRYOLOTomoTraining) - User Manual
        Overview

        The crYOLO Tomogram Training protocol is designed to generate a deep learning model capable of detecting
        particles directly within cryo-electron tomography data. Unlike standard particle picking workflows that
        operate on two-dimensional micrographs, this protocol is focused on volumetric tomographic information and
        therefore learns from three-dimensional particle annotations associated with tomograms.

        In cryo-electron tomography, particle localization is often more challenging than in single-particle
        analysis because tomograms contain higher noise levels, missing wedge artifacts, variable contrast, and
        crowded intracellular environments. This protocol provides a framework for training a dedicated neural
        network model that can later be applied to automate particle detection in similar tomographic datasets.

        The training procedure is especially useful when working with cellular tomography, subtomogram averaging
        projects, or in situ structural biology studies where particles must be identified within complex biological
        environments. By learning from manually curated annotations, the resulting model can significantly accelerate
        downstream analysis while maintaining biologically meaningful particle localization.

        Inputs and Biological Context

        The protocol requires two main inputs: a set of tomograms and a corresponding set of three-dimensional
        coordinates representing known particle locations. These coordinates typically originate from manual picking,
        template matching refinement, or previous curated picking workflows.

        The quality of the training data strongly influences the final model performance. High-quality annotations
        that accurately represent true biological particles are essential for obtaining reliable predictions.
        Training datasets should ideally include examples spanning the range of particle orientations, contrast
        conditions, and local environments expected in the final experimental data.

        In practical biological applications, users commonly begin with a relatively small curated dataset and later
        refine the model iteratively as additional annotations become available. This incremental strategy often
        improves robustness when studying heterogeneous or difficult cellular samples.

        Training Strategy and Model Optimization

        The protocol supports both training from scratch and fine-tuning of previously existing models. Training
        from scratch is generally appropriate when studying novel particle types or tomographic conditions that
        differ substantially from existing datasets. Fine-tuning is often preferred when a related pretrained model
        already exists because it reduces training time and usually improves convergence stability.

        Several training parameters influence the balance between convergence speed, model generalization, and
        computational cost. The learning rate controls how rapidly the model adapts during optimization. Smaller
        values usually provide more stable convergence, whereas larger values may accelerate training at the risk of
        instability.

        Batch size determines how many tomographic samples are processed simultaneously during training. Larger
        batches may improve stability when sufficient GPU memory is available, while smaller batches are often more
        practical for large tomographic volumes.

        Early stopping is included to prevent excessive training once the model performance no longer improves.
        This strategy helps reduce overfitting and avoids unnecessary computational expense. In biological practice,
        overfitting can lead to models that perform well on the training tomograms but fail to generalize to new
        experimental datasets.

        Tomographic Data Preparation

        Before training, tomograms and coordinate annotations are organized into a format suitable for neural
        network learning. This preparation stage standardizes the volumetric data and associates each annotation
        with its corresponding tomogram.

        Careful curation of the tomographic inputs is important for successful learning. Tomograms with severe
        reconstruction artifacts, incorrect voxel sizes, or inaccurate coordinate annotations may negatively affect
        the resulting model. Consistent preprocessing across all tomograms generally improves prediction stability.

        Biological users should also consider whether the selected training examples adequately represent the
        diversity present in the final dataset. Including particles from multiple tomographic conditions, defocus
        ranges, or cellular environments can substantially improve model robustness.

        Fine-Tuning Existing Models

        Fine-tuning allows previously trained crYOLO models to adapt to new tomographic datasets. This approach is
        especially useful when the biological target remains similar but imaging conditions or sample preparation
        differ slightly.

        In many practical cryo-electron tomography projects, fine-tuning dramatically reduces the number of manual
        annotations required. Instead of generating a large fully annotated dataset from the beginning, users can
        refine an existing model with a smaller collection of representative examples.

        Fine-tuning is particularly valuable for facility-scale workflows where related tomographic experiments are
        processed repeatedly over time. It enables continuous model improvement while maintaining consistency across
        datasets.

        Outputs and Downstream Applications

        The primary output is a trained crYOLO neural network model specialized for tomographic particle detection.
        This model can later be used in automated picking workflows to identify particles in unseen tomograms.

        From a biological perspective, the quality of the trained model directly affects downstream subtomogram
        averaging, classification, and structural interpretation. Accurate particle localization improves alignment
        quality and increases the likelihood of achieving high-resolution structural information.

        The resulting model may also serve as a reusable resource for future experiments involving similar particle
        types, cellular systems, or acquisition strategies.

        Practical Recommendations

        In routine cryo-electron tomography projects, it is often preferable to begin with a modest but highly
        curated training dataset rather than a large collection of uncertain annotations. Accurate annotations are
        typically more important than annotation quantity during the early stages of training.

        Fine-tuning existing models is generally recommended whenever compatible pretrained models are available.
        This approach reduces computational requirements and frequently improves prediction quality.

        Users should visually inspect prediction quality after training and verify that detected particles remain
        biologically meaningful across different tomograms. If systematic false positives or missing particles are
        observed, expanding the training set with additional representative annotations usually provides the largest
        improvement.

        Final Perspective

        For cryo-electron tomography workflows, automated particle detection is a critical step that strongly
        influences the quality and efficiency of downstream structural analysis. A carefully trained crYOLO model
        enables reproducible and scalable particle localization in complex tomographic environments while reducing
        the burden of manual annotation. Thoughtful dataset preparation, biologically accurate annotations, and
        iterative refinement of the training process are the main factors that determine successful model
        performance.
    """
    _label = 'cryolo tomo training'
    MODEL = 'model.h5'
    TRAIN = ['train_annotations', 'train_images']
    _IS_TRAIN = True

    # -------------------------- DEFINE param functions -----------------------
    def _defineParams(self, form):
        form.addSection(label='Input')
        form.addParam('inputTomograms', params.PointerParam,
                      pointerClass='SetOfTomograms',
                      label='Input tomograms', important=True,
                      help='Select the SetOfTomograms to be used during '
                           'picking.')
        form.addParam('inputCoordinates3D', params.PointerParam,
                      pointerClass='SetOfCoordinates3D',
                      label='Input coordinates 3D', important=True,
                      help="Please select a set of coordinates 3D, obtained "
                           "from a previous picking run.")

        SphireProtCRYOLOTraining._defineTrainParams(self, form)

    # --------------------------- STEPS functions -----------------------------
    def convertInputStep(self):
        """ Converts a set of coordinates to cbox files and binaries to mrc.
        It generates 2 folders: one for the cbox files and another for
        the mrc files.
        """
        inputTomos = self.getInputMicrographs()
        coordSet = self.inputCoordinates3D.get()

        paths = []
        for d in self.TRAIN:
            paths.append(self._getExtraPath(d))
            pwutils.makePath(paths[-1])

        tomoList = [tomo.clone() for tomo in inputTomos]
        convert.writeSetOfCoordinates3D(paths[0], coordSet, tomoList)
        convert.convertTomograms(tomoList, paths[1])

    # -------------------------- UTILS functions ------------------------------
    def getInputMicrographs(self):
        """ Redefine from the base class. """
        return self.inputTomograms.get()
