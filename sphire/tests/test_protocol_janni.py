# **************************************************************************
# *
# * Authors:     Jorge Jiménez (jjimenez@cnb.csic.es)
# *
# * Biocomputing Unit of Centro Nacional de Biotecnologia, (CNB-CSIC)
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

from pyworkflow.tests import BaseTest, setupTestProject, DataSet
from pyworkflow.plugin import Domain
from pyworkflow.utils import magentaStr
from pwem.protocols import ProtImportMicrographs

from ..protocols import SphireProtJanniDenoising


XmippProtPreprocessMicrographs = Domain.importFromPlugin(
    'xmipp3.protocols',
    'XmippProtPreprocessMicrographs',
    doRaise=True)


class TestJanni(BaseTest):
    @classmethod
    def setUpClass(cls):
        setupTestProject(cls)
        cls.ds_mrc = DataSet.getDataSet('xmipp_tutorial')
        cls.ds_tif = DataSet.getDataSet('rct')

    @classmethod
    def runImportMicrograph(cls, key, filePath):
        """ Run an Import micrograph protocol. """
        cls.protImport = cls.newProtocol(
            ProtImportMicrographs,
            filesPath=filePath,
            voltage=300,
            sphericalAberration=2.7,
            samplingRate=1.237
        )

        print(magentaStr(f"\n==> Importing data - micrographs ({key}):"))
        cls.launchProtocol(cls.protImport)

    @classmethod
    def runMicPreprocessing(cls, key):
        cls.protPreprocess = cls.newProtocol(
            XmippProtPreprocessMicrographs,
            inputMicrographs=cls.protImport.outputMicrographs,
            doDownsample=True,
            downFactor=5
        )

        print(magentaStr(f"\n==> Preprocessing micrographs ({key}):"))
        cls.launchProtocol(cls.protPreprocess)

    def runJanni(self, key):
        protJanni = self.newProtocol(
            SphireProtJanniDenoising,
            inputMicrographs=self.protPreprocess.outputMicrographs
        )

        print(magentaStr(f"\n==> Testing sphire - janni denoising ({key}):"))
        self.launchProtocol(protJanni)

        # Check if the generated files exist
        out_mics = protJanni.outputMicrographs
        for mic in out_mics:
            self.assertTrue(os.path.exists(os.path.abspath(mic.getFileName())))

        # Check that the number of generated files is equal than the number of input files
        self.assertSetSize(out_mics, size=self.protImport.outputMicrographs.getSize())

    def test_janni(self):
        dataDict = {'MRC': self.ds_mrc.getFile('allMics'),
                    'TIF': self.ds_tif.getFile('untilted')}
        for key in dataDict:
            self.runImportMicrograph(key, dataDict[key])
            self.runMicPreprocessing(key)
            self.runJanni(key)
