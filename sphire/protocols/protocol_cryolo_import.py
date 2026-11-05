# **************************************************************************
# *
# * Authors:     J.M. De la Rosa Trevin (delarosatrevin@scilifelab.se) [1]
# *
# * [1] SciLifeLab, Stockholm University
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

import pyworkflow.utils as pwutils
import pyworkflow.protocol.params as params
from pwem.protocols import ProtImport

from ..objects import CryoloModel


class SphireProtCryoloImport(ProtImport):
    """
    Imports an existing crYOLO training model into the workflow environment so
    it can be reused in later particle picking or model refinement procedures.

    AI Generated:

    crYOLO Model Import (SphireProtCryoloImport) — User Manual
        Overview

        The crYOLO Model Import protocol allows users to register a previously
        trained crYOLO neural network model within a Scipion project. Its main
        purpose is to make externally generated or previously trained particle
        picking models available for subsequent cryo-EM processing workflows,
        including automated particle detection, additional training cycles, or
        comparative testing between different models.

        In practical cryo-EM workflows, researchers frequently accumulate
        multiple trained particle picking models optimized for distinct sample
        types, imaging conditions, detector setups, or biological specimens.
        This protocol provides a convenient mechanism to integrate such models
        into a unified processing environment without retraining them from
        scratch. This is especially valuable in facility environments or
        collaborative projects where models are shared across users and
        experiments.

        General Purpose and Biological Context

        Particle picking models are often one of the most valuable assets in a
        cryo-EM workflow because they encode prior knowledge about particle
        appearance, contrast behavior, ice quality, and specimen morphology.
        Reusing an already optimized model can dramatically accelerate dataset
        processing and improve consistency between experiments.

        Biologically, this becomes especially important for projects involving
        repetitive acquisition of similar samples, such as membrane proteins,
        ribosomal complexes, filamentous assemblies, viral particles, or
        stable macromolecular complexes. A validated model may substantially
        reduce manual intervention and improve reproducibility during particle
        selection.

        The protocol is also useful for benchmarking purposes. Users may import
        several independently trained models and compare their picking behavior
        on the same dataset to determine which model generalizes best for a
        given biological specimen or imaging condition.

        Input Requirements

        The protocol requires access to a previously trained crYOLO model.
        Typically, this model originates from earlier training workflows,
        external collaborations, facility repositories, or archived cryo-EM
        projects. The imported model is treated as a reusable resource within
        the project and can later be selected by downstream protocols that
        require a trained picking network.

        In most practical situations, users should ensure that the imported
        model is compatible with the expected acquisition conditions. Models
        trained on strongly different magnifications, pixel sizes, detector
        types, or particle morphologies may produce suboptimal picking
        performance.

        Workflow Integration

        Once imported, the model becomes available as a standard project output
        and can be connected directly to particle picking protocols or further
        training procedures. This integration enables reproducible workflows
        where the exact picking model used during processing is preserved and
        traceable throughout the project history.

        The protocol is intentionally lightweight because its role is not to
        modify or retrain the neural network, but rather to establish a stable
        reference to an already existing model. This design supports rapid
        workflow construction and efficient reuse of validated resources.

        Practical Recommendations

        In routine cryo-EM processing, users are encouraged to maintain a
        curated collection of validated crYOLO models associated with specific
        specimen categories or acquisition strategies. Importing these models
        into individual projects simplifies workflow organization and reduces
        redundant training efforts.

        When sharing projects between systems or collaborators, users should
        verify that the referenced model files remain accessible from the new
        environment. Maintaining consistent storage organization for trained
        models improves portability and long-term reproducibility.

        For exploratory datasets, testing several imported models may help
        identify the most robust particle detection strategy before committing
        to large-scale extraction or downstream reconstruction workflows.

        Final Perspective

        The crYOLO Model Import protocol serves as a bridge between trained
        deep-learning particle picking models and operational cryo-EM
        workflows. By enabling efficient reuse of validated neural networks,
        it supports reproducibility, accelerates dataset processing, and helps
        standardize particle detection across projects and biological systems.
    """
    _label = 'cryolo import'

    # -------------------------- DEFINE param functions -----------------------
    def _defineParams(self, form):
        form.addSection(label='Import')
        form.addParam('modelPath', params.PathParam,
                      label="Training model path",
                      help="Provide the path of a previous crYOLO training "
                           "model.")

    # --------------------------- INSERT steps functions ----------------------
    def _insertAllSteps(self):
        self._insertFunctionStep(self.importModelStep, needsGPU=False)

    # --------------------------- STEPS functions -----------------------------
    def importModelStep(self):
        """ Create a link to the provided input model path
        and register the output to be used later for further training
        or picking.
        """
        absPath = os.path.abspath(self.modelPath.get())
        outputPath = self._getExtraPath(os.path.basename(absPath))
        self.info("Creating link:\n"
                  "%s -> %s" % (outputPath, absPath))
        self.info("NOTE: If you move this project to another computer, the symbolic"
                  "link to the model will be broken, but you can update the link "
                  "and get it working again.")

        pwutils.createAbsLink(absPath, outputPath)

        self._defineOutputs(outputModel=CryoloModel(outputPath))
