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

import os.path
from pyworkflow.tests import (BaseTest, setupTestProject, DataSet)
from pyworkflow.plugin import Domain
import pwem.protocols as emprot
import pwem.constants as emcons
import sphire.protocols as janniprots


class TestJanniMRC(BaseTest):
    """ Test Janni protocol with MRC files"""

    @classmethod
    def setData(cls):
        cls.ds = DataSet.getDataSet('xmipp_tutorial')

    @classmethod
    def setUpClass(cls):
        # Prepare test project
        setupTestProject(cls)
        # Prepare the test data
        cls.setData()
        # Execute the protocols required to generate the inputs for the janni protocol, which will be the preprocessed
        # images (downsampled) in the xmipp tutorial. Thus, the micrographs must be loaded and preprocessed before
        # executing the test
        cls.runImportMicrograph()
        cls.runMicPreprocessing()

    @classmethod
    def runImportMicrograph(cls):

        """ Run an Import micrograph protocol. """
        # Create protocol of the desired type
        protImport = cls.newProtocol(emprot.ProtImportMicrographs)
        # Set the value of the required attributes
        protImport.filesPath.set(TestJanniMRC.ds.getFile('allMics'))
        protImport.voltage.set(300)
        protImport.sphericalAberration.set(2.7)
        protImport.amplitudeContrast.set(0.1)
        protImport.magnification.set(50000)
        protImport.samplingRateMode.set(emcons.SAMPLING_FROM_IMAGE)
        protImport.samplingRate.set(1.237)

        # Launch protocol
        cls.launchProtocol(protImport)
        # Store it
        cls.protImport = protImport

    @classmethod
    def runMicPreprocessing(cls):

        print("Preprocessing the micrographs...")

        # Create protocol of the desired type (in this case it belongs to another plugin, which is xmipp3)
        XmippProtPreprocessMicrographs = Domain.importFromPlugin(
            'xmipp3.protocols',
            'XmippProtPreprocessMicrographs',
            doRaise=True)

        protPreprocess = cls.newProtocol(XmippProtPreprocessMicrographs)

        # Set the value of the required attributes
        protPreprocess.inputMicrographs.set(cls.protImport.outputMicrographs)
        protPreprocess.doDownsample.set(True)
        protPreprocess.downFactor.set(5)

        # Launch protocol
        cls.launchProtocol(protPreprocess)
        # Store it
        cls.protPreprocess = protPreprocess

    def testJanniMRC(self):

        # Create protocol of the desired type
        protJanni = self.newProtocol(janniprots.SphireProtJanniDenoising)

        # Set the value of the required attributes
        protJanni.inputMicrographs.set(self.protPreprocess.outputMicrographs)

        # Launch protocol
        self.launchProtocol(protJanni)

        # Check if the generated files exist
        out_mics = protJanni.outputMicrographs
        for mic in out_mics:
            self.assertTrue(os.path.exists(os.path.abspath(mic.getFileName())))

        # Check that the number of generated files is equal than the number of input files
        self.assertSetSize(out_mics, size=self.protImport.outputMicrographs.getSize())

        # Check the attributes of input and output set of mics: they all should be equal excepting the image
        tol = 1e-3
        in_mics = self.protPreprocess.outputMicrographs
        self.assertTrue(abs(in_mics.getSamplingRate() - out_mics.getSamplingRate()) <= tol)
        self.assertEqual(in_mics.hasCTF(), out_mics.hasCTF())
        self.assertEqual(in_mics.getAlignment(), out_mics.getAlignment())
        self.assertEqual(in_mics.isPhaseFlipped(), out_mics.isPhaseFlipped())
        self.assertEqual(in_mics.isAmplitudeCorrected(), out_mics.isAmplitudeCorrected())

        # Check acquisition params
        in_acq_dict = in_mics.getAcquisition().getMappedDict()
        out_acq_dict = out_mics.getAcquisition().getMappedDict()
        self.assertEqual(in_acq_dict.keys(), out_acq_dict.keys())
        for key in in_acq_dict.keys():
            self.assertTrue(out_acq_dict[key].equalAttributes(in_acq_dict[key]))


