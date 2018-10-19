# **************************************************************************
# *
# * Authors:     J.M. De la Rosa Trevin (delarosatrevin@scilifelab.se) [1]
# * Authors:     Grigory Sharov (gsharov@mrc-lmb.cam.ac.uk) [2]
# *
# * [1] SciLifeLab, Stockholm University
# * [2] MRC Laboratory of Molecular Biology (MRC-LMB)
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

import unittest

from pyworkflow.em import *
from pyworkflow.tests import *
from pyworkflow.em.packages.gautomatch.protocol_gautomatch import *

from sphire.protocols import *


class TestCryoloBase(BaseTest):
    @classmethod
    def setData(cls):
        cls.ds = DataSet.getDataSet('igbmc_gempicker')


    @classmethod
    def runImportMicrograph(cls, pattern, samplingRate, voltage, magnification,
                            sphericalAberration):
        """ Run an Import micrograph protocol. """
        cls.protImport = cls.newProtocol(ProtImportMicrographs,
                                         importFrom=ProtImportParticles.IMPORT_FROM_RELION,
                                         samplingRateMode=0,
                                         filesPath=pattern,
                                         samplingRate=samplingRate,
                                         magnification=magnification,
                                         voltage=voltage,
                                         amplitudeContrast=amplitudeContrast,
                                         sphericalAberration=sphericalAberration)

        cls.launchProtocol(cls.protImport)
        return cls.protImport

    @classmethod
    def runImportMicrograph(cls):
        """ Run an Import micrograph protocol. """
        return cls.runImportMicrograph(cls.ds.getFile('micrographs/*.mrc'),
                                       samplingRate=3.54,
                                       voltage=300, sphericalAberration=2,
                                       amplitudeContrast=0.1,
                                       magnification=59000)

    cls.launchProtocol(cls.protImport)
    return cls.protImport


    # @classmethod
    # def runImportCoords(cls):
    #     """ Run an Import coords protocol. """
    #     cls.protImportCoords = cls.newProtocol(ProtImportCoordinates,
    #                                            importFrom=ProtImportCoordinates.IMPORT_FROM_XMIPP,
    #                                            objLabel='import bad coords',
    #                                            filesPath=cls.ds.getFile(
    #                                                'coords/'),
    #                                            filesPattern='*.pos',
    #                                            boxSize=100)
    #     cls.protImportCoords.inputMicrographs.set(cls.protImportMics.outputMicrographs)
    #     cls.launchProtocol(cls.protImportCoords)
    #     return cls.protImportCoords


    @classmethod
    def _preparingCondaProgram(self, program, params='', label=''):
        CRYOLO_ENV_NAME = 'cryolo'
        f = open(self._getExtraPath('script_%s.sh' % label), "w")
        #print f
        #print ShellName
        # line0 = 'conda create -n cryolo -c anaconda python=2 pyqt=5 cudnn=7.1.2'
        lines = 'pwd\n'
        lines += 'ls\n'
        lines += 'source activate %s\n' % CRYOLO_ENV_NAME
        lines += 'export CUDA_VISIBLE_DEVICES=%s\n' % self.GPU.get()
        lines += '%s %s\n' % (program, params)
        lines += 'source deactivate\n'
        f.write(lines)
        f.close()




#     @classmethod
#     def runPicking1(cls):
#         """ Run a particle picking. """
#
#       protGM = ProtGautomatch(objLabel='sphire.sphire - crYOLO picking',
#                                 inputsize=768,
#                                 threshold=0.18,
#                                 particleSize=250,
#                                 advanced='False',
#                                 boxSize=150,
#                                 localSigmaCutoff=2.0)
#         protGM.inputMicrographs.set(cls.protImportMics.outputMicrographs)
#         protGM.inputReferences.set(cls.protImportAvgs.outputAverages)
#         cls.launchProtocol(protGM)
#         return protGM
#
#     @classmethod
#     def runPicking2(cls):
#         """ Run a particle picking with excludsive options. """
#         protGM2 = ProtGautomatch(objLabel='Gautomatch auto-picking 2 (klh)',
#                                  invertTemplatesContrast=True,
#                                  threshold=0.18,
#                                  particleSize=250,
#                                  advanced='False',
#                                  boxSize=150,
#                                  localSigmaCutoff=2.0,
#                                  exclusive=True)
#         protGM2.inputMicrographs.set(cls.protImportMics.outputMicrographs)
#         protGM2.inputReferences.set(cls.protImportAvgs.outputAverages)
#         protGM2.inputBadCoords.set(cls.protImportCoords.outputCoordinates)
#         cls.launchProtocol(protGM2)
#         return protGM2
#
#
# class TestCryoloAutomaticPicking(TestCryoloBase):
#     """This class check if the protocol to pick the micrographs automatically
#     by gautomatch works properly."""
#
#     @classmethod
#     def setUpClass(cls):
#         setupTestProject(cls)
#         TestCryoloBase.setData()
#         cls.protImportMics = cls.runImportMicrographKLH()
#         cls.protImportAvgs = cls.runImportAverages()
#         cls.protImportCoords = cls.runImportCoords()
#
#     def testAutomaticPicking(self):
#         self.runPicking1()
#         self.runPicking2()
#
#
# # if __name__ == "__main__":
# #     suite = unittest.TestLoader().loadTestsFromTestCase(
# #         TestCryoloAutomaticPicking)
# # unittest.TextTestRunner(verbosity=2).run(suite)