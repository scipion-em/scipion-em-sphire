# **************************************************************************
# *
# * Authors:     Pablo Conesa[1]
# *              Peter Horvath[1]
# *
# * [1] I2PC center
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

from pyworkflow.tests import (BaseTest, setupTestProject, DataSet,
                              setupTestOutput)
import pyworkflow.em as pwem
from pyworkflow.em.convert import Ccp4Header
import pyworkflow.utils as pwutils

import sphire.convert as convert
import sphire.protocols as protocols


XmippProtPreprocessMicrographs = pwutils.importFromPlugin(
    'xmipp3.protocols', 'XmippProtPreprocessMicrographs', doRaise=True)


class TestSphireConvert(BaseTest):

    @classmethod
    def setData(cls):
        cls.ds = DataSet.getDataSet('relion_tutorial')

    @classmethod
    def setUpClass(cls):
        cls.setData()
        setupTestOutput(cls)

    def testConvertCoords(self):
        boxSize = 100
        boxDir = self.getOutputPath('boxDir')
        pwutils.makePath(boxDir)

        def _convert(coordsIn, yFlipHeight=None):
            tmpFile = os.path.join(boxDir, 'tmp.box')
            # Write input coordinates
            writer = convert.CoordBoxWriter(boxSize, yFlipHeight=yFlipHeight)
            writer.open(tmpFile)
            for x, y in coordsIn:
                writer.writeCoord(pwem.Coordinate(x=x, y=y))
            writer.close()

            reader = convert.CoordBoxReader(boxSize, yFlipHeight=yFlipHeight)
            reader.open(tmpFile)
            coordsOut = [c for c in reader.iterCoords()]
            reader.close()

            return coordsOut

        coordsIn = [(100, 100), (100, 200), (200, 100), (200, 200)]

        # Case 1: No flip
        coordsOut = _convert(coordsIn)
        for c1, c2 in zip(coordsIn, coordsOut):
            self.assertEqual(c1, c2)

        # Case 2: Flipping on Y
        coordsOut = _convert(coordsIn, yFlipHeight=300)
        for c1, c2 in zip(coordsIn, coordsOut):
            self.assertEqual(c1, c2)

    def testConvertMic(self):
        """Check extension of the input micrographs"""

        micDir = self.getOutputPath('micDir')
        os.mkdir(micDir)

        mrcMic = TestSphireConvert.ds.getFile('micrographs/006.mrc')
        spiMic = os.path.join(micDir, "mic.spi")
        pwem.ImageHandler().convert(mrcMic, spiMic)

        mic = pwem.Micrograph(objId=1, location=spiMic)
        # Invoke the createMic function
        convert.convertMicrographs([mic], micDir)
        expectedDest = os.path.join(micDir, convert.getMicIdName(mic, '.mrc'))

        # If ext is not in [".mrc", ".tif", ".jpg"] return .mrc
        self.assertTrue(os.path.exists(expectedDest),
                        "spi file wasn't converted to mrc.")

    def testWriteSetOfCoordinatesWithoutFlip(self):
        # Define a temporary sqlite file for micrographs
        fn = self.getOutputPath('convert_mics.sqlite')

        mics = pwem.SetOfMicrographs(filename=fn)
        # Create SetOfCoordinates data
        # Define a temporary sqlite file for coordinates
        fn = self.getOutputPath('convert_coordinates.sqlite')
        coordSet = pwem.SetOfCoordinates(filename=fn)
        coordSet.setBoxSize(60)
        coordSet.setMicrographs(mics)

        data = {
            '006': [(30, 30)],
            '016': [(40, 40)]
        }

        micList = []
        for key, coords in data.iteritems():
            mic = pwem.Micrograph(self.ds.getFile('micrographs/%s.mrc' % key))
            mics.append(mic)
            micList.append(mic)
            print("Adding mic: %s, id: %s" % (key, mic.getObjId()))

            for x, y in coords:
                coord = pwem.Coordinate(x=x, y=y)
                coord.setMicrograph(mic)
                coordSet.append(coord)

        # Get boxDirectory
        boxFolder = self.getOutputPath('boxFolder')
        os.mkdir(boxFolder)

        micFolder = self.getOutputPath('micFolder')
        pwutils.makePath(micFolder)

        # Invoke the write set of coordinates method
        convert.writeSetOfCoordinates(boxFolder, coordSet)
        convert.convertMicrographs(micList, micFolder)

        # Assert output of writesetofcoordinates
        for mic in micList:
            boxFile = os.path.join(boxFolder,
                                   convert.getMicIdName(mic, '.box'))
            self.assertTrue(os.path.exists(boxFile),
                            'Missing box file: %s' % boxFile)
            micFile = os.path.join(micFolder,
                                   convert.getMicIdName(mic, '.mrc'))
            self.assertTrue(os.path.exists(micFile),
                            'Missing box file: %s' % micFile)

        # Assert coordinates in box files
        fh = open(os.path.join(boxFolder, 'mic00001.box'))
        box1 = fh.readline()
        fh.close()
        box1 = box1.split('\t')
        self.assertEquals(box1[0], '0')
        self.assertEquals(box1[1], '964')

    def testFlipAssessment(self):
        """ Test the method used to """

        mrcFile = self.ds.getFile('micrographs/006.mrc')

        # test wrong ispg value (0) in mrc file
        self.assertTrue(convert.needToFlipOnY(mrcFile),
                        "needToFlipOnY wrong for bad mrc.")

        # test non mrc file
        self.assertFalse(convert.needToFlipOnY('dummy.foo'),
                         "needToFlipOnY wrong for non mrc.")

        # Test right ispg value (0 in mrc file)
        # Copy 006
        goodMrc = self.getOutputPath('good_ispg.mrc')
        pwutils.copyFile(mrcFile, goodMrc)

        # Change the ISPG value in the file header
        header = Ccp4Header(goodMrc, readHeader=True)
        header.setISPG(0)
        header.writeHeader()

        # test good mrc file
        self.assertFalse(convert.needToFlipOnY(goodMrc),
                         "needToFlipOnY wrong for good mrc.")

    def testGetFlippingParams(self):
        mrcFile = TestSphireConvert.ds.getFile('micrographs/006.mrc')

        y = convert.getFlipYHeight(mrcFile)

        # test if image dimension is right
        self.assertEquals(y, 1024, "Y dimension of the micrograph is not correct.")

    def testInputSizeRounding(self):

        rounded = convert.roundInputSize(1000)

        self.assertEqual(rounded, 992, "input size rounding to the lower is wrong.")

        rounded = convert.roundInputSize(60)

        self.assertEqual(rounded, 64,
                         "input size rounding to the higher is wrong.")

        rounded = convert.roundInputSize(320)

        self.assertEqual(rounded, 320,
                         "input size rounding to exact is wrong.")

