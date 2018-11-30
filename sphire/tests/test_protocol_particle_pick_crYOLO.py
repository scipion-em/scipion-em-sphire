# **************************************************************************
# *
# * Authors:     It is me
# *
# *
# * [1]
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
    SetOfCoordinates, ProtImportMicrographs, ProtImportCoordinates, Ccp4Header
from pyworkflow.tests import BaseTest, setupTestProject, DataSet, \
    setupTestOutput
from sphire.convert import writeSetOfCoordinates, needToFlipOnY, \
    getFlippingParams
from sphire.protocols import SphireProtCRYOLO
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
        imgHeight=300
        coord = Coordinate(x=100, y=100)
        (x, y, sizeX, sizeY) = coordinateToBox(coord, boxSize, True, imgHeight)

        # Assert values
        self.assertEquals(x, 50, "x coordinate value %s is wrong when "
                                 "flipping on Y ")
        self.assertEquals(y, 250, "y coordinate value is wrong when no "
                                  "flipping on Y ")

        # Case exception raised
        self.assertRaises(ValueError, coordinateToBox, coord, boxSize, {'flipOnY': True})

    def testWriteSetOfCoordinates(self):
        # Define a temporary sqlite file for micrographs
        fn = self.getOutputPath('convert_mics.sqlite')

        mics = SetOfMicrographs(filename=fn)
        mic1 = Micrograph()
        mic1.setLocation(TestSphireConvert.ds.getFile('micrographs/006.mrc'))
        mics.append(mic1)

        # Define a temporary sqlite file for coordinates
        fn = self.getOutputPath('convert_coordinates.sqlite')

        # Create SetOfCoordinates data
        coordSet = SetOfCoordinates(filename=fn)
        coordSet.setBoxSize(60)
        coordSet.setMicrographs(mics)

        # Populate the set
        # Coordinate 1
        coord1 = Coordinate(x=30, y=30)
        coord1.setMicName('mic1.mrc')
        coord1.setMicId(10)
        coordSet.append(coord1)

        # Coordinate 2
        coord2 = Coordinate(x=40, y=40)
        coord2.setMicName('mic2.mrc')
        coord2.setMicId(11)
        coordSet.append(coord2)

        # Get boxDirectory
        boxFolder = self.getOutputPath('boxFolder')
        os.mkdir(boxFolder)

        micsNofified = []

        def micChange(micId):
            micsNofified.append(micId)

        # Invoke the write set of coordinates method
        writeSetOfCoordinates(boxFolder, coordSet, changeMicFunc=micChange)

        # Assert output of writesetofcoordinates
        files = [f for f in os.listdir(boxFolder) if re.match(r'mic[0-9]\.box', f)]
        self.assertEqual(2, len(files))

        # Assert mic notification
        self.assertEquals(2, len(micsNofified), "Mics notifications count were wrong")
        self.assertTrue(10 in micsNofified)
        self.assertTrue(11 in micsNofified)

        # Assert coordinates in box files
        fh = open(os.path.join(boxFolder, 'mic1.box'))
        box1 = fh.readline()
        fh.close()
        box1 = box1.split('\t')
        self.assertEquals(box1[0], '0')
        self.assertEquals(box1[1], '1024')


    def testFlipAssessment(self):
        """ Test the method used to """

        mrcFile = TestSphireConvert.ds.getFile('micrographs/006.mrc')

        # test wrong ispg value (0) in mrc file
        self.assertTrue(needToFlipOnY(mrcFile), "needToFlipOnY wrong for bad mrc.")

        # test non mrc file
        self.assertFalse(needToFlipOnY('dummy.foo'), "needToFlipOnY wrong for non mrc.")

        # Test right ispg value (0 in mrc file) TODO
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

    def testCryoloPicking(self):

        # Run needed protocols
        self.runImportMicrograph()
        self.runMicPreprocessing()
        self.runImportCoords()

        # No training mode
        protcryolo = self.newProtocol(SphireProtCRYOLO,
                                      trainDataset=False,
                                      inputMicrographs=self.protPreprocess.outputMicrographs,
                                      anchors=65)
        self.launchProtocol(protcryolo)
        self.assertSetSize(protcryolo.outputCoordinates, msg="There was a problem picking with crYOLO")

        # Training mode
        protcryolo2 = self.newProtocol(SphireProtCRYOLO,
                                      trainDataset=True,
                                      inputMicrographs=self.protPreprocess.outputMicrographs,
                                      inputCoordinates=self.protImportCoords.outputCoordinates,
                                      anchors=65)
        self.launchProtocol(protcryolo2)
        self.assertSetSize(protcryolo2.outputCoordinates, msg="There was a problem picking with crYOLO")
