# -*- coding: utf-8 -*-
# **************************************************************************
# *
# * Authors:     Jorge Jiménez (jjimenez@cnb.csic.es)
# *
# * Biocomputing Unit of Centro Nacional de Biotecnologia, (CNB-CSIC)
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
from pyworkflow.protocol import params, ValidationException
from pyworkflow.utils.properties import Message
from pyworkflow.em.protocol import ProtMicrographs
from sphire import Plugin

"""
Describe your python module here:
This module implements the integration of the denoising functionality of Sphire-Janni 
software whithin Scipion framework
"""

class SphireProtJanniDenoising(ProtMicrographs):
    """ Protocol to denoise a set of micrographs in the project.
    """
    _label = 'janni denoising'
    _input_path = ""
    _output_path = ""
    _some_mics_failed = ""

    # -------------------------- DEFINE param functions ----------------------
    def _defineParams(self, form):
        """ Define the input parameters that will be used.
        Params:
            form: this is the form to be populated with sections and params.
        """
        # Create inputs section in the generated pop-up window:
        form.addSection(label=Message.LABEL_INPUT)
        form.addParam('inputMicrographs',  # Variable name
                      params.PointerParam,  # Variable type
                      pointerClass='SetOfMicrographs',
                      label='Input Micrographs',
                      important=True,
                      help='Path of the directory which contains the images to denoise. Aligned averages works better.')


    # --------------------------- STEPS functions ------------------------------
    # Main
    def _insertAllSteps(self):
        # Insert processing steps
        self._insertFunctionStep('denoisingStep')
        self._insertFunctionStep('createOutputStep')

    def denoisingStep(self):

        input_mics = self.inputMicrographs.get()
        mic_list = [os.path.relpath(mic.getFileName()) for mic in input_mics]
        working_dir = os.path.dirname(mic_list[0])
        self._input_path = os.path.abspath(working_dir)
        self._output_path = os.path.abspath(self._getExtraPath())

        args = "denoise {}/ {}/ {}".format(self._input_path, self._output_path, self.getInputModel())
        Plugin.runCryolo(self, 'janni_denoise.py', args)

    def createOutputStep(self):
        in_mics = self.inputMicrographs.get()  # Get input set of micrographs
        out_mics = self._createSetOfMicrographs()  # Create an empty set of micrographs
        out_mics.copyInfo(in_mics)  # Copy all the info of the inputs, then the filename attribute will be edited with
        # the path of the output files

        # Update micrograph name and append to the new Set
        n_failed_mics = 0
        for mic in in_mics:
            current_out_mic = self._getOutputMicrograph(mic)
            if os.path.exists(current_out_mic):
                mic.setFileName(current_out_mic)
                out_mics.append(mic)

            else:
                n_failed_mics += 1
                print("Denoised mic wasn't correctly generated --> {}", mic.getFileName())
                continue

        # Check if the output list is empty
        if n_failed_mics > 0:
            n_mics_in = len(in_mics)
            if n_failed_mics == n_mics_in:
                raise ValidationException("No output micrographs were generated.")
            else:
                _some_mics_failed = "{} of {} micrographs weren't correctly processed. Please check the log for more " \
                                    "details".format(n_failed_mics, n_mics_in)

        self._defineOutputs(outputMicrographs=out_mics)
        self._defineTransformRelation(self.inputMicrographs, out_mics)

    # --------------------------- INFO functions -----------------------------------
    def _summary(self):
        """ Summarize what the protocol has done"""
        summary = []

        if self.isFinished():
            summary.append("Denoising using general model: {}".format(self.getInputModel()))
            summary.append("Micrographs processed: {}".format(self.outputMicrographs.getSize()))
            summary.append(self._some_mics_failed)

        return summary

    def _methods(self):
        methods = []

        if self.isFinished():
            methods.append("The micrographs in set {} were denoised.".format(self.getObjectTag('inputMicrographs')))
            methods.append("The resulting set of micrographs is {}.".format(self.getObjectTag('outputMicrographs')))

        return methods

    def _validate(self):
        validateMsgs = []
        modelPath = self.getInputModel()
        if not os.path.exists(modelPath):
            validateMsgs.append("Input model file '%s' does not exists." % modelPath)

        return validateMsgs

    # -------------------------- UTILS functions ------------------------------
    def getInputModel(self):

        m = Plugin.getJanniGeneralModel()
        return os.path.abspath(m) if m else ''

    def _getOutputMicrograph(self, mic):
        """ Return the name of the output micrograph, given
        the input Micrograph object.
        """
        # Janni generates automatically a sub-folder in the output directory provided. The name of this folder is the
        # same name as the deeper folder name in the input directory introduced. For example, if input_dir =
        # /home/username/abc and output_dir = /home/outdata, the files generated by janni will be stored in
        # /home/outdata/abc. Thus, it is necessary to split the inputh path and take the last element. Apart from that,
        # generated files preserve the file name and extension
        in_file_path, in_file_name = os.path.split(mic.getFileName())

        return os.path.join(self._getExtraPath(),  # Relative path to output dir (rel. paths are required in DDBB)
                            os.path.split(in_file_path)[-1],  # Deeper folder name in the input path
                            in_file_name)  # File name and extension