class TestCryolo(BaseTest):
    """ Test cryolo protocol"""

    @classmethod
    def setData(cls):
        cls.ds = DataSet.getDataSet('relion_tutorial')

    @classmethod
    def setUpClass(cls):
        setupTestProject(cls)
        cls.setData()
        # Run needed protocols
        cls.runImportMicrograph()
        cls.runMicPreprocessing()
        cls.runImportCoords()

    @classmethod
    def runImportMicrograph(cls):

        """ Run an Import micrograph protocol. """
        protImport = cls.newProtocol(
            pwem.ProtImportMicrographs,
            samplingRateMode=0,
            filesPath=TestCryolo.ds.getFile('micrographs/*.mrc'),
            samplingRate=3.54,
            magnification=59000,
            voltage=300,
            sphericalAberration=2)

        cls.launchProtocol(protImport)
        #cls.assertSetSize(protImport.outputMicrographs, 20,
        #                   "There was a problem with the import")

        cls.protImport = protImport

    @classmethod
    def runMicPreprocessing(cls):

        print "Preprocessing the micrographs..."
        protPreprocess = cls.newProtocol(XmippProtPreprocessMicrographs,
                                          doCrop=True, cropPixels=25)
        protPreprocess.inputMicrographs.set(cls.protImport.outputMicrographs)
        protPreprocess.setObjLabel('crop 50px')
        cls.launchProtocol(protPreprocess)
        # self.assertSetSize(protPreprocess.outputMicrographs, 20,
        #                    "There was a problem with the preprocessing")
        cls.protPreprocess = protPreprocess

    @classmethod
    def runImportCoords(cls):
        """ Run an Import coords protocol. """
        protImportCoords = cls.newProtocol(
            pwem.ProtImportCoordinates,
            importFrom=pwem.ProtImportCoordinates.IMPORT_FROM_EMAN,
            objLabel='import EMAN coordinates',
            filesPath=TestCryolo.ds.getFile('pickingEman/info/'),
            inputMicrographs=cls.protPreprocess.outputMicrographs,
            filesPattern='*.json',
            boxSize=65)
        cls.launchProtocol(protImportCoords)
        #cls.assertSetSize(protImportCoords.outputCoordinates,
        #                   msg="There was a problem importing eman coordinates")
        cls.protImportCoords = protImportCoords

    def testPicking(self):
        # No training mode picking
        protcryolo = self.newProtocol(
            protocols.SphireProtCRYOLOPicking,
            useGenMod=True,
            inputMicrographs=self.protPreprocess.outputMicrographs,
            boxSize=65,
            input_size=750,
            streamingBatchSize=10)

        self.launchProtocol(protcryolo)
        self.assertSetSize(protcryolo.outputCoordinates,
                           msg="There was a problem picking with crYOLO")

    def _runTraing(self, fineTune):
        # crYOLO training
        protTraining = self.newProtocol(
            protocols.SphireProtCRYOLOTraining,
            label='Training 1',
            inputMicrographs=self.protPreprocess.outputMicrographs,
            inputCoordinates=self.protImportCoords.outputCoordinates,
            boxSize=65,
            input_size=750,
            eFlagParam=2,
            doFineTune=fineTune,
            nb_epochVal=2)
        self.launchProtocol(protTraining)

        # Training mode picking
        protPicking = self.newProtocol(
            protocols.SphireProtCRYOLOPicking,
            label="Picking after Training 1",
            inputMicrographs=self.protPreprocess.outputMicrographs,

            useGenMod=False,
            sphireTraining=protTraining,
            boxSize=65,
            input_size=750,
            streamingBatchSize=10)

        self.launchProtocol(protPicking)
        self.assertSetSize(protPicking.outputCoordinates,
                           msg="There was a problem picking with crYOLO")

    def testTraining(self):
        self._runTraing(fineTune=False)

    def testTraningFineTune(self):
        self._runTraing(fineTune=True)

