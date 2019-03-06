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
import re
import os

from pyworkflow.em import Coordinate, SetOfMicrographs, Micrograph, \
    SetOfCoordinates, ProtImportMicrographs, ProtImportCoordinates, Ccp4Header, \
    ImageHandler
from pyworkflow.tests import BaseTest, setupTestProject, DataSet, \
    setupTestOutput
from sphire.convert import writeSetOfCoordinates, needToFlipOnY, \
    getFlippingParams, createMic
from sphire.protocols import SphireProtCRYOLOPicking, SphireProtCRYOLOTraining
from pyworkflow.utils import importFromPlugin, copyFile

XmippProtPreprocessMicrographs = \
    importFromPlugin('xmipp3.protocols', 'XmippProtPreprocessMicrographs',
                     doRaise=True)


class TestSphireConvert(BaseTest):

    @classmethod
    def setData(cls):
        cls.ds = DataSet.getDataSet('relion_tutorial')

    @classmethod
    def setUpClass(cls):
        cls.setData()
        setupTestOutput(cls)

    def testConvert(self):

        from sphire.convert import coordinateToBox

        boxSize = 100

        # Case 1: No flip
        coord = Coordinate(x=100, y=100)
        (x, y, sizeX, sizeY) = coordinateToBox(coord, boxSize)

        # Assert values
        self.assertEquals(boxSize, sizeX, "SizeX does not match boxsize")
        self.assertEquals(boxSize, sizeY, "SizeY does not match boxsize")
        self.assertEquals(y, 50, "y coordinate value is wrong when no flipping on Y ")

        self.assertEquals(x, 50, "x coordinate value is wrong when no flipping on Y ")

        # Case 2: Flipping on Y
        imgHeight = 300
        coord = Coordinate(x=100, y=100)
        (x, y, sizeX, sizeY) = coordinateToBox(coord, boxSize, True, imgHeight)

        # Assert values
        self.assertEquals(x, 50, "x coordinate value %s is wrong when "
                                 "flipping on Y ")
        self.assertEquals(y, 150, "y coordinate value is wrong when "
                                  "flipping on Y ")

        # Case exception raised
        self.assertRaises(ValueError, coordinateToBox, coord, boxSize, {'flipOnY': True})


    def testcheckCreateMicConversion(self):
        """Check extension of the input micrographs"""

        micDir = self.getOutputPath('micDir')
        os.mkdir(micDir)

        mrcMic = TestSphireConvert.ds.getFile('micrographs/006.mrc')
        spiMic = os.path.join(micDir, "mic.spi")
        ImageHandler().convert(mrcMic, spiMic)

        mic1 = Micrograph()
        mic1.setLocation(spiMic)

        # Invoke the createMic function
        dest = createMic(mic1, micDir)
        expectedDest = os.path.join(micDir, "mic.mrc")

        # If ext is not in [".mrc", ".tif", ".jpg"] return .mrc
        self.assertEquals(dest, expectedDest)
        self.assertTrue(os.path.exists(expectedDest), "spi file wasn't converted to mrc.")

    def testWriteSetOfCoordinatesWithoutFlip(self):
        # Define a temporary sqlite file for micrographs
        fn = self.getOutputPath('convert_mics.sqlite')

        mics = SetOfMicrographs(filename=fn)
        mic1 = Micrograph()
        mic1.setLocation(TestSphireConvert.ds.getFile('micrographs/006.mrc'))
        mics.append(mic1)

        mic2 = Micrograph()
        mic2.setLocation(TestSphireConvert.ds.getFile('micrographs/016.mrc'))
        mics.append(mic2)

        # Define a temporary sqlite file for coordinates
        fn = self.getOutputPath('convert_coordinates.sqlite')

        # Create SetOfCoordinates data
        coordSet = SetOfCoordinates(filename=fn)
        coordSet.setBoxSize(60)
        coordSet.setMicrographs(mics)

        # Populate the set
        # Coordinate 1
        coord1 = Coordinate(x=30, y=30)
        coord1.setMicName('006.mrc')
        coord1.setMicId(1)
        coordSet.append(coord1)

        # Coordinate 2
        coord2 = Coordinate(x=40, y=40)
        coord2.setMicName('016.mrc')
        coord2.setMicId(2)
        coordSet.append(coord2)

        # Get boxDirectory
        boxFolder = self.getOutputPath('boxFolder')
        os.mkdir(boxFolder)

        micFolder = self.getOutputPath('micFolder')
        os.mkdir(micFolder)

        # Invoke the write set of coordinates method
        writeSetOfCoordinates(boxFolder, coordSet, micFolder)

        # Assert output of writesetofcoordinates
        files = [f for f in os.listdir(boxFolder) if re.match(r'0[0,1]6\.box', f)]
        self.assertEqual(2, len(files))

        # Assert mic notification
        mics = [f for f in os.listdir(micFolder)]
        self.assertEquals(2, len(mics), "Mics creation count were wrong")


        # Assert coordinates in box files
        fh = open(os.path.join(boxFolder, '006.box'))
        box1 = fh.readline()
        fh.close()
        box1 = box1.split('\t')
        self.assertEquals(box1[0], '0')
        self.assertEquals(box1[1], '964')


    def testFlipAssessment(self):
        """ Test the method used to """

        mrcFile = TestSphireConvert.ds.getFile('micrographs/006.mrc')

        # test wrong ispg value (0) in mrc file
        self.assertTrue(needToFlipOnY(mrcFile), "needToFlipOnY wrong for bad mrc.")

        # test non mrc file
        self.assertFalse(needToFlipOnY('dummy.foo'), "needToFlipOnY wrong for non mrc.")

        # Test right ispg value (0 in mrc file)
        # Copy 006
        goodMrc = self.getOutputPath('good_ispg.mrc')
        copyFile(mrcFile, goodMrc)

        # Change the ISPG value in the file header
        header = Ccp4Header(goodMrc, readHeader=True)
        header.setISPG(0)
        header.writeHeader()

        # test good mrc file
        self.assertFalse(needToFlipOnY(goodMrc), "needToFlipOnY wrong for good mrc.")

    def testGetFlippingParams(self):
        mrcFile = TestSphireConvert.ds.getFile('micrographs/006.mrc')
        flip, y = getFlippingParams(mrcFile)

        #test if image needs to be flipped according to the flipOnY
        self.assertEquals(flip, True, "Image need flipping.")

        # test if image dimension is right
        self.assertEquals(y, 1024, "Y dimension of the micrograph is not correct.")