class TestJanniTIF(BaseTest):
    """ Test Janni protocol with TIF files"""

    @classmethod
    def setData(cls):
        cls.ds = DataSet.getDataSet('rct')

    @classmethod
    def setUpClass(cls):
        # Prepare test project
        setupTestProject(cls)
        # Prepare the test data
        cls.setData()
        # Execute the protocols required to generate the inputs for the janni protocol, which will be the preprocessed
        # images (downsampled) in the xmipp tutorial. Thus, the micrographs must be loaded and preprocessed before
        # executing the test
        cls.runImportMicrograph()
        cls.runMicPreprocessing()

    @classmethod
    def runImportMicrograph(cls):

        """ Run an Import micrograph protocol. """
        # Create protocol of the desired type
        protImport = cls.newProtocol(emprot.ProtImportMicrographs)
        # Set the value of the required attributes
        protImport.filesPath.set(TestJanniTIF.ds.getFile('untilted'))
        protImport.voltage.set(300)
        protImport.sphericalAberration.set(2.7)
        protImport.amplitudeContrast.set(0.1)
        protImport.magnification.set(50000)
        protImport.samplingRateMode.set(emcons.SAMPLING_FROM_IMAGE)
        protImport.samplingRate.set(1.237)

        # Launch protocol
        cls.launchProtocol(protImport)
        # Store it
        cls.protImport = protImport

    @classmethod
    def runMicPreprocessing(cls):

        print("Preprocessing the micrographs...")

        # Create protocol of the desired type (in this case it belongs to another plugin, which is xmipp3)
        XmippProtPreprocessMicrographs = Domain.importFromPlugin(
            'xmipp3.protocols',
            'XmippProtPreprocessMicrographs',
            doRaise=True)

        protPreprocess = cls.newProtocol(XmippProtPreprocessMicrographs)

        # Set the value of the required attributes
        protPreprocess.inputMicrographs.set(cls.protImport.outputMicrographs)
        protPreprocess.doDownsample.set(True)
        protPreprocess.downFactor.set(5)

        # Launch protocol
        cls.launchProtocol(protPreprocess)
        # Store it
        cls.protPreprocess = protPreprocess

    def testJanniTIF(self):

        # Create protocol of the desired type
        protJanni = self.newProtocol(janniprots.SphireProtJanniDenoising)

        # Set the value of the required attributes
        protJanni.inputMicrographs.set(self.protPreprocess.outputMicrographs)

        # Launch protocol
        self.launchProtocol(protJanni)

        in_mics = self.protPreprocess.outputMicrographs
        out_mics = protJanni.outputMicrographs
        # Check if the generated files exist
        for mic in out_mics:
            self.assertTrue(os.path.exists(os.path.abspath(mic.getFileName())))
            # self.assertTrue(os.path.exists(os.path.abspath(mic._filename)))

        # Check that the number of generated files is equal than the number of input files
        self.assertSetSize(out_mics, size=self.protImport.outputMicrographs.getSize())

        # Check the attributes of input and output set of mics: they all should be equal excepting the image
        tol = 1e-3
        self.assertTrue(abs(in_mics.getSamplingRate() - out_mics.getSamplingRate()) <= tol)
        self.assertEqual(in_mics.hasCTF(), out_mics.hasCTF())
        self.assertEqual(in_mics.getAlignment(), out_mics.getAlignment())
        self.assertEqual(in_mics.isPhaseFlipped(), out_mics.isPhaseFlipped())
        self.assertEqual(in_mics.isAmplitudeCorrected(), out_mics.isAmplitudeCorrected())
        # self.assertDictEqual(in_mics.getAcquisition().getMappedDict(), out_mics.getAcquisition().getMappedDict())

        # Check acquisition params
        in_acq_dict = in_mics.getAcquisition().getMappedDict()
        out_acq_dict = out_mics.getAcquisition().getMappedDict()
        self.assertEqual(in_acq_dict.keys(), out_acq_dict.keys())
        for key in in_acq_dict.keys():
            self.assertTrue(out_acq_dict[key].equalAttributes(in_acq_dict[key]))