class TestCryolo(BaseTest):
    """ Test cryolo protocol"""

    @classmethod
    def setData(cls):
        cls.ds = DataSet.getDataSet('relion_tutorial')

    @classmethod
    def setUpClass(cls):
        setupTestProject(cls)
        cls.setData()

    def runImportMicrograph(self):

        """ Run an Import micrograph protocol. """
        protImport = self.newProtocol(ProtImportMicrographs,
                                         samplingRateMode=0,
                                         filesPath=TestCryolo.ds.getFile('micrographs/*.mrc'),
                                         samplingRate=3.54,
                                         magnification=59000,
                                         voltage=300,
                                         sphericalAberration=2)

        self.launchProtocol(protImport)
        self.assertSetSize(protImport.outputMicrographs, 20,
                           "There was a problem with the import")

        self.protImport = protImport

    def runMicPreprocessing(self):

        print "Preprocessing the micrographs..."
        protPreprocess = self.newProtocol(XmippProtPreprocessMicrographs,
                                          doCrop=True, cropPixels=25)
        protPreprocess.inputMicrographs.set(self.protImport.outputMicrographs)
        protPreprocess.setObjLabel('crop 50px')
        self.launchProtocol(protPreprocess)
        self.assertSetSize(protPreprocess.outputMicrographs, 20,
                             "There was a problem with the preprocessing")

        self.protPreprocess = protPreprocess

    def runImportCoords(self):
        """ Run an Import coords protocol. """
        protImportCoords = self.newProtocol(ProtImportCoordinates,
                                               importFrom=ProtImportCoordinates.IMPORT_FROM_EMAN,
                                               objLabel='import EMAN coordinates',
                                               filesPath=TestCryolo.ds.getFile(
                                                   'pickingEman/info/'),
                                               inputMicrographs=self.protPreprocess.outputMicrographs,
                                               filesPattern='*.json',
                                               boxSize=65)
        self.launchProtocol(protImportCoords)
        self.assertSetSize(protImportCoords.outputCoordinates, msg="There was a problem importing eman coordinates")
        self.protImportCoords = protImportCoords


    def testCryoloTraining(self):

        # Run needed protocols
        self.runImportMicrograph()
        self.runMicPreprocessing()
        self.runImportCoords()

        # crYOLO training
        protcryolotraining = self.newProtocol(SphireProtCRYOLOTraining,
                        inputMicrographs=self.protPreprocess.outputMicrographs,
                        inputCoordinates=self.protImportCoords.outputCoordinates,
                        boxsize=65,
                        input_size=750,
                        eFlag=True,
                        eFlagParam=2,
                        nb_epoch=True,
                        nb_epochVal=2)
        self.launchProtocol(protcryolotraining)

        print ("\n"+"Training has finished, first running crYOLO picking with general"
               " network."+"\n")

        # No training mode picking
        protcryolo = self.newProtocol(SphireProtCRYOLOPicking,
                        allowsNull=True,
                        useGenMod=True,
                        inputMicrographs=self.protPreprocess.outputMicrographs,
                        boxSize=65,
                        input_size=750)

        self.launchProtocol(protcryolo)
        self.assertSetSize(protcryolo.outputCoordinates, msg="There was a "
                                                "problem picking with crYOLO")

        print ("\n" + "Picking with general network has finished, running crYOLO"
                      " picking with the trained network." + "\n")

        # Training mode picking
        protcryolo2 = self.newProtocol(SphireProtCRYOLOPicking,
                        condition="useGenMod == False",
                        allowsNull = False,
                        label="Cryolo trainin run",
                        pointerClass='SphireProtCRYOLOTraining',
                        inputMicrographs=self.protPreprocess.outputMicrographs,
                        inputCoordinates=self.protImportCoords.outputCoordinates,
                        boxSize=65,
                        input_size=750)

        print ("\n" + "Picking with trained network has finished" + "\n")
        self.launchProtocol(protcryolo2)
        self.assertSetSize(protcryolo2.outputCoordinates, msg="There was a problem picking with crYOLO")
